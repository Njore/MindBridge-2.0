from flask import Blueprint, request, jsonify, session
from models import (db, Capsule, Message, MessageTag, MessageAttachment, 
                    ClientTherapistRelationship, Notification, ActivityLog)
from datetime import datetime, timedelta

messaging_bp = Blueprint('messaging', __name__)

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
# CAPSULES
# ========================================

@messaging_bp.route('/capsules', methods=['POST'])
@require_auth()
def create_capsule():
    """Create a new capsule (client only)"""
    user_id = session['user_id']
    user_type = session['user_type']
    
    if user_type != 'client':
        return jsonify({'error': 'Only clients can create capsules'}), 403
    
    data = request.get_json()
    
    if 'therapist_id' not in data:
        return jsonify({'error': 'therapist_id required'}), 400
    
    # Verify active relationship
    relationship = ClientTherapistRelationship.query.filter_by(
        client_id=user_id,
        therapist_id=data['therapist_id'],
        status='active'
    ).first()
    
    if not relationship:
        return jsonify({'error': 'No active relationship with this therapist'}), 404
    
    try:
        capsule = Capsule(
            client_id=user_id,
            therapist_id=data['therapist_id'],
            relationship_id=relationship.relationship_id,
            title=data.get('title', f"Capsule - {datetime.utcnow().strftime('%Y-%m-%d')}"),
            user_tag=data.get('user_tag', 'general'),
            status='open'
        )
        db.session.add(capsule)
        db.session.commit()
        
        return jsonify({
            'message': 'Capsule created successfully',
            'capsule_id': capsule.capsule_id,
            'status': capsule.status,
            'created_at': capsule.created_at.isoformat()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to create capsule: {str(e)}'}), 500

@messaging_bp.route('/capsules', methods=['GET'])
@require_auth()
def get_capsules():
    """Get user's capsules"""
    user_id = session['user_id']
    user_type = session['user_type']
    
    status = request.args.get('status')
    
    if user_type == 'client':
        query = Capsule.query.filter_by(client_id=user_id)
    else:
        query = Capsule.query.filter_by(therapist_id=user_id)
    
    if status:
        query = query.filter_by(status=status)
    
    capsules = query.order_by(Capsule.created_at.desc()).limit(50).all()
    
    return jsonify({
        'capsules': [{
            'capsule_id': c.capsule_id,
            'client_id': c.client_id,
            'therapist_id': c.therapist_id,
            'title': c.title,
            'user_tag': c.user_tag,
            'status': c.status,
            'created_at': c.created_at.isoformat(),
            'sealed_at': c.sealed_at.isoformat() if c.sealed_at else None
        } for c in capsules]
    }), 200

@messaging_bp.route('/capsules/<int:capsule_id>', methods=['GET'])
@require_auth()
def get_capsule(capsule_id):
    """Get capsule with messages"""
    user_id = session['user_id']
    
    capsule = Capsule.query.get(capsule_id)
    if not capsule:
        return jsonify({'error': 'Capsule not found'}), 404
    
    # Verify access
    if capsule.client_id != user_id and capsule.therapist_id != user_id:
        return jsonify({'error': 'Access denied'}), 403
    
    # Get messages
    messages = Message.query.filter_by(
        capsule_id=capsule_id
    ).order_by(Message.created_at).all()
    
    return jsonify({
        'capsule': {
            'capsule_id': capsule.capsule_id,
            'client_id': capsule.client_id,
            'therapist_id': capsule.therapist_id,
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

@messaging_bp.route('/capsules/<int:capsule_id>/seal', methods=['POST'])
@require_auth()
def seal_capsule(capsule_id):
    """Seal a capsule (24-hour window closed)"""
    user_id = session['user_id']
    
    capsule = Capsule.query.get(capsule_id)
    if not capsule:
        return jsonify({'error': 'Capsule not found'}), 404
    
    # Only client can seal their own capsule
    if capsule.client_id != user_id:
        return jsonify({'error': 'Only the client can seal this capsule'}), 403
    
    if capsule.status != 'open':
        return jsonify({'error': 'Capsule is already sealed'}), 400
    
    capsule.status = 'sealed'
    capsule.sealed_at = datetime.utcnow()
    db.session.commit()
    
    # Notify therapist
    notification = Notification(
        user_id=capsule.therapist_id,
        notification_type='capsule_sealed',
        title='New Capsule Sealed',
        message=f'A client has sealed a capsule: {capsule.title}',
        related_entity_type='capsule',
        related_entity_id=capsule_id
    )
    db.session.add(notification)
    db.session.commit()
    
    return jsonify({
        'message': 'Capsule sealed successfully',
        'sealed_at': capsule.sealed_at.isoformat()
    }), 200

@messaging_bp.route('/capsules/<int:capsule_id>/archive', methods=['POST'])
@require_auth()
def archive_capsule(capsule_id):
    """Archive a capsule"""
    user_id = session['user_id']
    
    capsule = Capsule.query.get(capsule_id)
    if not capsule:
        return jsonify({'error': 'Capsule not found'}), 404
    
    # Both client and therapist can archive
    if capsule.client_id != user_id and capsule.therapist_id != user_id:
        return jsonify({'error': 'Access denied'}), 403
    
    capsule.status = 'archived'
    capsule.archived_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({'message': 'Capsule archived successfully'}), 200

# ========================================
# MESSAGES
# ========================================

@messaging_bp.route('/capsules/<int:capsule_id>/messages', methods=['POST'])
@require_auth()
def create_message(capsule_id):
    """Add a message to a capsule"""
    user_id = session['user_id']
    data = request.get_json()
    
    capsule = Capsule.query.get(capsule_id)
    if not capsule:
        return jsonify({'error': 'Capsule not found'}), 404
    
    # Verify access
    if capsule.client_id != user_id and capsule.therapist_id != user_id:
        return jsonify({'error': 'Access denied'}), 403
    
    # Check if capsule is open
    if capsule.status == 'sealed' and user_id == capsule.client_id:
        return jsonify({'error': 'Cannot add messages to sealed capsule'}), 400
    
    if not data.get('content'):
        return jsonify({'error': 'Content required'}), 400
    
    try:
        message = Message(
            capsule_id=capsule_id,
            sender_id=user_id,
            content=data['content']
        )
        db.session.add(message)
        db.session.commit()
        
        # Notify the other party
        recipient_id = capsule.therapist_id if user_id == capsule.client_id else capsule.client_id
        notification = Notification(
            user_id=recipient_id,
            notification_type='new_message',
            title='New Message',
            message=f'You have a new message in: {capsule.title}',
            related_entity_type='capsule',
            related_entity_id=capsule_id
        )
        db.session.add(notification)
        db.session.commit()
        
        return jsonify({
            'message': 'Message created successfully',
            'message_id': message.message_id,
            'created_at': message.created_at.isoformat()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to create message: {str(e)}'}), 500

@messaging_bp.route('/messages/<int:message_id>/tags', methods=['POST'])
@require_auth()
def add_message_tag(message_id):
    """Add a tag to a message (user or system)"""
    user_id = session['user_id']
    data = request.get_json()
    
    message = Message.query.get(message_id)
    if not message:
        return jsonify({'error': 'Message not found'}), 404
    
    # Verify sender
    if message.sender_id != user_id:
        return jsonify({'error': 'Can only tag your own messages'}), 403
    
    if not data.get('tag_type'):
        return jsonify({'error': 'tag_type required'}), 400
    
    try:
        tag = MessageTag(
            message_id=message_id,
            tag_type=data['tag_type'],
            source='user'  # User-added tags
        )
        db.session.add(tag)
        db.session.commit()
        
        return jsonify({
            'message': 'Tag added successfully',
            'tag_id': tag.tag_id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to add tag: {str(e)}'}), 500

# ========================================
# NOTIFICATIONS
# ========================================

@messaging_bp.route('/notifications', methods=['GET'])
@require_auth()
def get_notifications():
    """Get user's notifications"""
    user_id = session['user_id']
    
    unread_only = request.args.get('unread_only', 'false').lower() == 'true'
    
    query = Notification.query.filter_by(user_id=user_id)
    
    if unread_only:
        query = query.filter_by(is_read=False)
    
    notifications = query.order_by(Notification.created_at.desc()).limit(50).all()
    
    return jsonify({
        'notifications': [{
            'notification_id': n.notification_id,
            'notification_type': n.notification_type,
            'title': n.title,
            'message': n.message,
            'is_read': n.is_read,
            'created_at': n.created_at.isoformat()
        } for n in notifications]
    }), 200

@messaging_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
@require_auth()
def mark_notification_read(notification_id):
    """Mark notification as read"""
    user_id = session['user_id']
    
    notification = Notification.query.filter_by(
        notification_id=notification_id,
        user_id=user_id
    ).first()
    
    if not notification:
        return jsonify({'error': 'Notification not found'}), 404
    
    notification.is_read = True
    notification.read_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({'message': 'Notification marked as read'}), 200

@messaging_bp.route('/notifications/read-all', methods=['POST'])
@require_auth()
def mark_all_read():
    """Mark all notifications as read"""
    user_id = session['user_id']
    
    Notification.query.filter_by(
        user_id=user_id,
        is_read=False
    ).update({
        'is_read': True,
        'read_at': datetime.utcnow()
    })
    db.session.commit()
    
    return jsonify({'message': 'All notifications marked as read'}), 200