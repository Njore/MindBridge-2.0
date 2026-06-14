"""
MindBridge Extras Seed Script
==============================
Run this AFTER seed.py has already run.
Adds to existing users — does NOT create any new users.

Creates:
  - 2 therapeutic prompts per client (from their therapist)
  - 1 client response per prompt (so prompts have replies)
  - 2 private pocket journal entries per client

Run:
    flask seed-extras
OR standalone:
    python seed_extras.py
"""

import os
import bcrypt
from datetime import datetime, date, timedelta
from cryptography.fernet import Fernet
import random

from models import (
    db, User, ClientTherapistRelationship,
    TherapeuticPrompt, PromptResponse,
    PrivatePocket, Notification
)


# ── Encryption (must match client.py) ────────────────────────
# Reads ENCRYPTION_KEY from .env — same key the app uses.
# If not set, generates a fresh one (dev only, entries won't
# be readable by the app in that case — set the key in .env).

def _get_cipher():
    key = os.getenv('ENCRYPTION_KEY')
    if key:
        return Fernet(key.encode())
    print("⚠️  ENCRYPTION_KEY not set in .env — generating a temporary key.")
    print("   Journal entries seeded this way will NOT be readable by the app.")
    print("   Add ENCRYPTION_KEY to your .env and re-run to fix this.")
    return Fernet(Fernet.generate_key())


# ── Prompt seed data ──────────────────────────────────────────

PROMPTS = [
    {
        'prompt_type': 'reflection',
        'title': 'End of Week Reflection',
        'description': 'A guided reflection on your emotional experiences this week.',
        'prompt_content': (
            'Take a few quiet minutes and think about the past seven days. '
            'What emotions came up most often? Were there moments where you handled '
            'something better than you expected? Were there moments you wish had gone differently? '
            'Write freely — there are no right answers here.'
        ),
        'instructions': 'Write for at least 10 minutes without stopping to edit yourself.',
        'expected_duration_minutes': 15,
        'frequency': 'weekly',
    },
    {
        'prompt_type': 'cbt_exercise',
        'title': 'Thought Record — Challenging a Negative Belief',
        'description': 'A CBT thought record to examine and challenge an unhelpful thought pattern.',
        'prompt_content': (
            'Think of a situation this week where you felt distressed. '
            'Write down: (1) the situation, (2) the automatic thought that came up, '
            '(3) the emotion and how intense it was (0-100%), '
            '(4) evidence that supports the thought, '
            '(5) evidence that does NOT support the thought, '
            '(6) a more balanced alternative thought.'
        ),
        'instructions': 'Be as specific as possible in step 1 — the more concrete the situation, the more useful the exercise.',
        'expected_duration_minutes': 20,
        'frequency': 'once',
    },
    {
        'prompt_type': 'gratitude',
        'title': 'Three Good Things',
        'description': 'A positive psychology exercise to shift attention toward what is going well.',
        'prompt_content': (
            'Write down three things that went well today or this week — '
            'they can be small (a good cup of tea, a kind interaction) or significant. '
            'For each one, write a sentence about why it happened or what it means to you.'
        ),
        'instructions': 'Try not to repeat the same things each time you do this exercise.',
        'expected_duration_minutes': 10,
        'frequency': 'weekly',
    },
    {
        'prompt_type': 'emotion_check',
        'title': 'Body Scan — Where Do You Hold Stress?',
        'description': 'A mindfulness exercise to connect physical sensations with emotional states.',
        'prompt_content': (
            'Find a comfortable position and close your eyes for a moment. '
            'Starting from your feet and moving upward, notice any tension, tightness, or discomfort. '
            'When you find something, pause and ask: what emotion might be connected to this sensation? '
            'After the scan, write down what you noticed — both physically and emotionally.'
        ),
        'instructions': 'There is no wrong way to do this. Write whatever came up, even if it feels strange.',
        'expected_duration_minutes': 15,
        'frequency': 'once',
    },
    {
        'prompt_type': 'goal_setting',
        'title': 'One Small Step This Week',
        'description': 'A structured exercise to translate a larger goal into a concrete action.',
        'prompt_content': (
            'Think about something you have been wanting to change or work on. '
            'Now break it down: what is the smallest possible step you could take toward it this week? '
            'Not the full thing — just one step that would take 15 minutes or less. '
            'Write down what it is, when you will do it, and what might get in the way.'
        ),
        'instructions': 'The goal is not to solve the whole problem — just to move the needle slightly.',
        'expected_duration_minutes': 10,
        'frequency': 'weekly',
    },
]

