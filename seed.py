"""
MindBridge Seed Script
======================
Creates:
  - 3 therapists (verified)
  - 21 clients (7 per therapist)
  - Active relationships for each pair
  - 3-4 capsules per client (mix of open/sealed, LOW/MEDIUM/HIGH/CRITICAL)
  - 3-6 messages per capsule
  - Crisis events for CRITICAL capsules
  - Unread notifications on therapists (to test backlog panel)
  - Consent agreements and privacy settings for everyone

Run:
    flask seed-db
OR standalone:
    python seed.py
"""

import bcrypt
from datetime import datetime, date, timedelta
import random

from models import (
    db, User, ClientTherapistRelationship, Capsule, Message,
    CrisisEvent, Notification, ConsentAgreement, UserPrivacySetting
)


# ── Helpers ───────────────────────────────────────────────────

def hp(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

def days_ago(n: int) -> datetime:
    return datetime.utcnow() - timedelta(days=n)

def rand_date_ago(min_days=10, max_days=180) -> date:
    return (datetime.utcnow() - timedelta(days=random.randint(min_days, max_days))).date()


# ── Static data ───────────────────────────────────────────────

THERAPISTS = [
    {
        'email': 'amina.hassan@mindbridge.dev',
        'first_name': 'Amina', 'last_name': 'Hassan',
        'phone': '+254711000001',
        'bio': 'Specialises in trauma-informed care and CBT. 8 years experience.',
        'dob': date(1985, 3, 14),
    },
    {
        'email': 'brian.otieno@mindbridge.dev',
        'first_name': 'Brian', 'last_name': 'Otieno',
        'phone': '+254711000002',
        'bio': 'Focuses on anxiety, depression, and young adult transitions. DBT practitioner.',
        'dob': date(1980, 7, 22),
    },
    {
        'email': 'grace.wanjiku@mindbridge.dev',
        'first_name': 'Grace', 'last_name': 'Wanjiku',
        'phone': '+254711000003',
        'bio': 'Grief counselling, relationship therapy, and mindfulness-based stress reduction.',
        'dob': date(1990, 11, 5),
    },
]

CLIENTS_PER_THERAPIST = [
    # Amina's clients
    [
        {'email': 'client.wanjiru@test.dev',  'first_name': 'Wanjiru',  'last_name': 'Kamau',    'dob': date(1998, 4, 2)},
        {'email': 'client.john@test.dev',     'first_name': 'John',     'last_name': 'Mwangi',   'dob': date(1995, 8, 17)},
        {'email': 'client.fatuma@test.dev',   'first_name': 'Fatuma',   'last_name': 'Ali',      'dob': date(2001, 1, 30)},
        {'email': 'client.peter@test.dev',    'first_name': 'Peter',    'last_name': 'Njoroge',  'dob': date(1993, 6, 11)},
        {'email': 'client.mary@test.dev',     'first_name': 'Mary',     'last_name': 'Achieng',  'dob': date(2000, 9, 25)},
        {'email': 'client.david@test.dev',    'first_name': 'David',    'last_name': 'Kimani',   'dob': date(1997, 12, 3)},
        {'email': 'client.sarah@test.dev',    'first_name': 'Sarah',    'last_name': 'Odhiambo', 'dob': date(1999, 5, 19)},
    ],
    # Brian's clients
    [
        {'email': 'client.kevin@test.dev',    'first_name': 'Kevin',    'last_name': 'Mutua',    'dob': date(2002, 3, 8)},
        {'email': 'client.diana@test.dev',    'first_name': 'Diana',    'last_name': 'Waweru',   'dob': date(1996, 7, 14)},
        {'email': 'client.james@test.dev',    'first_name': 'James',    'last_name': 'Omondi',   'dob': date(1994, 10, 22)},
        {'email': 'client.ruth@test.dev',     'first_name': 'Ruth',     'last_name': 'Chebet',   'dob': date(2003, 2, 5)},
        {'email': 'client.michael@test.dev',  'first_name': 'Michael',  'last_name': 'Githinji', 'dob': date(1991, 8, 30)},
        {'email': 'client.esther@test.dev',   'first_name': 'Esther',   'last_name': 'Ndungu',   'dob': date(1998, 11, 16)},
        {'email': 'client.samuel@test.dev',   'first_name': 'Samuel',   'last_name': 'Kipchoge', 'dob': date(2000, 6, 7)},
    ],
    # Grace's clients
    [
        {'email': 'client.alice@test.dev',    'first_name': 'Alice',    'last_name': 'Mugo',     'dob': date(1995, 1, 23)},
        {'email': 'client.joseph@test.dev',   'first_name': 'Joseph',   'last_name': 'Njeru',    'dob': date(1989, 4, 18)},
        {'email': 'client.linda@test.dev',    'first_name': 'Linda',    'last_name': 'Wambui',   'dob': date(2001, 9, 11)},
        {'email': 'client.charles@test.dev',  'first_name': 'Charles',  'last_name': 'Kariuki',  'dob': date(1997, 7, 29)},
        {'email': 'client.betty@test.dev',    'first_name': 'Betty',    'last_name': 'Moraa',    'dob': date(1993, 3, 6)},
        {'email': 'client.felix@test.dev',    'first_name': 'Felix',    'last_name': 'Onyango',  'dob': date(2002, 12, 20)},
        {'email': 'client.naomi@test.dev',    'first_name': 'Naomi',    'last_name': 'Muthoni',  'dob': date(1999, 8, 4)},
    ],
]

CAPSULE_SCENARIOS = {
    'CRITICAL': [
        {
            'title': "I don't want to be here anymore",
            'tag': 'trigger',
            'messages': [
                "I've been thinking a lot this week about what the point of all this is.",
                "Last night I couldn't sleep and I just kept thinking about disappearing. Not making it dramatic, I just mean I don't see a future for myself right now.",
                "I haven't told anyone else this. I don't know if I can keep going.",
                "I have my dad's pills in my room. I keep looking at them.",
            ]
        },
        {
            'title': "Worst week of my life",
            'tag': 'trigger',
            'messages': [
                "I lost my job on Monday. My girlfriend left on Wednesday. I have almost no money left.",
                "I've been sitting in the dark since Thursday. I haven't eaten properly.",
                "I keep having these thoughts that everyone would be better off. I know that's probably not true but I can't stop the thought.",
                "I don't see a way out of this.",
            ]
        },
    ],
    'HIGH': [
        {
            'title': "Panic attacks getting worse",
            'tag': 'trigger',
            'messages': [
                "Had three panic attacks this week. The worst one was in the supermarket, I had to leave my trolley and just get out.",
                "I'm starting to avoid going outside because I'm scared of it happening again.",
                "At night I wake up with my heart racing even when nothing is happening.",
                "I feel like I'm losing control of my own body.",
            ]
        },
        {
            'title': "Drinking more than I should",
            'tag': 'mixed',
            'messages': [
                "I've been drinking every night this week to fall asleep. I know it's not healthy.",
                "It started as just a glass or two but now it takes more to feel anything.",
                "I missed work twice because I felt terrible in the morning.",
                "I'm scared to tell my family because they'll think I'm turning into my father.",
            ]
        },
        {
            'title': "Can't stop hurting myself",
            'tag': 'trigger',
            'messages': [
                "I did it again last night. I promised myself I wouldn't but when the feelings got too big I didn't know what else to do.",
                "It's the only thing that makes the noise in my head stop for a bit.",
                "I'm wearing long sleeves to work. No one knows.",
            ]
        },
    ],
    'MEDIUM': [
        {
            'title': "Work stress is overwhelming me",
            'tag': 'general',
            'messages': [
                "My manager keeps piling on more tasks and I don't know how to say no.",
                "I've been staying at the office until 9pm almost every night and I still feel behind.",
                "I snapped at my partner this morning over nothing. I feel terrible about it.",
                "I haven't exercised or cooked a proper meal in two weeks.",
            ]
        },
        {
            'title': "Feeling disconnected from everyone",
            'tag': 'general',
            'messages': [
                "Even when I'm with people I care about I feel like I'm watching from outside.",
                "My friends invited me out this weekend and I made up an excuse not to go.",
                "I used to enjoy things. Now most days feel grey and flat.",
                "I'm functioning fine externally. Inside feels hollow.",
            ]
        },
        {
            'title': "Struggling with my parents",
            'tag': 'mixed',
            'messages': [
                "My mum called again to ask about marriage. I'm 26. The pressure is relentless.",
                "I love my family but every visit leaves me exhausted for days.",
                "I feel guilty for not wanting to be around them as much as I used to.",
            ]
        },
    ],
    'LOW': [
        {
            'title': "Week 1 check-in",
            'tag': 'general',
            'messages': [
                "This week was actually okay. Work was manageable.",
                "I tried the breathing exercise you suggested. It helped a bit in the stressful moments.",
                "Slept better than usual. Feeling cautiously optimistic.",
            ]
        },
        {
            'title': "Progress on the things we talked about",
            'tag': 'breakthrough',
            'messages': [
                "I did the thing we discussed — I set a boundary with my sister about the money issue.",
                "She was upset at first but I held my ground. Felt really strange but also kind of good.",
                "I think I'm starting to understand what you mean about self-respect not being selfish.",
            ]
        },
        {
            'title': "Reflecting on last session",
            'tag': 'breakthrough',
            'messages': [
                "I've been thinking about what you said last time about the inner critic.",
                "I noticed it today when I made a mistake at work. Instead of spiralling I just observed it.",
                "Baby steps but it felt different. Thank you.",
            ]
        },
    ]
}

THERAPIST_RESPONSES = [
    "Thank you for sharing this with me. I hear how difficult this has been.",
    "This takes real courage to put into words. Let's explore this together in our next session.",
    "I've read through carefully. What you're describing is significant — I want to make sure we give this proper attention. Can we schedule an extra session this week?",
    "I'm glad you reached out. The pattern you're noticing is important. We'll work through this.",
    "You've made real progress here. What you wrote shows a lot of self-awareness.",
]


# ── Priority helpers ──────────────────────────────────────────

def _priority_score(level: str) -> float:
    return {
        'CRITICAL': random.uniform(0.85, 0.99),
        'HIGH':     random.uniform(0.60, 0.84),
        'MEDIUM':   random.uniform(0.35, 0.59),
        'LOW':      random.uniform(0.05, 0.34),
    }[level]


def _risk_flags(level: str) -> list:
    pool = {
        'CRITICAL': ['suicidal_ideation', 'hopelessness', 'access_to_means'],
        'HIGH':     ['self_harm', 'severe_anxiety', 'panic', 'substance_use'],
        'MEDIUM':   ['depression', 'isolation', 'sleep_disturbance'],
        'LOW':      ['mild_stress'],
    }[level]
    return random.sample(pool, k=random.randint(1, len(pool)))


# ── Main seed function ────────────────────────────────────────

def seed(app):
    with app.app_context():

        if User.query.filter_by(user_type='therapist').count() >= 3:
            print("⚠️  Seed data already present. Run 'flask reset-db' first if you want a fresh seed.")
            return

        print("🌱 Starting seed...")

        # ── Therapists ────────────────────────────────────────
        therapist_users = []
        for t in THERAPISTS:
            therapist = User(
                email=t['email'],
                password_hash=hp('Therapist@1234'),
                user_type='therapist',
                first_name=t['first_name'],
                last_name=t['last_name'],
                phone=t['phone'],
                bio=t['bio'],
                date_of_birth=t['dob'],
                is_active=True,
                is_verified=True,
                created_at=days_ago(random.randint(60, 180)),
            )
            db.session.add(therapist)
            therapist_users.append(therapist)

        db.session.flush()
        print(f"✓ Created {len(therapist_users)} therapists")

        # ── Clients, relationships, capsules ─────────────────
        for t_idx, therapist in enumerate(therapist_users):
            for c_def in CLIENTS_PER_THERAPIST[t_idx]:

                client = User(
                    email=c_def['email'],
                    password_hash=hp('Client@1234'),
                    user_type='client',
                    first_name=c_def['first_name'],
                    last_name=c_def['last_name'],
                    date_of_birth=c_def['dob'],
                    is_active=True,
                    is_verified=False,
                    created_at=days_ago(random.randint(30, 120)),
                )
                db.session.add(client)
                db.session.flush()

                for agreement_type in ['terms_of_service', 'privacy_policy']:
                    db.session.add(ConsentAgreement(
                        user_id=client.user_id,
                        agreement_type=agreement_type,
                        version='1.0',
                        agreed_date=client.created_at,
                        agreed_ip_address='127.0.0.1',
                        is_active=True,
                    ))

                db.session.add(UserPrivacySetting(
                    user_id=client.user_id,
                    allow_data_analytics=True,
                    allow_session_recordings=False,
                    share_progress_with_therapist=True,
                    encrypted_storage_preference=True,
                    data_retention_days=730,
                ))

                relationship = ClientTherapistRelationship(
                    client_id=client.user_id,
                    therapist_id=therapist.user_id,
                    status='active',
                    relationship_start_date=rand_date_ago(30, 90),
                    client_goals="Improve emotional regulation and develop healthy coping strategies.",
                )
                db.session.add(relationship)
                db.session.flush()

                priority_mix = random.choice([
                    ['LOW', 'LOW', 'MEDIUM'],
                    ['LOW', 'MEDIUM', 'HIGH'],
                    ['MEDIUM', 'MEDIUM', 'LOW', 'LOW'],
                    ['LOW', 'CRITICAL'],
                    ['MEDIUM', 'HIGH', 'LOW'],
                    ['LOW', 'LOW', 'MEDIUM', 'HIGH'],
                ])

                for cap_idx, priority in enumerate(priority_mix):
                    scenario    = random.choice(CAPSULE_SCENARIOS[priority])
                    is_sealed   = cap_idx < len(priority_mix) - 1
                    cap_created = days_ago(random.randint(2, 60))
                    sealed_at   = cap_created + timedelta(days=random.randint(1, 5)) if is_sealed else None

                    capsule = Capsule(
                        client_id=client.user_id,
                        therapist_id=therapist.user_id,
                        relationship_id=relationship.relationship_id,
                        title=scenario['title'],
                        user_tag=scenario['tag'],
                        status='sealed' if is_sealed else 'open',
                        priority_level=priority,
                        priority_score=_priority_score(priority),
                        priority_analyzed_at=cap_created + timedelta(hours=1),
                        priority_reasons={
                            'risk_flags': _risk_flags(priority),
                            'sentiment_summary': f"{priority} priority: {scenario['title']}",
                            'reasons': [f'Seeded scenario for testing — {priority} level'],
                        },
                        priority_reviewed_by_therapist=is_sealed and random.random() > 0.3,
                        created_at=cap_created,
                        sealed_at=sealed_at,
                    )
                    db.session.add(capsule)
                    db.session.flush()

                    for msg_text in scenario['messages']:
                        db.session.add(Message(
                            capsule_id=capsule.capsule_id,
                            sender_id=client.user_id,
                            content=msg_text,
                            created_at=cap_created + timedelta(hours=random.randint(0, 12)),
                        ))

                    if is_sealed:
                        db.session.add(Message(
                            capsule_id=capsule.capsule_id,
                            sender_id=therapist.user_id,
                            content=random.choice(THERAPIST_RESPONSES),
                            created_at=sealed_at + timedelta(hours=random.randint(1, 48)),
                        ))

                    if priority == 'CRITICAL':
                        crisis = CrisisEvent(
                            client_id=client.user_id,
                            relationship_id=relationship.relationship_id,
                            crisis_type=random.choice(['suicidal_ideation', 'self_harm']),
                            severity_level=random.randint(8, 10),
                            description=scenario['messages'][0],
                            status=random.choice(['logged', 'in_progress']),
                            therapist_notified=True,
                            therapist_notification_date=cap_created + timedelta(minutes=5),
                            created_at=cap_created,
                        )
                        db.session.add(crisis)
                        db.session.flush()

                        db.session.add(Notification(
                            user_id=therapist.user_id,
                            notification_type='crisis_alert',
                            title='High-Severity Crisis Alert',
                            message=f'{client.first_name} {client.last_name} has logged a critical crisis event.',
                            related_entity_type='crisis_event',
                            related_entity_id=crisis.crisis_id,
                            is_read=random.random() > 0.4,
                            created_at=cap_created + timedelta(minutes=5),
                        ))

                    if priority == 'HIGH' and random.random() > 0.5:
                        db.session.add(Notification(
                            user_id=therapist.user_id,
                            notification_type='priority_high',
                            title='High Priority Capsule',
                            message=f'A capsule from {client.first_name} has been flagged HIGH priority.',
                            related_entity_type='capsule',
                            related_entity_id=capsule.capsule_id,
                            is_read=random.random() > 0.5,
                            created_at=cap_created + timedelta(minutes=10),
                        ))

        # ── Therapist consent + privacy ───────────────────────
        for therapist in therapist_users:
            for agreement_type in ['terms_of_service', 'privacy_policy']:
                db.session.add(ConsentAgreement(
                    user_id=therapist.user_id,
                    agreement_type=agreement_type,
                    version='1.0',
                    agreed_date=therapist.created_at,
                    agreed_ip_address='127.0.0.1',
                    is_active=True,
                ))
            db.session.add(UserPrivacySetting(
                user_id=therapist.user_id,
                allow_data_analytics=True,
                allow_session_recordings=False,
                share_progress_with_therapist=False,
                encrypted_storage_preference=True,
                data_retention_days=730,
            ))

        db.session.commit()

        print(f"✓ Created 21 clients across 3 therapists")
        print(f"✓ Created {Capsule.query.count()} capsules")
        print(f"✓ Created {Message.query.count()} messages")
        print(f"✓ Created {CrisisEvent.query.count()} crisis events")
        print(f"✓ Created {Notification.query.count()} notifications")
        print()
        print("── Login credentials ──────────────────────────────")
        print("Therapists  (password: Therapist@1234)")
        for t in THERAPISTS:
            print(f"  {t['email']}")
        print()
        print("Clients  (password: Client@1234)")
        for group in CLIENTS_PER_THERAPIST:
            for c in group:
                print(f"  {c['email']}")
        print()
        print("🌱 Seed complete.")


# ── Flask CLI registration ────────────────────────────────────

def register_seed_command(app):
    import click

    @app.cli.command('seed-db')
    def seed_db():
        """Seed the database with test therapists, clients, capsules and messages."""
        seed(app)


# ── Standalone entry point ────────────────────────────────────

if __name__ == '__main__':
    from app import create_app
    seed(create_app())