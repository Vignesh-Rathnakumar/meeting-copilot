# agents/analyzer_agent.py
# Reads transcript and extracts action items, decisions, and summary

import os
import sys
import json
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.azure_clients import gpt_client

load_dotenv()


# ─────────────────────────────────────────
# Analyze transcript with GPT-4o
# ─────────────────────────────────────────
def analyze_transcript(labeled_transcript: str) -> dict:
    """
    Send transcript to GPT-4o and extract:
    - Meeting summary
    - Action items (owner, task, deadline)
    - Key decisions
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
- Return ONLY the JSON, no extra text
"""

    response = gpt_client.chat.completions.create(
        model=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
        messages=[
            {
                "role": "system",
                "content": "You are a meeting analyst. Always respond with valid JSON only."
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

    # Clean up markdown code blocks if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    result = json.loads(raw)

    print("✅ Analysis complete!")
    print("\n--- ANALYSIS RESULT ---")
    print(json.dumps(result, indent=2))

    return result


# ─────────────────────────────────────────
# Test
# ─────────────────────────────────────────
if __name__ == "__main__":

    # Use our test transcript
    test_transcript = """
Speaker A: Hi everyone, let's start the meeting. John will handle the UI design and it should be done by Friday.
Speaker B: Sure, I will complete the design by Friday. Sarah should handle the testing by next Monday.
Speaker A: Great, we also decided to launch version two in April. Any objections?
Speaker B: No objections from my side. Let's go ahead with the April launch.
"""

    result = analyze_transcript(test_transcript)
    print("\n✅ Full Result:")
    print(result)