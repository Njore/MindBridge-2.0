# MindBridge - Therapeutic Support Platform

A secure HIPAA-compliant messaging platform that bridges the gap between scheduled therapy sessions, enabling continuous therapeutic engagement and progress tracking.

## Features

### For Clients
- **Breakthrough Tracking**: Document and share achievements and progress moments
- **Trigger Documentation**: Log triggers with sentiment analysis for anxiety, panic, depression
- **Digital Journaling**: Weekly note-taking that can be shared with therapists
- **Therapeutic Prompts**: Respond to exercises sent by therapists
- **Crisis Support**: 24/7 access to emergency resources and de-escalation techniques
- **Secure Messaging**: HIPAA-compliant communication with therapists

### For Therapists
- **Client Management**: Track multiple client relationships
- **Progress Monitoring**: Review breakthroughs, triggers, and journal entries
- **Prompt Creation**: Send therapeutic exercises to clients
- **Crisis Alerts**: Receive notifications for high-severity events
- **Sentiment Analysis**: Review automated emotional analysis of client inputs

## Technology Stack

- **Backend**: Python Flask
- **Database**: SQL
- **Frontend**: Bootstrap 5, Vanilla JavaScript
- **Security**: Flask-Bcrypt, Session Management, CSRF Protection

## Project Structure

```
mindbridge/
│
├── app.py                      # Main application entry point
├── models.py                   # SQLAlchemy database models
├── requirements.txt            # Python dependencies
├── README.md                   # This file
│
├── blueprints/                 # Flask blueprints
│   ├── __init__.py
│   ├── auth.py                 # Authentication routes
│   ├── client.py               # Client functionality
│   ├── therapist.py            # Therapist functionality
│   ├── messaging.py            # Secure messaging
│   └── crisis.py               # Crisis management
│
├── templates/                  # Jinja2 templates
│   ├── base.html               # Base template
│   ├── index.html              # Landing page
│   │
│   ├── auth/                   # Authentication templates
│   │   ├── login.html
│   │   ├── register.html
│   │   └── profile.html
│   │
│   ├── client/                 # Client templates
│   │   ├── dashboard.html
│   │   ├── breakthroughs.html
│   │   ├── add_breakthrough.html
│   │   ├── triggers.html
│   │   ├── add_trigger.html
│   │   ├── journal.html
│   │   ├── add_journal_entry.html
│   │   ├── prompts.html
│   │   └── respond_to_prompt.html
│   │
│   ├── therapist/              # Therapist templates
│   │   ├── dashboard.html
│   │   ├── clients.html
│   │   ├── client_detail.html
│   │   ├── create_prompt.html
│   │   ├── view_trigger.html
│   │   └── view_prompt_responses.html
│   │
│   ├── messaging/              # Messaging templates
│   │   ├── inbox.html
│   │   └── conversation.html
│   │
│   ├── crisis/                 # Crisis management templates
│   │   ├── index.html
│   │   ├── resources.html
│   │   ├── techniques.html
│   │   ├── technique_detail.html
│   │   ├── log_event.html
│   │   ├── my_events.html
│   │   └── event_detail.html
│   │
│   └── errors/                 # Error pages
│       ├── 403.html
│       ├── 404.html
│       └── 500.html
│
└── static/                     # Static files (optional)
    ├── css/
    ├── js/
    └── images/
```

## Installation & Setup

### Prerequisites
- Python 3.9 or higher
- pip (Python package installer)

### Installation Steps

1. **Clone or download the project**
   ```bash
   mkdir mindbridge
   cd mindbridge
   ```

2. **Create virtual environment**
   ```bash
   python -m venv .venv
   
   # On Windows:
   .venv\Scripts\activate
   
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Create necessary directories**
   ```bash
   mkdir blueprints templates templates/auth templates/client templates/therapist templates/messaging templates/crisis templates/errors
   ```

5. **Set environment variables (optional)**
   ```bash
   # On Windows:
   set SECRET_KEY=your-secret-key-here
   set FLASK_ENV=development
   
   # On macOS/Linux:
   export SECRET_KEY=your-secret-key-here
   export FLASK_ENV=development
   ```

6. **Initialize database**
   ```bash
   flask db init
   flask db migrate -m "Initial migration"
   flask db upgrade
   ```

7. **Run the application**
   ```bash
   python app.py
   ```

8. **Access the application**
   Open your browser and navigate to: `http://localhost:5000`

## Quick Start Guide

### For First-Time Users

1. **Register an Account**
   - Go to `/auth/register`
   - Choose either "Client" or "Therapist" user type
   - Fill in required information

2. **As a Client:**
   - Complete your profile
   - Your therapist will establish a relationship with you
   - Start logging breakthroughs, triggers, and journal entries
   - Respond to therapeutic prompts
   - Access crisis resources anytime

