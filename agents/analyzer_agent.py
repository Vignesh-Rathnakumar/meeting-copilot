# agents/analyzer_agent.py
# Reads transcript and extracts action items, decisions, and summary

import os
import sys
import json
import time
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.azure_clients import gpt_client

load_dotenv()


# ─────────────────────────────────────────
# Utility: Safe JSON Parse
# ─────────────────────────────────────────
def safe_json_parse(raw_text: str):
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return None


# ─────────────────────────────────────────
# Utility: Validate Output Schema
# ─────────────────────────────────────────
def validate_schema(data: dict) -> bool:
    required_keys = ["summary", "action_items", "decisions", "attendees", "follow_up_needed"]

    if not all(key in data for key in required_keys):
        return False

    if not isinstance(data["action_items"], list):
        return False

    for item in data["action_items"]:
        if not all(k in item for k in ["owner", "task", "deadline", "priority"]):
            return False

    return True


# ─────────────────────────────────────────
# Clean GPT Response (remove markdown)
# ─────────────────────────────────────────
def clean_response(raw: str) -> str:
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


# ─────────────────────────────────────────
# Analyze transcript with GPT-4o (robust)
# ─────────────────────────────────────────
def analyze_transcript(labeled_transcript: str, retries: int = 3) -> dict:
    """
    Send transcript to GPT-4o and extract structured meeting insights.
    Includes retry + validation for production reliability.
    """

    print("🧠 Analyzing transcript with GPT-4o...")

    prompt = f"""
You are an expert meeting analyst. Analyze the following meeting transcript and extract structured information.

TRANSCRIPT:
{labeled_transcript}

Return a JSON object with exactly this structure:
{{
    "summary": "2-3 sentence summary of the meeting",
    "action_items": [
        {{
            "owner": "person's name",
            "task": "what they need to do",
            "deadline": "deadline mentioned or 'Not specified'",
            "priority": "high/medium/low"
        }}
    ],
    "decisions": [
        "decision 1",
        "decision 2"
    ],
    "attendees": ["name1", "name2"],
    "follow_up_needed": true or false
}}

Rules:
- Extract REAL names from the transcript, not Speaker A/B
- If no deadline mentioned, use "Not specified"
- Be concise and specific
- Return ONLY valid JSON
"""

    for attempt in range(retries):
        try:
            response = gpt_client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
                messages=[
                    {
                        "role": "system",
                        "content": "You must return STRICT valid JSON only. No explanation."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,
                max_tokens=1000,
            )

            raw = response.choices[0].message.content.strip()
            cleaned = clean_response(raw)

            parsed = safe_json_parse(cleaned)

            if parsed and validate_schema(parsed):
                print("✅ Analysis complete!")
                print("\n--- ANALYSIS RESULT ---")
                print(json.dumps(parsed, indent=2))
                return parsed

            print(f"⚠️ Invalid JSON (attempt {attempt + 1}/{retries})")

        except Exception as e:
            print(f"⚠️ Error (attempt {attempt + 1}/{retries}): {e}")

        time.sleep(1)

    raise ValueError("❌ Failed to get valid structured response after retries")


# ─────────────────────────────────────────
# Test
# ─────────────────────────────────────────
if __name__ == "__main__":

    test_transcript = """
Speaker A: Hi everyone, let's start the meeting. John will handle the UI design and it should be done by Friday.
Speaker B: Sure, I will complete the design by Friday. Sarah should handle the testing by next Monday.
Speaker A: Great, we also decided to launch version two in April. Any objections?
Speaker B: No objections from my side. Let's go ahead with the April launch.
"""

    result = analyze_transcript(test_transcript)

    print("\n✅ Full Result:")
    print(result)