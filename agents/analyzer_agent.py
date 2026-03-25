# agents/analyzer_agent.py
# Reads transcript and extracts action items, decisions, and summary
# Includes: retry + validation + storage + caching

import os
import sys
import json
import time
import hashlib
from datetime import datetime
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
# Generate hash for caching
# ─────────────────────────────────────────
def get_transcript_hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


# ─────────────────────────────────────────
# Save analysis to file
# ─────────────────────────────────────────
def save_analysis_to_file(data: dict):
    os.makedirs("outputs", exist_ok=True)

    filename = datetime.now().strftime("outputs/meeting_%Y%m%d_%H%M%S.json")

    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

    print(f"💾 Saved analysis to {filename}")


# ─────────────────────────────────────────
# Check cache
# ─────────────────────────────────────────
def load_from_cache(transcript_hash: str):
    cache_file = f"outputs/cache_{transcript_hash}.json"

    if os.path.exists(cache_file):
        print("⚡ Using cached result (no API call)")
        with open(cache_file, "r") as f:
            return json.load(f)

    return None


# ─────────────────────────────────────────
# Save to cache
# ─────────────────────────────────────────
def save_to_cache(transcript_hash: str, data: dict):
    os.makedirs("outputs", exist_ok=True)

    cache_file = f"outputs/cache_{transcript_hash}.json"

    with open(cache_file, "w") as f:
        json.dump(data, f, indent=2)


# ─────────────────────────────────────────
# Analyze transcript with GPT-4o (robust + cache)
# ─────────────────────────────────────────
def analyze_transcript(labeled_transcript: str, retries: int = 3) -> dict:
    print("🧠 Analyzing transcript with GPT-4o...")

    # 🔥 Step 1: Check cache
    transcript_hash = get_transcript_hash(labeled_transcript)
    cached = load_from_cache(transcript_hash)
    if cached:
        return cached

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
                    {"role": "system", "content": "You must return STRICT valid JSON only."},
                    {"role": "user", "content": prompt}
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

                # 💾 Save results
                save_analysis_to_file(parsed)

                # ⚡ Save cache
                save_to_cache(transcript_hash, parsed)

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