from flask import Blueprint, request, jsonify, session, render_template, redirect
from models import (db, User, Capsule, Message, ClientTherapistRelationship,
                    CrisisEvent, Notification, ActivityLog, ConsentAgreement,
                    DataErasureRequest, PasswordResetRequest)
from datetime import datetime, timedelta
from services.timezone import today_eat
from sqlalchemy import func
from flask import url_for
import logging
import secrets

admin_bp = Blueprint('admin', __name__)
logger = logging.getLogger(__name__)


# ========================================
# GUARD: Admin-only decorator
# ========================================

def require_admin():
    """Decorator to restrict endpoints to admin users only"""
    def decorator(f):
        def wrapper(*args, **kwargs):
            if 'user_id' not in session:
                return jsonify({'error': 'Unauthorized'}), 401
            if session.get('user_type') != 'admin':
                return jsonify({'error': 'Admin access only'}), 403
            return f(*args, **kwargs)
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator


def admin_log(action_type, description):
    """Convenience: write an ActivityLog entry for the current admin session"""
    log = ActivityLog(
        user_id=session['user_id'],
        action_type=action_type,
        description=description,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent', '')[:500]
    )
    db.session.add(log)


# ========================================
# TEMPLATE ROUTE
# ========================================

@admin_bp.route('/dashboard', methods=['GET'])
def dashboard():
    """Render the admin dashboard"""
    if 'user_id' not in session or session.get('user_type') != 'admin':
        return redirect('/auth/login')
    return render_template('admin/dashboard.html')


# ========================================
# LOGOUT
# ========================================

@admin_bp.route('/logout', methods=['POST'])
def logout():
    """
    Log out the current admin session.
    Writes an activity log entry before clearing the session so the
    audit trail captures who logged out and when.
    """
    if 'user_id' in session:
        try:
            admin_log('admin_logout', f'Admin {session["user_id"]} logged out')
            db.session.commit()
        except Exception:
            pass  # don't block logout on a logging failure
        session.clear()

    return jsonify({'message': 'Logged out successfully'}), 200


# ========================================
# OVERVIEW STATS
# ========================================

@admin_bp.route('/api/stats', methods=['GET'])
@require_admin()
def get_stats():
    """
    Platform-wide overview numbers for the dashboard header cards.
    Covers users, capsules, crisis events, and AI alert backlog.
    """
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    total_clients    = User.query.filter_by(user_type='client', is_active=True).count()
    total_therapists = User.query.filter_by(user_type='therapist', is_active=True).count()
    new_users_week   = User.query.filter(User.created_at >= week_ago).count()
    unverified_therapists = User.query.filter_by(
        user_type='therapist', is_verified=False, is_active=True
    ).count()

    open_capsules   = Capsule.query.filter_by(status='open').count()
    sealed_capsules = Capsule.query.filter_by(status='sealed').count()

    critical_unreviewed = Capsule.query.filter(
        Capsule.priority_level == 'CRITICAL',
        Capsule.priority_reviewed_by_therapist == False
    ).count()
    high_unreviewed = Capsule.query.filter(
        Capsule.priority_level == 'HIGH',
        Capsule.priority_reviewed_by_therapist == False
    ).count()

    crisis_this_month = CrisisEvent.query.filter(
        CrisisEvent.created_at >= month_ago
    ).count()
    high_severity_crisis = CrisisEvent.query.filter(
        CrisisEvent.created_at >= month_ago,
        CrisisEvent.severity_level >= 7
    ).count()

    active_relationships = ClientTherapistRelationship.query.filter_by(
        status='active'
    ).count()

    pending_erasures = DataErasureRequest.query.filter_by(status='pending').count()
    pending_resets   = PasswordResetRequest.query.filter_by(status='pending').count()

    return jsonify({
        'users': {
            'total_clients':         total_clients,
            'total_therapists':      total_therapists,
            'new_this_week':         new_users_week,
            'unverified_therapists': unverified_therapists,
            'active_relationships':  active_relationships,
        },
        'capsules': {
            'open':   open_capsules,
            'sealed': sealed_capsules,
        },
        'safety': {
            'critical_unreviewed':  critical_unreviewed,
            'high_unreviewed':      high_unreviewed,
            'crisis_this_month':    crisis_this_month,
            'high_severity_crisis': high_severity_crisis,
        },
        'compliance': {
            'pending_erasure_requests': pending_erasures,
            'pending_password_resets':  pending_resets,
        }
    }), 200


