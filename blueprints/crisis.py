"""
Crisis Management Blueprint
Handles crisis resources, de-escalation techniques, and crisis events
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from models import (db, User, CrisisDirectory, DeescalationTechnique, CrisisEvent,
                    ClientDeescalationHistory, ClientTherapistRelationship, Notification,
                    CrisisType, CrisisStatus, TechniqueCategory, RelationshipStatus)
from blueprints.auth import login_required, client_required, log_activity
from datetime import datetime
from sqlalchemy import desc

crisis_bp = Blueprint('crisis', __name__)


@crisis_bp.route('/')
@login_required
def index():
    """Crisis support landing page"""
    user = User.query.get(session['user_id'])

    # Get crisis resources
    resources = CrisisDirectory.query.filter_by(is_active=True).all()

    # Get de-escalation techniques
    techniques = DeescalationTechnique.query.filter_by(is_active=True).order_by(
        DeescalationTechnique.difficulty_level,
        DeescalationTechnique.technique_category
    ).all()

    # Group techniques by category
    techniques_by_category = {}
    for technique in techniques:
        category = technique.technique_category.value
        if category not in techniques_by_category:
            techniques_by_category[category] = []
        techniques_by_category[category].append(technique)

    return render_template('crisis/index.html',
                           user=user,
                           resources=resources,
                           techniques_by_category=techniques_by_category)


@crisis_bp.route('/resources')
@login_required
def resources():
    """View crisis resources directory"""
    user = User.query.get(session['user_id'])

    resources = CrisisDirectory.query.filter_by(is_active=True).order_by(
        CrisisDirectory.resource_type,
        CrisisDirectory.resource_name
    ).all()

    # Group by resource type
    resources_by_type = {}
    for resource in resources:
        resource_type = resource.resource_type
        if resource_type not in resources_by_type:
            resources_by_type[resource_type] = []
        resources_by_type[resource_type].append(resource)

    return render_template('crisis/resources.html',
                           user=user,
                           resources_by_type=resources_by_type)


@crisis_bp.route('/techniques')
@login_required
def techniques():
    """View de-escalation techniques"""
    user = User.query.get(session['user_id'])

    category = request.args.get('category', '')
    difficulty = request.args.get('difficulty', '')

    query = DeescalationTechnique.query.filter_by(is_active=True)

    if category:
        query = query.filter_by(technique_category=TechniqueCategory(category))

    if difficulty:
        query = query.filter_by(difficulty_level=difficulty)

    techniques = query.order_by(DeescalationTechnique.technique_name).all()

    return render_template('crisis/techniques.html',
                           user=user,
                           techniques=techniques,
                           selected_category=category,
                           selected_difficulty=difficulty)


@crisis_bp.route('/techniques/<int:technique_id>')
@login_required
def technique_detail(technique_id):
    """View technique details"""
    user = User.query.get(session['user_id'])
    technique = DeescalationTechnique.query.get_or_404(technique_id)

    # Get user's usage history for this technique
    usage_history = None
    if session.get('user_type') == 'client':
        usage_history = ClientDeescalationHistory.query.filter_by(
            client_id=user.user_id,
            technique_id=technique_id
        ).order_by(desc(ClientDeescalationHistory.usage_date)).limit(10).all()

    return render_template('crisis/technique_detail.html',
                           user=user,
                           technique=technique,
                           usage_history=usage_history)


@crisis_bp.route('/techniques/<int:technique_id>/use', methods=['POST'])
@client_required
def log_technique_usage(technique_id):
    """Log usage of a de-escalation technique"""
    user = User.query.get(session['user_id'])
    technique = DeescalationTechnique.query.get_or_404(technique_id)

    effectiveness_rating = request.form.get('effectiveness_rating', type=int)
    duration_used = request.form.get('duration_used_minutes', type=int)
    notes = request.form.get('notes', '').strip()
    crisis_id = request.form.get('crisis_id', type=int)

    history = ClientDeescalationHistory(
        client_id=user.user_id,
        crisis_id=crisis_id,
        technique_id=technique_id,
        effectiveness_rating=effectiveness_rating,
        duration_used_minutes=duration_used,
        notes=notes
    )

    db.session.add(history)
    db.session.commit()

    log_activity(user.user_id, 'technique_used', 'deescalation_technique',
                 technique_id, f'Used technique: {technique.technique_name}')

    flash('Technique usage logged. Thank you for tracking your progress!', 'success')
    return redirect(url_for('crisis.technique_detail', technique_id=technique_id))


@crisis_bp.route('/log-event', methods=['GET', 'POST'])
@client_required
def log_crisis_event():
    """Log a crisis event"""
    user = User.query.get(session['user_id'])

    # Get active relationship
    relationship = ClientTherapistRelationship.query.filter_by(
        client_id=user.user_id,
        status=RelationshipStatus.ACTIVE
    ).first()

    if not relationship:
        flash('You need an active therapist relationship to log crisis events.', 'warning')
        return redirect(url_for('crisis.index'))

    if request.method == 'POST':
        crisis_type = request.form.get('crisis_type')
        severity_level = request.form.get('severity_level', type=int)
        description = request.form.get('description', '').strip()
        immediate_action = request.form.get('immediate_action', '').strip()
        notify_therapist = request.form.get('notify_therapist', False)

        if not crisis_type or not description:
            flash('Crisis type and description are required.', 'danger')
            return render_template('crisis/log_event.html', user=user)

        crisis = CrisisEvent(
            client_id=user.user_id,
            relationship_id=relationship.relationship_id,
            crisis_type=CrisisType(crisis_type),
            severity_level=severity_level,
            description=description,
            immediate_action_taken=immediate_action,
            therapist_notified=bool(notify_therapist),
            status=CrisisStatus.LOGGED
        )

        if bool(notify_therapist):
            crisis.therapist_notification_date = datetime.utcnow()

        db.session.add(crisis)
        db.session.commit()

        log_activity(user.user_id, 'crisis_event_logged', 'crisis_event',
                     crisis.crisis_id, f'Crisis event: {crisis_type}')

        # Notify therapist if requested or if high severity
        if bool(notify_therapist) or severity_level >= 8:
            crisis.notify_therapist()
            db.session.commit()

            notification = Notification(
                user_id=relationship.therapist_id,
                notification_type='crisis_event',
                title='URGENT: Crisis Event',
                message=f'{user.get_full_name()} logged a crisis event (severity: {severity_level}/10). Immediate attention needed.',
                related_entity_type='crisis_event',
                related_entity_id=crisis.crisis_id
            )
            db.session.add(notification)
            db.session.commit()

        flash('Crisis event logged. Please seek immediate help if needed.', 'warning')
        return redirect(url_for('crisis.my_events'))

    return render_template('crisis/log_event.html', user=user)


@crisis_bp.route('/my-events')
@client_required
def my_events():
    """View client's crisis events"""
    user = User.query.get(session['user_id'])

    events = CrisisEvent.query.filter_by(
        client_id=user.user_id
    ).order_by(desc(CrisisEvent.created_at)).all()

    return render_template('crisis/my_events.html',
                           user=user,
                           events=events)


