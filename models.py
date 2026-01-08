"""
Therapeutic Support App - SQLAlchemy Models
Flask application models using SQLAlchemy ORM for database interaction
"""

from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from datetime import datetime, timedelta
import json
from enum import Enum

db = SQLAlchemy()
bcrypt = Bcrypt()


# ========================================
# 1. USERS & AUTHENTICATION
# ========================================

class UserType(str, Enum):
    CLIENT = "client"
    THERAPIST = "therapist"


class User(db.Model):
    __tablename__ = 'users'

    user_id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    user_type = db.Column(db.Enum(UserType), nullable=False, index=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    date_of_birth = db.Column(db.Date)
    profile_picture_url = db.Column(db.String(500))
    bio = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, index=True)
    is_verified = db.Column(db.Boolean, default=False)
    email_verification_token = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    client_relationships = db.relationship(
        'ClientTherapistRelationship',
        foreign_keys='ClientTherapistRelationship.client_id',
        backref='client_user',
        cascade='all, delete-orphan'
    )
    therapist_relationships = db.relationship(
        'ClientTherapistRelationship',
        foreign_keys='ClientTherapistRelationship.therapist_id',
        backref='therapist_user',
        cascade='all, delete-orphan'
    )
    breakthroughs = db.relationship('Breakthrough', backref='client', cascade='all, delete-orphan')
    triggers = db.relationship('Trigger', backref='client', cascade='all, delete-orphan')
    session_notes = db.relationship('SessionNote', backref='client', cascade='all, delete-orphan')
    therapeutic_prompts = db.relationship('TherapeuticPrompt', backref='therapist', cascade='all, delete-orphan')
    prompt_responses = db.relationship('PromptResponse', backref='client', cascade='all, delete-orphan')
    crisis_events = db.relationship('CrisisEvent', backref='client', cascade='all, delete-orphan')
    messages_sent = db.relationship(
        'Message',
        foreign_keys='Message.sender_id',
        backref='sender',
        cascade='all, delete-orphan'
    )
    messages_received = db.relationship(
        'Message',
        foreign_keys='Message.recipient_id',
        backref='recipient',
        cascade='all, delete-orphan'
    )
    privacy_settings = db.relationship('UserPrivacySetting', backref='user', uselist=False,
                                       cascade='all, delete-orphan')
    consent_agreements = db.relationship('ConsentAgreement', backref='user', cascade='all, delete-orphan')
    activity_logs = db.relationship('ActivityLog', backref='user', cascade='all, delete-orphan')

    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        """Verify password"""
        return bcrypt.check_password_hash(self.password_hash, password)

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

    def __repr__(self):
        return f'<User {self.email}>'


# ========================================
# 2. CLIENT-THERAPIST RELATIONSHIPS
# ========================================

class RelationshipStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ENDED = "ended"


class ClientTherapistRelationship(db.Model):
    __tablename__ = 'client_therapist_relationships'

    relationship_id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    therapist_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    status = db.Column(db.Enum(RelationshipStatus), default=RelationshipStatus.ACTIVE, index=True)
    relationship_start_date = db.Column(db.Date, nullable=False)
    relationship_end_date = db.Column(db.Date)
    therapist_notes = db.Column(db.Text)
    client_goals = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    breakthroughs = db.relationship('Breakthrough', backref='relationship', cascade='all, delete-orphan')
    triggers = db.relationship('Trigger', backref='relationship', cascade='all, delete-orphan')
    session_notes = db.relationship('SessionNote', backref='relationship', cascade='all, delete-orphan')
    therapeutic_prompts = db.relationship('TherapeuticPrompt', backref='relationship', cascade='all, delete-orphan')
    prompt_responses = db.relationship('PromptResponse', backref='relationship', cascade='all, delete-orphan')
    crisis_events = db.relationship('CrisisEvent', backref='relationship', cascade='all, delete-orphan')
    messages = db.relationship('Message', backref='relationship', cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('client_id', 'therapist_id', 'status', name='unique_active_relationship'),
        db.CheckConstraint('client_id != therapist_id', name='check_different_users'),
    )

    def is_active(self):
        return self.status == RelationshipStatus.ACTIVE

    def __repr__(self):
        return f'<ClientTherapistRelationship client={self.client_id} therapist={self.therapist_id}>'


# ========================================
# 3. BREAKTHROUGHS & ACHIEVEMENTS
# ========================================

class ImpactLevel(str, Enum):
    MINOR = "minor"
    MODERATE = "moderate"
    SIGNIFICANT = "significant"


