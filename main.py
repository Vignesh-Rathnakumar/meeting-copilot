# main.py
# FastAPI backend for Meeting Copilot
# Exposes REST API endpoints for processing meetings, listing results, and searching

import os
import uuid
import logging
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, Request, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import json
from pathlib import Path
from contextlib import asynccontextmanager

from agents.orchestrator import (
    process_meeting,
    list_meetings,
    load_meeting_result
)

# Optional RAG memory integration
try:
    from memory.rag import MeetingMemory
    memory_available = True
except ImportError:
    memory_available = False

# ─────────────────────────────────────────
# Logging Configuration
# ─────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────
# Job Storage (in-memory)
# ─────────────────────────────────────────
jobs = {}

# ─────────────────────────────────────────
# Authentication Dependency
# ─────────────────────────────────────────
def verify_api_key(request: Request):
    """
    Dependency that verifies the X-API-Key header matches API_KEY env var.
    Raises HTTPException with 401 if missing or invalid.
    """
    api_key = request.headers.get("X-API-Key")
    expected_key = os.getenv("API_KEY")

    if not expected_key:
        logger.error("API_KEY environment variable not set")
        raise HTTPException(status_code=500, detail="Server configuration error: API_KEY not set")

    if api_key != expected_key:
        logger.warning(f"Invalid API key attempt: {api_key}")
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    return True

# ─────────────────────────────────────────
# CORS Configuration
# ─────────────────────────────────────────
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:8501")
if allowed_origins:
    allowed_origins = [origin.strip() for origin in allowed_origins.split(",")]
else:
    allowed_origins = ["http://localhost:8501"]

# ─────────────────────────────────────────
# Lifespan Context Manager
# ─────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("="*60)
    logger.info("🚀 Meeting Copilot API starting...")
    logger.info("="*60)

    # Ensure directories exist
    os.makedirs("outputs", exist_ok=True)
    os.makedirs("temp_uploads", exist_ok=True)

    logger.info("✅ Directories ready")
    logger.info(f"📂 Outputs: {os.path.abspath('outputs')}")
    logger.info(f"🌐 API docs: http://localhost:8000/docs")
    logger.info("="*60)

    yield

    # Shutdown
    logger.info("Shutting down...")

# ─────────────────────────────────────────
# FastAPI App Setup
# ─────────────────────────────────────────
app = FastAPI(
    title="Meeting Copilot API",
    description="Process meeting audio, extract insights, create tasks, and manage meeting knowledge.",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────
class ProcessRequest(BaseModel):
    send_email: bool = False
    create_tasks: bool = False
    attendees_emails: Optional[List[str]] = None


class MeetingSummary(BaseModel):
    id: str
    file_name: str
    timestamp: str
    summary: str
    attendees: List[str]
    action_items_count: int


class EmailRequest(BaseModel):
    meeting_id: str
    recipients: List[str]


class TaskRequest(BaseModel):
    meeting_id: str


class SearchRequest(BaseModel):
    query: str
    k: int = 5


# ─────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────
@app.get("/")
def root():
    return {
        "message": "Meeting Copilot API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "process": "/process (POST)",
            "meetings": "/meetings (GET)",
            "meeting_detail": "/meetings/{meeting_id} (GET)",
            "search": "/search (POST)",
            "health": "/health (GET)"
        }
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "memory_available": memory_available,
        "outputs_dir_exists": os.path.exists("outputs")
    }


# ─────────────────────────────────────────
# Background Processing Function
# ─────────────────────────────────────────
def process_meeting_background(
    job_id: str,
    file_path: str,
    send_email: bool,
    create_tasks: bool,
    attendees_emails: Optional[list]
):
    """
    Background task to process a meeting audio file.
    Updates job status in the jobs dictionary.
    """
    try:
        # Update job status to processing
        jobs[job_id] = {"status": "processing"}

        logger.info(f"Job {job_id}: Starting meeting processing")

        # Process the meeting
        result = process_meeting(
            file_path=file_path,
            send_email=send_email,
            create_tasks=create_tasks,
            attendees_emails=attendees_emails
        )

        # Update job status to done with result
        jobs[job_id] = {"status": "done", "result": result}

        # Clean up temp file
        if os.path.exists(file_path):
            os.remove(file_path)

        logger.info(f"Job {job_id}: Processing complete")

    except Exception as e:
        logger.error(f"Job {job_id}: Processing failed - {e}")
        jobs[job_id] = {"status": "error", "detail": str(e)}
        # Clean up temp file on error
        if os.path.exists(file_path):
            os.remove(file_path)


