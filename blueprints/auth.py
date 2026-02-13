from flask import Blueprint, request, jsonify, session
from models import db, User, ConsentAgreement, UserPrivacySetting, ActivityLog
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


@auth_bp.route('/register', methods=['POST'])
def register():
    """
    Register new user with explicit consent
    PRD: 1.1 Explicit User Consent
    """
    data = request.get_json()

    # Validate required fields
    required = ['email', 'password', 'user_type', 'first_name', 'last_name']
    if not all(field in data for field in required):
        return jsonify({'error': 'Missing required fields'}), 400

    # Validate consent (PRD 1.1 - No pre-checked boxes)
    if not data.get('consent_terms') or not data.get('consent_privacy'):
        return jsonify({'error': 'Explicit consent required for Terms of Service and Privacy Policy'}), 400

    if data.get('user_type') not in ['client', 'therapist']:
        return jsonify({'error': 'Invalid user_type'}), 400

    # Validate email
    email = data['email'].lower().strip()
    if not validate_email(email):
        return jsonify({'error': 'Invalid email format'}), 400

    # Check if email exists
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already registered'}), 409

    # Validate password strength
    password = data['password']
    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400

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

        return jsonify({
            'message': 'Registration successful',
            'user_id': user.user_id,
            'email': user.email,
            'user_type': user.user_type
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Registration failed: {str(e)}'}), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    """User login with session management"""
    data = request.get_json()

    if not data.get('email') or not data.get('password'):
        return jsonify({'error': 'Email and password required'}), 400

    email = data['email'].lower().strip()
    user = User.query.filter_by(email=email).first()

    if not user or not verify_password(data['password'], user.password_hash):
        return jsonify({'error': 'Invalid credentials'}), 401

    if not user.is_active:
        return jsonify({'error': 'Account deactivated'}), 403

    # Create session (PRD 2.2 - Secure session management)
    session['user_id'] = user.user_id
    session['user_type'] = user.user_type
    session['email'] = user.email

    # Log login
    log_activity(user.user_id, 'login', 'User logged in')

    return jsonify({
        'message': 'Login successful',
        'user': {
            'user_id': user.user_id,
            'email': user.email,
            'user_type': user.user_type,
            'first_name': user.first_name,
            'last_name': user.last_name
        }
    }), 200


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