@crisis_bp.route('/events/<int:crisis_id>')
@login_required
def event_detail(crisis_id):
    """View crisis event details"""
    user = User.query.get(session['user_id'])
    crisis = CrisisEvent.query.get_or_404(crisis_id)

    # Verify access
    can_view = False
    if session.get('user_type') == 'client' and crisis.client_id == user.user_id:
        can_view = True
    elif session.get('user_type') == 'therapist':
        relationship = ClientTherapistRelationship.query.filter_by(
            relationship_id=crisis.relationship_id,
            therapist_id=user.user_id
        ).first()
        if relationship:
            can_view = True

    if not can_view:
        flash('Access denied.', 'danger')
        return redirect(url_for('crisis.index'))

    # Get de-escalation techniques used during this crisis
    techniques_used = ClientDeescalationHistory.query.filter_by(
        crisis_id=crisis_id
    ).all()

    return render_template('crisis/event_detail.html',
                           user=user,
                           crisis=crisis,
                           techniques_used=techniques_used)


@crisis_bp.route('/events/<int:crisis_id>/update-status', methods=['POST'])
@client_required
def update_crisis_status(crisis_id):
    """Update crisis event status"""
    user = User.query.get(session['user_id'])
    crisis = CrisisEvent.query.get_or_404(crisis_id)

    if crisis.client_id != user.user_id:
        flash('Access denied.', 'danger')
        return redirect(url_for('crisis.my_events'))

    new_status = request.form.get('status')
    resolution_notes = request.form.get('resolution_notes', '').strip()

    if new_status:
        crisis.status = CrisisStatus(new_status)
        if resolution_notes:
            crisis.resolution_notes = resolution_notes

        db.session.commit()

        log_activity(user.user_id, 'crisis_status_updated', 'crisis_event',
                     crisis_id, f'Status updated to: {new_status}')

        flash('Crisis event status updated.', 'success')

    return redirect(url_for('crisis.event_detail', crisis_id=crisis_id))


@crisis_bp.route('/api/emergency-contacts')
@login_required
def emergency_contacts():
    """API endpoint for emergency contacts"""
    resources = CrisisDirectory.query.filter_by(
        is_active=True,
        available_24_7=True
    ).all()

    contacts = []
    for resource in resources:
        contacts.append({
            'name': resource.resource_name,
            'type': resource.resource_type,
            'phone': resource.phone_number,
            'text': resource.text_number,
            'website': resource.website_url
        })

    return jsonify({'contacts': contacts})