# ─────────────────────────────────────────
# Process Meeting (now async with background tasks)
# ─────────────────────────────────────────
@app.post("/process", dependencies=[Depends(verify_api_key)])
async def process_meeting_endpoint(
    audio: UploadFile = File(...),
    send_email: bool = Form(False),
    create_tasks: bool = Form(False),
    attendees_emails: Optional[str] = Form(None),  # JSON string
    background_tasks: BackgroundTasks = None
):
    """
    Upload and process a meeting audio file (asynchronous).

    - **audio**: Audio file (.mp3, .wav, .m4a, etc.)
    - **send_email**: Whether to send email summary (default: False)
    - **create_tasks**: Whether to create tasks from action items (default: False)
    - **attendees_emails**: Optional JSON string of email addresses (overrides extracted attendees)

    Returns: Immediately with `job_id` (202 Accepted). Use GET /jobs/{job_id} to check status.
    """
    try:
        # Validate file extension
        allowed_extensions = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".txt"}
        file_ext = Path(audio.filename).suffix.lower()

        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file_ext}. Allowed: {', '.join(allowed_extensions)}"
            )

        # Parse attendees_emails if provided
        recipients = None
        if attendees_emails:
            try:
                recipients = json.loads(attendees_emails)
                if not isinstance(recipients, list):
                    raise ValueError("attendees_emails must be a JSON array of strings")
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid JSON in attendees_emails")

        # Save uploaded file temporarily
        temp_dir = "temp_uploads"
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, f"{uuid.uuid4().hex}{file_ext}")

        with open(temp_path, "wb") as f:
            content = await audio.read()
            f.write(content)

        # Generate job ID
        job_id = uuid.uuid4().hex

        # Initialize job status
        jobs[job_id] = {"status": "queued"}

        # Add background task
        background_tasks.add_task(
            process_meeting_background,
            job_id=job_id,
            file_path=temp_path,
            send_email=send_email,
            create_tasks=create_tasks,
            attendees_emails=recipients
        )

        logger.info(f"Job {job_id}: Queued for processing")

        # Return immediately with job ID
        return JSONResponse(
            status_code=202,
            content={
                "job_id": job_id,
                "message": "Processing started",
                "status_url": f"/jobs/{job_id}"
            }
        )

    except HTTPException:
        # Re-raise HTTPExceptions without wrapping
        raise
    except Exception as e:
        logger.error(f"Failed to queue job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jobs/{job_id}")
