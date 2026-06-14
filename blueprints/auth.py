from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for
from models import db, User, ConsentAgreement, UserPrivacySetting, ActivityLog, DataErasureRequest, PasswordResetRequest
from datetime import datetime, timedelta
import bcrypt
import re
import secrets

auth_bp = Blueprint('auth', __name__)


def validate_email(email):
    """Basic email validation"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def hash_password(password):
    """Hash password with bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password, password_hash):
    """Verify password against hash"""
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))


def log_activity(user_id, action_type, description, ip_address=None):
    """Log user activity"""
    log = ActivityLog(
        user_id=user_id,
        action_type=action_type,
        description=description,
        ip_address=ip_address or request.remote_addr,
        user_agent=request.headers.get('User-Agent', '')[:500]
    )
    db.session.add(log)
    db.session.commit()


def admin_required(f):
    """Decorator — restricts route to admin users only."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('user_type') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated


def _dashboard_for(user_type):
    """Return the dashboard URL for a given user_type."""
    dashboards = {
        'client':    '/client/dashboard',
        'therapist': '/therapist/dashboard',
        'admin':     '/admin/dashboard',
    }
    return dashboards.get(user_type, '/')


# ── Template GET routes ───────────────────────────────────────────────────────

@auth_bp.route('/register', methods=['GET'])
def register_page():
    """Show registration form"""
    if 'user_id' in session:
        return redirect(_dashboard_for(session.get('user_type')))
    return render_template('auth/register.html')


@auth_bp.route('/login', methods=['GET'])
def login_page():
    """Show login form"""
    if 'user_id' in session:
        return redirect(_dashboard_for(session.get('user_type')))
    return render_template('auth/login.html')


@auth_bp.route('/profile', methods=['GET'])
def profile():
    """Show user profile"""
    if 'user_id' not in session:
        return redirect('/auth/login')
    user = User.query.get(session['user_id'])
    return render_template('auth/profile.html', user=user)


@auth_bp.route('/logout', methods=['GET'])
def logout_page():
    """Logout user"""
    user_id = session.get('user_id')
    if user_id:
        log_activity(user_id, 'logout', 'User logged out')
    session.clear()
    return redirect('/')


# ── API routes ────────────────────────────────────────────────────────────────

@auth_bp.route('/register', methods=['POST'])
def register():
    """
    Register new user with explicit consent
    PRD: 1.1 Explicit User Consent
    """
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form.to_dict()
        data['consent_terms']   = 'consent_terms' in request.form
        data['consent_privacy'] = 'consent_privacy' in request.form
        data['allow_analytics'] = 'allow_analytics' in request.form

    required = ['email', 'password', 'user_type', 'first_name', 'last_name']
    if not all(field in data for field in required):
        if request.is_json:
            return jsonify({'error': 'Missing required fields'}), 400
        return render_template('auth/register.html', error='Missing required fields'), 400

    if not data.get('consent_terms') or not data.get('consent_privacy'):
        error = 'Explicit consent required for Terms of Service and Privacy Policy'
        if request.is_json:
            return jsonify({'error': error}), 400
        return render_template('auth/register.html', error=error), 400

    if data.get('user_type') not in ['client', 'therapist']:
        error = 'Invalid user_type'
        if request.is_json:
            return jsonify({'error': error}), 400
        return render_template('auth/register.html', error=error), 400

    email = data['email'].lower().strip()
    if not validate_email(email):
        error = 'Invalid email format'
        if request.is_json:
            return jsonify({'error': error}), 400
        return render_template('auth/register.html', error=error), 400

    if User.query.filter_by(email=email).first():
        error = 'Email already registered'
        if request.is_json:
            return jsonify({'error': error}), 409
        return render_template('auth/register.html', error=error), 409

    password = data['password']
    if len(password) < 8:
        error = 'Password must be at least 8 characters'
        if request.is_json:
            return jsonify({'error': error}), 400
        return render_template('auth/register.html', error=error), 400

    try:
        user = User(
            email=email,
            password_hash=hash_password(password),
            user_type=data['user_type'],
            first_name=data['first_name'].strip(),
            last_name=data['last_name'].strip(),
            phone=data.get('phone'),
            date_of_birth=data.get('date_of_birth'),
            is_active=True,
            is_verified=False
        )
        db.session.add(user)
        db.session.flush()

        consents = [
            ConsentAgreement(
                user_id=user.user_id,
                agreement_type='terms_of_service',
                version='1.0',
                agreed_date=datetime.utcnow(),
                agreed_ip_address=request.remote_addr,
                is_active=True
            ),
            ConsentAgreement(
                user_id=user.user_id,
                agreement_type='privacy_policy',
                version='1.0',
                agreed_date=datetime.utcnow(),
                agreed_ip_address=request.remote_addr,
                is_active=True
            )
        ]
        db.session.add_all(consents)

        privacy_settings = UserPrivacySetting(
            user_id=user.user_id,
            allow_data_analytics=data.get('allow_analytics', True),
            allow_session_recordings=False,
            share_progress_with_therapist=True if data['user_type'] == 'client' else False,
            encrypted_storage_preference=True,
            data_retention_days=730
        )
        db.session.add(privacy_settings)
        db.session.commit()

        log_activity(user.user_id, 'registration', f"User registered as {data['user_type']}")

        if request.is_json:
            return jsonify({
                'message':   'Registration successful',
                'user_id':   user.user_id,
                'email':     user.email,
                'user_type': user.user_type
            }), 201
        return redirect('/auth/login?registered=true')

    except Exception as e:
        db.session.rollback()
        error = f'Registration failed: {str(e)}'
        if request.is_json:
            return jsonify({'error': error}), 500
        return render_template('auth/register.html', error=error), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    """User login with session management"""
    data = request.get_json() if request.is_json else request.form

    if not data.get('email') or not data.get('password'):
        if request.is_json:
            return jsonify({'error': 'Email and password required'}), 400
        return render_template('auth/login.html', error='Email and password required')

    email = data['email'].lower().strip()
    user  = User.query.filter_by(email=email).first()

    if not user or not verify_password(data['password'], user.password_hash):
        if request.is_json:
            return jsonify({'error': 'Invalid credentials'}), 401
        return render_template('auth/login.html', error='Invalid credentials')

    if not user.is_active:
        if request.is_json:
            return jsonify({'error': 'Account deactivated'}), 403
        return render_template('auth/login.html', error='Account deactivated')

    session['user_id']   = user.user_id
    session['user_type'] = user.user_type
    session['email']     = user.email
    session['first_name'] = user.first_name

    log_activity(user.user_id, 'login', 'User logged in')

    if user.user_type == 'client':
        return redirect('/client/dashboard')
    elif user.user_type == 'therapist':
        return redirect('/therapist/dashboard')
    elif user.user_type == 'admin':
        return redirect('/admin/dashboard')
    else:
        session.clear()
        return render_template('auth/login.html', error='Unknown account type'), 403


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """User logout"""
    user_id = session.get('user_id')
    if user_id:
        log_activity(user_id, 'logout', 'User logged out')
    session.clear()
    return jsonify({'message': 'Logged out successfully'}), 200


@auth_bp.route('/consent/update', methods=['PUT'])
def update_consent():
    """Update consent preferences — PRD 1.1"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session['user_id']
    data    = request.get_json()

    consent_type = data.get('consent_type')
    if consent_type not in ['terms_of_service', 'privacy_policy', 'data_processing']:
        return jsonify({'error': 'Invalid consent type'}), 400

    ConsentAgreement.query.filter_by(
        user_id=user_id,
        agreement_type=consent_type,
        is_active=True
    ).update({'is_active': False})

    new_consent = ConsentAgreement(
        user_id=user_id,
        agreement_type=consent_type,
        version=data.get('version', '1.0'),
        agreed_date=datetime.utcnow(),
        agreed_ip_address=request.remote_addr,
        is_active=True
    )
    db.session.add(new_consent)
    db.session.commit()

    log_activity(user_id, 'consent_update', f'Updated consent: {consent_type}')
    return jsonify({'message': 'Consent updated successfully'}), 200


