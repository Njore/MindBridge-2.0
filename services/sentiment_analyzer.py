import requests
import json
import re
from datetime import datetime
from typing import Dict, List


class GraniteSentimentAnalyzer:
    """Analyze message sentiment using Granite AI (via Ollama API)"""

    def __init__(self, model_name="granite4:micro-h", base_url="http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url
        self.api_url = f"{base_url}/api/chat"

    def _call_ollama(self, prompt: str) -> Dict:
        """Make API call to Ollama with robust JSON parsing"""
        try:
            response = requests.post(
                self.api_url,
                json={
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "format": "json"
                },
                timeout=60
            )

            if response.status_code != 200:
                print(f"Ollama API error: {response.status_code} - {response.text}")
                return {}

            result = response.json()
            raw_content = result.get('message', {}).get('content', '')
            print(f"[Granite raw response]: {raw_content[:300]}")

            try:
                return json.loads(raw_content)
            except json.JSONDecodeError:
                pass

            match = re.search(r'\{.*\}', raw_content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass

            print(f"[Granite] Could not parse JSON from response: {raw_content[:200]}")
            return {}

        except requests.exceptions.ConnectionError:
            print(f"Error: Cannot connect to Ollama at {self.base_url}")
            return {}
        except requests.exceptions.Timeout:
            print("Error: Ollama timed out — model may still be loading, try again")
            return {}
        except Exception as e:
            print(f"Ollama API call error: {e}")
            return {}

    def analyze_capsule_messages(self, messages: List[str]) -> Dict:
        """
        Analyze all messages in a capsule and determine clinical priority.
        Delegates the actual assessment to Granite's own training.
        """
        if not messages:
            return {
                'priority_level': 'LOW',
                'priority_score': 0.0,
                'reasons': ['No messages to analyze'],
                'risk_flags': [],
                'sentiment_summary': ''
            }

        combined_text = "\n".join(messages)
        if len(combined_text) > 3000:
            combined_text = combined_text[:3000] + "..."

        result = self._analyze_with_single_call(combined_text)

        return {
            'priority_level': result.get('priority_level', 'LOW'),
            'priority_score': result.get('priority_score', 0.0),
            'reasons': result.get('reasons', []),
            'risk_flags': result.get('risk_flags', []),
            'sentiment_summary': result.get('summary', '')
        }

    def _analyze_with_single_call(self, text: str) -> Dict:
        """
        Lets Granite assess the message using its own clinical understanding.
        We define the output shape — Granite determines the clinical content.
        """

        prompt = f"""You are a clinical AI assistant embedded in a mental health support platform. A therapist will review your assessment.

Read the client message below and use your clinical understanding of mental health, emotional distress, and psychotherapy to assess it. Trust your own judgment — do not follow mechanical scoring rules.

Client message:
{text}

Assess:
- How urgent is this? Does anything in the message signal immediate risk to the client's safety or wellbeing?
- What emotional state is the client in? What themes or patterns do you notice?
- What clinical risk flags, if any, are present?

Then return ONLY a valid JSON object in this exact shape — no explanation, no markdown:

{{
  "priority_level": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW",
  "priority_score": <float between 0.0 and 1.0>,
  "reasons": ["<your clinical reasoning, one point per item>"],
  "risk_flags": ["<only clinically significant flags, e.g. suicidal_ideation, self_harm, dissociation, hopelessness, severe_anxiety, panic, depression, sadness, none>"],
  "summary": "<one sentence describing the client's current emotional state and what needs attention>"
}}

Use CRITICAL for any immediate safety concern. Use your clinical judgment for everything else. Return only the JSON."""

        try:
            result = self._call_ollama(prompt)

            if not result:
                return self._get_default_result()

            valid_levels = {'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'}
            level = str(result.get('priority_level', 'LOW')).upper()
            if level not in valid_levels:
                level = 'LOW'

            return {
                'priority_level': level,
                'priority_score': float(result.get('priority_score', 0.0)),
                'reasons': result.get('reasons', ['Analysis completed']),
                'risk_flags': result.get('risk_flags', []),
                'summary': result.get('summary', 'Message analyzed')
            }

        except Exception as e:
            print(f"Analysis error: {e}")
            return self._get_default_result()

    def _get_default_result(self) -> Dict:
        return {
            'priority_level': 'LOW',
            'priority_score': 0.0,
            'reasons': ['Analysis unavailable'],
            'risk_flags': [],
            'summary': 'Unable to analyze message'
        }


analyzer = GraniteSentimentAnalyzer(model_name="granite4:micro-h")