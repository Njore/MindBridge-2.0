"""
Messaging Blueprint
Handles secure messaging between clients and therapists
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from models import (db, User, Message, ClientTherapistRelationship, MessageType,
                    RelationshipStatus, Notification)
from blueprints.auth import login_required, log_activity
from datetime import datetime
from sqlalchemy import desc, or_, and_

messaging_bp = Blueprint('messaging', __name__)


@messaging_bp.route('/')
@login_required
def inbox():
    """View inbox"""
    user = User.query.get(session['user_id'])

    # Get all messages for this user
    messages = Message.query.filter(
        or_(
            and_(Message.recipient_id == user.user_id, Message.is_deleted_by_recipient == False),
            and_(Message.sender_id == user.user_id, Message.is_deleted_by_sender == False)
        )
    ).order_by(desc(Message.created_at)).all()

    # Group messages by conversation
    conversations = {}
    for message in messages:
        other_user_id = message.sender_id if message.recipient_id == user.user_id else message.recipient_id
        if other_user_id not in conversations:
            conversations[other_user_id] = {
                'other_user': User.query.get(other_user_id),
                'messages': [],
                'unread_count': 0,
                'last_message': None
            }

        conversations[other_user_id]['messages'].append(message)

        if message.recipient_id == user.user_id and not message.read_status:
            conversations[other_user_id]['unread_count'] += 1

        if not conversations[other_user_id]['last_message'] or \
                message.created_at > conversations[other_user_id]['last_message'].created_at:
            conversations[other_user_id]['last_message'] = message

    # Sort conversations by last message
    conversations = dict(sorted(
        conversations.items(),
        key=lambda x: x[1]['last_message'].created_at if x[1]['last_message'] else datetime.min,
        reverse=True
    ))

    return render_template('messaging/inbox.html',
                           user=user,
                           conversations=conversations)


@messaging_bp.route('/conversation/<int:other_user_id>')
@login_required
def conversation(other_user_id):
    """View conversation with specific user"""
    user = User.query.get(session['user_id'])
    other_user = User.query.get_or_404(other_user_id)

    # Verify they have a relationship
    relationship = ClientTherapistRelationship.query.filter(
        or_(
            and_(ClientTherapistRelationship.client_id == user.user_id,
                 ClientTherapistRelationship.therapist_id == other_user_id),
            and_(ClientTherapistRelationship.client_id == other_user_id,
                 ClientTherapistRelationship.therapist_id == user.user_id)
        ),
        ClientTherapistRelationship.status == RelationshipStatus.ACTIVE
    ).first()

    if not relationship:
        flash('No active relationship found with this user.', 'warning')
        return redirect(url_for('messaging.inbox'))

    # Get messages between users
    messages = Message.query.filter(
        Message.relationship_id == relationship.relationship_id,
        or_(
            and_(Message.sender_id == user.user_id, Message.is_deleted_by_sender == False),
            and_(Message.recipient_id == user.user_id, Message.is_deleted_by_recipient == False)
        )
    ).order_by(Message.created_at).all()

    # Mark unread messages as read
    for message in messages:
        if message.recipient_id == user.user_id and not message.read_status:
            message.mark_as_read()

    db.session.commit()

    return render_template('messaging/conversation.html',
                           user=user,
                           other_user=other_user,
                           messages=messages,
                           relationship=relationship)


@messaging_bp.route('/send', methods=['POST'])
@login_required
def send_message():
    """Send a message"""
    user = User.query.get(session['user_id'])

    recipient_id = request.form.get('recipient_id', type=int)
    message_type = request.form.get('message_type', 'general')
    subject = request.form.get('subject', '').strip()
    content = request.form.get('content', '').strip()

    if not recipient_id or not content:
        flash('Recipient and content are required.', 'danger')
        return redirect(url_for('messaging.inbox'))

    # Verify relationship exists
    relationship = ClientTherapistRelationship.query.filter(
        or_(
            and_(ClientTherapistRelationship.client_id == user.user_id,
                 ClientTherapistRelationship.therapist_id == recipient_id),
            and_(ClientTherapistRelationship.client_id == recipient_id,
                 ClientTherapistRelationship.therapist_id == user.user_id)
        ),
        ClientTherapistRelationship.status == RelationshipStatus.ACTIVE
    ).first()

    if not relationship:
        flash('No active relationship found with this user.', 'danger')
        return redirect(url_for('messaging.inbox'))

    message = Message(
        sender_id=user.user_id,
        recipient_id=recipient_id,
        relationship_id=relationship.relationship_id,
        message_type=MessageType(message_type),
        subject=subject,
        content=content,
        is_encrypted=True
    )

    db.session.add(message)
    db.session.commit()

    log_activity(user.user_id, 'message_sent', 'message',
                 message.message_id, f'Sent message to user {recipient_id}')

    # Create notification for recipient
    notification = Notification(
        user_id=recipient_id,
        notification_type='new_message',
        title='New Message',
        message=f'{user.get_full_name()} sent you a message',
        related_entity_type='message',
        related_entity_id=message.message_id
    )
    db.session.add(notification)
    db.session.commit()

    flash('Message sent successfully!', 'success')
    return redirect(url_for('messaging.conversation', other_user_id=recipient_id))


@messaging_bp.route('/delete/<int:message_id>', methods=['POST'])
@login_required
def delete_message(message_id):
    """Delete a message (soft delete)"""
    user = User.query.get(session['user_id'])
    message = Message.query.get_or_404(message_id)

    # Soft delete based on user role
    if message.sender_id == user.user_id:
        message.is_deleted_by_sender = True
    elif message.recipient_id == user.user_id:
        message.is_deleted_by_recipient = True
    else:
        flash('Access denied.', 'danger')
        return redirect(url_for('messaging.inbox'))

    db.session.commit()

    log_activity(user.user_id, 'message_deleted', 'message',
                 message_id, 'Deleted message')

    flash('Message deleted.', 'success')
    return redirect(url_for('messaging.inbox'))


@messaging_bp.route('/api/unread-count')
@login_required
def unread_count():
    """Get unread message count (API endpoint)"""
    user = User.query.get(session['user_id'])

    count = Message.query.filter_by(
        recipient_id=user.user_id,
        read_status=False,
        is_deleted_by_recipient=False
    ).count()

    return jsonify({'unread_count': count})