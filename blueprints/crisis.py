from flask import Blueprint, request, jsonify, session, render_template, redirect
from models import (db, CrisisEvent, DeescalationTechnique, ClientDeescalationHistory,
                    ClientTherapistRelationship, Notification, ActivityLog)
from datetime import datetime

crisis_bp = Blueprint('crisis', __name__)


def require_auth():
    """Decorator to require authentication"""

    def decorator(f):
        def wrapper(*args, **kwargs):
            if 'user_id' not in session:
                return jsonify({'error': 'Unauthorized'}), 401
            return f(*args, **kwargs)

        wrapper.__name__ = f.__name__
        return wrapper

    return decorator


# ========================================
# TEMPLATE ROUTES (GET)
# ========================================

@crisis_bp.route('/resources', methods=['GET'])
def resources():
    """Show crisis resources - always accessible"""
    return render_template('crisis/resources.html')


@crisis_bp.route('/techniques', methods=['GET'])
def techniques():
    """Show deescalation techniques - always accessible"""
    return render_template('crisis/techniques.html')


@crisis_bp.route('/log-event', methods=['GET'])
def log_event_page():
    """Show log crisis event form"""
    if 'user_id' not in session:
        return redirect('/auth/login')
    return render_template('crisis/log_event.html')


# ========================================
# CRISIS EVENTS
# ========================================

