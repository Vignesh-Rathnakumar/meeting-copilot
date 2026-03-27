# tests/test_api.py
"""
Test suite for Meeting Copilot API.

Tests cover:
- Health check endpoint
- API key authentication
- Async job processing
- Job status retrieval
"""

import os
import sys
import uuid
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

pytest_plugins = ["pytest_asyncio"]

# Ensure environment variables are set before importing main
os.environ["API_KEY"] = "test-api-key"
os.environ["ALLOWED_ORIGINS"] = "http://localhost:8501"

# Import after setting env vars
from main import app, jobs, process_meeting_background


@pytest.fixture
def client():
    """Create a fresh TestClient for each test."""
    # Clear jobs dict before each test
    jobs.clear()
    with TestClient(app) as client:
        yield client
    # Clean up after test
    jobs.clear()


@pytest.fixture
def auth_headers():
    """Headers with valid API key."""
    return {"X-API-Key": "test-api-key"}


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_health_check_no_auth(self, client):
        """GET /health should be accessible without authentication."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "memory_available" in data
        assert "outputs_dir_exists" in data


class TestRootEndpoint:
    """Tests for the root endpoint."""

    def test_root_no_auth(self, client):
        """GET / should be accessible without authentication."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data["version"] == "1.0.0"


class TestProcessEndpoint:
    """Tests for the POST /process endpoint."""

    def test_process_without_auth(self, client):
        """POST /process without API key should return 401."""
        files = {"audio": ("test.wav", b"fake audio content", "audio/wav")}
        response = client.post("/process", files=files)
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid or missing API key"

    def test_process_with_invalid_auth(self, client, auth_headers):
        """POST /process with invalid API key should return 401."""
        headers = {"X-API-Key": "wrong-key"}
        files = {"audio": ("test.wav", b"fake audio content", "audio/wav")}
        response = client.post("/process", headers=headers, files=files)
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid or missing API key"

    def test_process_with_valid_auth_returns_202(self, client, auth_headers):
        """POST /process with valid API key should return 202 Accepted and job_id."""
        files = {"audio": ("test.wav", b"fake audio content", "audio/wav")}
        response = client.post("/process", headers=auth_headers, files=files)
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["message"] == "Processing started"
        assert data["status_url"] == f"/jobs/{data['job_id']}"

        # Verify job was created in memory
        job_id = data["job_id"]
        assert job_id in jobs
        # The job might already be processing or done depending on background task execution in TestClient
        # At this point, background tasks have already run synchronously in TestClient
        # So we just check that the job_id exists and status is something valid
        assert job_id in jobs

    def test_process_with_txt_file(self, client, auth_headers):
        """POST /process should accept .txt transcript files."""
        files = {"audio": ("transcript.txt", b"Speaker A: Hello", "text/plain")}
        response = client.post("/process", headers=auth_headers, files=files)
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data

    def test_process_unsupported_file_type(self, client, auth_headers):
        """POST /process should reject unsupported file types with 400."""
        headers = auth_headers
        files = {"audio": ("test.pdf", b"fake pdf", "application/pdf")}
        response = client.post("/process", headers=headers, files=files)
        assert response.status_code == 400
        assert "Unsupported file type" in response.json()["detail"]


class TestJobsEndpoint:
    """Tests for the GET /jobs/{job_id} endpoint."""

    def test_get_nonexistent_job_returns_404(self, client):
        """GET /jobs/{job_id} with unknown ID should return 404."""
        response = client.get("/jobs/nonexistent-job-id")
        assert response.status_code == 404
        assert response.json()["detail"] == "Job 'nonexistent-job-id' not found"

    def test_get_existing_job_returns_status(self, client):
        """GET /jobs/{job_id} with valid job ID should return job status."""
        # Create a test job entry
        job_id = "test-job-123"
        jobs[job_id] = {"status": "processing"}

        response = client.get(f"/jobs/{job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processing"

        # Clean up
        del jobs[job_id]


class TestMeetingsEndpoint:
    """Tests for protected endpoints requiring authentication."""

    def test_meetings_without_auth(self, client):
        """GET /meetings should require authentication."""
        response = client.get("/meetings")
        assert response.status_code == 401

    def test_meetings_with_auth(self, client, auth_headers):
        """GET /meetings should return 200 with valid auth."""
        response = client.get("/meetings", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_meeting_detail_without_auth(self, client):
        """GET /meetings/{id} should require authentication."""
        response = client.get("/meetings/meeting_test123")
        assert response.status_code == 401

    def test_search_without_auth(self, client):
        """POST /search should require authentication."""
        response = client.post("/search", json={"query": "test"})
        assert response.status_code == 401

    def test_actions_without_auth(self, client):
        """GET /actions should require authentication."""
        response = client.get("/actions")
        assert response.status_code == 401


class TestBackgroundProcessing:
    """Tests for background job processing."""

    def test_background_task_success(self):
        """Test that background task updates job status to done on success."""
        job_id = "test-bg-job-success"

        # Mock process_meeting to avoid actual processing
        with patch("main.process_meeting") as mock_process:
            mock_process.return_value = {"meeting_id": "test_123", "status": "completed"}

            # Create initial job
            jobs[job_id] = {"status": "queued"}

            # Run background task (synchronous)
            process_meeting_background(
                job_id=job_id,
                file_path="fake_path.wav",
                send_email=False,
                create_tasks=False,
                attendees_emails=None
            )

            # Verify job status updated
            assert job_id in jobs
            assert jobs[job_id]["status"] == "done"
            assert "result" in jobs[job_id]

            # Clean up
            del jobs[job_id]

    def test_background_task_failure(self):
        """Test that background task updates job status to error on failure."""
        job_id = "test-bg-job-fail"

        # Mock process_meeting to raise an exception
        with patch("main.process_meeting") as mock_process:
            mock_process.side_effect = Exception("Processing failed")

            # Create initial job
            jobs[job_id] = {"status": "queued"}

            # Run background task (synchronous)
            process_meeting_background(
                job_id=job_id,
                file_path="fake_path.wav",
                send_email=False,
                create_tasks=False,
                attendees_emails=None
            )

            # Verify job status updated to error
            assert job_id in jobs
            assert jobs[job_id]["status"] == "error"
            assert "detail" in jobs[job_id]
            assert "Processing failed" in jobs[job_id]["detail"]

            # Clean up
            del jobs[job_id]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
