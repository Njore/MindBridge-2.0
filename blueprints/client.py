from flask import Blueprint, request, jsonify, session, send_file, render_template, redirect
from models import (db, User, PrivatePocket, ConsentAgreement, UserPrivacySetting,
                    ActivityLog, Capsule, Message, CrisisEvent, PromptResponse,
                    TherapeuticPrompt, ClientTherapistRelationship, Notification)
from datetime import datetime, date, timedelta
from cryptography.fernet import Fernet
import os
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.units import inch

client_bp = Blueprint('client', __name__)

# Encryption for Private Pockets (PRD 2.2 - Encryption)
ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY')
if ENCRYPTION_KEY:
    cipher_suite = Fernet(ENCRYPTION_KEY.encode())
else:
    # Generate a key if not in .env (development only)
    cipher_suite = Fernet(Fernet.generate_key())


def encrypt_content(content):
    """Encrypt private pocket content"""
    return cipher_suite.encrypt(content.encode()).decode()


def decrypt_content(encrypted_content):
    """Decrypt private pocket content"""
    return cipher_suite.decrypt(encrypted_content.encode()).decode()


def require_client():
    """Decorator to require client user type"""

    def decorator(f):
        def wrapper(*args, **kwargs):
            if 'user_id' not in session:
                return jsonify({'error': 'Unauthorized'}), 401
            if session.get('user_type') != 'client':
                return jsonify({'error': 'Client access only'}), 403
            return f(*args, **kwargs)

        wrapper.__name__ = f.__name__
        return wrapper

    return decorator


# ========================================
# TEMPLATE ROUTES (GET)
# ========================================

@client_bp.route('/dashboard', methods=['GET'])
def dashboard():
    """Show client dashboard"""
    if 'user_id' not in session or session.get('user_type') != 'client':
        return redirect('/auth/login')
    return render_template('client/dashboard.html')


@client_bp.route('/journal', methods=['GET'])
def journal():
    """Show 7 Pockets journal"""
    if 'user_id' not in session:
        return redirect('/auth/login')
    return render_template('client/journal.html')


@client_bp.route('/prompts', methods=['GET'])
def prompts():
    """Show therapeutic prompts"""
    if 'user_id' not in session:
        return redirect('/auth/login')
    return render_template('client/prompts.html')


@client_bp.route('/create-capsule', methods=['GET'])
def create_capsule_page():
    """Show create capsule page"""
    if 'user_id' not in session:
        return redirect('/auth/login')
    return render_template('messaging/create_capsule.html')


# ========================================
# PRIVATE POCKETS (7 Pockets)
# ========================================

