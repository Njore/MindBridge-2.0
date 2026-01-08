"""
Enhanced Therapist Blueprint
Handles therapist-client connection functionality
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models import (db, User, ClientTherapistRelationship, Breakthrough, Trigger,
                    SessionNote, TherapeuticPrompt, PromptResponse, Notification,
                    RelationshipStatus, PromptFrequency, TriggerSentimentAnalysis, UserType)
from blueprints.auth import therapist_required, log_activity
from datetime import datetime, date
from sqlalchemy import desc, and_, or_

therapist_bp = Blueprint('therapist', __name__)


@therapist_bp.route('/dashboard')
@therapist_required
def dashboard():
    """Therapist dashboard"""
    user = User.query.get(session['user_id'])

    # Get active clients
    active_relationships = ClientTherapistRelationship.query.filter_by(
        therapist_id=user.user_id,
        status=RelationshipStatus.ACTIVE
    ).all()

    # Get recent client activity
    recent_breakthroughs = []
    recent_triggers = []
    crisis_alerts = []

    for rel in active_relationships:
        breakthroughs = Breakthrough.query.filter_by(
            relationship_id=rel.relationship_id,
            is_shared_with_therapist=True
        ).order_by(desc(Breakthrough.created_at)).limit(3).all()
        recent_breakthroughs.extend(breakthroughs)

        triggers = Trigger.query.filter_by(
            relationship_id=rel.relationship_id
        ).order_by(desc(Trigger.date_logged)).limit(3).all()
        recent_triggers.extend(triggers)

        for trigger in triggers:
            if trigger.sentiment_analysis and trigger.sentiment_analysis.crisis_flag:
                crisis_alerts.append(trigger)

    recent_breakthroughs.sort(key=lambda x: x.created_at, reverse=True)
    recent_triggers.sort(key=lambda x: x.date_logged, reverse=True)

    recent_breakthroughs = recent_breakthroughs[:10]
    recent_triggers = recent_triggers[:10]
    crisis_alerts = crisis_alerts[:5]

    unread_notifications = Notification.query.filter_by(
        user_id=user.user_id,
        is_read=False
    ).order_by(desc(Notification.created_at)).limit(5).all()

    return render_template('therapist/dashboard.html',
                           user=user,
                           active_relationships=active_relationships,
                           recent_breakthroughs=recent_breakthroughs,
                           recent_triggers=recent_triggers,
                           crisis_alerts=crisis_alerts,
                           unread_notifications=unread_notifications)


@therapist_bp.route('/clients')
@therapist_required
def clients():
    """View all clients"""
    user = User.query.get(session['user_id'])

    relationships = ClientTherapistRelationship.query.filter_by(
        therapist_id=user.user_id
    ).order_by(ClientTherapistRelationship.relationship_start_date.desc()).all()

    return render_template('therapist/clients.html',
                           user=user,
                           relationships=relationships)


@therapist_bp.route('/clients/search', methods=['GET', 'POST'])
@therapist_required
def search_clients():
    """Search for clients to connect with"""
    user = User.query.get(session['user_id'])

    search_results = []
    search_query = ''

    if request.method == 'POST':
        search_query = request.form.get('search_query', '').strip()

        if search_query:
            # Search for clients by name or email
            search_results = User.query.filter(
                User.user_type == UserType.CLIENT,
                User.is_active == True,
                or_(
                    User.first_name.ilike(f'%{search_query}%'),
                    User.last_name.ilike(f'%{search_query}%'),
                    User.email.ilike(f'%{search_query}%')
                )
            ).all()

            # Filter out clients already connected
            existing_client_ids = [
                r.client_id for r in ClientTherapistRelationship.query.filter_by(
                    therapist_id=user.user_id,
                    status=RelationshipStatus.ACTIVE
                ).all()
            ]

            search_results = [c for c in search_results if c.user_id not in existing_client_ids]

    return render_template('therapist/search_clients.html',
                           user=user,
                           search_results=search_results,
                           search_query=search_query)


@therapist_bp.route('/clients/<int:client_id>/connect', methods=['GET', 'POST'])
@therapist_required
def connect_client(client_id):
    """Connect with a new client"""
    user = User.query.get(session['user_id'])
    client = User.query.get_or_404(client_id)

    # Verify client is actually a client
    if client.user_type != UserType.CLIENT:
        flash('Invalid user type. Can only connect with clients.', 'danger')
        return redirect(url_for('therapist.search_clients'))

    # Check if relationship already exists
    existing = ClientTherapistRelationship.query.filter_by(
        therapist_id=user.user_id,
        client_id=client_id,
        status=RelationshipStatus.ACTIVE
    ).first()

    if existing:
        flash('An active relationship with this client already exists.', 'warning')
        return redirect(url_for('therapist.clients'))

    if request.method == 'POST':
        relationship_start = request.form.get('relationship_start_date', '')
        client_goals = request.form.get('client_goals', '').strip()
        therapist_notes = request.form.get('therapist_notes', '').strip()

        # Parse date or use today
        try:
            start_date = datetime.strptime(relationship_start, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            start_date = date.today()

        relationship = ClientTherapistRelationship(
            client_id=client_id,
            therapist_id=user.user_id,
            status=RelationshipStatus.ACTIVE,
            relationship_start_date=start_date,
            client_goals=client_goals,
            therapist_notes=therapist_notes
        )

        db.session.add(relationship)
        db.session.commit()

        log_activity(user.user_id, 'relationship_created', 'relationship',
                     relationship.relationship_id, f'New relationship with client {client.get_full_name()}')

        # Notify client
        notification = Notification(
            user_id=client_id,
            notification_type='new_relationship',
            title='New Therapist Connection',
            message=f'{user.get_full_name()} has established a therapeutic relationship with you.',
            related_entity_type='relationship',
            related_entity_id=relationship.relationship_id
        )
        db.session.add(notification)
        db.session.commit()

        flash(f'Successfully connected with {client.get_full_name()}!', 'success')
        return redirect(url_for('therapist.client_detail', client_id=client_id))

    # FIXED: Pass today's date to the template
    return render_template('therapist/connect_client.html',
                           user=user,
                           client=client,
                           today=date.today())


@therapist_bp.route('/clients/<int:client_id>')
@therapist_required
def client_detail(client_id):
    """View client details"""
    user = User.query.get(session['user_id'])

    relationship = ClientTherapistRelationship.query.filter_by(
        therapist_id=user.user_id,
        client_id=client_id
    ).first_or_404()

    client = User.query.get(client_id)

    breakthroughs = Breakthrough.query.filter_by(
        relationship_id=relationship.relationship_id,
        is_shared_with_therapist=True
    ).order_by(desc(Breakthrough.created_at)).all()

    triggers = Trigger.query.filter_by(
        relationship_id=relationship.relationship_id
    ).order_by(desc(Trigger.date_logged)).all()

    journal_entries = SessionNote.query.filter_by(
        relationship_id=relationship.relationship_id,
        is_shared_with_therapist=True
    ).order_by(desc(SessionNote.created_at)).all()

    prompts = TherapeuticPrompt.query.filter_by(
        relationship_id=relationship.relationship_id
    ).order_by(desc(TherapeuticPrompt.sent_date)).all()

    return render_template('therapist/client_detail.html',
                           user=user,
                           relationship=relationship,
                           client=client,
                           breakthroughs=breakthroughs,
                           triggers=triggers,
                           journal_entries=journal_entries,
                           prompts=prompts)


@therapist_bp.route('/clients/<int:client_id>/edit-relationship', methods=['GET', 'POST'])
@therapist_required
def edit_relationship(client_id):
    """Edit client relationship details"""
    user = User.query.get(session['user_id'])

    relationship = ClientTherapistRelationship.query.filter_by(
        therapist_id=user.user_id,
        client_id=client_id
    ).first_or_404()

    client = User.query.get(client_id)

    if request.method == 'POST':
        relationship.client_goals = request.form.get('client_goals', '').strip()
        relationship.therapist_notes = request.form.get('therapist_notes', '').strip()

        db.session.commit()

        log_activity(user.user_id, 'relationship_updated', 'relationship',
                     relationship.relationship_id, 'Updated relationship details')

        flash('Relationship details updated successfully!', 'success')
        return redirect(url_for('therapist.client_detail', client_id=client_id))

    return render_template('therapist/edit_relationship.html',
                           user=user,
                           relationship=relationship,
                           client=client)


@therapist_bp.route('/clients/<int:client_id>/end-relationship', methods=['POST'])
@therapist_required
def end_relationship(client_id):
    """End client relationship"""
    user = User.query.get(session['user_id'])

    relationship = ClientTherapistRelationship.query.filter_by(
        therapist_id=user.user_id,
        client_id=client_id,
        status=RelationshipStatus.ACTIVE
    ).first_or_404()

    relationship.status = RelationshipStatus.ENDED
    relationship.relationship_end_date = date.today()

    db.session.commit()

    log_activity(user.user_id, 'relationship_ended', 'relationship',
                 relationship.relationship_id, 'Ended therapeutic relationship')

    # Notify client
    notification = Notification(
        user_id=client_id,
        notification_type='relationship_ended',
        title='Therapeutic Relationship Ended',
        message=f'{user.get_full_name()} has concluded your therapeutic relationship.',
        related_entity_type='relationship',
        related_entity_id=relationship.relationship_id
    )
    db.session.add(notification)
    db.session.commit()

    flash('Relationship ended successfully.', 'info')
    return redirect(url_for('therapist.clients'))


@therapist_bp.route('/prompts/create', methods=['GET', 'POST'])
@therapist_required
def create_prompt():
    """Create a therapeutic prompt"""
    user = User.query.get(session['user_id'])

    relationships = ClientTherapistRelationship.query.filter_by(
        therapist_id=user.user_id,
        status=RelationshipStatus.ACTIVE
    ).all()

    if request.method == 'POST':
        relationship_id = request.form.get('relationship_id', type=int)
        prompt_type = request.form.get('prompt_type', '').strip()
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        prompt_content = request.form.get('prompt_content', '').strip()
        instructions = request.form.get('instructions', '').strip()
        expected_duration = request.form.get('expected_duration_minutes', type=int)
        frequency = request.form.get('frequency', 'once')
        deadline_date_str = request.form.get('deadline_date', '')

        if not all([relationship_id, prompt_type, title, prompt_content]):
            flash('All required fields must be filled.', 'danger')
            return render_template('therapist/create_prompt.html',
                                   user=user,
                                   relationships=relationships,
                                   today=date.today())

        deadline_date = None
        if deadline_date_str:
            try:
                deadline_date = datetime.strptime(deadline_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        prompt = TherapeuticPrompt(
            therapist_id=user.user_id,
            relationship_id=relationship_id,
            prompt_type=prompt_type,
            title=title,
            description=description,
            prompt_content=prompt_content,
            instructions=instructions,
            expected_duration_minutes=expected_duration,
            frequency=PromptFrequency(frequency),
            deadline_date=deadline_date
        )

        db.session.add(prompt)
        db.session.commit()

        log_activity(user.user_id, 'prompt_created', 'prompt',
                     prompt.prompt_id, f'Created prompt: {title}')

        relationship = ClientTherapistRelationship.query.get(relationship_id)
        notification = Notification(
            user_id=relationship.client_id,
            notification_type='new_prompt',
            title='New Therapeutic Prompt',
            message=f'Your therapist sent you a new prompt: {title}',
            related_entity_type='prompt',
            related_entity_id=prompt.prompt_id
        )
        db.session.add(notification)
        db.session.commit()

        flash('Prompt created and sent to client!', 'success')
        return redirect(url_for('therapist.dashboard'))

    return render_template('therapist/create_prompt.html',
                           user=user,
                           relationships=relationships,
                           today=date.today())


@therapist_bp.route('/breakthroughs/<int:breakthrough_id>/respond', methods=['POST'])
@therapist_required
def respond_to_breakthrough(breakthrough_id):
    """Respond to a client's breakthrough"""
    user = User.query.get(session['user_id'])
    breakthrough = Breakthrough.query.get_or_404(breakthrough_id)

    relationship = ClientTherapistRelationship.query.filter_by(
        relationship_id=breakthrough.relationship_id,
        therapist_id=user.user_id
    ).first_or_404()

    response = request.form.get('response', '').strip()

    if response:
        breakthrough.therapist_response = response
        breakthrough.therapist_response_date = datetime.utcnow()
        db.session.commit()

        log_activity(user.user_id, 'breakthrough_responded', 'breakthrough',
                     breakthrough_id, 'Responded to client breakthrough')

        notification = Notification(
            user_id=breakthrough.client_id,
            notification_type='therapist_response',
            title='Therapist Response to Breakthrough',
            message=f'Your therapist responded to your breakthrough: {breakthrough.title}',
            related_entity_type='breakthrough',
            related_entity_id=breakthrough_id
        )
        db.session.add(notification)
        db.session.commit()

        flash('Response sent to client!', 'success')

    return redirect(url_for('therapist.client_detail', client_id=breakthrough.client_id))


