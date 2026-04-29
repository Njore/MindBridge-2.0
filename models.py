from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy.dialects.mysql import JSON

db = SQLAlchemy()

# ========================================
# 1. USERS
# ========================================
class User(db.Model):
    __tablename__ = 'users'
    
    user_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    user_type = db.Column(db.Enum('client', 'therapist', 'admin'), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    date_of_birth = db.Column(db.Date)
    profile_picture_url = db.Column(db.String(500))
    bio = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    is_verified = db.Column(db.Boolean, default=False)
    email_verification_token = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ========================================
# 2. CLIENT-THERAPIST RELATIONSHIPS
# ========================================
class ClientTherapistRelationship(db.Model):
    __tablename__ = 'client_therapist_relationships'
    
    relationship_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    client_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    therapist_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    status = db.Column(db.Enum('active', 'inactive', 'ended'), default='active')
    relationship_start_date = db.Column(db.Date, nullable=False)
    relationship_end_date = db.Column(db.Date)
    therapist_notes = db.Column(db.Text)
    client_goals = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.Index('idx_client_active', 'client_id', 'status'),
        db.Index('idx_therapist_active', 'therapist_id', 'status'),
    )

# ========================================
# 3. CAPSULES
# ========================================
class Capsule(db.Model):
    __tablename__ = 'capsules'
    
    capsule_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    client_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    therapist_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    relationship_id = db.Column(db.Integer, db.ForeignKey('client_therapist_relationships.relationship_id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(255))
    user_tag = db.Column(db.Enum('trigger', 'breakthrough', 'mixed', 'general'), default='general')
    status = db.Column(db.Enum('open', 'sealed', 'archived'), default='open')
    mood_shift_data = db.Column(JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sealed_at = db.Column(db.DateTime)
    archived_at = db.Column(db.DateTime)
    
    __table_args__ = (
        db.Index('idx_client_status', 'client_id', 'status'),
        db.Index('idx_therapist_date', 'therapist_id', 'created_at'),
        db.Index('idx_sealed_at', 'sealed_at'),
    )

    priority_score = db.Column(db.Float, default=0.0)  # 0.0 to 1.0
    priority_level = db.Column(db.Enum('LOW', 'MEDIUM', 'HIGH', 'CRITICAL'), default='LOW')
    priority_analyzed_at = db.Column(db.DateTime)
    priority_reasons = db.Column(JSON)  # Store why it got this priority

    # For therapist to mark as reviewed
    priority_reviewed_by_therapist = db.Column(db.Boolean, default=False)

# ========================================
# 4. MESSAGES
# ========================================
class Message(db.Model):
    __tablename__ = 'messages'
    
    message_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    capsule_id = db.Column(db.Integer, db.ForeignKey('capsules.capsule_id', ondelete='CASCADE'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.Index('idx_capsule_date', 'capsule_id', 'created_at'),
    )

# ========================================
# 5. MESSAGE TAGS
# ========================================
class MessageTag(db.Model):
    __tablename__ = 'message_tags'
    
    tag_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    message_id = db.Column(db.Integer, db.ForeignKey('messages.message_id', ondelete='CASCADE'), nullable=False)
    tag_type = db.Column(db.String(100), nullable=False)
    source = db.Column(db.Enum('user', 'system'), default='system')
    confidence = db.Column(db.Numeric(3, 2))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.Index('idx_message_tag', 'message_id', 'tag_type'),
        db.Index('idx_tag_source', 'tag_type', 'source'),
    )

# ========================================
# 6. MULTIMEDIA ATTACHMENTS
# ========================================
class MessageAttachment(db.Model):
    __tablename__ = 'message_attachments'
    
    attachment_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    message_id = db.Column(db.Integer, db.ForeignKey('messages.message_id', ondelete='CASCADE'), nullable=False)
    attachment_type = db.Column(db.Enum('image', 'voice', 'document'), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_type = db.Column(db.String(50))
    file_size_bytes = db.Column(db.Integer)
    duration_seconds = db.Column(db.Integer)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.Index('idx_message_type', 'message_id', 'attachment_type'),
    )

# ========================================
# 7. PRIVATE POCKETS (7 Pockets - Encrypted)
# ========================================
class PrivatePocket(db.Model):
    __tablename__ = 'private_pockets'
    
    pocket_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    client_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    pocket_number = db.Column(db.Integer, nullable=False)  # 1-7
    content = db.Column(db.Text, nullable=False)  # Encrypted at app level
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('client_id', 'date', 'pocket_number', name='unique_daily_pocket'),
        db.Index('idx_client_week', 'client_id', 'date'),
    )

# ========================================
# 8. THERAPEUTIC PROMPTS & EXERCISES
# ========================================
class TherapeuticPrompt(db.Model):
    __tablename__ = 'therapeutic_prompts'
    
    prompt_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    therapist_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    relationship_id = db.Column(db.Integer, db.ForeignKey('client_therapist_relationships.relationship_id', ondelete='CASCADE'), nullable=False)
    prompt_type = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    prompt_content = db.Column(db.Text, nullable=False)
    instructions = db.Column(db.Text)
    expected_duration_minutes = db.Column(db.Integer)
    delivery_timing = db.Column(db.Enum('immediate', 'scheduled', 'randomized'), default='immediate')
    scheduled_datetime = db.Column(db.DateTime)
    randomization_window_start = db.Column(db.Time)
    randomization_window_end = db.Column(db.Time)
    frequency = db.Column(db.Enum('once', 'daily', 'weekly', 'custom'), default='once')
    frequency_custom_days = db.Column(db.Integer)
    is_active = db.Column(db.Boolean, default=True)
    sent_date = db.Column(db.DateTime, default=datetime.utcnow)
    deadline_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.Index('idx_therapist_active', 'therapist_id', 'is_active'),
        db.Index('idx_delivery_timing', 'delivery_timing', 'scheduled_datetime'),
    )

class PromptResponse(db.Model):
    __tablename__ = 'prompt_responses'
    
    response_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    prompt_id = db.Column(db.Integer, db.ForeignKey('therapeutic_prompts.prompt_id', ondelete='CASCADE'), nullable=False)
    message_id = db.Column(db.Integer, db.ForeignKey('messages.message_id', ondelete='SET NULL'))
    client_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    relationship_id = db.Column(db.Integer, db.ForeignKey('client_therapist_relationships.relationship_id', ondelete='CASCADE'), nullable=False)
    response_content = db.Column(db.Text, nullable=False)
    insights_gained = db.Column(db.Text)
    emotional_state = db.Column(db.String(100))
    response_date = db.Column(db.DateTime, default=datetime.utcnow)
    is_shared_with_therapist = db.Column(db.Boolean, default=False)
    shared_date = db.Column(db.DateTime)
    therapist_feedback = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.Index('idx_client_shared', 'client_id', 'is_shared_with_therapist'),
        db.Index('idx_prompt_date', 'prompt_id', 'response_date'),
    )

