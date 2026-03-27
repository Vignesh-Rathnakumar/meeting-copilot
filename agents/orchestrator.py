# agents/orchestrator.py
# Orchestrates the full meeting processing pipeline:
# 1. Transcribe audio → labeled transcript
# 2. Analyze transcript → structured JSON
# 3. Optionally: create tasks and send emails
# 4. Store results and cache

import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.transcription_agent import process_audio as transcribe
from agents.analyzer_agent import analyze_transcript
from agents.task_agent import create_tasks as create_tasks_from_items
from agents.email_agent import send_meeting_summary

load_dotenv()
logger = logging.getLogger(__name__)


def generate_meeting_id():
    """Generate unique meeting ID based on timestamp"""
    return datetime.now().strftime("meeting_%Y%m%d_%H%M%S")


def save_meeting_result(meeting_id: str, data: dict):
    """
    Save complete meeting result to outputs directory.

    Args:
        meeting_id: Unique identifier for the meeting
        data: Dictionary containing transcript, analysis, file_name, etc.
    """
    os.makedirs("outputs", exist_ok=True)

    filename = f"outputs/{meeting_id}.json"

    with open(filename, "w") as f:
        json.dump(data, f, indent=2, default=str)

    logger.info(f"💾 Saved meeting result to {filename}")

    return filename


def load_meeting_result(meeting_id: str) -> dict:
    """
    Load meeting result from outputs directory.

    Args:
        meeting_id: Meeting identifier

    Returns:
        Meeting data dictionary or None if not found
    """
    filepath = f"outputs/{meeting_id}.json"

    if not os.path.exists(filepath):
        return None

    with open(filepath, "r") as f:
        return json.load(f)


def list_meetings(limit: int = 50):
    """
    List all meetings in outputs directory, sorted by date (newest first).

    Args:
        limit: Maximum number of meetings to return

    Returns:
        List of meeting metadata dictionaries
    """
    if not os.path.exists("outputs"):
        return []

    meetings = []

    for filename in sorted(os.listdir("outputs"), reverse=True):
        if filename.startswith("meeting_") and filename.endswith(".json"):
            filepath = os.path.join("outputs", filename)
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                    meetings.append({
                        "id": filename.replace(".json", ""),
                        "file_name": data.get("file_name", "Unknown"),
                        "timestamp": data.get("timestamp", filename.split("_")[1] + "_" + filename.split("_")[2].replace(".json", "")),
                        "summary": data.get("analysis", {}).get("summary", "No summary")[:100] + "...",
                        "attendees": data.get("analysis", {}).get("attendees", []),
                        "action_items_count": len(data.get("analysis", {}).get("action_items", [])),
                    })
            except Exception as e:
                logger.warning(f"⚠️  Error reading {filename}: {e}")

            if len(meetings) >= limit:
                break

    return meetings


