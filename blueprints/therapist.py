from flask import Blueprint, request, jsonify, session, render_template, redirect
from models import (db, User, ClientTherapistRelationship, Capsule, Message,
                    TherapeuticPrompt, PromptResponse, Notification, ActivityLog)
from datetime import datetime, date

therapist_bp = Blueprint('therapist', __name__)


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
        clients.append({
            'relationship_id': rel.relationship_id,
            'client_id': client.user_id,
            'first_name': client.first_name,
            'last_name': client.last_name,
            'email': client.email,
            'relationship_start': rel.relationship_start_date.isoformat(),
            'client_goals': rel.client_goals
        })

    return jsonify({'clients': clients}), 200


@therapist_bp.route('/clients/<int:client_id>', methods=['GET'])
@require_therapist()
def get_client_detail(client_id):
    """Get detailed info for a specific client"""
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

    # Get recent capsules
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
# CAPSULES (View Client Capsules)
# ========================================

@therapist_bp.route('/capsules', methods=['GET'])
@require_therapist()
def get_therapist_capsules():
    """Get all capsules for therapist's clients"""
    therapist_id = session['user_id']

    status = request.args.get('status', 'sealed')  # Default to sealed only

    capsules = Capsule.query.filter_by(
        therapist_id=therapist_id,
        status=status
    ).order_by(Capsule.created_at.desc()).limit(50).all()

    return jsonify({
        'capsules': [{
            'capsule_id': c.capsule_id,
            'client_id': c.client_id,
            'title': c.title,
            'user_tag': c.user_tag,
            'status': c.status,
            'created_at': c.created_at.isoformat(),
            'sealed_at': c.sealed_at.isoformat() if c.sealed_at else None
        } for c in capsules]
    }), 200


@therapist_bp.route('/capsules/<int:capsule_id>', methods=['GET'])
@require_therapist()
def get_capsule_detail(capsule_id):
    """Get capsule details with messages"""
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

    return jsonify({
        'capsule': {
            'capsule_id': capsule.capsule_id,
            'client_id': capsule.client_id,
            'title': capsule.title,
            'user_tag': capsule.user_tag,
            'status': capsule.status,
            'created_at': capsule.created_at.isoformat(),
            'sealed_at': capsule.sealed_at.isoformat() if capsule.sealed_at else None
        },
        'messages': [{
            'message_id': m.message_id,
            'sender_id': m.sender_id,
            'content': m.content,
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
# DASHBOARD
# ========================================

@therapist_bp.route('/dashboard', methods=['GET'])
@require_therapist()
def get_dashboard():
    """Get therapist dashboard overview"""
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

    # Recent capsules
    recent_capsules = Capsule.query.filter_by(
        therapist_id=therapist_id,
        status='sealed'
    ).order_by(Capsule.sealed_at.desc()).limit(5).all()

    return jsonify({
        'active_clients': active_clients,
        'pending_responses': pending_responses,
        'recent_capsules': [{
            'capsule_id': c.capsule_id,
            'client_id': c.client_id,
            'title': c.title,
            'user_tag': c.user_tag,
            'sealed_at': c.sealed_at.isoformat()
        } for c in recent_capsules]
    }), 200