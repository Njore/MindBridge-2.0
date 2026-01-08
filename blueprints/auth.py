"""
Authentication Blueprint
Handles user registration, login, and logout
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models import db, User, UserType, ActivityLog, UserPrivacySetting
from functools import wraps
from datetime import datetime

auth_bp = Blueprint('auth', __name__)


def login_required(f):
    """Decorator to require login"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)

    return decorated_function


def client_required(f):
    """Decorator to require client role"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))

        user = User.query.get(session['user_id'])
        if not user or user.user_type != UserType.CLIENT:
            flash('Access denied. Client access only.', 'danger')
            return redirect(url_for('index'))

        return f(*args, **kwargs)

    return decorated_function


def therapist_required(f):
    """Decorator to require therapist role"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))

        user = User.query.get(session['user_id'])
        if not user or user.user_type != UserType.THERAPIST:
            flash('Access denied. Therapist access only.', 'danger')
            return redirect(url_for('index'))

        return f(*args, **kwargs)

    return decorated_function


def log_activity(user_id, action_type, resource_type=None, resource_id=None, description=None):
    """Helper function to log user activity"""
    log = ActivityLog(
        user_id=user_id,
        action_type=action_type,
        resource_type=resource_type,
        resource_id=resource_id,
        description=description,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
    )
    db.session.add(log)
    db.session.commit()


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        user_type = request.form.get('user_type', '')
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        phone = request.form.get('phone', '').strip()

        # Validation
        if not all([email, password, user_type, first_name, last_name]):
            flash('All required fields must be filled.', 'danger')
            return render_template('auth/register.html')

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/register.html')

        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'danger')
            return render_template('auth/register.html')

        if user_type not in ['client', 'therapist']:
            flash('Invalid user type.', 'danger')
            return render_template('auth/register.html')

        # Check if user exists
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return render_template('auth/register.html')

        # Create user
        user = User(
            email=email,
            user_type=UserType(user_type),
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            is_active=True,
            is_verified=False
        )
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        # Create default privacy settings
        privacy_settings = UserPrivacySetting(user_id=user.user_id)
        db.session.add(privacy_settings)
        db.session.commit()

        # Log activity
        log_activity(user.user_id, 'user_registered', 'user', user.user_id, 'New user registration')

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)

        if not email or not password:
            flash('Email and password are required.', 'danger')
            return render_template('auth/login.html')

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            if not user.is_active:
                flash('Your account has been deactivated. Please contact support.', 'danger')
                return render_template('auth/login.html')

            # Set session
            session.permanent = bool(remember)
            session['user_id'] = user.user_id
            session['user_type'] = user.user_type.value
            session['user_name'] = user.get_full_name()

            # Log activity
            log_activity(user.user_id, 'user_login', 'user', user.user_id, 'User logged in')

            flash(f'Welcome back, {user.first_name}!', 'success')

            # Redirect based on user type
            if user.user_type == UserType.CLIENT:
                return redirect(url_for('client.dashboard'))
            elif user.user_type == UserType.THERAPIST:
                return redirect(url_for('therapist.dashboard'))
        else:
            flash('Invalid email or password.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """User logout"""
    user_id = session.get('user_id')

    if user_id:
        log_activity(user_id, 'user_logout', 'user', user_id, 'User logged out')

    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('index'))


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """User profile management"""
    user = User.query.get(session['user_id'])

    if request.method == 'POST':
        user.first_name = request.form.get('first_name', '').strip()
        user.last_name = request.form.get('last_name', '').strip()
        user.phone = request.form.get('phone', '').strip()
        user.bio = request.form.get('bio', '').strip()

        # Update password if provided
        new_password = request.form.get('new_password', '')
        if new_password:
            current_password = request.form.get('current_password', '')
            if not user.check_password(current_password):
                flash('Current password is incorrect.', 'danger')
                return render_template('auth/profile.html', user=user)

            if len(new_password) < 8:
                flash('New password must be at least 8 characters long.', 'danger')
                return render_template('auth/profile.html', user=user)

            user.set_password(new_password)

        db.session.commit()
        log_activity(user.user_id, 'profile_updated', 'user', user.user_id, 'Profile information updated')

        flash('Profile updated successfully!', 'success')
        return redirect(url_for('auth.profile'))

    return render_template('auth/profile.html', user=user)