class Breakthrough(db.Model):
    __tablename__ = 'breakthroughs'

    breakthrough_id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    relationship_id = db.Column(db.Integer,
                                db.ForeignKey('client_therapist_relationships.relationship_id', ondelete='CASCADE'),
                                nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(100))
    impact_level = db.Column(db.Enum(ImpactLevel), default=ImpactLevel.MODERATE)
    date_occurred = db.Column(db.Date, index=True)
    is_shared_with_therapist = db.Column(db.Boolean, default=False, index=True)
    therapist_response = db.Column(db.Text)
    therapist_response_date = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def share_with_therapist(self):
        self.is_shared_with_therapist = True

    def __repr__(self):
        return f'<Breakthrough {self.title}>'


# ========================================
# 4. TRIGGER DOCUMENTATION & SENTIMENT ANALYSIS
# ========================================

class Trigger(db.Model):
    __tablename__ = 'triggers'

    trigger_id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    relationship_id = db.Column(db.Integer,
                                db.ForeignKey('client_therapist_relationships.relationship_id', ondelete='CASCADE'),
                                nullable=False, index=True)
    trigger_description = db.Column(db.Text, nullable=False)
    trigger_type = db.Column(db.String(100), index=True)
    intensity_level = db.Column(db.Integer, nullable=False)
    physical_symptoms = db.Column(db.Text)
    emotional_response = db.Column(db.Text)
    coping_strategy_used = db.Column(db.String(255))
    coping_effectiveness = db.Column(db.Integer)
    location = db.Column(db.String(255))
    time_of_day = db.Column(db.String(50))
    date_logged = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    sentiment_analysis = db.relationship('TriggerSentimentAnalysis', backref='trigger', uselist=False,
                                         cascade='all, delete-orphan')

    __table_args__ = (
        db.CheckConstraint('intensity_level >= 1 AND intensity_level <= 10'),
        db.CheckConstraint('coping_effectiveness >= 1 AND coping_effectiveness <= 10'),
    )

    def __repr__(self):
        return f'<Trigger type={self.trigger_type} intensity={self.intensity_level}>'


class TriggerSentimentAnalysis(db.Model):
    __tablename__ = 'trigger_sentiment_analysis'

    sentiment_id = db.Column(db.Integer, primary_key=True)
    trigger_id = db.Column(db.Integer, db.ForeignKey('triggers.trigger_id', ondelete='CASCADE'), nullable=False,
                           unique=True)
    primary_emotion = db.Column(db.String(100), index=True)
    emotion_confidence = db.Column(db.Numeric(3, 2))
    secondary_emotions = db.Column(db.JSON)  # Array of emotions with confidence scores
    mental_health_concerns = db.Column(db.JSON)  # {anxiety: 0.8, panic: 0.6, depression: 0.3}
    anxiety_score = db.Column(db.Numeric(3, 2))
    panic_score = db.Column(db.Numeric(3, 2))
    depression_score = db.Column(db.Numeric(3, 2))
    crisis_flag = db.Column(db.Boolean, default=False, index=True)
    requires_therapist_review = db.Column(db.Boolean, default=False, index=True)
    analysis_timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def is_crisis_level(self):
        return self.crisis_flag or (self.anxiety_score and float(self.anxiety_score) > 0.8)

    def __repr__(self):
        return f'<TriggerSentimentAnalysis emotion={self.primary_emotion}>'


class PredefinedTriggerResponse(db.Model):
    __tablename__ = 'predefined_trigger_responses'

    response_id = db.Column(db.Integer, primary_key=True)
    therapist_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    relationship_id = db.Column(db.Integer,
                                db.ForeignKey('client_therapist_relationships.relationship_id', ondelete='SET NULL'))
    trigger_type = db.Column(db.String(100), index=True)
    emotion_target = db.Column(db.String(100), index=True)
    response_message = db.Column(db.Text, nullable=False)
    is_template = db.Column(db.Boolean, default=True, index=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __repr__ = lambda self: f'<PredefinedTriggerResponse emotion={self.emotion_target}>'


# ========================================
# 5. SESSION NOTES & JOURNALING
# ========================================

class NoteType(str, Enum):
    WEEKLY_JOURNAL = "weekly_journal"
    BETWEEN_SESSION = "between_session"
    PRE_SESSION = "pre_session"


class SessionNote(db.Model):
    __tablename__ = 'session_notes'

    note_id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    relationship_id = db.Column(db.Integer,
                                db.ForeignKey('client_therapist_relationships.relationship_id', ondelete='CASCADE'),
                                nullable=False, index=True)
    note_type = db.Column(db.Enum(NoteType), default=NoteType.BETWEEN_SESSION, index=True)
    title = db.Column(db.String(255))
    content = db.Column(db.Text, nullable=False)
    mood_before = db.Column(db.Integer)
    mood_after = db.Column(db.Integer)
    topics_covered = db.Column(db.JSON)  # Array of topics
    is_shared_with_therapist = db.Column(db.Boolean, default=False, index=True)
    shared_date = db.Column(db.DateTime)
    therapist_has_reviewed = db.Column(db.Boolean, default=False)
    therapist_review_date = db.Column(db.DateTime)
    therapist_feedback = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.CheckConstraint('mood_before >= 1 AND mood_before <= 10'),
        db.CheckConstraint('mood_after >= 1 AND mood_after <= 10'),
    )

    def share_with_therapist(self):
        self.is_shared_with_therapist = True
        self.shared_date = datetime.utcnow()

    def __repr__(self):
        return f'<SessionNote type={self.note_type}>'


