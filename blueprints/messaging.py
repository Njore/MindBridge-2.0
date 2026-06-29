from flask import Blueprint, request, jsonify, session, render_template, redirect, current_app
from models import (db, Capsule, Message, MessageTag, MessageAttachment,
                    ClientTherapistRelationship, Notification, ActivityLog, User)
from datetime import datetime, timedelta
from services.sentiment_analyzer import analyzer
from services.encryption import encrypt_content, decrypt_content
from threading import Thread
import logging

messaging_bp = Blueprint('messaging', __name__)

# Setup logging
logger = logging.getLogger(__name__)


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


PRIORITY_RANK = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2, 'CRITICAL': 3}


def _should_escalate(current_level: str, new_level: str) -> bool:
    """
    Return True only when the new analysis is strictly higher than what we
    already have stored.  Priority never goes down — once CRITICAL, always
    CRITICAL for this capsule unless a therapist manually resets it.
    """
    return PRIORITY_RANK.get(new_level, 0) > PRIORITY_RANK.get(current_level or 'LOW', 0)


def analyze_capsule_priority(capsule_id, app=None):
    """
    Background task to analyze capsule priority using Granite AI.
    Runs asynchronously so it doesn't block the response.

    Key behaviours:
    - Analyses ALL messages in the capsule so each new message adds context.
    - Priority can only escalate (CRITICAL > HIGH > MEDIUM > LOW).
      A later LOW result will never override a previously stored HIGH/CRITICAL.
    - The capsule starts with priority_analyzed_at=None (shown as "Analyzing…"
      in the UI) and is only cleared once the first real result arrives.
    """
    from app import create_app
    if app is None:
        app = create_app()

    try:
        with app.app_context():
            capsule = Capsule.query.get(capsule_id)
            if not capsule:
                logger.error(f"Capsule {capsule_id} not found for analysis")
                return

            # Always re-fetch all client messages so every analysis has full context
            messages = Message.query.filter_by(capsule_id=capsule_id) \
                .order_by(Message.created_at) \
                .all()

            if not messages:
                logger.info(f"No messages in capsule {capsule_id}, skipping analysis")
                return

            message_texts = [decrypt_content(m.content) for m in messages]
            logger.info(f"Analyzing capsule {capsule_id} with {len(message_texts)} messages")

            # Analyze using Granite AI
            analysis = analyzer.analyze_capsule_messages(message_texts)
            new_level = analysis['priority_level']

            # ── Escalation-only logic ────────────────────────────────────────
            # Preserve the highest priority ever seen; never downgrade.
            current_level = capsule.priority_level or 'LOW'
            if _should_escalate(current_level, new_level):
                capsule.priority_level = new_level
                capsule.priority_score = analysis['priority_score']
                capsule.priority_reasons = {
                    'reasons': analysis['reasons'],
                    'risk_flags': analysis['risk_flags'],
                    'sentiment_summary': analysis['sentiment_summary']
                }
                logger.info(
                    f"Capsule {capsule_id} escalated: {current_level} → {new_level} "
                    f"(score={analysis['priority_score']})"
                )
            else:
                # No escalation — but still update the score/reasons so the
                # therapist always sees the most recent rationale.
                if new_level == current_level:
                    capsule.priority_score = max(
                        float(capsule.priority_score or 0),
                        float(analysis['priority_score'])
                    )
                    capsule.priority_reasons = {
                        'reasons': analysis['reasons'],
                        'risk_flags': analysis['risk_flags'],
                        'sentiment_summary': analysis['sentiment_summary']
                    }
                logger.info(
                    f"Capsule {capsule_id}: new result {new_level} did not escalate "
                    f"stored {current_level} — keeping existing priority"
                )

            # Mark analysis as completed (clears the "Analyzing…" state in UI)
            capsule.priority_analyzed_at = datetime.utcnow()
            db.session.commit()

            # ── Notifications (only fire when we actually escalate) ───────────
            if _should_escalate(current_level, new_level) or (
                new_level == 'CRITICAL' and current_level == 'CRITICAL'
            ):
                if new_level == 'CRITICAL':
                    notification = Notification(
                        user_id=capsule.therapist_id,
                        notification_type='crisis_alert',
                        title='⚠️ CRITICAL: Client in distress',
                        message=(
                            f'URGENT: Client shows signs of crisis in capsule '
                            f'"{capsule.title}". Priority score: {analysis["priority_score"]:.2f}'
                        ),
                        related_entity_type='capsule',
                        related_entity_id=capsule_id
                    )
                    db.session.add(notification)
                    db.session.commit()
                    logger.warning(f"CRITICAL alert created for capsule {capsule_id}")

                elif new_level == 'HIGH':
                    notification = Notification(
                        user_id=capsule.therapist_id,
                        notification_type='high_priority',
                        title='⚠️ High Priority Capsule',
                        message=f'High priority capsule requires attention: {capsule.title}',
                        related_entity_type='capsule',
                        related_entity_id=capsule_id
                    )
                    db.session.add(notification)
                    db.session.commit()

    except Exception as e:
        logger.error(f"Error analyzing capsule {capsule_id}: {str(e)}", exc_info=True)