@auth_bp.route('/consent/status', methods=['GET'])
def get_consent_status():
    """Get user's current consent status"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    consents = ConsentAgreement.query.filter_by(
        user_id=session['user_id'],
        is_active=True
    ).all()

    return jsonify({
        'consents': [{
            'type':       c.agreement_type,
            'version':    c.version,
            'agreed_date': c.agreed_date.isoformat(),
            'is_active':  c.is_active
        } for c in consents]
    }), 200


@auth_bp.route('/me', methods=['GET'])
def get_current_user():
    """Get current logged-in user info"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 404

    return jsonify({
        'user_id':      user.user_id,
        'email':        user.email,
        'user_type':    user.user_type,
        'first_name':   user.first_name,
        'last_name':    user.last_name,
        'phone':        user.phone,
        'date_of_birth': user.date_of_birth.isoformat() if user.date_of_birth else None,
        'bio':          user.bio,
        'is_verified':  user.is_verified,
        'created_at':   user.created_at.isoformat()
    }), 200


@auth_bp.route('/account/request-erasure', methods=['POST'])
def request_erasure():
    """Submit a right-to-erasure request (GDPR Article 17)."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    user_id  = session['user_id']
    existing = DataErasureRequest.query.filter_by(user_id=user_id, status='pending').first()

    if existing:
        return jsonify({
            'error':        'You already have a pending erasure request',
            'submitted_at': existing.requested_at.isoformat()
        }), 409

    data   = request.get_json() or {}
    reason = data.get('reason', '').strip() or None

    erasure_req = DataErasureRequest(user_id=user_id, reason=reason, status='pending')
    db.session.add(erasure_req)

    log_activity(user_id, 'erasure_request_submitted', 'User submitted a data erasure request')
    db.session.commit()

    return jsonify({
        'message':      (
            'Your erasure request has been submitted and will be reviewed '
            'by our team within 30 days. Note: clinical records may be retained '
            'as required by applicable law even after erasure is approved.'
        ),
        'request_id':   erasure_req.request_id,
        'submitted_at': erasure_req.requested_at.isoformat()
    }), 201


@auth_bp.route('/account/erasure-status', methods=['GET'])
def get_erasure_status():
    """Let a user check the status of their erasure request."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    req = (DataErasureRequest.query
           .filter_by(user_id=session['user_id'])
           .order_by(DataErasureRequest.requested_at.desc())
           .first())

    if not req:
        return jsonify({'request': None}), 200

    return jsonify({
        'request': {
            'request_id':  req.request_id,
            'status':      req.status,
            'submitted_at': req.requested_at.isoformat(),
            'reviewed_at': req.reviewed_at.isoformat() if req.reviewed_at else None,
            'notes':       req.notes if req.status == 'rejected' else None,
        }
    }), 200