# ========================================
# USER MANAGEMENT
# ========================================

@admin_bp.route('/api/users', methods=['GET'])
@require_admin()
def get_all_users():
    """
    List all users with optional filters.
    Query params: user_type, is_active, is_verified, search (name/email)
    """
    user_type   = request.args.get('user_type')
    is_active   = request.args.get('is_active')
    is_verified = request.args.get('is_verified')
    search      = request.args.get('search', '').strip()

    query = User.query

    if user_type:
        query = query.filter_by(user_type=user_type)
    if is_active is not None:
        query = query.filter_by(is_active=(is_active == 'true'))
    if is_verified is not None:
        query = query.filter_by(is_verified=(is_verified == 'true'))
    if search:
        like = f'%{search}%'
        query = query.filter(
            db.or_(
                User.email.ilike(like),
                User.first_name.ilike(like),
                User.last_name.ilike(like)
            )
        )

    users = query.order_by(User.created_at.desc()).limit(200).all()

    result = []
    for u in users:
        if u.user_type == 'therapist':
            extra_count = ClientTherapistRelationship.query.filter_by(
                therapist_id=u.user_id, status='active'
            ).count()
            extra_label = 'active_clients'
        else:
            extra_count = Capsule.query.filter_by(client_id=u.user_id).count()
            extra_label = 'total_capsules'

        result.append({
            'user_id':    u.user_id,
            'full_name':  f'{u.first_name} {u.last_name}',
            'email':      u.email,
            'user_type':  u.user_type,
            'is_active':  u.is_active,
            'is_verified': u.is_verified,
            'created_at': u.created_at.isoformat(),
            extra_label:  extra_count,
        })

    return jsonify({'users': result, 'total': len(result)}), 200


@admin_bp.route('/api/users/<int:user_id>/toggle-active', methods=['POST'])
@require_admin()
def toggle_user_active(user_id):
    """Activate or deactivate a user account"""
    user = User.query.get_or_404(user_id)

    if user.user_type == 'admin':
        return jsonify({'error': 'Cannot deactivate admin accounts'}), 400

    user.is_active = not user.is_active
    action = 'activated' if user.is_active else 'deactivated'

    admin_log('admin_user_toggle', f'Admin {action} user {user_id} ({user.email})')
    db.session.commit()

    logger.info(f"Admin {session['user_id']} {action} user {user_id}")

    return jsonify({
        'message': f'User {action} successfully',
        'is_active': user.is_active
    }), 200


@admin_bp.route('/api/users/<int:user_id>/verify', methods=['POST'])
@require_admin()
def verify_therapist(user_id):
    """Verify a therapist account (approve credentials)"""
    user = User.query.get_or_404(user_id)

    if user.user_type != 'therapist':
        return jsonify({'error': 'Only therapist accounts can be verified'}), 400

    user.is_verified = True

    admin_log('admin_therapist_verified', f'Therapist {user.email} verified by admin')

    notification = Notification(
        user_id=user_id,
        notification_type='account_verified',
        title='Your account has been verified',
        message='Your therapist credentials have been reviewed and approved. You can now connect with clients.',
        related_entity_type='user',
        related_entity_id=user_id
    )
    db.session.add(notification)
    db.session.commit()

    logger.info(f"Admin {session['user_id']} verified therapist {user_id}")

    return jsonify({'message': 'Therapist verified successfully'}), 200


# ========================================
# SAFETY MONITORING
# ========================================