# Client responses — realistic, varied in length and tone
PROMPT_RESPONSES = {
    'reflection': [
        {
            'response_content': (
                "This week was exhausting but I think I managed better than last week. "
                "Monday was the hardest — I had a panic moment in a meeting but I used the breathing "
                "technique and it actually helped. By Wednesday I felt more settled. "
                "I'm noticing that my mood really depends on how much sleep I get. "
                "When I sleep badly everything feels harder. I want to work on that."
            ),
            'insights_gained': "Sleep is more connected to my mood than I realised.",
            'emotional_state': 'cautiously hopeful',
        },
        {
            'response_content': (
                "Honestly this week I just went through the motions. "
                "Work, home, sleep, repeat. I didn't feel much — not bad, not good. Just flat. "
                "I'm not sure if that's progress or avoidance. "
                "One good moment: my sister called and we talked for an hour. That was nice."
            ),
            'insights_gained': "Connection with family lifts my mood even when I don't expect it.",
            'emotional_state': 'neutral, slightly disconnected',
        },
    ],
    'cbt_exercise': [
        {
            'response_content': (
                "Situation: My manager didn't respond to my email for two days.\n"
                "Automatic thought: She thinks my work is bad and she's avoiding me.\n"
                "Emotion: Anxiety, about 75%.\n"
                "Evidence for: She usually responds same day. Silence feels pointed.\n"
                "Evidence against: She was in back-to-back meetings. She replied on day 3 with nothing wrong.\n"
                "Alternative thought: People are busy and delayed responses usually mean nothing about me."
            ),
            'insights_gained': "I jump to personal explanations for neutral events.",
            'emotional_state': 'anxious, then relieved after reflection',
        },
        {
            'response_content': (
                "Situation: I made a mistake in a report at work.\n"
                "Automatic thought: I'm incompetent. Everyone will notice. I'll get fired.\n"
                "Emotion: Shame and fear, about 85%.\n"
                "Evidence for: The mistake was in a section I should know well.\n"
                "Evidence against: I've never been in trouble at work before. Everyone makes mistakes. "
                "I caught it before it caused any problem.\n"
                "Alternative: I made a mistake. It's been corrected. That's it."
            ),
            'insights_gained': "I catastrophise small mistakes. The shame response is disproportionate.",
            'emotional_state': 'ashamed, working through it',
        },
    ],
    'gratitude': [
        {
            'response_content': (
                "1. My coffee this morning — I sat with it for 10 minutes without looking at my phone. "
                "It happened because I set my phone across the room last night.\n"
                "2. A colleague said my presentation was clear and helpful. "
                "It meant something because I had worked hard on it.\n"
                "3. The weather was cool enough to walk home. Small thing but it reset my mood."
            ),
            'insights_gained': "Small intentional moments matter more than I give them credit for.",
            'emotional_state': 'warm, grounded',
        },
        {
            'response_content': (
                "1. Finished a book I'd been meaning to read for months. Felt good.\n"
                "2. Cooked a proper meal instead of ordering food — first time this week.\n"
                "3. A friend texted to check in without me reaching out first. "
                "Reminded me people think of me even when I'm quiet."
            ),
            'insights_gained': "Taking care of basics like cooking affects my self-esteem.",
            'emotional_state': 'content',
        },
    ],
    'emotion_check': [
        {
            'response_content': (
                "Shoulders and jaw. That's where I hold everything apparently. "
                "I noticed my shoulders were basically up by my ears and I hadn't even realised. "
                "When I stayed with the jaw tension I felt something like dread — vague, no specific cause. "
                "After the scan I felt slightly lighter, like acknowledging it released some of it."
            ),
            'insights_gained': "My body is carrying stress I'm not consciously registering.",
            'emotional_state': 'tense, then slightly lighter',
        },
        {
            'response_content': (
                "Mostly in my chest and stomach. "
                "The chest thing felt like anticipation or low-level worry. "
                "The stomach was more like dread. "
                "I think it's about the conversation I've been avoiding with my mum. "
                "Writing this out makes it feel more manageable than it did in my body."
            ),
            'insights_gained': "Avoidance is physically expensive.",
            'emotional_state': 'anxious but more aware',
        },
    ],
    'goal_setting': [
        {
            'response_content': (
                "I want to exercise more but I keep not doing it. "
                "Smallest step: put on running shoes and walk around the block. That's it. No gym, no plan. "
                "I'll do it Wednesday after work. "
                "What might get in the way: I'll be tired and I'll convince myself I'll do it tomorrow. "
                "Plan: shoes go by the door tonight."
            ),
            'insights_gained': "I overcomplicate goals and then feel bad when I don't meet them.",
            'emotional_state': 'motivated but realistic',
        },
        {
            'response_content': (
                "I've been meaning to call my dad for three weeks. We don't have an easy relationship "
                "but I know it matters. "
                "Smallest step: send him a WhatsApp message this evening. Not a call — just a message. "
                "What might stop me: I'll overthink what to say. "
                "Plan: keep it simple. 'Hi dad, thinking of you. Hope you're well.'"
            ),
            'insights_gained': "I let perfect be the enemy of good with relationships too.",
            'emotional_state': 'slightly anxious, determined',
        },
    ],
}