@auth_bp.route('/check-reset', methods=['GET'])
def check_reset_page():
    """
    Public page — user enters their email to check if admin has approved
    their reset request. Requires no login.
    """
    return render_template('auth/check_reset.html')


@auth_bp.route('/check-reset', methods=['POST'])
def check_reset_status():
    """
    Looks up an approved, unexpired reset token for the submitted email.
    If found, redirects straight to the reset form.
    If not, shows a 'not ready yet' message — never reveals why.
    Always behaves the same whether the email exists or not (no enumeration).
    """
    data  = request.get_json(silent=True) or request.form
    email = (data.get('email') or '').strip().lower()

    redirect_url = None

    if email and validate_email(email):
        user = User.query.filter_by(email=email).first()
        if user:
            reset_req = (
                PasswordResetRequest.query
                .filter_by(user_id=user.user_id, status='approved')
                .filter(PasswordResetRequest.expires_at > datetime.utcnow())
                .order_by(PasswordResetRequest.approved_at.desc())
                .first()
            )
            if reset_req:
                redirect_url = url_for(
                    'auth.reset_password_page',
                    token=reset_req.token,
                    _external=False
                )

    if redirect_url:
        return redirect(redirect_url)

    # No approved token found — show a neutral holding message
    return render_template(
        'auth/check_reset.html',
        message='Your request is still pending admin approval. Please check back shortly.'
    )


# =============================================================================
# PASSWORD RESET FLOW
# =============================================================================

@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    """
    STEP 1 — User submits email from the login modal.
    Saves a pending reset request for the admin to review.
    Always returns 200 — never confirms whether the email exists.
    """
    data  = request.get_json(silent=True) or request.form
    email = (data.get('email') or '').strip().lower()

    if email and validate_email(email):
        user = User.query.filter_by(email=email).first()

        if user:
            # Don't stack duplicate pending requests
            existing = PasswordResetRequest.query.filter_by(
                user_id=user.user_id,
                status='pending'
            ).first()

            if not existing:
                reset_req = PasswordResetRequest(
                    user_id=user.user_id,
                    email=email,
                    status='pending',
                    requested_at=datetime.utcnow()
                )
                db.session.add(reset_req)
                db.session.commit()

                log_activity(
                    user.user_id,
                    'password_reset_requested',
                    'User submitted a password reset request'
                )

    return jsonify({'success': True}), 200