@admin_bp.route('/api/safety-alerts', methods=['GET'])
@require_admin()
def get_safety_alerts():
    """
    Platform-wide view of all CRITICAL and HIGH capsules.
    Catches any client in distress whose assigned therapist may not have responded.
    """
    levels   = request.args.getlist('level') or ['CRITICAL', 'HIGH']
    reviewed = request.args.get('reviewed')  # 'true', 'false', or None for all

    query = Capsule.query.filter(Capsule.priority_level.in_(levels))

    if reviewed == 'false':
        query = query.filter(Capsule.priority_reviewed_by_therapist == False)
    elif reviewed == 'true':
        query = query.filter(Capsule.priority_reviewed_by_therapist == True)

    capsules = query.order_by(
        Capsule.priority_score.desc(),
        Capsule.priority_analyzed_at.desc()
    ).limit(100).all()

    all_ids  = list({c.client_id for c in capsules} | {c.therapist_id for c in capsules})
    users    = User.query.filter(User.user_id.in_(all_ids)).all()
    user_map = {u.user_id: f'{u.first_name} {u.last_name}' for u in users}

    result = []
    for c in capsules:
        result.append({
            'capsule_id':       c.capsule_id,
            'title':            c.title,
            'status':           c.status,
            'client_name':      user_map.get(c.client_id, 'Unknown'),
            'client_id':        c.client_id,
            'therapist_name':   user_map.get(c.therapist_id, 'Unknown'),
            'therapist_id':     c.therapist_id,
            'priority_level':   c.priority_level,
            'priority_score':   float(c.priority_score) if c.priority_score else 0,
            'priority_reasons': c.priority_reasons,
            'reviewed':         c.priority_reviewed_by_therapist or False,
            'analyzed_at':      c.priority_analyzed_at.isoformat() if c.priority_analyzed_at else None,
            'sealed_at':        c.sealed_at.isoformat() if c.sealed_at else None,
        })

    return jsonify({'alerts': result, 'total': len(result)}), 200


# ========================================
# NOTIFICATION BACKLOG
# ========================================

@admin_bp.route('/api/notification-backlog', methods=['GET'])
@require_admin()
def get_notification_backlog():
    """
    Therapists who have unread crisis-related notifications.
    Flags anyone sitting on unread CRITICAL/HIGH alerts — the safety gap
    where a client is at risk but the therapist hasn't opened the alert yet.
    is_urgent = True when the oldest unread alert has been waiting over 24 hours.
    """
    unread = db.session.query(
        Notification.user_id,
        func.count(Notification.notification_id).label('unread_count'),
        func.min(Notification.created_at).label('oldest_unread')
    ).filter(
        Notification.is_read == False,
        Notification.notification_type.in_([
            'crisis_alert', 'priority_critical', 'priority_high'
        ])
    ).group_by(Notification.user_id).all()

    if not unread:
        return jsonify({'backlog': [], 'total': 0}), 200

    therapist_ids = [row.user_id for row in unread]
    therapists    = User.query.filter(
        User.user_id.in_(therapist_ids),
        User.user_type == 'therapist'
    ).all()
    therapist_map = {u.user_id: u for u in therapists}

    backlog = []
    for row in unread:
        therapist = therapist_map.get(row.user_id)
        if not therapist:
            continue  # notification exists for a non-therapist user, skip

        hours_waiting = (
            datetime.utcnow() - row.oldest_unread
        ).total_seconds() / 3600

        backlog.append({
            'therapist_id':     therapist.user_id,
            'therapist_name':   f'{therapist.first_name} {therapist.last_name}',
            'email':            therapist.email,
            'unread_count':     row.unread_count,
            'oldest_unread_at': row.oldest_unread.isoformat(),
            'hours_waiting':    round(hours_waiting, 1),
            'is_urgent':        hours_waiting > 24,
        })

    # Urgent first, then by longest wait
    backlog.sort(key=lambda x: (-x['is_urgent'], -x['hours_waiting']))

    return jsonify({'backlog': backlog, 'total': len(backlog)}), 200


