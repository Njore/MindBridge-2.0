from flask import Blueprint, request, jsonify, session, render_template, redirect
from models import (db, User, ClientTherapistRelationship, Capsule, Message,
                    TherapeuticPrompt, PromptResponse, Notification, ActivityLog)
from datetime import datetime
from services.encryption import encrypt_content, decrypt_content
from services.timezone import today_eat
import logging

therapist_bp = Blueprint('therapist', __name__)
logger = logging.getLogger(__name__)


def require_therapist():
    """Decorator to require therapist user type"""

    def decorator(f):
        def wrapper(*args, **kwargs):
            if 'user_id' not in session:
                return jsonify({'error': 'Unauthorized'}), 401
            if session.get('user_type') != 'therapist':
                return jsonify({'error': 'Therapist access only'}), 403
            return f(*args, **kwargs)

        wrapper.__name__ = f.__name__
        return wrapper

    return decorator


# ========================================
# TEMPLATE ROUTES (GET)
# ========================================

@therapist_bp.route('/dashboard', methods=['GET'])
def dashboard_page():
    """Show therapist dashboard"""
    if 'user_id' not in session or session.get('user_type') != 'therapist':
        return redirect('/auth/login')
    return render_template('therapist/dashboard.html')


@therapist_bp.route('/clients', methods=['GET'])
def clients_page():
    """Show clients list page"""
    if 'user_id' not in session or session.get('user_type') != 'therapist':
        return redirect('/auth/login')
    return render_template('therapist/clients.html')


@therapist_bp.route('/create-prompt', methods=['GET'])
def create_prompt_page():
    """Show create prompt form"""
    if 'user_id' not in session or session.get('user_type') != 'therapist':
        return redirect('/auth/login')
    return render_template('therapist/create_prompt.html')


@therapist_bp.route('/add-client', methods=['GET'])
def add_client_page():
    """Show add/connect client page"""
    if 'user_id' not in session or session.get('user_type') != 'therapist':
        return redirect('/auth/login')
    return render_template('therapist/add_client.html')


@therapist_bp.route('/prioritized', methods=['GET'])
def prioritized_capsules_page():
    """Show prioritized capsules dashboard"""
    if 'user_id' not in session or session.get('user_type') != 'therapist':
        return redirect('/auth/login')
    return render_template('therapist/prioritized_capsules.html')


# ========================================
# CLIENT RELATIONSHIPS (API)
# ========================================

@therapist_bp.route('/api/clients', methods=['GET'])
@require_therapist()
def get_clients():
    """Get all clients for this therapist"""
    therapist_id = session['user_id']

    relationships = ClientTherapistRelationship.query.filter_by(
        therapist_id=therapist_id,
        status='active'
    ).all()

    clients = []
    for rel in relationships:
        client = User.query.get(rel.client_id)

        # Get unread capsules count for this client (CRITICAL + HIGH priority)
        unread_count = Capsule.query.filter_by(
            client_id=client.user_id,
            therapist_id=therapist_id,
            priority_reviewed_by_therapist=False
        ).filter(
            Capsule.priority_level.in_(['CRITICAL', 'HIGH'])
        ).count()

        clients.append({
            'relationship_id': rel.relationship_id,
            'client_id': client.user_id,
            'first_name': client.first_name,
            'last_name': client.last_name,
            'email': client.email,
            'relationship_start': rel.relationship_start_date.isoformat(),
            'client_goals': rel.client_goals,
            'unread_priority_count': unread_count
        })

    return jsonify({'clients': clients}), 200


