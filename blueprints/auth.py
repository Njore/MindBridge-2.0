from flask import Blueprint, request, jsonify, session, render_template, redirect
from models import db, User, ConsentAgreement, UserPrivacySetting, ActivityLog, DataErasureRequest
from datetime import datetime
import bcrypt
import re

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


# Template GET routes
@auth_bp.route('/register', methods=['GET'])
def register_page():
    """Show registration form"""
    return render_template('auth/register.html')


@auth_bp.route('/login', methods=['GET'])
def login_page():
    """Show login form"""
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


# API routes
@auth_bp.route('/register', methods=['POST'])
def register():
    """
    Register new user with explicit consent
    PRD: 1.1 Explicit User Consent
    """
    # Handle both JSON and form data
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form.to_dict()
        # Convert checkbox values to boolean
        data['consent_terms'] = 'consent_terms' in request.form
        data['consent_privacy'] = 'consent_privacy' in request.form
        data['allow_analytics'] = 'allow_analytics' in request.form

    # Validate required fields
    required = ['email', 'password', 'user_type', 'first_name', 'last_name']
    if not all(field in data for field in required):
        if request.is_json:
            return jsonify({'error': 'Missing required fields'}), 400
        return render_template('auth/register.html', error='Missing required fields'), 400

    # Validate consent (PRD 1.1 - No pre-checked boxes)
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

    # Validate email
    email = data['email'].lower().strip()
    if not validate_email(email):
        error = 'Invalid email format'
        if request.is_json:
            return jsonify({'error': error}), 400
        return render_template('auth/register.html', error=error), 400

    # Check if email exists
    if User.query.filter_by(email=email).first():
        error = 'Email already registered'
        if request.is_json:
            return jsonify({'error': error}), 409
        return render_template('auth/register.html', error=error), 409

    # Validate password strength
    password = data['password']
    if len(password) < 8:
        error = 'Password must be at least 8 characters'
        if request.is_json:
            return jsonify({'error': error}), 400
        return render_template('auth/register.html', error=error), 400

    try:
        # Create user
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
        db.session.flush()  # Get user_id

        # Record consent agreements (PRD 1.1)
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

        # Create default privacy settings (PRD 2.2)
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

        # Log registration
        log_activity(user.user_id, 'registration', f"User registered as {data['user_type']}")

        if request.is_json:
            return jsonify({
                'message': 'Registration successful',
                'user_id': user.user_id,
                'email': user.email,
                'user_type': user.user_type
            }), 201
        else:
            # Redirect to login page after successful registration
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
    user = User.query.filter_by(email=email).first()

    if not user or not verify_password(data['password'], user.password_hash):
        if request.is_json:
            return jsonify({'error': 'Invalid credentials'}), 401
        return render_template('auth/login.html', error='Invalid credentials')

    if not user.is_active:
        if request.is_json:
            return jsonify({'error': 'Account deactivated'}), 403
        return render_template('auth/login.html', error='Account deactivated')

    # Create session (PRD 2.2 - Secure session management)
    session['user_id'] = user.user_id
    session['user_type'] = user.user_type
    session['email'] = user.email
    session['first_name'] = user.first_name

    # Log login
    log_activity(user.user_id, 'login', 'User logged in')

    # Redirect based on user type
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
    """
    Update consent preferences
    PRD: 1.1 - Users can withdraw consent by deleting account
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session['user_id']
    data = request.get_json()

    consent_type = data.get('consent_type')
    if consent_type not in ['terms_of_service', 'privacy_policy', 'data_processing']:
        return jsonify({'error': 'Invalid consent type'}), 400

    # Deactivate old consent
    ConsentAgreement.query.filter_by(
        user_id=user_id,
        agreement_type=consent_type,
        is_active=True
    ).update({'is_active': False})

    # Create new consent record
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

    user_id = session['user_id']

    consents = ConsentAgreement.query.filter_by(
        user_id=user_id,
        is_active=True
    ).all()

    return jsonify({
        'consents': [{
            'type': c.agreement_type,
            'version': c.version,
            'agreed_date': c.agreed_date.isoformat(),
            'is_active': c.is_active
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
        'user_id': user.user_id,
        'email': user.email,
        'user_type': user.user_type,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'phone': user.phone,
        'date_of_birth': user.date_of_birth.isoformat() if user.date_of_birth else None,
        'bio': user.bio,
        'is_verified': user.is_verified,
        'created_at': user.created_at.isoformat()
    }), 200

# ========================================
# GDPR — USER ERASURE REQUEST
# Add these routes to auth.py
# Also add DataErasureRequest to the import line at the top of auth.py:
#   from models import db, User, ConsentAgreement, UserPrivacySetting, ActivityLog, DataErasureRequest
# ========================================

@auth_bp.route('/account/request-erasure', methods=['POST'])
def request_erasure():
    """
    Submit a right-to-erasure request (GDPR Article 17).
    The request is queued for admin review — not instant.
    Users are told upfront that clinical records may be retained
    by law regardless of the outcome.
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session['user_id']

    # Block duplicate pending requests
    existing = DataErasureRequest.query.filter_by(
        user_id=user_id,
        status='pending'
    ).first()
    if existing:
        return jsonify({
            'error': 'You already have a pending erasure request',
            'submitted_at': existing.requested_at.isoformat()
        }), 409

    data = request.get_json() or {}
    reason = data.get('reason', '').strip() or None  # Optional

    erasure_req = DataErasureRequest(
        user_id=user_id,
        reason=reason,
        status='pending'
    )
    db.session.add(erasure_req)

    log_activity(
        user_id,
        'erasure_request_submitted',
        'User submitted a data erasure request'
    )

    db.session.commit()

    return jsonify({
        'message': (
            'Your erasure request has been submitted and will be reviewed '
            'by our team within 30 days. Note: clinical records may be retained '
            'as required by applicable law even after erasure is approved.'
        ),
        'request_id': erasure_req.request_id,
        'submitted_at': erasure_req.requested_at.isoformat()
    }), 201


@auth_bp.route('/account/erasure-status', methods=['GET'])
def get_erasure_status():
    """
    Let a user check the status of their erasure request.
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    req = DataErasureRequest.query.filter_by(
        user_id=session['user_id']
    ).order_by(DataErasureRequest.requested_at.desc()).first()

    if not req:
        return jsonify({'request': None}), 200

    return jsonify({
        'request': {
            'request_id':   req.request_id,
            'status':       req.status,
            'submitted_at': req.requested_at.isoformat(),
            'reviewed_at':  req.reviewed_at.isoformat() if req.reviewed_at else None,
            'notes':        req.notes if req.status in ('rejected',) else None,
            # Don't expose admin notes on approved/completed — nothing useful to show
        }
    }), 200