# ========================================
# TEMPLATE ROUTES (GET)
# ========================================

@messaging_bp.route('/inbox', methods=['GET'])
def inbox():
    """Show capsules inbox"""
    if 'user_id' not in session:
        return redirect('/auth/login')
    return render_template('messaging/inbox.html')


@messaging_bp.route('/conversation/<int:capsule_id>', methods=['GET'])
def conversation(capsule_id):
    """Show capsule conversation"""
    if 'user_id' not in session:
        return redirect('/auth/login')
    return render_template('messaging/conversation.html', capsule_id=capsule_id)


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
            status='open',
            priority_level='LOW',  # Default priority
            priority_score=0.0
        )
        db.session.add(capsule)
        db.session.commit()

        # If first message was provided, add it
        first_message = data.get('first_message')
        if first_message:
            message = Message(
                capsule_id=capsule.capsule_id,
                sender_id=user_id,
                content=encrypt_content(first_message)
            )
            db.session.add(message)

            # Mark as "Analyzing…" — cleared once the background thread finishes
            capsule.priority_analyzed_at = None
            db.session.commit()

            # Trigger analysis for the new capsule
            thread = Thread(target=analyze_capsule_priority, args=(capsule.capsule_id, current_app._get_current_object()))
            thread.daemon = True
            thread.start()

        return jsonify({
            'message': 'Capsule created successfully',
            'capsule_id': capsule.capsule_id,
            'status': capsule.status,
            'created_at': capsule.created_at.isoformat()
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to create capsule: {str(e)}")
        return jsonify({'error': f'Failed to create capsule: {str(e)}'}), 500


@messaging_bp.route('/capsules', methods=['GET'])
@require_auth()
def get_capsules():
    """Get user's capsules with priority sorting for therapists"""
    user_id = session['user_id']
    user_type = session['user_type']

    status = request.args.get('status')
    sort_by_priority = request.args.get('sort_by_priority', 'false').lower() == 'true'

    # Therapist-only filters
    read_filter = request.args.get('read')        # 'read' | 'unread'
    client_id_filter = request.args.get('client_id', type=int)
    priority_filter = request.args.get('priority') # CRITICAL|HIGH|MEDIUM|LOW

    if user_type == 'client':
        query = Capsule.query.filter_by(client_id=user_id)
    else:
        query = Capsule.query.filter_by(therapist_id=user_id)
        sort_by_priority = True  # Therapists always see priority order

    if status:
        query = query.filter_by(status=status)

    # Apply therapist-specific filters
        if read_filter == 'unread':
            query = query.filter_by(therapist_read=False)
        elif read_filter == 'read':
            query = query.filter_by(therapist_read=True)
        if client_id_filter:
            query = query.filter_by(client_id=client_id_filter)
        if priority_filter:
            query = query.filter_by(priority_level=priority_filter)

    capsules = query.order_by(Capsule.created_at.desc()).limit(50).all()

    # For therapists, sort by priority (CRITICAL → HIGH → MEDIUM → LOW)
    if user_type == 'therapist' and sort_by_priority:
        priority_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
        capsules.sort(key=lambda c: priority_order.get(c.priority_level or 'LOW', 3))

    # Build client name lookup (for therapist view)
    client_ids = list({c.client_id for c in capsules})
    client_map = {}
    if client_ids:
        clients = User.query.filter(User.user_id.in_(client_ids)).all()
        client_map = {u.user_id: f"{u.first_name} {u.last_name}" for u in clients}

    return jsonify({
        'capsules': [{
            'capsule_id': c.capsule_id,
            'client_id': c.client_id,
            'client_name': client_map.get(c.client_id, 'Unknown Client'),
            'therapist_id': c.therapist_id,
            'title': c.title,
            'user_tag': c.user_tag,
            'status': c.status,
            'is_read': getattr(c, 'is_read', True),   # False = therapist hasn't opened it yet
            'priority_level': c.priority_level or 'LOW',
            'priority_score': float(c.priority_score) if c.priority_score else 0,
            'created_at': c.created_at.isoformat(),
            'sealed_at': c.sealed_at.isoformat() if c.sealed_at else None
        } for c in capsules]
    }), 200


@messaging_bp.route('/capsules/<int:capsule_id>', methods=['GET'])
@require_auth()
def get_capsule(capsule_id):
    """Get capsule with messages and priority info"""
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

    # Perform final priority analysis when sealing
    capsule.priority_analyzed_at = None
    db.session.commit()
    thread = Thread(target=analyze_capsule_priority, args=(capsule_id, current_app._get_current_object()))
    thread.daemon = True
    thread.start()

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
    """Add a message to a capsule and trigger priority analysis"""
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
            content=encrypt_content(data['content'])
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

        # Trigger priority analysis in background (only for client messages)
        if user_id == capsule.client_id:  # Only analyze when client sends message
            # Mark as "Analyzing…" so UI shows pending state immediately
            capsule.priority_analyzed_at = None
            db.session.commit()
            thread = Thread(target=analyze_capsule_priority, args=(capsule_id, current_app._get_current_object()))
            thread.daemon = True
            thread.start()
            logger.info(f"Priority analysis triggered for capsule {capsule_id}")

        return jsonify({
            'message': 'Message created successfully',
            'message_id': message.message_id,
            'created_at': message.created_at.isoformat()
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to create message: {str(e)}")
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
# THERAPIST PRIORITY ENDPOINTS
# ========================================

@messaging_bp.route('/therapist/prioritized', methods=['GET'])
@require_auth()
def therapist_prioritized_view():
    """Render therapist prioritized capsules dashboard"""
    if session.get('user_type') != 'therapist':
        return redirect('/dashboard')
    return render_template('therapist/prioritized_capsules.html')


@messaging_bp.route('/api/therapist/prioritized-capsules', methods=['GET'])
@require_auth()
def get_prioritized_capsules():
    """API endpoint for therapist to get capsules sorted by priority"""
    user_id = session['user_id']

    if session.get('user_type') != 'therapist':
        return jsonify({'error': 'Access denied'}), 403

    # Priority order for sorting
    priority_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}

    # Get all sealed and archived capsules for this therapist
    capsules = (
        Capsule.query
        .filter_by(therapist_id=user_id)
        .filter(Capsule.status.in_(['sealed', 'archived']))
        .all()
    )

    # Filter out capsules without messages (shouldn't happen but just in case)
    valid_capsules = []
    for capsule in capsules:
        message_count = Message.query.filter_by(capsule_id=capsule.capsule_id).count()
        if message_count > 0:
            valid_capsules.append(capsule)

    # Sort by priority (critical first)
    valid_capsules.sort(key=lambda c: priority_order.get(c.priority_level or 'LOW', 3))

    # Get client names
    client_ids = list({c.client_id for c in valid_capsules})
    clients = User.query.filter(User.user_id.in_(client_ids)).all()
    client_map = {u.user_id: f"{u.first_name} {u.last_name}" for u in clients}

    # Build response with additional data
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

        result.append({
            'capsule_id': capsule.capsule_id,
            'title': capsule.title,
            'client_name': client_map.get(capsule.client_id, 'Unknown'),
            'priority_level': capsule.priority_level or 'LOW',
            'priority_score': float(capsule.priority_score) if capsule.priority_score else 0,
            'priority_reasons': capsule.priority_reasons,
            'priority_analyzed_at': capsule.priority_analyzed_at.isoformat() if capsule.priority_analyzed_at else None,
            'message_count': message_count,
            'first_message_preview': first_message.content[:100] + '...' if first_message and len(
                first_message.content) > 100 else (first_message.content if first_message else ''),
            'last_message_at': last_message.created_at.isoformat() if last_message else None,
            'status': capsule.status,
            'sealed_at': capsule.sealed_at.isoformat() if capsule.sealed_at else None
        })

    return jsonify({'capsules': result}), 200


@messaging_bp.route('/api/therapist/capsules/<int:capsule_id>/reanalyze', methods=['POST'])
@require_auth()
def reanalyze_capsule(capsule_id):
    """
    Manually re-run Granite analysis on a capsule.
    Runs synchronously so the UI gets the result immediately.
    Only the assigned therapist can trigger this.
    """
    user_id = session['user_id']

    if session.get('user_type') != 'therapist':
        return jsonify({'error': 'Access denied'}), 403

    capsule = Capsule.query.get(capsule_id)
    if not capsule or capsule.therapist_id != user_id:
        return jsonify({'error': 'Capsule not found'}), 404

    messages = Message.query.filter_by(capsule_id=capsule_id)\
        .order_by(Message.created_at).all()

    if not messages:
        return jsonify({'error': 'No messages in this capsule to analyze'}), 400

    try:
        message_texts = [decrypt_content(m.content) for m in messages]
        analysis = analyzer.analyze_capsule_messages(message_texts)

        # Escalation-only: only overwrite if the new result is strictly higher
        current_level = capsule.priority_level or 'LOW'
        if _should_escalate(current_level, analysis['priority_level']) or current_level == analysis['priority_level']:
            capsule.priority_level       = analysis['priority_level']
            capsule.priority_score       = analysis['priority_score']
            capsule.priority_reasons     = {
                'reasons':          analysis['reasons'],
                'risk_flags':       analysis['risk_flags'],
                'sentiment_summary': analysis['sentiment_summary']
            }
        else:
            # New result is lower than stored — keep stored priority, update reasons only
            capsule.priority_reasons = {
                'reasons':           analysis['reasons'],
                'risk_flags':        analysis['risk_flags'],
                'sentiment_summary': analysis['sentiment_summary']
            }
        capsule.priority_analyzed_at = datetime.utcnow()
        db.session.commit()

        # Re-issue notifications if the new result is critical
        if analysis['priority_level'] == 'CRITICAL':
            notification = Notification(
                user_id=capsule.therapist_id,
                notification_type='crisis_alert',
                title='⚠️ CRITICAL: Client in distress (reanalysis)',
                message=f'Reanalysis flagged a crisis in capsule "{capsule.title}". Score: {analysis["priority_score"]:.2f}',
                related_entity_type='capsule',
                related_entity_id=capsule_id
            )
            db.session.add(notification)
            db.session.commit()
            logger.warning(f"CRITICAL re-flagged on reanalysis for capsule {capsule_id}")

        elif analysis['priority_level'] == 'HIGH':
            notification = Notification(
                user_id=capsule.therapist_id,
                notification_type='high_priority',
                title='⚠️ High Priority Capsule (reanalysis)',
                message=f'Reanalysis: high priority capsule needs attention — {capsule.title}',
                related_entity_type='capsule',
                related_entity_id=capsule_id
            )
            db.session.add(notification)
            db.session.commit()

        logger.info(f"Capsule {capsule_id} reanalyzed: {analysis['priority_level']} ({analysis['priority_score']:.2f})")

        return jsonify({
            'message': 'Reanalysis complete',
            'analysis': {
                'priority_level': analysis['priority_level'],
                'priority_score': analysis['priority_score'],
                'reasons':        analysis['reasons'],
                'risk_flags':     analysis['risk_flags'],
                'sentiment_summary': analysis['sentiment_summary'],
                'analyzed_at':    capsule.priority_analyzed_at.isoformat()
            }
        }), 200

    except Exception as e:
        logger.error(f"Reanalysis failed for capsule {capsule_id}: {str(e)}", exc_info=True)
        return jsonify({'error': 'Analysis failed. Is Ollama running?'}), 500

@messaging_bp.route('/api/therapist/capsules/<int:capsule_id>/mark-reviewed', methods=['POST'])
@require_auth()
def mark_capsule_reviewed(capsule_id):
    """Mark a capsule as reviewed by therapist"""
    user_id = session['user_id']

    if session.get('user_type') != 'therapist':
        return jsonify({'error': 'Access denied'}), 403

    capsule = Capsule.query.get(capsule_id)
    if not capsule or capsule.therapist_id != user_id:
        return jsonify({'error': 'Capsule not found'}), 404

    capsule.priority_reviewed_by_therapist = True
    db.session.commit()

    return jsonify({'message': 'Capsule marked as reviewed'}), 200


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

# ========================================
# DIAGNOSTIC (remove in production)
# ========================================

@messaging_bp.route('/api/analyze-test', methods=['GET'])
def analyze_test():
    """Test Ollama connectivity and run a sample analysis. Remove before production."""
    try:
        result = analyzer.analyze_capsule_messages([
            "I had a rough episode of suicidal thoughts the other day"
        ])
        return jsonify({'ollama_reachable': True, 'result': result}), 200
    except Exception as e:
        return jsonify({'ollama_reachable': False, 'error': str(e)}), 500