@therapist_bp.route('/triggers/<int:trigger_id>')
@therapist_required
def view_trigger(trigger_id):
    """View trigger details with sentiment analysis"""
    user = User.query.get(session['user_id'])
    trigger = Trigger.query.get_or_404(trigger_id)

    relationship = ClientTherapistRelationship.query.filter_by(
        relationship_id=trigger.relationship_id,
        therapist_id=user.user_id
    ).first_or_404()

    client = User.query.get(trigger.client_id)

    return render_template('therapist/view_trigger.html',
                           user=user,
                           trigger=trigger,
                           client=client,
                           sentiment=trigger.sentiment_analysis)


@therapist_bp.route('/journal/<int:note_id>/review', methods=['POST'])
@therapist_required
def review_journal_entry(note_id):
    """Review and provide feedback on journal entry"""
    user = User.query.get(session['user_id'])
    note = SessionNote.query.get_or_404(note_id)

    relationship = ClientTherapistRelationship.query.filter_by(
        relationship_id=note.relationship_id,
        therapist_id=user.user_id
    ).first_or_404()

    feedback = request.form.get('feedback', '').strip()

    if feedback:
        note.therapist_feedback = feedback
        note.therapist_has_reviewed = True
        note.therapist_review_date = datetime.utcnow()
        db.session.commit()

        log_activity(user.user_id, 'journal_reviewed', 'session_note',
                     note_id, 'Reviewed journal entry')

        notification = Notification(
            user_id=note.client_id,
            notification_type='journal_feedback',
            title='Therapist Reviewed Your Journal',
            message='Your therapist provided feedback on your journal entry',
            related_entity_type='session_note',
            related_entity_id=note_id
        )
        db.session.add(notification)
        db.session.commit()

        flash('Feedback provided to client!', 'success')

    return redirect(url_for('therapist.client_detail', client_id=note.client_id))


@therapist_bp.route('/prompts/<int:prompt_id>/responses')
@therapist_required
def view_prompt_responses(prompt_id):
    """View responses to a therapeutic prompt"""
    user = User.query.get(session['user_id'])
    prompt = TherapeuticPrompt.query.get_or_404(prompt_id)

    if prompt.therapist_id != user.user_id:
        flash('Access denied.', 'danger')
        return redirect(url_for('therapist.dashboard'))

    responses = PromptResponse.query.filter_by(
        prompt_id=prompt_id,
        is_shared_with_therapist=True
    ).all()

    return render_template('therapist/view_prompt_responses.html',
                           user=user,
                           prompt=prompt,
                           responses=responses)