@crisis_bp.route('/events', methods=['POST'])
@require_auth()
def log_crisis_event():
    """Log a crisis event (client only)"""
    user_id = session['user_id']
    user_type = session['user_type']

    if user_type != 'client':
        return jsonify({'error': 'Only clients can log crisis events'}), 403

    data = request.get_json()

    required = ['crisis_type', 'severity_level', 'description']
    if not all(field in data for field in required):
        return jsonify({'error': 'Missing required fields'}), 400

    severity = data['severity_level']
    if severity < 1 or severity > 10:
        return jsonify({'error': 'Severity level must be between 1 and 10'}), 400

    # Get active relationship
    relationship = ClientTherapistRelationship.query.filter_by(
        client_id=user_id,
        status='active'
    ).first()

    if not relationship:
        return jsonify({'error': 'No active therapist relationship found'}), 404

    try:
        crisis = CrisisEvent(
            client_id=user_id,
            relationship_id=relationship.relationship_id,
            crisis_type=data['crisis_type'],
            severity_level=severity,
            description=data['description'],
            immediate_action_taken=data.get('immediate_action_taken'),
            resources_accessed=data.get('resources_accessed', []),
            status='logged'
        )
        db.session.add(crisis)
        db.session.commit()

        # Notify therapist if severity >= 7
        if severity >= 7:
            notification = Notification(
                user_id=relationship.therapist_id,
                notification_type='crisis_alert',
                title='High-Severity Crisis Alert',
                message=f'A client has logged a severity {severity} crisis event',
                related_entity_type='crisis_event',
                related_entity_id=crisis.crisis_id
            )
            db.session.add(notification)

            crisis.therapist_notified = True
            crisis.therapist_notification_date = datetime.utcnow()
            db.session.commit()

        # Log activity
        log = ActivityLog(
            user_id=user_id,
            action_type='crisis_logged',
            resource_type='crisis_event',
            resource_id=crisis.crisis_id,
            description=f'Crisis event logged: {data["crisis_type"]} (severity {severity})',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({
            'message': 'Crisis event logged successfully',
            'crisis_id': crisis.crisis_id,
            'therapist_notified': crisis.therapist_notified
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to log crisis: {str(e)}'}), 500


@crisis_bp.route('/events', methods=['GET'])
@require_auth()
def get_crisis_events():
    """Get user's crisis events"""
    user_id = session['user_id']
    user_type = session['user_type']

    if user_type == 'client':
        events = CrisisEvent.query.filter_by(
            client_id=user_id
        ).order_by(CrisisEvent.created_at.desc()).limit(50).all()
    else:
        # Therapist: get events from their clients
        relationships = ClientTherapistRelationship.query.filter_by(
            therapist_id=user_id,
            status='active'
        ).all()

        client_ids = [r.client_id for r in relationships]
        events = CrisisEvent.query.filter(
            CrisisEvent.client_id.in_(client_ids)
        ).order_by(CrisisEvent.created_at.desc()).limit(50).all()

    return jsonify({
        'events': [{
            'crisis_id': e.crisis_id,
            'client_id': e.client_id,
            'crisis_type': e.crisis_type,
            'severity_level': e.severity_level,
            'description': e.description,
            'immediate_action_taken': e.immediate_action_taken,
            'status': e.status,
            'therapist_notified': e.therapist_notified,
            'created_at': e.created_at.isoformat()
        } for e in events]
    }), 200


@crisis_bp.route('/events/<int:crisis_id>', methods=['PUT'])
@require_auth()
def update_crisis_event(crisis_id):
    """Update crisis event status (therapist or client)"""
    user_id = session['user_id']
    data = request.get_json()

    crisis = CrisisEvent.query.get(crisis_id)
    if not crisis:
        return jsonify({'error': 'Crisis event not found'}), 404

    # Verify access
    relationship = ClientTherapistRelationship.query.get(crisis.relationship_id)
    if crisis.client_id != user_id and relationship.therapist_id != user_id:
        return jsonify({'error': 'Access denied'}), 403

    # Update status
    if 'status' in data:
        if data['status'] not in ['logged', 'in_progress', 'resolved', 'escalated']:
            return jsonify({'error': 'Invalid status'}), 400
        crisis.status = data['status']

    # Update resolution notes (therapist only)
    if 'resolution_notes' in data and relationship.therapist_id == user_id:
        crisis.resolution_notes = data['resolution_notes']

    crisis.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'message': 'Crisis event updated successfully'}), 200


# ========================================
# DEESCALATION TECHNIQUES
# ========================================

@crisis_bp.route('/techniques', methods=['GET'])
def get_techniques():
    """
    Get deescalation techniques
    PRD: Available even when not logged in (crisis accessible)
    """
    category = request.args.get('category')
    crisis_type = request.args.get('crisis_type')

    query = DeescalationTechnique.query.filter_by(is_active=True)

    if category:
        query = query.filter_by(technique_category=category)

    techniques = query.all()

    # Filter by crisis type if provided
    if crisis_type and techniques:
        techniques = [t for t in techniques if not t.best_for or crisis_type in t.best_for]

    return jsonify({
        'techniques': [{
            'technique_id': t.technique_id,
            'technique_name': t.technique_name,
            'technique_category': t.technique_category,
            'description': t.description,
            'step_by_step_instructions': t.step_by_step_instructions,
            'estimated_duration_minutes': t.estimated_duration_minutes,
            'difficulty_level': t.difficulty_level,
            'audio_guide_url': t.audio_guide_url,
            'video_guide_url': t.video_guide_url
        } for t in techniques]
    }), 200


@crisis_bp.route('/techniques/<int:technique_id>', methods=['GET'])
def get_technique_detail(technique_id):
    """Get detailed technique instructions (always accessible)"""
    technique = DeescalationTechnique.query.filter_by(
        technique_id=technique_id,
        is_active=True
    ).first()

    if not technique:
        return jsonify({'error': 'Technique not found'}), 404

    return jsonify({
        'technique_id': technique.technique_id,
        'technique_name': technique.technique_name,
        'technique_category': technique.technique_category,
        'description': technique.description,
        'step_by_step_instructions': technique.step_by_step_instructions,
        'estimated_duration_minutes': technique.estimated_duration_minutes,
        'difficulty_level': technique.difficulty_level,
        'best_for': technique.best_for,
        'audio_guide_url': technique.audio_guide_url,
        'video_guide_url': technique.video_guide_url
    }), 200


@crisis_bp.route('/techniques/<int:technique_id>/use', methods=['POST'])
@require_auth()
def log_technique_usage(technique_id):
    """Log usage of a deescalation technique"""
    user_id = session['user_id']
    user_type = session['user_type']

    if user_type != 'client':
        return jsonify({'error': 'Only clients can log technique usage'}), 403

    data = request.get_json()

    technique = DeescalationTechnique.query.get(technique_id)
    if not technique:
        return jsonify({'error': 'Technique not found'}), 404

    try:
        history = ClientDeescalationHistory(
            client_id=user_id,
            crisis_id=data.get('crisis_id'),
            technique_id=technique_id,
            effectiveness_rating=data.get('effectiveness_rating'),
            duration_used_minutes=data.get('duration_used_minutes'),
            notes=data.get('notes')
        )
        db.session.add(history)
        db.session.commit()

        return jsonify({
            'message': 'Technique usage logged successfully',
            'history_id': history.history_id
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to log usage: {str(e)}'}), 500


@crisis_bp.route('/techniques/history', methods=['GET'])
@require_auth()
def get_technique_history():
    """Get user's technique usage history"""
    user_id = session['user_id']

    history = ClientDeescalationHistory.query.filter_by(
        client_id=user_id
    ).order_by(ClientDeescalationHistory.usage_date.desc()).limit(50).all()

    return jsonify({
        'history': [{
            'history_id': h.history_id,
            'technique_id': h.technique_id,
            'crisis_id': h.crisis_id,
            'effectiveness_rating': h.effectiveness_rating,
            'duration_used_minutes': h.duration_used_minutes,
            'notes': h.notes,
            'usage_date': h.usage_date.isoformat()
        } for h in history]
    }), 200


# ========================================
# ADMIN: MANAGE TECHNIQUES (Therapist)
# ========================================

@crisis_bp.route('/admin/techniques', methods=['POST'])
@require_auth()
def create_technique():
    """Create new deescalation technique (admin/therapist)"""
    user_type = session['user_type']

    if user_type != 'therapist':
        return jsonify({'error': 'Therapist access only'}), 403

    data = request.get_json()

    required = ['technique_name', 'technique_category', 'description', 'step_by_step_instructions']
    if not all(field in data for field in required):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        technique = DeescalationTechnique(
            technique_name=data['technique_name'],
            technique_category=data['technique_category'],
            description=data['description'],
            step_by_step_instructions=data['step_by_step_instructions'],
            estimated_duration_minutes=data.get('estimated_duration_minutes'),
            difficulty_level=data.get('difficulty_level', 'beginner'),
            best_for=data.get('best_for', []),
            audio_guide_url=data.get('audio_guide_url'),
            video_guide_url=data.get('video_guide_url'),
            is_active=True,
            is_crisis_accessible=data.get('is_crisis_accessible', True)
        )
        db.session.add(technique)
        db.session.commit()

        return jsonify({
            'message': 'Technique created successfully',
            'technique_id': technique.technique_id
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to create technique: {str(e)}'}), 500


# ========================================
# EMERGENCY RESOURCES
# ========================================

@crisis_bp.route('/resources', methods=['GET'])
def get_emergency_resources():
    """
    Get emergency resources (always accessible)
    Kenya-specific crisis hotlines
    """
    resources = {
        'kenya': {
            'suicide_prevention': {
                'name': 'Kenya Red Cross Society',
                'phone': '1199',
                'available': '24/7'
            },
            'mental_health': {
                'name': 'Befrienders Kenya',
                'phone': '+254 722 178 177',
                'available': '24/7'
            },
            'emergency': {
                'name': 'Emergency Services',
                'phone': '999 or 112',
                'available': '24/7'
            },
            'gender_violence': {
                'name': 'Gender Violence Recovery Centre',
                'phone': '0800 720 553',
                'available': '24/7'
            }
        },
        'international': {
            'suicide_prevention': {
                'name': 'International Association for Suicide Prevention',
                'website': 'https://www.iasp.info/resources/Crisis_Centres/'
            }
        }
    }

    return jsonify({'resources': resources}), 200