@client_bp.route('/pockets', methods=['POST'])
@require_client()
def create_pocket():
    """
    Create/update a private pocket entry
    PRD: Encrypted personal space - NEVER shared
    """
    user_id = session['user_id']
    data = request.get_json()

    # Validate pocket_number (1-7)
    pocket_number = data.get('pocket_number')
    if not pocket_number or pocket_number not in range(1, 8):
        return jsonify({'error': 'pocket_number must be between 1 and 7'}), 400

    content = data.get('content', '').strip()
    if not content:
        return jsonify({'error': 'Content cannot be empty'}), 400

    # Use today's date if not provided
    pocket_date = data.get('date', date.today().isoformat())

    try:
        # Check if pocket exists for this date
        existing = PrivatePocket.query.filter_by(
            client_id=user_id,
            date=pocket_date,
            pocket_number=pocket_number
        ).first()

        # Encrypt content (PRD 2.2)
        encrypted_content = encrypt_content(content)

        if existing:
            existing.content = encrypted_content
            existing.updated_at = datetime.utcnow()
        else:
            pocket = PrivatePocket(
                client_id=user_id,
                date=pocket_date,
                pocket_number=pocket_number,
                content=encrypted_content
            )
            db.session.add(pocket)

        db.session.commit()

        return jsonify({
            'message': 'Pocket saved successfully',
            'pocket_number': pocket_number,
            'date': pocket_date
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to save pocket: {str(e)}'}), 500


@client_bp.route('/pockets/<pocket_date>', methods=['GET'])
@require_client()
def get_pockets_by_date(pocket_date):
    """
    Get all pockets for a specific date
    PRD 1.2: User Data Access - Users can view their data
    """
    user_id = session['user_id']

    pockets = PrivatePocket.query.filter_by(
        client_id=user_id,
        date=pocket_date
    ).order_by(PrivatePocket.pocket_number).all()

    return jsonify({
        'date': pocket_date,
        'pockets': [{
            'pocket_number': p.pocket_number,
            'content': decrypt_content(p.content),
            'created_at': p.created_at.isoformat(),
            'updated_at': p.updated_at.isoformat()
        } for p in pockets]
    }), 200


@client_bp.route('/pockets/week', methods=['GET'])
@require_client()
def get_week_pockets():
    """Get all pockets for the current week"""
    user_id = session['user_id']

    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    pockets = PrivatePocket.query.filter(
        PrivatePocket.client_id == user_id,
        PrivatePocket.date >= start_of_week,
        PrivatePocket.date <= end_of_week
    ).order_by(PrivatePocket.date, PrivatePocket.pocket_number).all()

    return jsonify({
        'week_start': start_of_week.isoformat(),
        'week_end': end_of_week.isoformat(),
        'pockets': [{
            'date': p.date.isoformat(),
            'pocket_number': p.pocket_number,
            'content': decrypt_content(p.content),
            'updated_at': p.updated_at.isoformat()
        } for p in pockets]
    }), 200


# ========================================
# DATA EXPORT (PDF)
# PRD 1.3: Data Portability
# ========================================

@client_bp.route('/export/pockets', methods=['POST'])
@require_client()
def export_pockets_pdf():
    """
    Export 7 Pockets data as PDF
    PRD 1.3: Data Export (Portability)
    - Manual trigger
    - Generated on demand
    - Not permanently stored
    - Logged for audit
    """
    user_id = session['user_id']
    data = request.get_json()

    start_date = data.get('start_date')
    end_date = data.get('end_date', date.today().isoformat())

    if not start_date:
        start_date = (date.today() - timedelta(days=30)).isoformat()

    pockets = PrivatePocket.query.filter(
        PrivatePocket.client_id == user_id,
        PrivatePocket.date >= start_date,
        PrivatePocket.date <= end_date
    ).order_by(PrivatePocket.date, PrivatePocket.pocket_number).all()

    if not pockets:
        return jsonify({'error': 'No data found for the specified date range'}), 404

    user = User.query.get(user_id)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    story = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30
    )

    date_style = ParagraphStyle(
        'DateStyle',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=10
    )

    story.append(Paragraph("MindBridge - 7 Pockets Export", title_style))
    story.append(Paragraph(f"User: {user.first_name} {user.last_name}", styles['Normal']))
    story.append(Paragraph(f"Export Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", styles['Normal']))
    story.append(Paragraph(f"Period: {start_date} to {end_date}", styles['Normal']))
    story.append(Spacer(1, 0.5 * inch))

    current_date = None
    for pocket in pockets:
        if current_date != pocket.date:
            if current_date is not None:
                story.append(Spacer(1, 0.3 * inch))
            current_date = pocket.date
            story.append(Paragraph(f"Date: {pocket.date.strftime('%A, %B %d, %Y')}", date_style))

        content = decrypt_content(pocket.content)
        story.append(Paragraph(f"<b>Pocket {pocket.pocket_number}:</b>", styles['Normal']))
        story.append(Paragraph(content, styles['BodyText']))
        story.append(Spacer(1, 0.2 * inch))

    doc.build(story)
    buffer.seek(0)

    log = ActivityLog(
        user_id=user_id,
        action_type='data_export',
        resource_type='private_pockets',
        description=f'Exported pockets from {start_date} to {end_date}',
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent', '')[:500]
    )
    db.session.add(log)
    db.session.commit()

    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'mindbridge_pockets_{start_date}_to_{end_date}.pdf'
    )


