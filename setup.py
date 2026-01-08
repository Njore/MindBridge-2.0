"""
MindBridge Setup Script
Automates the initial setup of the application
"""

import os
import sys
import subprocess


def create_directory_structure():
    """Create necessary directories"""
    directories = [
        'blueprints',
        'templates',
        'templates/auth',
        'templates/client',
        'templates/therapist',
        'templates/messaging',
        'templates/crisis',
        'templates/errors',
        'static',
        'static/css',
        'static/js',
        'static/images',
    ]

    print("Creating directory structure...")
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        print(f"  ✓ {directory}")

    # Create __init__.py in blueprints
    init_file = os.path.join('blueprints', '__init__.py')
    if not os.path.exists(init_file):
        with open(init_file, 'w') as f:
            f.write('# Blueprints package\n')

    print("\n✓ Directory structure created successfully!\n")


def check_python_version():
    """Check if Python version is compatible"""
    print("Checking Python version...")
    if sys.version_info < (3, 9):
        print("  ✗ Python 3.9 or higher is required!")
        print(f"  Current version: {sys.version}")
        return False
    print(f"  ✓ Python {sys.version_info.major}.{sys.version_info.minor}")
    return True


def install_dependencies():
    """Install required packages"""
    print("\nInstalling dependencies...")
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])
        print("\n✓ Dependencies installed successfully!\n")
        return True
    except subprocess.CalledProcessError:
        print("\n✗ Failed to install dependencies!")
        return False


def create_env_file():
    """Create .env file with default settings"""
    env_file = '.env'
    if os.path.exists(env_file):
        print(f"\n.env file already exists, skipping...")
        return

    print("\nCreating .env file...")
    with open(env_file, 'w') as f:
        f.write('# MindBridge Environment Variables\n')
        f.write('SECRET_KEY=dev-secret-key-change-in-production\n')
        f.write('FLASK_ENV=development\n')
        f.write('SQLALCHEMY_DATABASE_URI=sqlite:///mindbridge.db\n')

    print("  ✓ .env file created")


def initialize_database():
    """Initialize the database"""
    print("\nInitializing database...")
    print("  Starting Flask application to create tables...")

    # Import here to avoid issues before dependencies are installed
    try:
        from app import create_app
        app = create_app()
        with app.app_context():
            from models import db
            db.create_all()
            print("  ✓ Database tables created")
        print("\n✓ Database initialized successfully!\n")
        return True
    except Exception as e:
        print(f"\n✗ Failed to initialize database: {e}")
        return False


def print_next_steps():
    """Print next steps for the user"""
    print("\n" + "=" * 60)
    print("🎉 SETUP COMPLETE!")
    print("=" * 60)
    print("\nNext steps:")
    print("\n1. Review the .env file and update SECRET_KEY for production")
    print("\n2. Start the application:")
    print("   python app.py")
    print("\n3. Open your browser and go to:")
    print("   http://localhost:5000")
    print("\n4. Create your first account:")
    print("   - Go to /auth/register")
    print("   - Choose 'Client' or 'Therapist' user type")
    print("\n5. For production deployment:")
    print("   - Change SECRET_KEY to a strong random value")
    print("   - Use PostgreSQL instead of SQLite")
    print("   - Enable HTTPS")
    print("   - Review security settings in app.py")
    print("\n" + "=" * 60)
    print("\n📚 Documentation: README.md")
    print("🚨 Emergency Resources: 988 (Suicide & Crisis Lifeline)")
    print("\n" + "=" * 60 + "\n")


def main():
    """Main setup function"""
    print("\n" + "=" * 60)
    print("MindBridge - Therapeutic Support Platform")
    print("Setup Script")
    print("=" * 60 + "\n")

    # Check Python version
    if not check_python_version():
        return

    # Create directory structure
    create_directory_structure()

    # Install dependencies
    if not install_dependencies():
        return

    # Create .env file
    create_env_file()

    # Initialize database
    if not initialize_database():
        print("\n⚠️  Database initialization failed, but you can try manually:")
        print(
            "   python -c 'from app import create_app; app = create_app(); app.app_context().push(); from models import db; db.create_all()'")

    # Print next steps
    print_next_steps()


if __name__ == '__main__':
    main()