# ========================================
# CLIENT-THERAPIST RELATIONSHIPS
# ========================================

@admin_bp.route('/api/relationships', methods=['GET'])
@require_admin()
def get_relationships():
    """All client-therapist pairings with status and capsule counts"""
    status = request.args.get('status', 'active')

    query = ClientTherapistRelationship.query
    if status:
        query = query.filter_by(status=status)

    relationships = query.order_by(
        ClientTherapistRelationship.relationship_start_date.desc()
    ).limit(200).all()

    all_ids  = list({r.client_id for r in relationships} |
                    {r.therapist_id for r in relationships})
    users    = User.query.filter(User.user_id.in_(all_ids)).all()
    user_map = {u.user_id: f'{u.first_name} {u.last_name}' for u in users}

    result = []
    for r in relationships:
        capsule_count = Capsule.query.filter_by(
            relationship_id=r.relationship_id
        ).count()

        result.append({
            'relationship_id': r.relationship_id,
            'client_name':     user_map.get(r.client_id, 'Unknown'),
            'client_id':       r.client_id,
            'therapist_name':  user_map.get(r.therapist_id, 'Unknown'),
            'therapist_id':    r.therapist_id,
            'status':          r.status,
            'start_date':      r.relationship_start_date.isoformat(),
            'capsule_count':   capsule_count,
        })

    return jsonify({'relationships': result, 'total': len(result)}), 200


@admin_bp.route('/api/relationships/<int:rel_id>/dissolve', methods=['POST'])
@require_admin()
def dissolve_relationship(rel_id):
    """
    Dissolve a client-therapist relationship.
    Use for safeguarding incidents or when a therapist leaves the platform.
    """
    rel = ClientTherapistRelationship.query.get_or_404(rel_id)

    if rel.status != 'active':
        return jsonify({'error': 'Relationship is not active'}), 400

    data   = request.get_json() or {}
    reason = data.get('reason', 'Administrative action')

    rel.status   = 'ended'
    rel.relationship_end_date = today_eat()

    for uid in [rel.client_id, rel.therapist_id]:
        db.session.add(Notification(
            user_id=uid,
            notification_type='relationship_ended',
            title='Therapeutic relationship ended',
            message=f'Your therapeutic relationship has been ended by a platform administrator. Reason: {reason}',
            related_entity_type='relationship',
            related_entity_id=rel_id
        ))

    admin_log('admin_relationship_dissolved', f'Admin dissolved relationship {rel_id}. Reason: {reason}')
    db.session.commit()

    logger.warning(f"Admin {session['user_id']} dissolved relationship {rel_id}: {reason}")

    return jsonify({'message': 'Relationship dissolved and both parties notified'}), 200


# ========================================
# CRISIS EVENTS (PLATFORM-WIDE)
# ========================================

@admin_bp.route('/api/crisis-events', methods=['GET'])
@require_admin()
def get_crisis_events():
    """All crisis events across the platform, sorted by severity"""
    severity_min = int(request.args.get('severity_min', 1))
    days         = int(request.args.get('days', 30))
    since        = datetime.utcnow() - timedelta(days=days)

    events = CrisisEvent.query.filter(
        CrisisEvent.created_at >= since,
        CrisisEvent.severity_level >= severity_min
    ).order_by(
        CrisisEvent.severity_level.desc(),
        CrisisEvent.created_at.desc()
    ).limit(100).all()

    client_ids = list({e.client_id for e in events})
    clients    = User.query.filter(User.user_id.in_(client_ids)).all()
    client_map = {u.user_id: f'{u.first_name} {u.last_name}' for u in clients}

    return jsonify({
        'events': [{
            'crisis_id':          e.crisis_id,
            'client_name':        client_map.get(e.client_id, 'Unknown'),
            'client_id':          e.client_id,
            'crisis_type':        e.crisis_type,
            'severity_level':     e.severity_level,
            'description':        e.description,
            'status':             e.status,
            'therapist_notified': e.therapist_notified,
            'created_at':         e.created_at.isoformat(),
        } for e in events],
        'total': len(events)
    }), 200


