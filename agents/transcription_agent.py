# agents/transcription_agent.py
# Upload audio to Azure Blob Storage and transcribe it

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.azure_clients import get_transcribe_client, get_container_client

load_dotenv()


# ─────────────────────────────────────────
# Step 1 — Upload audio to Azure Blob
# ─────────────────────────────────────────
def upload_audio(file_path: str) -> str:
    """Upload local audio file to Azure Blob Storage"""

    file_path = Path(file_path)
    blob_name = f"meetings/{file_path.name}"

    container = get_container_client()

    with open(file_path, "rb") as f:
        container.upload_blob(
            name=blob_name,
            data=f,
            overwrite=True
        )

    logger.info(f"✅ Uploaded: {blob_name}")
    return blob_name


# ─────────────────────────────────────────
# Step 2 — Transcribe audio
# ─────────────────────────────────────────
def transcribe_audio(file_path: str) -> dict:
    """Transcribe audio using Azure OpenAI gpt-4o-transcribe-diarize"""

    file_path = Path(file_path)

    logger.info(f"🎙️ Transcribing: {file_path.name} ...")

    with open(file_path, "rb") as audio_file:
        transcribe_client = get_transcribe_client()
        response = transcribe_client.audio.transcriptions.create(
            model=os.getenv("AZURE_TRANSCRIBE_DEPLOYMENT"),
            file=audio_file,
            response_format="diarized_json",
            chunking_strategy="auto",
        )

    # Convert response to dictionary
    response_dict = response.model_dump() if hasattr(response, "model_dump") else dict(response)

    transcript_lines = []

    # diarization may return utterances or segments
    utterances = response_dict.get("utterances") or response_dict.get("segments") or []

    if utterances:
        for u in utterances:
            speaker = u.get("speaker", u.get("speaker_id", "?"))
            text = u.get("text", "")
            transcript_lines.append(f"Speaker {speaker}: {text}")

        labeled_transcript = "\n".join(transcript_lines)

    else:
        labeled_transcript = response_dict.get("text", "")
        logger.warning("⚠️  No speaker labels — using plain transcript")

    result = {
        "file_name": file_path.name,
        "full_transcript": response_dict.get("text", ""),
        "labeled_transcript": labeled_transcript,
        "duration_seconds": response_dict.get("duration", None),
    }

    logger.info("✅ Transcription complete!")
    logger.info("\n--- TRANSCRIPT PREVIEW ---")
    logger.info(labeled_transcript[:500])
    logger.info("...")

    return result


# ─────────────────────────────────────────
# Full pipeline
# ─────────────────────────────────────────
def process_audio(file_path: str) -> dict:
    """Upload audio to blob storage then transcribe it"""

    upload_audio(file_path)
    return transcribe_audio(file_path)


# ─────────────────────────────────────────
# Test script
# ─────────────────────────────────────────
if __name__ == "__main__":

    test_file = "test_meeting.wav"

    if not os.path.exists(test_file):
        logger.warning("⚠️  No test audio file found!")
        logger.info("👉 Add a file named 'test_meeting.wav' in the project folder")

    else:
        result = process_audio(test_file)

        logger.info("\n✅ Full Result:")
        logger.info(result)