# ========================================
# ACCOUNT DELETION
# PRD 1.4: Right to Erasure
# ========================================

@client_bp.route('/account/delete', methods=['DELETE'])
@require_client()
def delete_account():
    """
    Delete user account and all associated data
    PRD 1.4: Account Deletion (Right to Erasure)
    """
    user_id = session['user_id']
    data = request.get_json()

    if not data.get('password'):
        return jsonify({'error': 'Password confirmation required'}), 400

    user = User.query.get(user_id)

    from blueprints.auth import verify_password

    if not verify_password(data['password'], user.password_hash):
        return jsonify({'error': 'Invalid password'}), 401

    try:
        log = ActivityLog(
            user_id=user_id,
            action_type='account_deletion',
            description='User initiated account deletion',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', '')[:500]
        )
        db.session.add(log)
        db.session.commit()

        db.session.delete(user)
        db.session.commit()

        session.clear()

        return jsonify({
            'message': 'Account deleted successfully',
            'note': 'All personal data has been permanently removed'
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Account deletion failed: {str(e)}'}), 500


# ========================================
# PRIVACY SETTINGS
# PRD 2.3: Data Minimization & 2.4: Data Retention
# ========================================

@client_bp.route('/privacy/settings', methods=['GET'])
@require_client()
def get_privacy_settings():
    """Get current privacy settings"""
    user_id = session['user_id']

    settings = UserPrivacySetting.query.filter_by(user_id=user_id).first()

    if not settings:
        return jsonify({'error': 'Privacy settings not found'}), 404

    return jsonify({
        'allow_data_analytics': settings.allow_data_analytics,
        'allow_session_recordings': settings.allow_session_recordings,
        'share_progress_with_therapist': settings.share_progress_with_therapist,
        'encrypted_storage_preference': settings.encrypted_storage_preference,
        'data_retention_days': settings.data_retention_days,
        'last_updated': settings.last_updated.isoformat()
    }), 200


@client_bp.route('/privacy/settings', methods=['PUT'])
@require_client()
def update_privacy_settings():
    """Update privacy settings — PRD 2.3: Data Minimization"""
    user_id = session['user_id']
    data = request.get_json()

    settings = UserPrivacySetting.query.filter_by(user_id=user_id).first()

    if not settings:
        return jsonify({'error': 'Privacy settings not found'}), 404

    if 'allow_data_analytics' in data:
        settings.allow_data_analytics = data['allow_data_analytics']
    if 'allow_session_recordings' in data:
        settings.allow_session_recordings = data['allow_session_recordings']
    if 'share_progress_with_therapist' in data:
        settings.share_progress_with_therapist = data['share_progress_with_therapist']
    if 'data_retention_days' in data:
        retention = data['data_retention_days']
        if retention < 30 or retention > 3650:
            return jsonify({'error': 'Retention days must be between 30 and 3650'}), 400
        settings.data_retention_days = retention

    settings.last_updated = datetime.utcnow()
    db.session.commit()

    log = ActivityLog(
        user_id=user_id,
        action_type='privacy_update',
        description='Privacy settings updated',
        ip_address=request.remote_addr
    )
    db.session.add(log)
    db.session.commit()

    return jsonify({'message': 'Privacy settings updated successfully'}), 200


# ========================================
# DASHBOARD API
# ========================================

@client_bp.route('/api/dashboard', methods=['GET'])
@require_client()
def get_dashboard():
    """Get client dashboard overview stats"""
    user_id = session['user_id']

    recent_pockets = PrivatePocket.query.filter(
        PrivatePocket.client_id == user_id,
        PrivatePocket.date >= date.today() - timedelta(days=7)
    ).count()

    recent_capsules = Capsule.query.filter(
        Capsule.client_id == user_id,
        Capsule.created_at >= datetime.utcnow() - timedelta(days=7)
    ).count()

    crisis_count = CrisisEvent.query.filter(
        CrisisEvent.client_id == user_id,
        CrisisEvent.created_at >= datetime.utcnow() - timedelta(days=30)
    ).count()

    return jsonify({
        'recent_pockets': recent_pockets,
        'recent_capsules': recent_capsules,
        'crisis_events_30d': crisis_count
    }), 200


# ========================================
# THERAPIST CONNECTION
# ========================================

@client_bp.route('/api/my-therapist', methods=['GET'])
@require_client()
def get_my_therapist():
    """Get the client's connected therapist and relationship details"""
    user_id = session['user_id']

    relationship = ClientTherapistRelationship.query.filter_by(
        client_id=user_id,
        status='active'
    ).first()

    if not relationship:
        return jsonify({'therapist': None}), 200

    therapist = User.query.get(relationship.therapist_id)

    return jsonify({
        'therapist': {
            'user_id':    therapist.user_id,
            'first_name': therapist.first_name,
            'last_name':  therapist.last_name,
            'email':      therapist.email,
            'bio':        therapist.bio,
        },
        'relationship': {
            'relationship_id':         relationship.relationship_id,
            'relationship_start_date': relationship.relationship_start_date.isoformat(),
            'client_goals':            relationship.client_goals,
        }
    }), 200


# ========================================
# THERAPEUTIC PROMPTS
# ========================================

@client_bp.route('/api/prompts', methods=['GET'])
@require_client()
def get_my_prompts():
    """Get all active prompts assigned to this client by their therapist"""
    user_id = session['user_id']

    relationship = ClientTherapistRelationship.query.filter_by(
        client_id=user_id,
        status='active'
    ).first()

    if not relationship:
        return jsonify({'prompts': []}), 200

    prompts = TherapeuticPrompt.query.filter_by(
        relationship_id=relationship.relationship_id,
        is_active=True
    ).order_by(TherapeuticPrompt.created_at.desc()).all()

    # Find which prompts the client has already responded to
    responded_ids = {
        r.prompt_id for r in PromptResponse.query.filter_by(client_id=user_id).all()
    }

    return jsonify({
        'prompts': [{
            'prompt_id':                 p.prompt_id,
            'prompt_type':               p.prompt_type,
            'title':                     p.title,
            'description':               p.description,
            'prompt_content':            p.prompt_content,
            'instructions':              p.instructions,
            'expected_duration_minutes': p.expected_duration_minutes,
            'created_at':                p.created_at.isoformat(),
            'already_responded':         p.prompt_id in responded_ids,
        } for p in prompts]
    }), 200


@client_bp.route('/api/prompts/<int:prompt_id>/respond', methods=['POST'])
@require_client()
def respond_to_prompt(prompt_id):
    """Submit a response to a therapeutic prompt"""
    user_id = session['user_id']
    data = request.get_json()

    relationship = ClientTherapistRelationship.query.filter_by(
        client_id=user_id,
        status='active'
    ).first()

    if not relationship:
        return jsonify({'error': 'No active therapist relationship'}), 404

    prompt = TherapeuticPrompt.query.filter_by(
        prompt_id=prompt_id,
        relationship_id=relationship.relationship_id
    ).first()

    if not prompt:
        return jsonify({'error': 'Prompt not found'}), 404

    if not data.get('response_content'):
        return jsonify({'error': 'response_content is required'}), 400

    try:
        response = PromptResponse(
            prompt_id=prompt_id,
            client_id=user_id,
            relationship_id=relationship.relationship_id,
            response_content=data['response_content'],
            insights_gained=data.get('insights_gained', ''),
            emotional_state=data.get('emotional_state', ''),
            response_date=date.today(),
            is_shared_with_therapist=data.get('share_with_therapist', True)
        )
        db.session.add(response)

        # Notify therapist
        notification = Notification(
            user_id=relationship.therapist_id,
            notification_type='prompt_response',
            title='Client Responded to Prompt',
            message=f'Your client responded to: {prompt.title}',
            related_entity_type='prompt',
            related_entity_id=prompt_id
        )
        db.session.add(notification)
        db.session.commit()

        return jsonify({'message': 'Response submitted successfully'}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to submit response: {str(e)}'}), 500