# ========================================
# 9. CRISIS MODULE
# ========================================
class CrisisEvent(db.Model):
    __tablename__ = 'crisis_events'
    
    crisis_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    client_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    relationship_id = db.Column(db.Integer, db.ForeignKey('client_therapist_relationships.relationship_id', ondelete='CASCADE'), nullable=False)
    crisis_type = db.Column(db.Enum('suicidal_ideation', 'severe_panic', 'severe_anxiety', 'self_harm_urge', 'dissociation', 'other'), nullable=False)
    severity_level = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text, nullable=False)
    immediate_action_taken = db.Column(db.String(255))
    resources_accessed = db.Column(JSON)
    therapist_notified = db.Column(db.Boolean, default=False)
    therapist_notification_date = db.Column(db.DateTime)
    status = db.Column(db.Enum('logged', 'in_progress', 'resolved', 'escalated'), default='logged')
    resolution_notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.CheckConstraint('severity_level >= 1 AND severity_level <= 10'),
        db.Index('idx_client_severity', 'client_id', 'severity_level'),
        db.Index('idx_status', 'status'),
    )

class DeescalationTechnique(db.Model):
    __tablename__ = 'deescalation_techniques'
    
    technique_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    technique_name = db.Column(db.String(255), nullable=False)
    technique_category = db.Column(db.Enum('grounding', 'breathing', 'mindfulness', 'distraction', 'physical', 'emotional_regulation', 'thought_challenging'), nullable=False)
    description = db.Column(db.Text, nullable=False)
    step_by_step_instructions = db.Column(db.Text, nullable=False)
    estimated_duration_minutes = db.Column(db.Integer)
    difficulty_level = db.Column(db.Enum('beginner', 'intermediate', 'advanced'), default='beginner')
    best_for = db.Column(JSON)
    audio_guide_url = db.Column(db.String(500))
    video_guide_url = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, default=True)
    is_crisis_accessible = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.Index('idx_category_active', 'technique_category', 'is_active'),
        db.Index('idx_crisis_access', 'is_crisis_accessible'),
    )