# ========================================
# AI ANALYSIS AUDIT
# ========================================

@admin_bp.route('/api/ai-audit', methods=['GET'])
@require_admin()
def get_ai_audit():
    """
    Audit trail of all AI-flagged capsules — CRITICAL and HIGH.
    Shows whether therapists acknowledged them and when analysis ran.
    """
    capsules = Capsule.query.filter(
        Capsule.priority_level.in_(['CRITICAL', 'HIGH']),
        Capsule.priority_analyzed_at.isnot(None)
    ).order_by(
        Capsule.priority_analyzed_at.desc()
    ).limit(200).all()

    all_ids  = list({c.client_id for c in capsules} | {c.therapist_id for c in capsules})
    users    = User.query.filter(User.user_id.in_(all_ids)).all()
    user_map = {u.user_id: f'{u.first_name} {u.last_name}' for u in users}

    return jsonify({
        'audit': [{
            'capsule_id':        c.capsule_id,
            'title':             c.title,
            'client_name':       user_map.get(c.client_id, 'Unknown'),
            'therapist_name':    user_map.get(c.therapist_id, 'Unknown'),
            'priority_level':    c.priority_level,
            'priority_score':    float(c.priority_score) if c.priority_score else 0,
            'risk_flags':        (c.priority_reasons or {}).get('risk_flags', []),
            'sentiment_summary': (c.priority_reasons or {}).get('sentiment_summary', ''),
            'analyzed_at':       c.priority_analyzed_at.isoformat(),
            'reviewed':          c.priority_reviewed_by_therapist or False,
            'status':            c.status,
        } for c in capsules],
        'total': len(capsules)
    }), 200


# ========================================
# ACTIVITY LOGS (AUDIT TRAIL)
# ========================================

@admin_bp.route('/api/activity-logs', methods=['GET'])
@require_admin()
def get_activity_logs():
    """
    Full audit trail — searchable by user, action type, or date range.
    Query params: user_id, action_type, days (default 7)
    """
    filter_user = request.args.get('user_id', type=int)
    action_type = request.args.get('action_type')
    days        = int(request.args.get('days', 7))
    since       = datetime.utcnow() - timedelta(days=days)

    # NOTE: ActivityLog uses `timestamp`, not `created_at`
    query = ActivityLog.query.filter(ActivityLog.timestamp >= since)

    if filter_user:
        query = query.filter_by(user_id=filter_user)
    if action_type:
        query = query.filter_by(action_type=action_type)

    logs = query.order_by(ActivityLog.timestamp.desc()).limit(300).all()

    user_ids = list({l.user_id for l in logs if l.user_id})
    users    = User.query.filter(User.user_id.in_(user_ids)).all()
    user_map = {u.user_id: f'{u.first_name} {u.last_name} ({u.email})' for u in users}

    return jsonify({
        'logs': [{
            'log_id':      l.log_id,
            'user':        user_map.get(l.user_id, 'System'),
            'user_id':     l.user_id,
            'action_type': l.action_type,
            'description': l.description,
            'ip_address':  l.ip_address,
            'created_at':  l.timestamp.isoformat(),  # normalised for frontend
        } for l in logs],
        'total': len(logs)
    }), 200


# ========================================
# CONSENT & COMPLIANCE
# ========================================