# Journal (private pocket) entries
POCKET_ENTRIES = [
    # Entry set 1 — a reflective day
    [
        (1, "Today was heavy. I woke up already tired and couldn't figure out why. Work was okay but I felt like I was performing being okay rather than actually being okay. I ate lunch alone which was fine but also felt lonely. I'm not sure what I want."),
        (2, "One moment that was good: a bird sat on my windowsill for about a minute. I watched it and felt completely present for that minute. I want more of those moments."),
        (3, "Things I'm grateful for today: my flat is warm, I have food, I spoke to one person who made me feel seen."),
    ],
    # Entry set 2 — a better day
    [
        (1, "Actually had a decent day. Woke up early without the alarm which felt like a good sign. Got some things done at work that had been sitting on my list. Small victory but it mattered."),
        (2, "I've been thinking about what my therapist said about the inner critic. I noticed it today when I made a small mistake — it started up immediately but then I caught it. Said to myself 'that's the critic, not the truth.' It helped."),
        (4, "I want to be kinder to myself. Not in a vague way — in a specific way. Like not skipping meals because I'm busy. Like going to bed when I'm tired instead of scrolling. I'm going to try this week."),
    ],
]


# ── Main extras seed function ─────────────────────────────────

def seed_extras(app):
    with app.app_context():
        from dotenv import load_dotenv
        load_dotenv()

        cipher = _get_cipher()

        # Fetch all therapist–client relationships we seeded
        relationships = ClientTherapistRelationship.query.filter_by(
            status='active'
        ).all()

        if not relationships:
            print("❌ No active relationships found. Run 'flask seed-db' first.")
            return

        # # Check if extras already seeded
        # if TherapeuticPrompt.query.count() > 0:
        #     print("⚠️  Prompts already exist. Skipping to avoid duplicates.")
        #     print("   Run 'flask reset-db' then 'flask seed-db' then 'flask seed-extras' for a clean reseed.")
        #     return

        print("🌱 Seeding extras (prompts, responses, journal entries)...")

        prompt_count    = 0
        response_count  = 0
        pocket_count    = 0

        for rel in relationships:
            therapist = User.query.get(rel.therapist_id)
            client    = User.query.get(rel.client_id)

            if not therapist or not client:
                continue

            # ── 2 prompts per client ──────────────────────────
            selected_prompts = random.sample(PROMPTS, k=2)

            for p_data in selected_prompts:
                prompt_created = datetime.utcnow() - timedelta(days=random.randint(5, 20))

                prompt = TherapeuticPrompt(
                    therapist_id=rel.therapist_id,
                    relationship_id=rel.relationship_id,
                    prompt_type=p_data['prompt_type'],
                    title=p_data['title'],
                    description=p_data['description'],
                    prompt_content=p_data['prompt_content'],
                    instructions=p_data['instructions'],
                    expected_duration_minutes=p_data['expected_duration_minutes'],
                    delivery_timing='immediate',
                    frequency=p_data['frequency'],
                    is_active=True,
                    created_at=prompt_created,
                )
                db.session.add(prompt)
                db.session.flush()
                prompt_count += 1

                # Notify client
                db.session.add(Notification(
                    user_id=rel.client_id,
                    notification_type='new_prompt',
                    title='New Therapeutic Prompt',
                    message=f'Your therapist has sent you a new prompt: {p_data["title"]}',
                    related_entity_type='prompt',
                    related_entity_id=prompt.prompt_id,
                    is_read=random.random() > 0.4,
                    created_at=prompt_created,
                ))

                # ── Client response to this prompt ────────────
                response_pool = PROMPT_RESPONSES.get(p_data['prompt_type'], [])
                if response_pool:
                    r_data = random.choice(response_pool)
                    response_created = prompt_created + timedelta(days=random.randint(1, 4))

                    response = PromptResponse(
                        prompt_id=prompt.prompt_id,
                        client_id=rel.client_id,
                        relationship_id=rel.relationship_id,
                        response_content=r_data['response_content'],
                        insights_gained=r_data['insights_gained'],
                        emotional_state=r_data['emotional_state'],
                        response_date=response_created.date(),
                        is_shared_with_therapist=True,
                        created_at=response_created,
                    )
                    db.session.add(response)
                    response_count += 1

                    # Notify therapist of response
                    db.session.add(Notification(
                        user_id=rel.therapist_id,
                        notification_type='prompt_response',
                        title='Client Responded to Prompt',
                        message=f'{client.first_name} responded to: {p_data["title"]}',
                        related_entity_type='prompt',
                        related_entity_id=prompt.prompt_id,
                        is_read=random.random() > 0.5,
                        created_at=response_created,
                    ))

            # ── 2 journal entries per client ──────────────────
            selected_entries = random.sample(POCKET_ENTRIES, k=2)

            for entry_idx, entry_set in enumerate(selected_entries):
                entry_date = date.today() - timedelta(days=(entry_idx + 1) * 3)

                for pocket_number, raw_content in entry_set:
                    # Encrypt exactly as client.py does
                    encrypted = cipher.encrypt(raw_content.encode()).decode()

                    # Respect the unique constraint (client_id, date, pocket_number)
                    existing = PrivatePocket.query.filter_by(
                        client_id=rel.client_id,
                        date=entry_date,
                        pocket_number=pocket_number,
                    ).first()

                    if not existing:
                        db.session.add(PrivatePocket(
                            client_id=rel.client_id,
                            date=entry_date,
                            pocket_number=pocket_number,
                            content=encrypted,
                        ))
                        pocket_count += 1

        db.session.commit()

        print(f"✓ Created {prompt_count} therapeutic prompts")
        print(f"✓ Created {response_count} prompt responses")
        print(f"✓ Created {pocket_count} journal pocket entries")
        print()
        print("🌱 Extras seed complete.")


# ── Flask CLI registration ────────────────────────────────────

def register_seed_extras_command(app):
    @app.cli.command('seed-extras')
    def seed_extras_cmd():
        """Seed prompts, responses and journal entries for existing users."""
        seed_extras(app)


# ── Standalone entry point ────────────────────────────────────

if __name__ == '__main__':
    from app import create_app
    seed_extras(create_app())