@therapist_bp.route('/api/clients/search', methods=['GET'])
@require_therapist()
def search_clients():
    """
    Search registered client accounts by email or name.
    Used by the Add Client page before sending a connection request.
    """
    therapist_id = session['user_id']
    query_str = request.args.get('q', '').strip()

    if len(query_str) < 2:
        return jsonify({'error': 'Search query must be at least 2 characters'}), 400

    # Client IDs that already have an ACTIVE relationship with ANY therapist
    actively_connected_ids = {
        r.client_id for r in ClientTherapistRelationship.query.filter_by(
            status='active'
        ).all()
    }

    results = User.query.filter(
        User.user_type == 'client',
        User.is_active == True,
        db.or_(
            User.email.ilike(f'%{query_str}%'),
            User.first_name.ilike(f'%{query_str}%'),
            User.last_name.ilike(f'%{query_str}%')
        )
    ).limit(10).all()

    users = []
    for u in results:
        if u.user_id in actively_connected_ids:
            continue  # already connected to a therapist, not searchable

        users.append({
            'user_id': u.user_id,
            'first_name': u.first_name,
            'last_name': u.last_name,
            'email': u.email,
            'already_connected': False
        })

    return jsonify({'results': users}), 200


@therapist_bp.route('/api/clients/connect', methods=['POST'])
@require_therapist()
def connect_client():
    """
    Create a new client-therapist relationship.
    Body: { client_id, client_goals (optional) }
    """
    therapist_id = session['user_id']
    data = request.get_json()

    client_id = data.get('client_id')
    if not client_id:
        return jsonify({'error': 'client_id is required'}), 400

    client = User.query.filter_by(user_id=client_id, user_type='client', is_active=True).first()
    if not client:
        return jsonify({'error': 'Client not found'}), 404

    # Prevent connecting a client who is already actively connected to ANY therapist
    existing = ClientTherapistRelationship.query.filter_by(
        client_id=client_id,
        status='active'
    ).first()
    if existing:
        return jsonify({'error': 'This client is already connected to a therapist'}), 409

    # Re-activate a previously ended relationship if one exists
    ended = ClientTherapistRelationship.query.filter_by(
        client_id=client_id,
        therapist_id=therapist_id,
        status='ended'
    ).order_by(ClientTherapistRelationship.created_at.desc()).first()

    try:
        if ended:
            ended.status = 'active'
            ended.relationship_start_date = today_eat()
            ended.relationship_end_date = None
            ended.client_goals = data.get('client_goals', ended.client_goals)
            ended.updated_at = datetime.utcnow()
            relationship = ended
        else:
            relationship = ClientTherapistRelationship(
                client_id=client_id,
                therapist_id=therapist_id,
                status='active',
                relationship_start_date=today_eat(),
                client_goals=data.get('client_goals', '')
            )
            db.session.add(relationship)

        db.session.flush()

        notification = Notification(
            user_id=client_id,
            notification_type='new_relationship',
            title='New Therapist Connection',
            message='You have been connected with a therapist on MindBridge.',
            related_entity_type='relationship',
            related_entity_id=relationship.relationship_id
        )
        db.session.add(notification)

        log = ActivityLog(
            user_id=therapist_id,
            action_type='client_connected',
            resource_type='relationship',
            resource_id=relationship.relationship_id,
            description=f'Connected with client user_id={client_id}',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({
            'message': 'Client connected successfully',
            'relationship_id': relationship.relationship_id,
            'client': {
                'user_id': client.user_id,
                'first_name': client.first_name,
                'last_name': client.last_name,
                'email': client.email
            },
            'relationship_start': relationship.relationship_start_date.isoformat()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to connect client: {str(e)}'}), 500


@therapist_bp.route('/api/clients/<int:client_id>/disconnect', methods=['POST'])
@require_therapist()
def disconnect_client(client_id):
    """
    End an active client-therapist relationship.
    Body: { reason (optional) }
    """
    therapist_id = session['user_id']
    data = request.get_json() or {}

    relationship = ClientTherapistRelationship.query.filter_by(
        client_id=client_id,
        therapist_id=therapist_id,
        status='active'
    ).first()

    if not relationship:
        return jsonify({'error': 'Active relationship not found'}), 404

    try:
        relationship.status = 'ended'
        relationship.relationship_end_date = today_eat()
        if data.get('reason'):
            relationship.therapist_notes = (relationship.therapist_notes or '') + \
                                           f'\n[Ended {today_eat().isoformat()}]: {data["reason"]}'
        relationship.updated_at = datetime.utcnow()

        notification = Notification(
            user_id=client_id,
            notification_type='relationship_ended',
            title='Therapist Connection Ended',
            message='Your therapist has ended the therapeutic relationship on MindBridge.',
            related_entity_type='relationship',
            related_entity_id=relationship.relationship_id
        )
        db.session.add(notification)

        log = ActivityLog(
            user_id=therapist_id,
            action_type='client_disconnected',
            resource_type='relationship',
            resource_id=relationship.relationship_id,
            description=f'Ended relationship with client user_id={client_id}',
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({'message': 'Client relationship ended successfully'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to end relationship: {str(e)}'}), 500


@therapist_bp.route('/clients/<int:client_id>', methods=['GET'])
def client_detail_page(client_id):
    """Render the client detail page"""
    if 'user_id' not in session or session.get('user_type') != 'therapist':
        return redirect('/auth/login')
    return render_template('therapist/client_detail.html', client_id=client_id)


@therapist_bp.route('/api/clients/<int:client_id>', methods=['GET'])
@require_therapist()
def get_client_detail(client_id):
    """Get detailed info for a specific client (JSON API)"""
    therapist_id = session['user_id']

    # Verify relationship exists
    relationship = ClientTherapistRelationship.query.filter_by(
        therapist_id=therapist_id,
        client_id=client_id,
        status='active'
    ).first()

    if not relationship:
        return jsonify({'error': 'Client relationship not found'}), 404

    client = User.query.get(client_id)

    # Get recent capsules with priority info
    recent_capsules = Capsule.query.filter_by(
        client_id=client_id,
        therapist_id=therapist_id
    ).order_by(Capsule.created_at.desc()).limit(10).all()

    return jsonify({
        'client': {
            'client_id': client.user_id,
            'first_name': client.first_name,
            'last_name': client.last_name,
            'email': client.email,
            'phone': client.phone
        },
        'relationship': {
            'relationship_id': relationship.relationship_id,
            'start_date': relationship.relationship_start_date.isoformat(),
            'therapist_notes': relationship.therapist_notes,
            'client_goals': relationship.client_goals
        },
        'recent_capsules': [{
            'capsule_id': c.capsule_id,
            'title': c.title,
            'user_tag': c.user_tag,
            'status': c.status,
            'priority_level': c.priority_level or 'LOW',
            'priority_score': float(c.priority_score) if c.priority_score else 0,
            'created_at': c.created_at.isoformat()
        } for c in recent_capsules]
    }), 200


@therapist_bp.route('/clients/<int:client_id>/notes', methods=['PUT'])
@require_therapist()
def update_client_notes(client_id):
    """Update therapist notes for a client"""
    therapist_id = session['user_id']
    data = request.get_json()

    relationship = ClientTherapistRelationship.query.filter_by(
        therapist_id=therapist_id,
        client_id=client_id,
        status='active'
    ).first()

    if not relationship:
        return jsonify({'error': 'Client relationship not found'}), 404

    if 'therapist_notes' in data:
        relationship.therapist_notes = data['therapist_notes']
    if 'client_goals' in data:
        relationship.client_goals = data['client_goals']

    relationship.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'message': 'Notes updated successfully'}), 200


# ========================================
# PRIORITIZED CAPSULES (NEW)
# ========================================

@therapist_bp.route('/api/prioritized-capsules', methods=['GET'])
@require_therapist()
def get_prioritized_capsules():
    """
    Get all capsules sorted by priority (CRITICAL → HIGH → MEDIUM → LOW)
    Includes unread/reviewed status tracking
    """
    therapist_id = session['user_id']

    # Get filter parameters
    status_filter = request.args.get('status', 'sealed,archived')  # Default to sealed and archived
    show_reviewed = request.args.get('show_reviewed', 'false').lower() == 'true'
    limit = request.args.get('limit', 100, type=int)

    # Parse status filter
    statuses = [s.strip() for s in status_filter.split(',')]

    # Priority order for sorting
    priority_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}

    # Get capsules for this therapist
    query = Capsule.query.filter_by(therapist_id=therapist_id)

    if statuses:
        query = query.filter(Capsule.status.in_(statuses))

    if not show_reviewed:
        query = query.filter_by(priority_reviewed_by_therapist=False)

    capsules = query.all()

    # Filter out capsules without messages
    valid_capsules = []
    for capsule in capsules:
        message_count = Message.query.filter_by(capsule_id=capsule.capsule_id).count()
        if message_count > 0:
            valid_capsules.append(capsule)

    # Sort by priority
    valid_capsules.sort(key=lambda c: priority_order.get(c.priority_level or 'LOW', 3))

    # Apply limit after sorting (prioritize critical ones)
    valid_capsules = valid_capsules[:limit]

    # Get client names
    client_ids = list({c.client_id for c in valid_capsules})
    clients = User.query.filter(User.user_id.in_(client_ids)).all()
    client_map = {u.user_id: f"{u.first_name} {u.last_name}" for u in clients}

    # Build response
    result = []
    for capsule in valid_capsules:
        # Count messages
        message_count = Message.query.filter_by(capsule_id=capsule.capsule_id).count()

        # Get last message
        last_message = (
            Message.query
            .filter_by(capsule_id=capsule.capsule_id)
            .order_by(Message.created_at.desc())
            .first()
        )

        # Get first message (for preview)
        first_message = (
            Message.query
            .filter_by(capsule_id=capsule.capsule_id)
            .order_by(Message.created_at.asc())
            .first()
        )

        # Get client object for more details
        client = User.query.get(capsule.client_id)

        first_message_content = decrypt_content(first_message.content) if first_message else ''

        result.append({
            'capsule_id': capsule.capsule_id,
            'title': capsule.title,
            'client_id': capsule.client_id,
            'client_name': client_map.get(capsule.client_id, 'Unknown'),
            'client_email': client.email if client else None,
            'priority_level': capsule.priority_level or 'LOW',
            'priority_score': float(capsule.priority_score) if capsule.priority_score else 0,
            'priority_reasons': capsule.priority_reasons,
            'priority_analyzed_at': capsule.priority_analyzed_at.isoformat() if capsule.priority_analyzed_at else None,
            'priority_reviewed_by_therapist': capsule.priority_reviewed_by_therapist,
            'message_count': message_count,
            'first_message_preview': first_message_content[:150] + '...' if len(
                first_message_content) > 150 else first_message_content,
            'last_message_at': last_message.created_at.isoformat() if last_message else None,
            'status': capsule.status,
            'user_tag': capsule.user_tag,
            'created_at': capsule.created_at.isoformat(),
            'sealed_at': capsule.sealed_at.isoformat() if capsule.sealed_at else None
        })

    # Add summary statistics
    summary = {
        'critical_count': len(
            [c for c in result if c['priority_level'] == 'CRITICAL' and not c['priority_reviewed_by_therapist']]),
        'high_count': len(
            [c for c in result if c['priority_level'] == 'HIGH' and not c['priority_reviewed_by_therapist']]),
        'total_unreviewed': len([c for c in result if not c['priority_reviewed_by_therapist']]),
        'total_capsules': len(result)
    }

    return jsonify({
        'capsules': result,
        'summary': summary
    }), 200


@therapist_bp.route('/api/prioritized-capsules/summary', methods=['GET'])
@require_therapist()
def get_priority_summary():
    """Get summary counts of capsules by priority level"""
    therapist_id = session['user_id']

    # Get all unreviewed capsules
    capsules = Capsule.query.filter_by(
        therapist_id=therapist_id,
        priority_reviewed_by_therapist=False
    ).filter(Capsule.status.in_(['sealed', 'archived'])).all()

    # Count by priority
    counts = {
        'CRITICAL': 0,
        'HIGH': 0,
        'MEDIUM': 0,
        'LOW': 0
    }

    for capsule in capsules:
        level = capsule.priority_level or 'LOW'
        if level in counts:
            counts[level] += 1

    return jsonify({
        'unreviewed_counts': counts,
        'total_unreviewed': sum(counts.values())
    }), 200


@therapist_bp.route('/api/capsules/<int:capsule_id>/mark-reviewed', methods=['POST'])
@require_therapist()
def mark_capsule_reviewed(capsule_id):
    """Mark a capsule as reviewed by the therapist"""
    therapist_id = session['user_id']

    capsule = Capsule.query.filter_by(
        capsule_id=capsule_id,
        therapist_id=therapist_id
    ).first()

    if not capsule:
        return jsonify({'error': 'Capsule not found'}), 404

    capsule.priority_reviewed_by_therapist = True
    db.session.commit()

    return jsonify({
        'message': 'Capsule marked as reviewed',
        'capsule_id': capsule_id
    }), 200


@therapist_bp.route('/api/capsules/<int:capsule_id>/reanalyze', methods=['POST'])
@require_therapist()
def reanalyze_capsule(capsule_id):
    """Manually trigger priority re-analysis for a capsule"""
    therapist_id = session['user_id']

    capsule = Capsule.query.filter_by(
        capsule_id=capsule_id,
        therapist_id=therapist_id
    ).first()

    if not capsule:
        return jsonify({'error': 'Capsule not found'}), 404

    # Import here to avoid circular imports
    from services.sentiment_analyzer import analyzer
    from threading import Thread

    def analyze_in_background():
        try:
            from flask import current_app
            with current_app.app_context():
                messages = Message.query.filter_by(capsule_id=capsule_id).all()
                message_texts = [decrypt_content(m.content) for m in messages]

                analysis = analyzer.analyze_capsule_messages(message_texts)

                capsule.priority_level = analysis['priority_level']
                capsule.priority_score = analysis['priority_score']
                capsule.priority_analyzed_at = datetime.utcnow()
                capsule.priority_reasons = {
                    'reasons': analysis['reasons'],
                    'risk_flags': analysis['risk_flags'],
                    'sentiment_summary': analysis['sentiment_summary']
                }
                # Reset reviewed status when re-analyzing
                capsule.priority_reviewed_by_therapist = False
                db.session.commit()

                logger.info(f"Manual re-analysis completed for capsule {capsule_id}")
        except Exception as e:
            logger.error(f"Manual re-analysis failed for capsule {capsule_id}: {str(e)}")

    thread = Thread(target=analyze_in_background)
    thread.daemon = True
    thread.start()

    return jsonify({'message': 'Priority re-analysis triggered'}), 200


@therapist_bp.route('/api/capsules/<int:capsule_id>/priority-details', methods=['GET'])
@require_therapist()
def get_capsule_priority_details(capsule_id):
    """Get detailed priority analysis for a specific capsule"""
    therapist_id = session['user_id']

    capsule = Capsule.query.filter_by(
        capsule_id=capsule_id,
        therapist_id=therapist_id
    ).first()

    if not capsule:
        return jsonify({'error': 'Capsule not found'}), 404

    # Get all messages for context
    messages = Message.query.filter_by(capsule_id=capsule_id).order_by(Message.created_at).all()

    return jsonify({
        'capsule_id': capsule.capsule_id,
        'title': capsule.title,
        'priority_level': capsule.priority_level or 'LOW',
        'priority_score': float(capsule.priority_score) if capsule.priority_score else 0,
        'priority_reasons': capsule.priority_reasons,
        'priority_analyzed_at': capsule.priority_analyzed_at.isoformat() if capsule.priority_analyzed_at else None,
        'priority_reviewed_by_therapist': capsule.priority_reviewed_by_therapist,
        'message_count': len(messages),
        'messages': [{
            'content': decrypt_content(m.content),
            'created_at': m.created_at.isoformat(),
            'sender_type': 'client' if m.sender_id == capsule.client_id else 'therapist'
        } for m in messages]
    }), 200


# ========================================
# CAPSULES (View Client Capsules)
# ========================================

@therapist_bp.route('/capsules', methods=['GET'])
@require_therapist()
def get_therapist_capsules():
    """Get all capsules for therapist's clients (with priority info)"""
    therapist_id = session['user_id']

    status = request.args.get('status', 'sealed')  # Default to sealed only
    sort_by_priority = request.args.get('sort_by_priority', 'false').lower() == 'true'

    capsules = Capsule.query.filter_by(
        therapist_id=therapist_id,
        status=status
    ).order_by(Capsule.created_at.desc()).all()

    # Sort by priority if requested
    if sort_by_priority:
        priority_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
        capsules.sort(key=lambda c: priority_order.get(c.priority_level or 'LOW', 3))

    return jsonify({
        'capsules': [{
            'capsule_id': c.capsule_id,
            'client_id': c.client_id,
            'title': c.title,
            'user_tag': c.user_tag,
            'status': c.status,
            'priority_level': c.priority_level or 'LOW',
            'priority_score': float(c.priority_score) if c.priority_score else 0,
            'priority_reviewed_by_therapist': c.priority_reviewed_by_therapist,
            'created_at': c.created_at.isoformat(),
            'sealed_at': c.sealed_at.isoformat() if c.sealed_at else None
        } for c in capsules]
    }), 200


@therapist_bp.route('/capsules/<int:capsule_id>', methods=['GET'])
@require_therapist()
def get_capsule_detail(capsule_id):
    """Get capsule details with messages and priority info"""
    therapist_id = session['user_id']

    capsule = Capsule.query.filter_by(
        capsule_id=capsule_id,
        therapist_id=therapist_id
    ).first()

    if not capsule:
        return jsonify({'error': 'Capsule not found'}), 404

    # Get messages
    messages = Message.query.filter_by(
        capsule_id=capsule_id
    ).order_by(Message.created_at).all()

    # Auto-mark as reviewed when therapist views a capsule
    if not capsule.priority_reviewed_by_therapist and capsule.status in ['sealed', 'archived']:
        capsule.priority_reviewed_by_therapist = True
        db.session.commit()

    return jsonify({
        'capsule': {
            'capsule_id': capsule.capsule_id,
            'client_id': capsule.client_id,
            'title': capsule.title,
            'user_tag': capsule.user_tag,
            'status': capsule.status,
            'priority_level': capsule.priority_level or 'LOW',
            'priority_score': float(capsule.priority_score) if capsule.priority_score else 0,
            'priority_reasons': capsule.priority_reasons,
            'priority_analyzed_at': capsule.priority_analyzed_at.isoformat() if capsule.priority_analyzed_at else None,
            'created_at': capsule.created_at.isoformat(),
            'sealed_at': capsule.sealed_at.isoformat() if capsule.sealed_at else None
        },
        'messages': [{
            'message_id': m.message_id,
            'sender_id': m.sender_id,
            'content': decrypt_content(m.content),
            'created_at': m.created_at.isoformat()
        } for m in messages]
    }), 200


# ========================================
# THERAPEUTIC PROMPTS
# ========================================

@therapist_bp.route('/prompts', methods=['POST'])
@require_therapist()
def create_prompt():
    """Create a therapeutic prompt for a client"""
    therapist_id = session['user_id']
    data = request.get_json()

    required = ['relationship_id', 'prompt_type', 'title', 'description', 'prompt_content']
    if not all(field in data for field in required):
        return jsonify({'error': 'Missing required fields'}), 400

    # Verify relationship
    relationship = ClientTherapistRelationship.query.filter_by(
        relationship_id=data['relationship_id'],
        therapist_id=therapist_id,
        status='active'
    ).first()

    if not relationship:
        return jsonify({'error': 'Invalid relationship'}), 404

    try:
        prompt = TherapeuticPrompt(
            therapist_id=therapist_id,
            relationship_id=data['relationship_id'],
            prompt_type=data['prompt_type'],
            title=data['title'],
            description=data['description'],
            prompt_content=data['prompt_content'],
            instructions=data.get('instructions'),
            expected_duration_minutes=data.get('expected_duration_minutes'),
            delivery_timing=data.get('delivery_timing', 'immediate'),
            scheduled_datetime=data.get('scheduled_datetime'),
            frequency=data.get('frequency', 'once'),
            deadline_date=data.get('deadline_date'),
            is_active=True
        )
        db.session.add(prompt)
        db.session.commit()

        # Create notification for client
        notification = Notification(
            user_id=relationship.client_id,
            notification_type='new_prompt',
            title='New Therapeutic Prompt',
            message=f'Your therapist has sent you a new prompt: {data["title"]}',
            related_entity_type='prompt',
            related_entity_id=prompt.prompt_id
        )
        db.session.add(notification)
        db.session.commit()

        return jsonify({
            'message': 'Prompt created successfully',
            'prompt_id': prompt.prompt_id
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to create prompt: {str(e)}'}), 500


@therapist_bp.route('/prompts', methods=['GET'])
@require_therapist()
def get_prompts():
    """Get all prompts created by this therapist"""
    therapist_id = session['user_id']

    prompts = TherapeuticPrompt.query.filter_by(
        therapist_id=therapist_id,
        is_active=True
    ).order_by(TherapeuticPrompt.created_at.desc()).all()

    return jsonify({
        'prompts': [{
            'prompt_id': p.prompt_id,
            'relationship_id': p.relationship_id,
            'prompt_type': p.prompt_type,
            'title': p.title,
            'delivery_timing': p.delivery_timing,
            'frequency': p.frequency,
            'created_at': p.created_at.isoformat()
        } for p in prompts]
    }), 200


@therapist_bp.route('/prompts/<int:prompt_id>/responses', methods=['GET'])
@require_therapist()
def get_prompt_responses(prompt_id):
    """Get responses to a specific prompt"""
    therapist_id = session['user_id']

    # Verify prompt belongs to therapist
    prompt = TherapeuticPrompt.query.filter_by(
        prompt_id=prompt_id,
        therapist_id=therapist_id
    ).first()

    if not prompt:
        return jsonify({'error': 'Prompt not found'}), 404

    responses = PromptResponse.query.filter_by(
        prompt_id=prompt_id,
        is_shared_with_therapist=True
    ).order_by(PromptResponse.response_date.desc()).all()

    return jsonify({
        'prompt': {
            'prompt_id': prompt.prompt_id,
            'title': prompt.title,
            'prompt_type': prompt.prompt_type
        },
        'responses': [{
            'response_id': r.response_id,
            'client_id': r.client_id,
            'response_content': r.response_content,
            'insights_gained': r.insights_gained,
            'emotional_state': r.emotional_state,
            'response_date': r.response_date.isoformat(),
            'therapist_feedback': r.therapist_feedback
        } for r in responses]
    }), 200

# Renders the page
@therapist_bp.route('/responses/all', methods=['GET'])
@require_therapist()
def all_responses_page():
    return render_template('therapist/all_responses.html')

# Returns the JSON data
@therapist_bp.route('/api/responses/all', methods=['GET'])
@require_therapist()
def get_all_responses():
    therapist_id = session['user_id']

    responses = PromptResponse.query\
        .join(TherapeuticPrompt, PromptResponse.prompt_id == TherapeuticPrompt.prompt_id)\
        .filter(
            TherapeuticPrompt.therapist_id == therapist_id,
            PromptResponse.is_shared_with_therapist == True
        )\
        .order_by(PromptResponse.created_at.desc())\
        .all()

    # Preload related clients and prompts to avoid per-row queries
    client_ids = {r.client_id for r in responses}
    prompt_ids = {r.prompt_id for r in responses}

    clients = {u.user_id: u for u in User.query.filter(User.user_id.in_(client_ids)).all()} if client_ids else {}
    prompts = {p.prompt_id: p for p in TherapeuticPrompt.query.filter(TherapeuticPrompt.prompt_id.in_(prompt_ids)).all()} if prompt_ids else {}

    result = []
    for r in responses:
        client = clients.get(r.client_id)
        prompt = prompts.get(r.prompt_id)

        result.append({
            'response_id': r.response_id,
            'client_id': r.client_id,
            'client_name': f"{client.first_name} {client.last_name}" if client else 'Unknown Client',
            'prompt_title': prompt.title if prompt else 'Untitled Prompt',
            'prompt_type': prompt.prompt_type if prompt else None,
            'prompt_id': r.prompt_id,
            'response_content': r.response_content,
            'insights_gained': r.insights_gained,
            'emotional_state': r.emotional_state,
            'response_date': r.response_date.isoformat(),
            'therapist_feedback': r.therapist_feedback
        })

    return jsonify({'responses': result}), 200



@therapist_bp.route('/prompts/responses/<int:response_id>/feedback', methods=['PUT'])
@require_therapist()
def add_response_feedback(response_id):
    """Add feedback to a client's prompt response"""
    therapist_id = session['user_id']
    data = request.get_json()

    response = PromptResponse.query.get(response_id)
    if not response:
        return jsonify({'error': 'Response not found'}), 404

    # Verify therapist owns the prompt
    prompt = TherapeuticPrompt.query.filter_by(
        prompt_id=response.prompt_id,
        therapist_id=therapist_id
    ).first()

    if not prompt:
        return jsonify({'error': 'Unauthorized'}), 403

    response.therapist_feedback = data.get('feedback')
    response.updated_at = datetime.utcnow()
    db.session.commit()

    # Notify client
    notification = Notification(
        user_id=response.client_id,
        notification_type='therapist_feedback',
        title='Feedback on Your Response',
        message='Your therapist has provided feedback on your prompt response',
        related_entity_type='prompt_response',
        related_entity_id=response_id
    )
    db.session.add(notification)
    db.session.commit()

    return jsonify({'message': 'Feedback added successfully'}), 200


# ========================================
# DASHBOARD (Enhanced with Priority Info)
# ========================================

@therapist_bp.route('/api/dashboard', methods=['GET'])
@require_therapist()
def get_dashboard():
    """Get therapist dashboard overview with priority stats"""
    therapist_id = session['user_id']

    # Active clients
    active_clients = ClientTherapistRelationship.query.filter_by(
        therapist_id=therapist_id,
        status='active'
    ).count()

    # Pending responses
    pending_responses = PromptResponse.query.join(TherapeuticPrompt).filter(
        TherapeuticPrompt.therapist_id == therapist_id,
        PromptResponse.is_shared_with_therapist == True,
        PromptResponse.therapist_feedback == None
    ).count()

    # Priority capsule statistics
    unreviewed_capsules = Capsule.query.filter_by(
        therapist_id=therapist_id,
        priority_reviewed_by_therapist=False
    ).filter(Capsule.status.in_(['sealed', 'archived'])).all()

    priority_counts = {
        'critical': len([c for c in unreviewed_capsules if c.priority_level == 'CRITICAL']),
        'high': len([c for c in unreviewed_capsules if c.priority_level == 'HIGH']),
        'medium': len([c for c in unreviewed_capsules if c.priority_level == 'MEDIUM']),
        'low': len([c for c in unreviewed_capsules if c.priority_level == 'LOW'])
    }

    # Recent capsules with priority (last 5 sealed capsules)
    recent_capsules = Capsule.query.filter_by(
        therapist_id=therapist_id
    ).order_by(Capsule.created_at.desc()).limit(5).all()

    total_capsules = Capsule.query.filter_by(therapist_id=therapist_id).count()

    return jsonify({
        'active_clients': active_clients,
        'pending_responses': pending_responses,
        'total_capsules': total_capsules,  # ← add this
        'unreviewed_priority_capsules': {
            'total': len(unreviewed_capsules),
            'by_priority': priority_counts
        }

    }), 200