def get_job_status(job_id: str):
    """
    Get the status of an asynchronous processing job.

    Path params:
    - job_id: Job identifier returned from POST /process

    Returns: Job status and result (if completed)
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    return jobs[job_id]


# ─────────────────────────────────────────
# List All Meetings
# ─────────────────────────────────────────
@app.get("/meetings", response_model=List[MeetingSummary], dependencies=[Depends(verify_api_key)])
def get_meetings(limit: int = 50):
    """
    List all processed meetings, sorted by date (newest first).

    Query params:
    - limit: Maximum number of meetings to return (default: 50)
    """
    meetings = list_meetings(limit=limit)
    return meetings


# ─────────────────────────────────────────
# Get Specific Meeting
# ─────────────────────────────────────────
@app.get("/meetings/{meeting_id}", dependencies=[Depends(verify_api_key)])
def get_meeting(meeting_id: str):
    """
    Get full details of a specific meeting by ID.

    Path params:
    - meeting_id: Meeting identifier (e.g., meeting_20240326_143022)
    """
    meeting = load_meeting_result(meeting_id)

    if not meeting:
        raise HTTPException(status_code=404, detail=f"Meeting '{meeting_id}' not found")

    return meeting


# ─────────────────────────────────────────
# Trigger Email for Existing Meeting
# ─────────────────────────────────────────
@app.post("/meetings/{meeting_id}/send-email", dependencies=[Depends(verify_api_key)])
async def send_meeting_email(meeting_id: str, request: EmailRequest):
    """
    Send meeting summary email for an already processed meeting.

    Path params:
    - meeting_id: Meeting identifier

    Body:
    - recipients: List of email addresses to send to
    """
    try:
        meeting = load_meeting_result(meeting_id)
        if not meeting:
            raise HTTPException(status_code=404, detail=f"Meeting '{meeting_id}' not found")

        analysis = meeting.get("analysis", {})
        transcript_preview = meeting.get("transcript", {}).get("labeled_transcript", "")[:500] + "..."

        from agents.email_agent import send_meeting_summary
        email_status = send_meeting_summary(
            analysis=analysis,
            transcript_preview=transcript_preview,
            recipients=request.recipients
        )

        return {
            "meeting_id": meeting_id,
            "email_sent": email_status.get("sent", False),
            "message_id": email_status.get("message_id"),
            "error": email_status.get("error")
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────
# Create Tasks for Existing Meeting
# ─────────────────────────────────────────
@app.post("/meetings/{meeting_id}/create-tasks", dependencies=[Depends(verify_api_key)])
async def create_meeting_tasks(meeting_id: str):
    """
    Create tasks from action items for an already processed meeting.

    Path params:
    - meeting_id: Meeting identifier
    """
    try:
        meeting = load_meeting_result(meeting_id)
        if not meeting:
            raise HTTPException(status_code=404, detail=f"Meeting '{meeting_id}' not found")

        analysis = meeting.get("analysis", {})
        action_items = analysis.get("action_items", [])

        if not action_items:
            return {
                "meeting_id": meeting_id,
                "tasks_created": False,
                "message": "No action items found in this meeting"
            }

        from agents.task_agent import create_tasks
        tasks_result = create_tasks(
            action_items=action_items,
            meeting_data={
                "meeting_id": meeting_id,
                "file_name": meeting.get("file_name"),
                "summary": analysis.get("summary", "")
            }
        )

        return {
            "meeting_id": meeting_id,
            "tasks_created": True,
            "tasks_count": len(tasks_result),
            "tasks": tasks_result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────
# Search Past Meetings (RAG)
# ─────────────────────────────────────────
@app.post("/search", dependencies=[Depends(verify_api_key)])
async def search_meetings(request: SearchRequest):
    """
    Search past meetings using semantic similarity.

    Body:
    - query: Search query
    - k: Number of results to return (default: 5)
    """
    if not memory_available:
        raise HTTPException(status_code=503, detail="RAG memory system not available. Check memory/rag.py dependencies.")

    try:
        from memory.rag import MeetingMemory
        memory = MeetingMemory()

        results = memory.search(query=request.query, k=request.k)

        return {
            "query": request.query,
            "results": results,
            "count": len(results)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────
# List Available Actions (tasks that can be performed)
# ─────────────────────────────────────────
@app.get("/actions", dependencies=[Depends(verify_api_key)])
def list_available_actions():
    """
    List actions that can be performed on meetings (e.g., send email, create tasks).
    Useful for frontend to show available operations.
    """
    return {
        "actions": [
            {
                "name": "send_email",
                "description": "Send meeting summary email to attendees",
                "required_credentials": ["gmail"],
                "parameters": ["recipients"]
            },
            {
                "name": "create_tasks",
                "description": "Create tasks from action items in Notion or Google Tasks",
                "required_credentials": ["notion", "google_calendar"],
                "parameters": []
            }
        ]
    }


# ─────────────────────────────────────────
# Error Handlers
# ─────────────────────────────────────────
@app.exception_handler(FileNotFoundError)
async def file_not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"detail": "File not found", "error": str(exc)}
    )


@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content={"detail": "Invalid request", "error": str(exc)}
    )


# ─────────────────────────────────────────
# Run with: uvicorn main:app --reload
# ─────────────────────────────────────────