@auth_bp.route('/admin/reset-requests', methods=['GET'])
@admin_required
def admin_reset_requests():
    """
    STEP 2 — Admin fetches all pending reset requests.
    Called by the admin dashboard to populate the requests table.
    """
    pending = (
        PasswordResetRequest.query
        .filter_by(status='pending')
        .order_by(PasswordResetRequest.requested_at.asc())
        .all()
    )

    return jsonify({
        'reset_requests': [
            {
                'id':           r.id,
                'user_id':      r.user_id,
                'email':        r.email,
                'requested_at': r.requested_at.isoformat(),
            }
            for r in pending
        ]
    }), 200


@auth_bp.route('/admin/approve-reset/<int:request_id>', methods=['POST'])
@admin_required
def admin_approve_reset(request_id):
    """
    STEP 3 — Admin approves the request.
    Generates a secure one-time token valid for 1 hour.
    Returns the reset link — admin shares it with the user manually
    (phone call, in-person, secure messaging, etc.).
    """
    reset_req = PasswordResetRequest.query.get(request_id)

    if not reset_req:
        return jsonify({'error': 'Reset request not found'}), 404

    if reset_req.status != 'pending':
        return jsonify({'error': f'Request is already {reset_req.status}'}), 409

    token = secrets.token_urlsafe(48)   # 64-char URL-safe string

    reset_req.token       = token
    reset_req.status      = 'approved'
    reset_req.approved_at = datetime.utcnow()
    reset_req.expires_at  = datetime.utcnow() + timedelta(hours=1)

    db.session.commit()

    log_activity(
        session['user_id'],
        'password_reset_approved',
        f'Admin approved password reset for user {reset_req.user_id}'
    )

    reset_link = url_for('auth.reset_password_page', token=token, _external=True)

    return jsonify({
        'message':    'Approved. Share this link with the user — it expires in 1 hour.',
        'reset_link': reset_link,
        'expires_at': reset_req.expires_at.isoformat(),
        'user_email': reset_req.email
    }), 200


@auth_bp.route('/admin/reject-reset/<int:request_id>', methods=['POST'])
@admin_required
def admin_reject_reset(request_id):
    """
    STEP 3 (alt) — Admin rejects a suspicious or duplicate request.
    """
    reset_req = PasswordResetRequest.query.get(request_id)

    if not reset_req:
        return jsonify({'error': 'Reset request not found'}), 404

    if reset_req.status != 'pending':
        return jsonify({'error': f'Request is already {reset_req.status}'}), 409

    reset_req.status = 'rejected'
    db.session.commit()

    log_activity(
        session['user_id'],
        'password_reset_rejected',
        f'Admin rejected password reset for user {reset_req.user_id}'
    )

    return jsonify({'message': 'Request rejected.'}), 200


@auth_bp.route('/reset-password', methods=['GET'])
def reset_password_page():
    """
    STEP 4 — User visits the link the admin shared.
    Validates the token before showing the form.
    """
    token     = request.args.get('token', '').strip()
    reset_req = PasswordResetRequest.query.filter_by(token=token, status='approved').first()

    if not reset_req:
        return render_template('auth/reset_password.html',
                               error='This reset link is invalid.')

    if datetime.utcnow() > reset_req.expires_at:
        return render_template('auth/reset_password.html',
                               error='This reset link has expired. Please submit a new request.')

    return render_template('auth/reset_password.html', token=token)


@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    """
    STEP 5 — User submits their new password.
    Token is burned immediately after — can never be reused.
    """
    data             = request.get_json(silent=True) or request.form
    token            = (data.get('token') or '').strip()
    new_password     = data.get('password', '')
    confirm_password = data.get('confirm_password', '')

    reset_req = PasswordResetRequest.query.filter_by(token=token, status='approved').first()

    if not reset_req:
        return render_template('auth/reset_password.html',
                               token=token, error='This reset link is invalid.')

    if datetime.utcnow() > reset_req.expires_at:
        return render_template('auth/reset_password.html',
                               token=token, error='This link has expired. Please submit a new request.')

    if len(new_password) < 8:
        return render_template('auth/reset_password.html',
                               token=token, error='Password must be at least 8 characters.')

    if new_password != confirm_password:
        return render_template('auth/reset_password.html',
                               token=token, error='Passwords do not match.')

    user = User.query.get(reset_req.user_id)
    if not user:
        return render_template('auth/reset_password.html',
                               token=token, error='User not found. Please contact support.')

    # Update password
    user.password_hash = hash_password(new_password)

    # Burn the token — single use only
    reset_req.status  = 'used'
    reset_req.used_at = datetime.utcnow()

    db.session.commit()

    log_activity(
        user.user_id,
        'password_reset_completed',
        'User successfully reset their password via admin-approved link'
    )

    return redirect('/auth/login?reset=success')