def process_meeting(
    file_path: str,
    send_email: bool = False,
    create_tasks: bool = False,
    attendees_emails: list = None
) -> dict:
    """
    Process a meeting audio file: transcribe, analyze, optionally send email/create tasks.

    Args:
        file_path: Path to audio file (or text file with .txt extension)
        send_email: Whether to send follow-up email after processing
        create_tasks: Whether to create tasks from action items
        attendees_emails: List of email addresses to send summary to (if None, uses extracted attendees)

    Returns:
        Dictionary with complete meeting data including transcript, analysis, and status
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"🚀 Starting meeting processing: {Path(file_path).name}")
    logger.info(f"{'='*60}\n")

    meeting_id = generate_meeting_id()
    result = {
        "meeting_id": meeting_id,
        "file_name": Path(file_path).name,
        "timestamp": datetime.now().isoformat(),
        "transcript": None,
        "analysis": None,
        "email_sent": False,
        "tasks_created": False,
        "status": "processing"
    }

    try:
        # ─────────────────────────────────────────
        # Step 1: Transcribe (audio) or load text
        # ─────────────────────────────────────────
        file_ext = Path(file_path).suffix.lower()

        if file_ext in [".mp3", ".wav", ".m4a", ".ogg", ".flac"]:
            logger.info("🎙️  Step 1: Transcribing audio...")
            transcript_data = transcribe(file_path)
            labeled_transcript = transcript_data.get("labeled_transcript", "")
            result["transcript"] = transcript_data
        elif file_ext == ".txt":
            logger.info("📄 Step 1: Loading text transcript...")
            with open(file_path, "r", encoding="utf-8") as f:
                labeled_transcript = f.read()
            result["transcript"] = {
                "file_name": Path(file_path).name,
                "full_transcript": labeled_transcript,
                "labeled_transcript": labeled_transcript,
                "duration_seconds": None
            }
        else:
            raise ValueError(f"Unsupported file type: {file_ext}. Use audio (.mp3, .wav) or .txt for transcript.")

        logger.info(f"✅ Transcript ready ({len(labeled_transcript)} characters)\n")

        # ─────────────────────────────────────────
        # Step 2: Analyze transcript
        # ─────────────────────────────────────────
        logger.info("🧠 Step 2: Analyzing transcript...")
        analysis = analyze_transcript(labeled_transcript)
        result["analysis"] = analysis
        logger.info(f"✅ Analysis complete: {len(analysis.get('action_items', []))} action items, {len(analysis.get('decisions', []))} decisions\n")

        # ─────────────────────────────────────────
        # Step 3: Create tasks (if requested)
        # ─────────────────────────────────────────
        if create_tasks and analysis.get("action_items"):
            logger.info("📋 Step 3: Creating tasks from action items...")
            try:
                tasks_result = create_tasks_from_items(
                    analysis["action_items"],
                    {
                        "meeting_id": meeting_id,
                        "file_name": result["file_name"],
                        "summary": analysis.get("summary", "")
                    }
                )
                result["tasks_created"] = True
                result["tasks"] = tasks_result
                logger.info(f"✅ Created {len(tasks_result)} tasks\n")
            except Exception as e:
                logger.warning(f"⚠️  Task creation failed: {e}")
                result["tasks_created"] = False
                result["tasks_error"] = str(e)

        # ─────────────────────────────────────────
        # Step 4: Send email (if requested)
        # ─────────────────────────────────────────
        if send_email:
            logger.info("📧 Step 4: Sending email summary...")

            # Determine recipients: attendees_emails override extracted attendees
            recipients = attendees_emails if attendees_emails else analysis.get("attendees", [])

            if not recipients:
                logger.warning("⚠️  No recipients specified for email. Skipping.")
            else:
                try:
                    email_status = send_meeting_summary(
                        analysis=analysis,
                        transcript_preview=labeled_transcript[:500] + "...",
                        recipients=recipients
                    )
                    result["email_sent"] = email_status.get("sent", False)
                    result["email_message_id"] = email_status.get("message_id")
                    result["email_error"] = email_status.get("error")

                    if result["email_sent"]:
                        logger.info(f"✅ Email sent to {len(recipients)} recipients\n")
                    else:
                        logger.warning(f"⚠️  Email failed: {email_status.get('error', 'Unknown error')}\n")
                except Exception as e:
                    logger.warning(f"⚠️  Email sending failed: {e}")
                    result["email_sent"] = False
                    result["email_error"] = str(e)

        # ─────────────────────────────────────────
        # Step 5: Save final result
        # ─────────────────────────────────────────
        logger.info("💾 Step 5: Saving results...")
        save_meeting_result(meeting_id, result)
        result["status"] = "completed"

        # ─────────────────────────────────────────
        # Step 6: Store in RAG memory (if available)
        # ─────────────────────────────────────────
        logger.info("🧠 Step 6: Storing in memory (RAG)...")
        try:
            from memory.rag import MeetingMemory
            memory = MeetingMemory()
            memory.add_meeting(
                meeting_id=meeting_id,
                transcript=labeled_transcript,
                analysis=analysis
            )
            result["in_rag"] = True
            logger.info("✅ Stored in RAG memory\n")
        except ImportError as e:
            result["in_rag"] = False
            logger.warning(f"⚠️  RAG not available: {e}")
        except Exception as e:
            result["in_rag"] = False
            logger.warning(f"⚠️  RAG storage failed: {e}")

        logger.info(f"\n{'='*60}")
        logger.info(f"✅ Meeting processing complete! ID: {meeting_id}")
        logger.info(f"{'='*60}\n")

        return result

    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
        logger.error(f"\n❌ Processing failed: {e}\n")
        raise


if __name__ == "__main__":
    # Quick test with sample text (no audio needed)
    test_transcript = """
    Speaker A: Hi everyone, let's start the meeting. John will handle the UI design and it should be done by Friday.
    Speaker B: Sure, I will complete the design by Friday. Sarah should handle the testing by next Monday.
    Speaker A: Great, we also decided to launch version two in April. Any objections?
    Speaker B: No objections from my side. Let's go ahead with the April launch.
    """

    logger.info("🧪 Testing orchestrator with sample transcript...\n")

    # Save sample transcript to temp file
    temp_file = "temp_test_transcript.txt"
    with open(temp_file, "w") as f:
        f.write(test_transcript)

    try:
        result = process_meeting(temp_file, send_email=False, create_tasks=False)
        logger.info("\n✅ Orchestrator test successful!")
        logger.info(json.dumps(result, indent=2, default=str))
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)