@admin_bp.route('/api/consent-summary', methods=['GET'])
@require_admin()
def get_consent_summary():
    """
    Summary of consent status across the platform.
    Identifies users who may be missing required agreements.
    """
    total_users = User.query.filter(
        User.user_type.in_(['client', 'therapist'])
    ).count()

    users_with_terms = db.session.query(
        func.count(func.distinct(ConsentAgreement.user_id))
    ).filter_by(agreement_type='terms_of_service', is_active=True).scalar()

    users_with_privacy = db.session.query(
        func.count(func.distinct(ConsentAgreement.user_id))
    ).filter_by(agreement_type='privacy_policy', is_active=True).scalar()

    recent = ConsentAgreement.query.filter(
        ConsentAgreement.agreed_date >= datetime.utcnow() - timedelta(days=30)
    ).count()

    return jsonify({
        'total_users':         total_users,
        'users_with_terms':    users_with_terms,
        'users_with_privacy':  users_with_privacy,
        'missing_terms':       total_users - users_with_terms,
        'missing_privacy':     total_users - users_with_privacy,
        'recent_consents_30d': recent,
    }), 200


# ========================================
# GDPR — RIGHT TO ERASURE (ADMIN SIDE)
# ========================================

@admin_bp.route('/api/erasure-requests', methods=['GET'])
@require_admin()
def get_erasure_requests():
    """
    All data erasure requests. Defaults to pending.
    Query param: status = pending | approved | completed | rejected
    Admin reviews these before any deletion is actioned —
    human in the loop is intentional.
    """
    status = request.args.get('status', 'pending')
    query  = DataErasureRequest.query
    if status:
        query = query.filter_by(status=status)

    reqs = query.order_by(DataErasureRequest.requested_at.desc()).all()

    user_ids = list({r.user_id for r in reqs})
    users    = User.query.filter(User.user_id.in_(user_ids)).all()
    user_map = {u.user_id: f'{u.first_name} {u.last_name} ({u.email})' for u in users}

    return jsonify({
        'requests': [{
            'request_id':   r.request_id,
            'user':         user_map.get(r.user_id, 'Unknown'),
            'user_id':      r.user_id,
            'requested_at': r.requested_at.isoformat(),
            'reason':       r.reason,
            'status':       r.status,
            'notes':        r.notes,
            'reviewed_at':  r.reviewed_at.isoformat() if r.reviewed_at else None,
        } for r in reqs],
        'total': len(reqs)
    }), 200