3. **As a Therapist:**
   - Complete your profile
   - Add client relationships
   - Create and send therapeutic prompts
   - Review client progress and provide feedback
   - Monitor crisis alerts

## Security Features

### HIPAA Compliance Considerations
- **Encrypted Sessions**: All sessions use secure cookies
- **Password Hashing**: Bcrypt for password storage
- **Activity Logging**: Comprehensive audit trail
- **Access Control**: Role-based permissions
- **Data Retention**: Configurable retention policies
- **Secure Messaging**: Encrypted message storage

### Additional Security Notes
- Change the `SECRET_KEY` in production
- Use HTTPS in production (set `SESSION_COOKIE_SECURE=True`)
- Implement rate limiting for production
- Regular security audits recommended
- Consider implementing 2FA for production

## Crisis Resources

The application includes a comprehensive crisis directory with:
- **988 Suicide & Crisis Lifeline**: 24/7 support
- **Crisis Text Line** (741741): Text-based support
- **De-escalation Techniques**: Grounding, breathing, mindfulness exercises

### Important Safety Note
This application is NOT a replacement for:
- Emergency services (911)
- Professional mental health treatment
- Crisis hotlines
- In-person therapy sessions

## Database Schema

The application uses 20+ tables including:
- User management and authentication
- Client-therapist relationships
- Breakthroughs and achievements
- Trigger documentation with sentiment analysis
- Session notes and journaling
- Therapeutic prompts and responses
- Crisis events and de-escalation history
- Secure messaging
- Activity logs and notifications

## Development

### Running in Development Mode
```bash
export FLASK_ENV=development
python app.py
```

### Database Migrations
```bash
# Create new migration
flask db migrate -m "Description of changes"

# Apply migration
flask db upgrade

# Rollback migration
flask db downgrade
```

### Adding New Features
1. Add models to `models.py`
2. Create blueprint in `blueprints/`
3. Register blueprint in `app.py`
4. Create templates in `templates/`
5. Run migrations

## Production Deployment

### Important Production Settings
1. Set strong `SECRET_KEY`
2. Use PostgreSQL instead of SQLite
3. Enable HTTPS
4. Set up proper backup strategy
5. Implement rate limiting
6. Configure logging
7. Set up monitoring
8. Regular security audits

### Environment Variables for Production
```bash
SECRET_KEY=your-very-strong-secret-key
SQLALCHEMY_DATABASE_URI=postgresql://user:password@localhost/mindbridge
FLASK_ENV=production
SESSION_COOKIE_SECURE=True
```

## API Endpoints (Summary)

### Authentication
- `POST /auth/register` - User registration
- `POST /auth/login` - User login
- `GET /auth/logout` - User logout
- `GET /auth/profile` - View/edit profile

### Client Routes
- `GET /client/dashboard` - Client dashboard
- `GET /client/breakthroughs` - View breakthroughs
- `POST /client/breakthroughs/add` - Add breakthrough
- `GET /client/triggers` - View triggers
- `POST /client/triggers/add` - Log trigger
- `GET /client/journal` - View journal entries
- `POST /client/journal/add` - Add journal entry
- `GET /client/prompts` - View prompts
- `POST /client/prompts/<id>/respond` - Respond to prompt

### Therapist Routes
- `GET /therapist/dashboard` - Therapist dashboard
- `GET /therapist/clients` - View all clients
- `GET /therapist/clients/<id>` - View client details
- `POST /therapist/prompts/create` - Create therapeutic prompt
- `POST /therapist/breakthroughs/<id>/respond` - Respond to breakthrough

### Messaging Routes
- `GET /messages/` - View inbox
- `GET /messages/conversation/<id>` - View conversation
- `POST /messages/send` - Send message

### Crisis Routes
- `GET /crisis/` - Crisis support center
- `GET /crisis/resources` - Crisis directory
- `GET /crisis/techniques` - De-escalation techniques
- `POST /crisis/log-event` - Log crisis event

## Contributing

This is a proof-of-concept application. For production use:
1. Conduct thorough security audit
2. Implement comprehensive testing
3. Add data encryption at rest
4. Implement backup and recovery
5. Add monitoring and alerting
6. Consider HIPAA compliance certification

## License

This project is provided as-is for educational and proof-of-concept purposes.

## Support

For questions or issues:
- Review the documentation
- Check error logs
- Ensure all dependencies are installed
- Verify database migrations are current

## Disclaimer

This application is a prototype and should undergo rigorous testing, security audits, and HIPAA compliance review before being used in a production healthcare environment. It is not a substitute for professional medical advice, diagnosis, or treatment.

---

**Emergency Resources:**
- **National Suicide Prevention Lifeline**: 988
- **Crisis Text Line**: Text HELLO to 741741
- **Emergency Services**: 911