class WeeklyJournalSummary(db.Model):
    __tablename__ = 'weekly_journal_summary'

    summary_id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    relationship_id = db.Column(db.Integer,
                                db.ForeignKey('client_therapist_relationships.relationship_id', ondelete='CASCADE'),
                                nullable=False, index=True)
    week_start_date = db.Column(db.Date, nullable=False)
    week_end_date = db.Column(db.Date, nullable=False)
    overall_mood_trend = db.Column(db.Integer)
    key_achievements = db.Column(db.Text)
    key_challenges = db.Column(db.Text)
    predominant_emotions = db.Column(db.JSON)  # Array of emotions
    total_triggers_logged = db.Column(db.Integer, default=0)
    total_coping_strategies_used = db.Column(db.Integer, default=0)
    is_ready_for_session = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('client_id', 'week_start_date', name='unique_week_client'),
        db.CheckConstraint('overall_mood_trend >= 1 AND overall_mood_trend <= 10'),
    )

    __repr__ = lambda self: f'<WeeklyJournalSummary week={self.week_start_date}>'


# ========================================
# 6. THERAPEUTIC PROMPTS
# ========================================

class PromptFrequency(str, Enum):
    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"
    CUSTOM = "custom"


class TherapeuticPrompt(db.Model):
    __tablename__ = 'therapeutic_prompts'

    prompt_id = db.Column(db.Integer, primary_key=True)
    therapist_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    relationship_id = db.Column(db.Integer,
                                db.ForeignKey('client_therapist_relationships.relationship_id', ondelete='CASCADE'),
                                nullable=False, index=True)
    prompt_type = db.Column(db.String(100), nullable=False, index=True)  # gratitude, shadow_work, inner_child, etc.
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    prompt_content = db.Column(db.Text, nullable=False)
    instructions = db.Column(db.Text)
    expected_duration_minutes = db.Column(db.Integer)
    frequency = db.Column(db.Enum(PromptFrequency), default=PromptFrequency.ONCE)
    frequency_custom_days = db.Column(db.Integer)
    is_active = db.Column(db.Boolean, default=True, index=True)
    sent_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    deadline_date = db.Column(db.Date, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    responses = db.relationship('PromptResponse', backref='prompt', cascade='all, delete-orphan')

    def is_overdue(self):
        if self.deadline_date:
            return datetime.utcnow().date() > self.deadline_date
        return False

    def __repr__(self):
        return f'<TherapeuticPrompt type={self.prompt_type}>'


class PromptResponseEmotion(str, Enum):
    IMPROVED = "improved"
    NEUTRAL = "neutral"
    WORSENED = "worsened"


class PromptResponse(db.Model):
    __tablename__ = 'prompt_responses'

    response_id = db.Column(db.Integer, primary_key=True)
    prompt_id = db.Column(db.Integer, db.ForeignKey('therapeutic_prompts.prompt_id', ondelete='CASCADE'),
                          nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    relationship_id = db.Column(db.Integer,
                                db.ForeignKey('client_therapist_relationships.relationship_id', ondelete='CASCADE'),
                                nullable=False, index=True)
    response_content = db.Column(db.Text, nullable=False)
    insights_gained = db.Column(db.Text)
    emotional_state = db.Column(db.Enum(PromptResponseEmotion), default=PromptResponseEmotion.NEUTRAL)
    response_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_shared_with_therapist = db.Column(db.Boolean, default=False, index=True)
    shared_date = db.Column(db.DateTime)
    therapist_feedback = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def share_with_therapist(self):
        self.is_shared_with_therapist = True
        self.shared_date = datetime.utcnow()

    __repr__ = lambda self: f'<PromptResponse emotional_state={self.emotional_state}>'


# ========================================
# 7. CRISIS MANAGEMENT
# ========================================

class CrisisType(str, Enum):
    SUICIDAL_IDEATION = "suicidal_ideation"
    SEVERE_PANIC = "severe_panic"
    SEVERE_ANXIETY = "severe_anxiety"
    SELF_HARM_URGE = "self_harm_urge"
    DISSOCIATION = "dissociation"
    OTHER = "other"


class CrisisStatus(str, Enum):
    LOGGED = "logged"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class CrisisDirectory(db.Model):
    __tablename__ = 'crisis_directory'

    resource_id = db.Column(db.Integer, primary_key=True)
    resource_name = db.Column(db.String(255), nullable=False)
    resource_type = db.Column(db.String(100), index=True)  # hotline, emergency_service, crisis_text, therapy_service
    description = db.Column(db.Text)
    phone_number = db.Column(db.String(20))
    text_number = db.Column(db.String(20))
    website_url = db.Column(db.String(500))
    email = db.Column(db.String(255))
    available_24_7 = db.Column(db.Boolean, default=True)
    languages_supported = db.Column(db.JSON)  # Array of language codes
    geographical_availability = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __repr__ = lambda self: f'<CrisisDirectory {self.resource_name}>'


class CrisisEvent(db.Model):
    __tablename__ = 'crisis_events'

    crisis_id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    relationship_id = db.Column(db.Integer,
                                db.ForeignKey('client_therapist_relationships.relationship_id', ondelete='CASCADE'),
                                nullable=False, index=True)
    crisis_type = db.Column(db.Enum(CrisisType), nullable=False, index=True)
    severity_level = db.Column(db.Integer, nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    immediate_action_taken = db.Column(db.String(255))
    resources_accessed = db.Column(db.JSON)  # Array of resource_ids
    therapist_notified = db.Column(db.Boolean, default=False)
    therapist_notification_date = db.Column(db.DateTime)
    emergency_contact_notified = db.Column(db.Boolean, default=False)
    status = db.Column(db.Enum(CrisisStatus), default=CrisisStatus.LOGGED, index=True)
    resolution_notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    deescalation_history = db.relationship('ClientDeescalationHistory', backref='crisis', cascade='all, delete-orphan')

    __table_args__ = (
        db.CheckConstraint('severity_level >= 1 AND severity_level <= 10'),
    )

    def is_high_severity(self):
        return self.severity_level >= 8

    def notify_therapist(self):
        self.therapist_notified = True
        self.therapist_notification_date = datetime.utcnow()

    __repr__ = lambda self: f'<CrisisEvent type={self.crisis_type} severity={self.severity_level}>'


# ========================================
# 8. CRISIS DE-ESCALATION TOOLS
# ========================================

class TechniqueDifficulty(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class TechniqueCategory(str, Enum):
    GROUNDING = "grounding"
    BREATHING = "breathing"
    MINDFULNESS = "mindfulness"
    DISTRACTION = "distraction"
    PHYSICAL = "physical"
    EMOTIONAL_REGULATION = "emotional_regulation"
    THOUGHT_CHALLENGING = "thought_challenging"


class DeescalationTechnique(db.Model):
    __tablename__ = 'deescalation_techniques'

    technique_id = db.Column(db.Integer, primary_key=True)
    technique_name = db.Column(db.String(255), nullable=False)
    technique_category = db.Column(db.Enum(TechniqueCategory), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    step_by_step_instructions = db.Column(db.Text, nullable=False)
    estimated_duration_minutes = db.Column(db.Integer)
    difficulty_level = db.Column(db.Enum(TechniqueDifficulty), default=TechniqueDifficulty.BEGINNER, index=True)
    best_for = db.Column(db.JSON)  # Array of crisis types effective for
    audio_guide_url = db.Column(db.String(500))
    video_guide_url = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    usage_history = db.relationship('ClientDeescalationHistory', backref='technique', cascade='all, delete-orphan')

    __repr__ = lambda self: f'<DeescalationTechnique {self.technique_name}>'


class ClientDeescalationHistory(db.Model):
    __tablename__ = 'client_deescalation_history'

    history_id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    crisis_id = db.Column(db.Integer, db.ForeignKey('crisis_events.crisis_id', ondelete='SET NULL'))
    technique_id = db.Column(db.Integer, db.ForeignKey('deescalation_techniques.technique_id', ondelete='RESTRICT'),
                             nullable=False, index=True)
    usage_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    effectiveness_rating = db.Column(db.Integer)
    duration_used_minutes = db.Column(db.Integer)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.CheckConstraint('effectiveness_rating >= 1 AND effectiveness_rating <= 10'),
    )

    def was_effective(self):
        if self.effectiveness_rating:
            return self.effectiveness_rating >= 7
        return False

    __repr__ = lambda self: f'<ClientDeescalationHistory effectiveness={self.effectiveness_rating}>'


# ========================================
# 9. SECURE MESSAGING
# ========================================

class MessageType(str, Enum):
    PROGRESS_UPDATE = "progress_update"
    TRIGGER_DOCUMENTATION = "trigger_documentation"
    BREAKTHROUGH = "breakthrough"
    GENERAL = "general"
    PROMPT_RESPONSE = "prompt_response"
    THERAPIST_PROMPT = "therapist_prompt"


class Message(db.Model):
    __tablename__ = 'messages'

    message_id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    relationship_id = db.Column(db.Integer,
                                db.ForeignKey('client_therapist_relationships.relationship_id', ondelete='CASCADE'),
                                nullable=False, index=True)
    message_type = db.Column(db.Enum(MessageType), nullable=False, index=True)
    subject = db.Column(db.String(255))
    content = db.Column(db.Text, nullable=False)
    is_encrypted = db.Column(db.Boolean, default=True)
    read_status = db.Column(db.Boolean, default=False, index=True)
    read_at = db.Column(db.DateTime)
    is_deleted_by_sender = db.Column(db.Boolean, default=False)
    is_deleted_by_recipient = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    attachments = db.relationship('MessageAttachment', backref='message', cascade='all, delete-orphan')

    def mark_as_read(self):
        self.read_status = True
        self.read_at = datetime.utcnow()

    def is_visible_to_user(self, user_id):
        if self.sender_id == user_id:
            return not self.is_deleted_by_sender
        elif self.recipient_id == user_id:
            return not self.is_deleted_by_recipient
        return False

    __repr__ = lambda self: f'<Message type={self.message_type}>'


class MessageAttachment(db.Model):
    __tablename__ = 'message_attachments'

    attachment_id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('messages.message_id', ondelete='CASCADE'), nullable=False,
                           index=True)
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_type = db.Column(db.String(50))
    file_size_bytes = db.Column(db.Integer)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __repr__ = lambda self: f'<MessageAttachment {self.file_name}>'


# ========================================
# 10. ACTIVITY LOG & AUDIT TRAIL
# ========================================

class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'

    log_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    action_type = db.Column(db.String(100))
    resource_type = db.Column(db.String(100))
    resource_id = db.Column(db.Integer)
    description = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        db.Index('idx_resource', 'resource_type', 'resource_id'),
    )

    __repr__ = lambda self: f'<ActivityLog action={self.action_type}>'


# ========================================
# 11. NOTIFICATIONS
# ========================================

class Notification(db.Model):
    __tablename__ = 'notifications'

    notification_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    notification_type = db.Column(db.String(100))
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    related_entity_type = db.Column(db.String(100))
    related_entity_id = db.Column(db.Integer)
    is_read = db.Column(db.Boolean, default=False, index=True)
    read_at = db.Column(db.DateTime)
    is_dismissed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def mark_as_read(self):
        self.is_read = True
        self.read_at = datetime.utcnow()

    __repr__ = lambda self: f'<Notification type={self.notification_type}>'


# ========================================
# 12. PRIVACY & CONSENT
# ========================================

class UserPrivacySetting(db.Model):
    __tablename__ = 'user_privacy_settings'

    setting_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), unique=True, nullable=False)
    allow_data_analytics = db.Column(db.Boolean, default=True)
    allow_session_recordings = db.Column(db.Boolean, default=False)
    share_progress_with_therapist = db.Column(db.Boolean, default=True)
    encrypted_storage_preference = db.Column(db.Boolean, default=True)
    data_retention_days = db.Column(db.Integer, default=730)  # 2 years
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __repr__ = lambda self: f'<UserPrivacySetting user_id={self.user_id}>'


class ConsentAgreement(db.Model):
    __tablename__ = 'consent_agreements'

    agreement_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    agreement_type = db.Column(db.String(100))  # terms_of_service, privacy_policy, therapy_waiver
    version = db.Column(db.String(20))
    agreed_date = db.Column(db.DateTime, nullable=False)
    agreed_ip_address = db.Column(db.String(45))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __repr__ = lambda self: f'<ConsentAgreement type={self.agreement_type}>'