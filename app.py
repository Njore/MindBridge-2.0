"""
MindBridge - Therapeutic Support Platform
Main Application Entry Point
"""

from flask import Flask, render_template, redirect, url_for, session
from flask_migrate import Migrate
from datetime import timedelta
import os

# Import models and database
from models import db, bcrypt

# Import blueprints
from blueprints.auth import auth_bp
from blueprints.client import client_bp
from blueprints.therapist import therapist_bp
from blueprints.messaging import messaging_bp
from blueprints.crisis import crisis_bp


def create_app():
    app = Flask(__name__)

    # Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mindbridge.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)
    app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS only in production
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

    # Initialize extensions
    db.init_app(app)
    bcrypt.init_app(app)
    migrate = Migrate(app, db)

    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(client_bp, url_prefix='/client')
    app.register_blueprint(therapist_bp, url_prefix='/therapist')
    app.register_blueprint(messaging_bp, url_prefix='/messages')
    app.register_blueprint(crisis_bp, url_prefix='/crisis')

    # Context processor for templates
    @app.context_processor
    def inject_user():
        from models import User
        user = None
        if 'user_id' in session:
            user = User.query.get(session['user_id'])
        return dict(current_user=user)

    # Home route
    @app.route('/')
    def index():
        if 'user_id' in session:
            from models import User, UserType
            user = User.query.get(session['user_id'])
            if user:
                if user.user_type == UserType.CLIENT:
                    return redirect(url_for('client.dashboard'))
                elif user.user_type == UserType.THERAPIST:
                    return redirect(url_for('therapist.dashboard'))
        return render_template('index.html')

    # Error handlers
    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template('errors/500.html'), 500

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    # Create database tables
    with app.app_context():
        db.create_all()
        init_crisis_resources()
        init_deescalation_techniques()

    return app


def init_crisis_resources():
    """Initialize crisis resources if they don't exist"""
    from models import CrisisDirectory

    if CrisisDirectory.query.count() == 0:
        resources = [
            CrisisDirectory(
                resource_name="National Suicide Prevention Lifeline",
                resource_type="hotline",
                description="24/7 confidential support for people in distress",
                phone_number="988",
                available_24_7=True,
                languages_supported=["en", "es"],
                geographical_availability="United States"
            ),
            CrisisDirectory(
                resource_name="Crisis Text Line",
                resource_type="crisis_text",
                description="Free 24/7 support via text message",
                text_number="741741",
                available_24_7=True,
                languages_supported=["en"],
                geographical_availability="United States"
            ),
            CrisisDirectory(
                resource_name="SAMHSA National Helpline",
                resource_type="hotline",
                description="Treatment referral and information service",
                phone_number="1-800-662-4357",
                available_24_7=True,
                languages_supported=["en", "es"],
                geographical_availability="United States"
            )
        ]

        for resource in resources:
            db.session.add(resource)
        db.session.commit()


def init_deescalation_techniques():
    """Initialize de-escalation techniques if they don't exist"""
    from models import DeescalationTechnique, TechniqueCategory, TechniqueDifficulty

    if DeescalationTechnique.query.count() == 0:
        techniques = [
            DeescalationTechnique(
                technique_name="5-4-3-2-1 Grounding",
                technique_category=TechniqueCategory.GROUNDING,
                description="A sensory awareness technique to ground yourself in the present moment",
                step_by_step_instructions="""1. Name 5 things you can see around you
2. Name 4 things you can touch
3. Name 3 things you can hear
4. Name 2 things you can smell
5. Name 1 thing you can taste""",
                estimated_duration_minutes=5,
                difficulty_level=TechniqueDifficulty.BEGINNER,
                best_for=["severe_anxiety", "severe_panic", "dissociation"]
            ),
            DeescalationTechnique(
                technique_name="Box Breathing",
                technique_category=TechniqueCategory.BREATHING,
                description="A simple breathing technique used by Navy SEALs to manage stress",
                step_by_step_instructions="""1. Breathe in for 4 counts
2. Hold your breath for 4 counts
3. Breathe out for 4 counts
4. Hold for 4 counts
5. Repeat for 5-10 cycles""",
                estimated_duration_minutes=5,
                difficulty_level=TechniqueDifficulty.BEGINNER,
                best_for=["severe_anxiety", "severe_panic"]
            ),
            DeescalationTechnique(
                technique_name="Progressive Muscle Relaxation",
                technique_category=TechniqueCategory.PHYSICAL,
                description="Systematically tense and relax different muscle groups",
                step_by_step_instructions="""1. Start with your toes - tense for 5 seconds, then release
2. Move to your calves - tense and release
3. Continue up through thighs, abdomen, arms, shoulders
4. Finish with facial muscles
5. Notice the difference between tension and relaxation""",
                estimated_duration_minutes=15,
                difficulty_level=TechniqueDifficulty.INTERMEDIATE,
                best_for=["severe_anxiety", "dissociation"]
            ),
            DeescalationTechnique(
                technique_name="Cold Water Immersion",
                technique_category=TechniqueCategory.PHYSICAL,
                description="Use cold water to activate your body's dive reflex",
                step_by_step_instructions="""1. Fill a bowl with ice-cold water
2. Hold your breath and submerge your face for 30 seconds
3. Or hold ice cubes in your hands
4. Focus on the intense cold sensation
5. This interrupts the panic response""",
                estimated_duration_minutes=2,
                difficulty_level=TechniqueDifficulty.BEGINNER,
                best_for=["severe_panic", "self_harm_urge"]
            )
        ]

        for technique in techniques:
            db.session.add(technique)
        db.session.commit()


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)