@admin_bp.route('/api/erasure-requests/<int:request_id>/action', methods=['POST'])
@require_admin()
def action_erasure_request(request_id):
    """
    Approve or reject an erasure request.

    Approving anonymizes the user's PII — it does NOT hard-delete rows,
    which would break referential integrity and clinical record-keeping.
    Instead it nulls out identifying fields so the user is unidentifiable.

    IMPORTANT: Capsule content and messages are intentionally left intact.
    In many jurisdictions (Kenya Data Protection Act 2019, EU GDPR Article 17(3)(b))
    clinical records must be retained for a legally mandated period even after
    an erasure request is approved. Get legal advice for your jurisdiction before
    changing this behaviour.
    """
    erasure_req = DataErasureRequest.query.get_or_404(request_id)

    if erasure_req.status != 'pending':
        return jsonify({'error': 'Request already actioned'}), 400

    data   = request.get_json() or {}
    action = data.get('action')  # 'approve' or 'reject'
    notes  = data.get('notes', '').strip()

    if action not in ('approve', 'reject'):
        return jsonify({'error': 'action must be "approve" or "reject"'}), 422

    erasure_req.reviewed_by = session['user_id']
    erasure_req.reviewed_at = datetime.utcnow()
    erasure_req.notes       = notes

    if action == 'reject':
        erasure_req.status = 'rejected'
        admin_log(
            'gdpr_erasure_rejected',
            f'Admin rejected erasure request {request_id} for user {erasure_req.user_id}'
        )
        db.session.commit()
        return jsonify({'message': 'Request rejected'}), 200

    # ── APPROVE: anonymize PII ──────────────────────────────────────────────
    user = User.query.get(erasure_req.user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    user.is_active    = False
    user.email        = f'deleted_{user.user_id}@erased.invalid'
    user.first_name   = 'Deleted'
    user.last_name    = 'User'
    user.password_hash = ''
    user.phone        = None
    user.date_of_birth = None
    user.bio          = None
    user.profile_picture_url = None

    erasure_req.status       = 'completed'
    erasure_req.completed_at = datetime.utcnow()

    admin_log(
        'gdpr_erasure_completed',
        f'Admin completed erasure for user {erasure_req.user_id}'
    )
    db.session.commit()

    logger.warning(
        f"GDPR erasure completed for user {erasure_req.user_id} "
        f"by admin {session['user_id']}"
    )

    return jsonify({'message': 'User data anonymized successfully'}), 200


# ========================================
# PASSWORD RESET REQUESTS (ADMIN SIDE)
# ========================================

@admin_bp.route('/api/password-reset-requests', methods=['GET'])
@require_admin()
def get_password_reset_requests():
    """
    All password reset requests, defaulting to pending.
    Query param: status = pending | approved | used | rejected
    """
    status = request.args.get('status', 'pending')
    query  = PasswordResetRequest.query
    if status:
        query = query.filter_by(status=status)

    reqs = query.order_by(PasswordResetRequest.requested_at.asc()).all()

    user_ids = list({r.user_id for r in reqs})
    users    = User.query.filter(User.user_id.in_(user_ids)).all()
    user_map = {u.user_id: f'{u.first_name} {u.last_name}' for u in users}

    now = datetime.utcnow()
    return jsonify({
        'requests': [{
            'id':           r.id,
            'user_id':      r.user_id,
            'user':         user_map.get(r.user_id, 'Unknown'),
            'email':        r.email,
            'status':       r.status,
            'requested_at': r.requested_at.isoformat(),
            'approved_at':  r.approved_at.isoformat() if r.approved_at else None,
            'expires_at':   r.expires_at.isoformat() if r.expires_at else None,
            # Expose the link for approved-but-not-yet-used tokens so admin
            # can re-copy without re-approving. Never expose used/rejected tokens.
            'reset_link': (
                url_for('auth.reset_password_page', token=r.token, _external=True)
                if r.status == 'approved' and r.token and r.expires_at and r.expires_at > now
                else None
            ),
            'is_expired': bool(
                r.status == 'approved' and r.expires_at and r.expires_at <= now
            ),
        } for r in reqs],
        'total': len(reqs)
    }), 200


@admin_bp.route('/api/password-reset-requests/<int:request_id>/approve', methods=['POST'])
@require_admin()
def approve_password_reset(request_id):
    """
    Approve a reset request — generates a secure one-time link valid for 1 hour.
    Admin manually shares the link with the user (phone / in-person).
    """
    reset_req = PasswordResetRequest.query.get_or_404(request_id)

    if reset_req.status != 'pending':
        return jsonify({'error': f'Request is already {reset_req.status}'}), 409

    token = secrets.token_urlsafe(48)

    reset_req.token       = token
    reset_req.status      = 'approved'
    reset_req.approved_at = datetime.utcnow()
    reset_req.expires_at  = datetime.utcnow() + timedelta(hours=1)

    admin_log(
        'password_reset_approved',
        f'Admin approved password reset for user {reset_req.user_id} ({reset_req.email})'
    )
    db.session.commit()

    reset_link = url_for('auth.reset_password_page', token=token, _external=True)

    return jsonify({
        'message':    'Approved. Share this link with the user — it expires in 1 hour.',
        'reset_link': reset_link,
        'expires_at': reset_req.expires_at.isoformat(),
        'user_email': reset_req.email,
    }), 200


@admin_bp.route('/api/password-reset-requests/<int:request_id>/reject', methods=['POST'])
@require_admin()
def reject_password_reset(request_id):
    """Reject a suspicious or duplicate reset request."""
    reset_req = PasswordResetRequest.query.get_or_404(request_id)

    if reset_req.status != 'pending':
        return jsonify({'error': f'Request is already {reset_req.status}'}), 409

    reset_req.status = 'rejected'

    admin_log(
        'password_reset_rejected',
        f'Admin rejected password reset for user {reset_req.user_id} ({reset_req.email})'
    )
    db.session.commit()

    return jsonify({'message': 'Request rejected.'}), 200