class ClientDeescalationHistory(db.Model):
    __tablename__ = 'client_deescalation_history'
    
    history_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    client_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    crisis_id = db.Column(db.Integer, db.ForeignKey('crisis_events.crisis_id', ondelete='SET NULL'))
    technique_id = db.Column(db.Integer, db.ForeignKey('deescalation_techniques.technique_id', ondelete='RESTRICT'), nullable=False)
    usage_date = db.Column(db.DateTime, default=datetime.utcnow)
    effectiveness_rating = db.Column(db.Integer)
    duration_used_minutes = db.Column(db.Integer)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.CheckConstraint('effectiveness_rating >= 1 AND effectiveness_rating <= 10'),
        db.Index('idx_client_technique', 'client_id', 'technique_id'),
        db.Index('idx_effectiveness', 'effectiveness_rating'),
    )

# ========================================
# 10. THEME & AMBIENCE SETTINGS
# ========================================
class ThemeSetting(db.Model):
    __tablename__ = 'theme_settings'
    
    setting_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, unique=True)
    user_type = db.Column(db.Enum('client', 'therapist'), nullable=False)
    theme_style = db.Column(db.Enum('warm', 'cool', 'minimalist'), default='warm')
    use_circadian_mode = db.Column(db.Boolean, default=True)
    uses_therapist_theme = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.Index('idx_user_type', 'user_id', 'user_type'),
    )

# ========================================
# 11. NOTIFICATIONS & ACTIVITY LOGS
# ========================================
class Notification(db.Model):
    __tablename__ = 'notifications'
    
    notification_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    notification_type = db.Column(db.String(100))
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    related_entity_type = db.Column(db.String(100))
    related_entity_id = db.Column(db.Integer)
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime)
    is_dismissed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.Index('idx_user_unread', 'user_id', 'is_read'),
        db.Index('idx_created', 'created_at'),
    )

class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    
    log_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    action_type = db.Column(db.String(100))
    resource_type = db.Column(db.String(100))
    resource_id = db.Column(db.Integer)
    description = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.Index('idx_user_action', 'user_id', 'action_type'),
        db.Index('idx_timestamp', 'timestamp'),
    )

# ========================================
# 12. PRIVACY & CONSENT (PRD Requirements)
# ========================================
class UserPrivacySetting(db.Model):
    __tablename__ = 'user_privacy_settings'
    
    setting_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, unique=True)
    allow_data_analytics = db.Column(db.Boolean, default=True)
    allow_session_recordings = db.Column(db.Boolean, default=False)
    share_progress_with_therapist = db.Column(db.Boolean, default=True)
    encrypted_storage_preference = db.Column(db.Boolean, default=True)
    data_retention_days = db.Column(db.Integer, default=730)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ConsentAgreement(db.Model):
    __tablename__ = 'consent_agreements'
    
    agreement_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    agreement_type = db.Column(db.String(100))
    version = db.Column(db.String(20))
    agreed_date = db.Column(db.DateTime, nullable=False)
    agreed_ip_address = db.Column(db.String(45))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.Index('idx_user_type', 'user_id', 'agreement_type'),
    )

# ========================================
# ADD TO models.py
# ========================================

class DataErasureRequest(db.Model):
    __tablename__ = 'data_erasure_requests'

    request_id   = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    reason       = db.Column(db.Text, nullable=True)
    status       = db.Column(
        db.Enum('pending', 'approved', 'completed', 'rejected'),
        default='pending',
        nullable=False
    )
    reviewed_by  = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=True)
    reviewed_at  = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    notes        = db.Column(db.Text, nullable=True)  # Admin-only notes

    __table_args__ = (
        db.Index('idx_erasure_user_status', 'user_id', 'status'),
        db.Index('idx_erasure_status', 'status'),
    )