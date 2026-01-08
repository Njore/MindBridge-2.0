"""
Enhanced Client Blueprint
Includes therapist connection awareness and invitation system
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from models import (db, User, ClientTherapistRelationship, Breakthrough, Trigger,
                    SessionNote, PromptResponse, TherapeuticPrompt, Notification,
                    ImpactLevel, NoteType, RelationshipStatus, TriggerSentimentAnalysis, UserType)
from blueprints.auth import client_required, log_activity
from datetime import datetime, date
from sqlalchemy import desc

client_bp = Blueprint('client', __name__)


@client_bp.route('/dashboard')
@client_required
def dashboard():
    """Client dashboard"""
    user = User.query.get(session['user_id'])

    # Get active therapist relationship
    relationship = ClientTherapistRelationship.query.filter_by(
        client_id=user.user_id,
        status=RelationshipStatus.ACTIVE
    ).first()

    # Get recent breakthroughs
    recent_breakthroughs = Breakthrough.query.filter_by(
        client_id=user.user_id
    ).order_by(desc(Breakthrough.created_at)).limit(5).all()

    # Get recent triggers
    recent_triggers = Trigger.query.filter_by(
        client_id=user.user_id
    ).order_by(desc(Trigger.date_logged)).limit(5).all()

    # Get pending prompts
    pending_prompts = []
    if relationship:
        pending_prompts = TherapeuticPrompt.query.filter_by(
            relationship_id=relationship.relationship_id,
            is_active=True
        ).filter(
            ~TherapeuticPrompt.prompt_id.in_(
                db.session.query(PromptResponse.prompt_id).filter_by(
                    client_id=user.user_id
                )
            )
        ).order_by(TherapeuticPrompt.deadline_date).all()

    # Get unread notifications
    unread_notifications = Notification.query.filter_by(
        user_id=user.user_id,
        is_read=False
    ).order_by(desc(Notification.created_at)).limit(5).all()

    return render_template('client/dashboard.html',
                           user=user,
                           relationship=relationship,
                           recent_breakthroughs=recent_breakthroughs,
                           recent_triggers=recent_triggers,
                           pending_prompts=pending_prompts,
                           unread_notifications=unread_notifications)


@client_bp.route('/therapists')
@client_required
def my_therapists():
    """View connected therapists"""
    user = User.query.get(session['user_id'])

    # Get all relationships
    relationships = ClientTherapistRelationship.query.filter_by(
        client_id=user.user_id
    ).order_by(desc(ClientTherapistRelationship.relationship_start_date)).all()

    return render_template('client/my_therapists.html',
                           user=user,
                           relationships=relationships)


@client_bp.route('/therapists/search', methods=['GET', 'POST'])
@client_required
def search_therapists():
    """Search for therapists (optional feature)"""
    user = User.query.get(session['user_id'])

    search_results = []
    search_query = ''

    if request.method == 'POST':
        search_query = request.form.get('search_query', '').strip()

        if search_query:
            # Search for therapists by name or email
            search_results = User.query.filter(
                User.user_type == UserType.THERAPIST,
                User.is_active == True,
                db.or_(
                    User.first_name.ilike(f'%{search_query}%'),
                    User.last_name.ilike(f'%{search_query}%'),
                    User.email.ilike(f'%{search_query}%')
                )
            ).all()

            # Filter out therapists already connected
            existing_therapist_ids = [
                r.therapist_id for r in ClientTherapistRelationship.query.filter_by(
                    client_id=user.user_id,
                    status=RelationshipStatus.ACTIVE
                ).all()
            ]

            search_results = [t for t in search_results if t.user_id not in existing_therapist_ids]

    return render_template('client/search_therapists.html',
                           user=user,
                           search_results=search_results,
                           search_query=search_query)


@client_bp.route('/breakthroughs')
@client_required
def breakthroughs():
    """View all breakthroughs"""
    user = User.query.get(session['user_id'])

    page = request.args.get('page', 1, type=int)
    breakthroughs = Breakthrough.query.filter_by(
        client_id=user.user_id
    ).order_by(desc(Breakthrough.date_occurred)).paginate(
        page=page, per_page=10, error_out=False
    )

    return render_template('client/breakthroughs.html',
                           user=user,
                           breakthroughs=breakthroughs)


@client_bp.route('/breakthroughs/add', methods=['GET', 'POST'])
@client_required
def add_breakthrough():
    """Add a new breakthrough"""
    user = User.query.get(session['user_id'])
    relationship = ClientTherapistRelationship.query.filter_by(
        client_id=user.user_id,
        status=RelationshipStatus.ACTIVE
    ).first()

    if not relationship:
        flash('You need an active therapist relationship to add breakthroughs.', 'warning')
        return redirect(url_for('client.dashboard'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        category = request.form.get('category', '').strip()
        impact_level = request.form.get('impact_level', 'moderate')
        date_occurred_str = request.form.get('date_occurred', '')
        share_with_therapist = request.form.get('share_with_therapist', False)

        if not title or not description:
            flash('Title and description are required.', 'danger')
            return render_template('client/add_breakthrough.html', user=user)

        try:
            date_occurred = datetime.strptime(date_occurred_str,
                                              '%Y-%m-%d').date() if date_occurred_str else date.today()
        except ValueError:
            date_occurred = date.today()

        breakthrough = Breakthrough(
            client_id=user.user_id,
            relationship_id=relationship.relationship_id,
            title=title,
            description=description,
            category=category,
            impact_level=ImpactLevel(impact_level),
            date_occurred=date_occurred,
            is_shared_with_therapist=bool(share_with_therapist)
        )

        db.session.add(breakthrough)
        db.session.commit()

        log_activity(user.user_id, 'breakthrough_created', 'breakthrough',
                     breakthrough.breakthrough_id, 'New breakthrough recorded')

        if share_with_therapist:
            notification = Notification(
                user_id=relationship.therapist_id,
                notification_type='new_breakthrough',
                title='New Breakthrough Shared',
                message=f'{user.get_full_name()} shared a new breakthrough: {title}',
                related_entity_type='breakthrough',
                related_entity_id=breakthrough.breakthrough_id
            )
            db.session.add(notification)
            db.session.commit()

        flash('Breakthrough added successfully!', 'success')
        return redirect(url_for('client.breakthroughs'))

    return render_template('client/add_breakthrough.html', user=user, now=datetime.now())


@client_bp.route('/triggers')
@client_required
def triggers():
    """View all triggers"""
    user = User.query.get(session['user_id'])

    page = request.args.get('page', 1, type=int)
    triggers = Trigger.query.filter_by(
        client_id=user.user_id
    ).order_by(desc(Trigger.date_logged)).paginate(
        page=page, per_page=10, error_out=False
    )

    return render_template('client/triggers.html',
                           user=user,
                           triggers=triggers)


@client_bp.route('/triggers/add', methods=['GET', 'POST'])
@client_required
def add_trigger():
    """Add a new trigger"""
    user = User.query.get(session['user_id'])
    relationship = ClientTherapistRelationship.query.filter_by(
        client_id=user.user_id,
        status=RelationshipStatus.ACTIVE
    ).first()

    if not relationship:
        flash('You need an active therapist relationship to log triggers.', 'warning')
        return redirect(url_for('client.dashboard'))

    if request.method == 'POST':
        trigger_description = request.form.get('trigger_description', '').strip()
        trigger_type = request.form.get('trigger_type', '').strip()
        intensity_level = request.form.get('intensity_level', 5, type=int)
        physical_symptoms = request.form.get('physical_symptoms', '').strip()
        emotional_response = request.form.get('emotional_response', '').strip()
        coping_strategy_used = request.form.get('coping_strategy_used', '').strip()
        coping_effectiveness = request.form.get('coping_effectiveness', type=int)
        location = request.form.get('location', '').strip()
        time_of_day = request.form.get('time_of_day', '').strip()

        if not trigger_description:
            flash('Trigger description is required.', 'danger')
            return render_template('client/add_trigger.html', user=user)

        trigger = Trigger(
            client_id=user.user_id,
            relationship_id=relationship.relationship_id,
            trigger_description=trigger_description,
            trigger_type=trigger_type,
            intensity_level=intensity_level,
            physical_symptoms=physical_symptoms,
            emotional_response=emotional_response,
            coping_strategy_used=coping_strategy_used,
            coping_effectiveness=coping_effectiveness,
            location=location,
            time_of_day=time_of_day
        )

        db.session.add(trigger)
        db.session.commit()

        perform_sentiment_analysis(trigger, emotional_response, intensity_level)

        log_activity(user.user_id, 'trigger_logged', 'trigger',
                     trigger.trigger_id, 'New trigger documented')

        flash('Trigger logged successfully!', 'success')
        return redirect(url_for('client.triggers'))

    return render_template('client/add_trigger.html', user=user)


def perform_sentiment_analysis(trigger, emotional_response, intensity_level):
    """Simplified sentiment analysis for triggers"""
    anxiety_keywords = ['anxious', 'worried', 'nervous', 'panic', 'fear']
    depression_keywords = ['sad', 'depressed', 'hopeless', 'empty', 'numb']
    anger_keywords = ['angry', 'frustrated', 'irritated', 'rage']

    emotional_text = emotional_response.lower()

    primary_emotion = 'neutral'
    anxiety_score = 0.0
    depression_score = 0.0
    crisis_flag = False

    if any(keyword in emotional_text for keyword in anxiety_keywords):
        primary_emotion = 'anxiety'
        anxiety_score = min(intensity_level / 10.0, 1.0)

    if any(keyword in emotional_text for keyword in depression_keywords):
        if anxiety_score < 0.5:
            primary_emotion = 'depression'
        depression_score = min(intensity_level / 10.0, 1.0)

    if any(keyword in emotional_text for keyword in anger_keywords):
        if anxiety_score < 0.3 and depression_score < 0.3:
            primary_emotion = 'anger'

    crisis_keywords = ['suicide', 'kill myself', 'end it', 'self-harm', 'hurt myself']
    if any(keyword in emotional_text for keyword in crisis_keywords):
        crisis_flag = True

    if intensity_level >= 8 or anxiety_score >= 0.8:
        crisis_flag = True

    sentiment = TriggerSentimentAnalysis(
        trigger_id=trigger.trigger_id,
        primary_emotion=primary_emotion,
        emotion_confidence=0.7,
        anxiety_score=anxiety_score,
        depression_score=depression_score,
        crisis_flag=crisis_flag,
        requires_therapist_review=crisis_flag or intensity_level >= 7
    )

    db.session.add(sentiment)
    db.session.commit()

    if crisis_flag:
        relationship = ClientTherapistRelationship.query.get(trigger.relationship_id)
        notification = Notification(
            user_id=relationship.therapist_id,
            notification_type='crisis_alert',
            title='URGENT: Crisis Alert',
            message=f'{User.query.get(trigger.client_id).get_full_name()} logged a high-severity trigger. Immediate attention required.',
            related_entity_type='trigger',
            related_entity_id=trigger.trigger_id
        )
        db.session.add(notification)
        db.session.commit()


@client_bp.route('/journal')
@client_required
def journal():
    """View journal entries"""
    user = User.query.get(session['user_id'])

    page = request.args.get('page', 1, type=int)
    notes = SessionNote.query.filter_by(
        client_id=user.user_id
    ).order_by(desc(SessionNote.created_at)).paginate(
        page=page, per_page=10, error_out=False
    )

    return render_template('client/journal.html',
                           user=user,
                           notes=notes)


@client_bp.route('/journal/add', methods=['GET', 'POST'])
@client_required
def add_journal_entry():
    """Add a journal entry"""
    user = User.query.get(session['user_id'])
    relationship = ClientTherapistRelationship.query.filter_by(
        client_id=user.user_id,
        status=RelationshipStatus.ACTIVE
    ).first()

    if not relationship:
        flash('You need an active therapist relationship to create journal entries.', 'warning')
        return redirect(url_for('client.dashboard'))

    if request.method == 'POST':
        note_type = request.form.get('note_type', 'between_session')
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        mood_before = request.form.get('mood_before', type=int)
        mood_after = request.form.get('mood_after', type=int)
        share_with_therapist = request.form.get('share_with_therapist', False)

        if not content:
            flash('Content is required.', 'danger')
            return render_template('client/add_journal_entry.html', user=user)

        note = SessionNote(
            client_id=user.user_id,
            relationship_id=relationship.relationship_id,
            note_type=NoteType(note_type),
            title=title,
            content=content,
            mood_before=mood_before,
            mood_after=mood_after,
            is_shared_with_therapist=bool(share_with_therapist)
        )

        if bool(share_with_therapist):
            note.shared_date = datetime.utcnow()

        db.session.add(note)
        db.session.commit()

        log_activity(user.user_id, 'journal_entry_created', 'session_note',
                     note.note_id, 'New journal entry')

        flash('Journal entry added successfully!', 'success')
        return redirect(url_for('client.journal'))

    return render_template('client/add_journal_entry.html', user=user)


@client_bp.route('/prompts')
@client_required
def prompts():
    """View therapeutic prompts"""
    user = User.query.get(session['user_id'])
    relationship = ClientTherapistRelationship.query.filter_by(
        client_id=user.user_id,
        status=RelationshipStatus.ACTIVE
    ).first()

    prompts = []
    if relationship:
        prompts = TherapeuticPrompt.query.filter_by(
            relationship_id=relationship.relationship_id,
            is_active=True
        ).order_by(TherapeuticPrompt.deadline_date).all()

    responded_prompt_ids = [r.prompt_id for r in PromptResponse.query.filter_by(
        client_id=user.user_id
    ).all()]

    return render_template('client/prompts.html',
                           user=user,
                           prompts=prompts,
                           responded_prompt_ids=responded_prompt_ids)


@client_bp.route('/prompts/<int:prompt_id>/respond', methods=['GET', 'POST'])
@client_required
def respond_to_prompt(prompt_id):
    """Respond to a therapeutic prompt"""
    user = User.query.get(session['user_id'])
    prompt = TherapeuticPrompt.query.get_or_404(prompt_id)

    existing_response = PromptResponse.query.filter_by(
        prompt_id=prompt_id,
        client_id=user.user_id
    ).first()

    if existing_response:
        flash('You have already responded to this prompt.', 'info')
        return redirect(url_for('client.prompts'))

    if request.method == 'POST':
        response_content = request.form.get('response_content', '').strip()
        insights_gained = request.form.get('insights_gained', '').strip()
        emotional_state = request.form.get('emotional_state', 'neutral')
        share_with_therapist = request.form.get('share_with_therapist', True)

        if not response_content:
            flash('Response content is required.', 'danger')
            return render_template('client/respond_to_prompt.html', user=user, prompt=prompt)

        response = PromptResponse(
            prompt_id=prompt_id,
            client_id=user.user_id,
            relationship_id=prompt.relationship_id,
            response_content=response_content,
            insights_gained=insights_gained,
            emotional_state=emotional_state,
            is_shared_with_therapist=bool(share_with_therapist)
        )

        if bool(share_with_therapist):
            response.shared_date = datetime.utcnow()

        db.session.add(response)
        db.session.commit()

        log_activity(user.user_id, 'prompt_response_created', 'prompt_response',
                     response.response_id, f'Responded to prompt: {prompt.title}')

        if bool(share_with_therapist):
            notification = Notification(
                user_id=prompt.therapist_id,
                notification_type='prompt_response',
                title='New Prompt Response',
                message=f'{user.get_full_name()} responded to your prompt: {prompt.title}',
                related_entity_type='prompt_response',
                related_entity_id=response.response_id
            )
            db.session.add(notification)
            db.session.commit()

        flash('Response submitted successfully!', 'success')
        return redirect(url_for('client.prompts'))

    return render_template('client/respond_to_prompt.html', user=user, prompt=prompt)