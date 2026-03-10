import sys
import subprocess
import os

# ----------------------------------------
# Virtual Environment Check
# ----------------------------------------

def ensure_venv():
    """Ensure the script is running inside the .venv virtual environment."""
    venv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.venv')

    # Check if the current Python executable is already inside .venv
    if os.path.abspath(sys.executable).startswith(os.path.abspath(venv_path)):
        return  # Already running inside .venv

    # Determine the python executable inside .venv
    if sys.platform == 'win32':
        venv_python = os.path.join(venv_path, 'Scripts', 'python.exe')
    else:
        venv_python = os.path.join(venv_path, 'bin', 'python')

    if not os.path.exists(venv_python):
        print(f"❌ No .venv found at: {venv_path}")
        print("   Run: python -m venv .venv && pip install -r requirements.txt")
        sys.exit(1)

    print("⚡ Restarting inside .venv...")
    result = subprocess.run([venv_python] + sys.argv)
    sys.exit(result.returncode)


ensure_venv()


from flask import Flask, render_template, session
from models import db
import click
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def create_app():
    app = Flask(__name__)

    # Database configuration
    app.config['SQLALCHEMY_DATABASE_URI'] = (
        f"mysql+pymysql://{os.getenv('DB_USER', 'root')}:"
        f"{os.getenv('DB_PASSWORD', '')}@"
        f"{os.getenv('DB_HOST', 'localhost')}:"
        f"{os.getenv('DB_PORT', '3306')}/"
        f"{os.getenv('DB_NAME', 'mindbridge2')}"
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

    # Security configs
    app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS only
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    # Initialize database
    db.init_app(app)

    # Register blueprints
    from blueprints.auth import auth_bp
    from blueprints.client import client_bp
    from blueprints.therapist import therapist_bp
    from blueprints.messaging import messaging_bp
    from blueprints.crisis import crisis_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(client_bp, url_prefix='/client')
    app.register_blueprint(therapist_bp, url_prefix='/therapist')
    app.register_blueprint(messaging_bp, url_prefix='/messaging')
    app.register_blueprint(crisis_bp, url_prefix='/crisis')

    # Register CLI commands
    register_commands(app)

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/health')
    def health():
        return {'status': 'healthy', 'database': 'connected'}

    # Error handlers
    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template('errors/500.html'), 500

    # Static pages
    @app.route('/privacy')
    def privacy():
        return render_template('privacy.html')

    @app.route('/terms')
    def terms():
        return render_template('terms.html')

    return app


# ----------------------------------------
# CLI Commands // run this // (.venv/Scripts/flask reset-db)
# ----------------------------------------

def register_commands(app):
    @app.cli.command('reset-db')
    @click.confirmation_option(prompt='⚠️  This will DELETE all data. Are you sure?')
    def reset_db():
        """Drop all tables and recreate them from the current models."""
        env = os.getenv('FLASK_ENV', 'development')
        allow_reset = os.getenv('ALLOW_DB_RESET', 'false').lower() == 'true'

        if env == 'production' and not allow_reset:
            click.echo('❌ Blocked in production. Set ALLOW_DB_RESET=true to override.')
            return

        click.echo('⚠️  Dropping all tables...')
        db.drop_all()
        click.echo('✓ All tables dropped.')
        click.echo('🔧 Recreating tables from models...')
        db.create_all()
        click.echo('✓ Database reset successfully!')


if __name__ == '__main__':
    app = create_app()

    # Create tables
    with app.app_context():
        print("Creating database tables...")
        db.create_all()
        print("✓ Tables created successfully!")

    # Run app
    app.run(debug=True, host='0.0.0.0', port=5000)