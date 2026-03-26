# dashboard/app.py
# Streamlit dashboard for Meeting Copilot

import streamlit as st
import requests
import json
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────
# Page Config
# ─────────────────────────────────────────
st.set_page_config(
    page_title="Meeting Copilot",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────
# Constants
# ─────────────────────────────────────────
API_BASE_URL = st.sidebar.text_input("API Base URL", value="http://localhost:8000", help="FastAPI backend URL")
st.sidebar.markdown("---")

# ─────────────────────────────────────────
# Utility Functions
# ─────────────────────────────────────────
def call_api(endpoint: str, method="GET", json_data=None, files=None, params=None):
    """Call FastAPI endpoint with error handling"""
    url = f"{API_BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"

    try:
        if method.upper() == "GET":
            response = requests.get(url, params=params, timeout=30)
        elif method.upper() == "POST":
            response = requests.post(url, json=json_data, files=files, timeout=60)
        else:
            st.error(f"Unsupported method: {method}")
            return None

        if response.status_code == 200:
            return response.json()
        else:
            error_msg = response.json().get("detail", str(response.text)) if response.headers.get("content-type") == "application/json" else response.text
            st.error(f"API Error {response.status_code}: {error_msg}")
            return None

    except requests.exceptions.ConnectionError:
        st.error(f"❌ Cannot connect to API at {url}. Is the server running?")
        return None
    except Exception as e:
        st.error(f"❌ Request failed: {e}")
        return None


def get_meetings():
    """Fetch all meetings"""
    return call_api("/meetings") or []


def get_meeting(meeting_id: str):
    """Fetch specific meeting"""
    return call_api(f"/meetings/{meeting_id}")


def upload_and_process(file, send_email=False, create_tasks=False):
    """Upload audio file and start processing"""
    files = {"audio": (file.name, file.getvalue(), "audio/wav")}
    data = {
        "send_email": send_email,
        "create_tasks": create_tasks
    }
    return call_api("/process", method="POST", files=files, json_data=data)


def send_meeting_email(meeting_id: str, recipients: list):
    """Send email for existing meeting"""
    return call_api(
        f"/meetings/{meeting_id}/send-email",
        method="POST",
        json_data={"recipients": recipients}
    )


def create_meeting_tasks(meeting_id: str):
    """Create tasks for existing meeting"""
    return call_api(f"/meetings/{meeting_id}/create-tasks", method="POST")


def search_meetings(query: str, k: int = 5):
    """Search past meetings"""
    return call_api("/search", method="POST", json_data={"query": query, "k": k})


# ─────────────────────────────────────────
# Sidebar Navigation
# ─────────────────────────────────────────
st.sidebar.title("🤖 Meeting Copilot")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigation",
    ["📤 Upload & Process", "📋 Meetings List", "🔍 Search Past", "⚙️ Settings"],
    label_visibility="collapsed"
)

# ─────────────────────────────────────────
# Page 1: Upload & Process
# ─────────────────────────────────────────
if page == "📤 Upload & Process":
    st.title("📤 Upload & Process Meeting")
    st.markdown("Upload an audio file (MP3, WAV, M4A) to transcribe and analyze.")

    col1, col2 = st.columns([2, 1])

    with col1:
        uploaded_file = st.file_uploader(
            "Choose an audio file",
            type=["mp3", "wav", "m4a", "ogg", "flac"],
            help="Max 25MB (Azure limit may apply)"
        )

        if uploaded_file:
            st.audio(uploaded_file, format="audio/wav")

    with col2:
        st.markdown("### Options")
        send_email = st.checkbox("📧 Send email automatically", value=False, help="Requires Gmail credentials")
        create_tasks = st.checkbox("📋 Create tasks automatically", value=False, help="Requires Notion credentials")

        st.markdown("---")
        st.markdown("### Recipients (for email)")
        email_input = st.text_area(
            "Email addresses (one per line)",
            placeholder="alice@example.com\\nbob@example.com",
            disabled=not send_email
        )

    if st.button("🚀 Process Meeting", type="primary", disabled=not uploaded_file):
        recipients = [e.strip() for e in email_input.split("\n") if e.strip()] if email_input else None

        with st.spinner(f"Processing {uploaded_file.name}... This may take a minute."):
            result = upload_and_process(
                uploaded_file,
                send_email=send_email,
                create_tasks=create_tasks
            )

            if result:
                st.success(f"✅ Processing complete! Meeting ID: {result.get('meeting_id')}")

                # Show summary
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Status", result.get("status", "N/A"))
                with col2:
                    st.metric("Transcript Length", f"{len(result.get('transcript', {}).get('labeled_transcript', '')):,} chars")
                with col3:
                    analysis = result.get("analysis", {})
                    st.metric("Action Items", len(analysis.get("action_items", [])))

                # Show analysis details
                if analysis:
                    st.markdown("---")
                    st.markdown("### 📊 Analysis Results")

                    with st.expander("📝 Summary", expanded=True):
                        st.write(analysis.get("summary", "No summary"))

                    col1, col2 = st.columns(2)
                    with col1:
                        with st.expander("👥 Attendees"):
                            attendees = analysis.get("attendees", [])
                            if attendees:
                                for a in attendees:
                                    st.write(f"- {a}")
                            else:
                                st.write("No attendees recorded")

                    with col2:
                        with st.expander("✅ Decisions"):
                            decisions = analysis.get("decisions", [])
                            if decisions:
                                for d in decisions:
                                    st.write(f"- {d}")
                            else:
                                st.write("No decisions recorded")

                    with st.expander("📋 Action Items"):
                        action_items = analysis.get("action_items", [])
                        if action_items:
                            for i, item in enumerate(action_items, 1):
                                st.markdown(f"""
                                **{i}. {item.get('task', 'N/A')}**
                                - Owner: {item.get('owner', 'Unassigned')}
                                - Deadline: {item.get('deadline', 'Not specified')}
                                - Priority: **{item.get('priority', 'Medium')}**
                                """)
                        else:
                            st.write("No action items identified")

                # Show follow-up actions
                st.markdown("---")
                col1, col2 = st.columns(2)

                with col1:
                    if result.get("email_sent"):
                        st.success("📧 Email sent successfully!")
                    elif result.get("email_error"):
                        st.error(f"📧 Email failed: {result['email_error']}")

                with col2:
                    if result.get("tasks_created"):
                        st.success(f"📋 Created {len(result.get('tasks', {}))} tasks")
                    elif result.get("tasks_error"):
                        st.warning(f"📋 Tasks not created: {result['tasks_error']}")

# ─────────────────────────────────────────
# Page 2: Meetings List
# ─────────────────────────────────────────
elif page == "📋 Meetings List":
    st.title("📋 All Meetings")
    st.markdown("Browse all processed meetings and their analyses.")

    if st.button("🔄 Refresh List"):
        st.rerun()

    meetings = get_meetings()

    if not meetings:
        st.info("No meetings found. Upload and process an audio file to get started.")
    else:
        st.markdown(f"**Total meetings:** {len(meetings)}")

        for meeting in meetings:
            with st.container():
                col1, col2, col3 = st.columns([1, 2, 1])

                with col1:
                    st.markdown(f"**ID:** `{meeting['id']}`")
                    st.caption(meeting.get('timestamp', 'Unknown date'))

                with col2:
                    st.markdown(f"**Summary:** {meeting.get('summary', 'No summary')}")
                    attendees = meeting.get('attendees', [])
                    if attendees:
                        st.caption(f"Attendees: {', '.join(attendees[:5])}" + (f" +{len(attendees)-5} more" if len(attendees) > 5 else ""))

                with col3:
                    action_count = meeting.get('action_items_count', 0)
                    st.metric("Action Items", action_count)

                    if st.button("📖 View Details", key=f"view_{meeting['id']}"):
                        # Store meeting_id in session state to show details
                        st.session_state.selected_meeting = meeting['id']

                st.divider()

        # Show selected meeting details
        if hasattr(st.session_state, 'selected_meeting'):
            meeting_id = st.session_state.selected_meeting
            st.markdown("---")
            st.markdown(f"## 📖 Meeting Details: `{meeting_id}`")

            meeting_data = get_meeting(meeting_id)
            if meeting_data:
                analysis = meeting_data.get("analysis", {})
                transcript = meeting_data.get("transcript", {}).get("labeled_transcript", "")

                tab1, tab2, tab3 = st.tabs(["📝 Summary", "📺 Transcript", "🔍 Actions"])

                with tab1:
                    st.write(analysis.get("summary", "No summary"))
                    st.markdown("**Attendees:**")
                    st.write(", ".join(analysis.get("attendees", [])))

                    st.markdown("**Decisions:**")
                    for d in analysis.get("decisions", []):
                        st.write(f"- {d}")

                with tab2:
                    st.text_area("Full Transcript", transcript, height=400)

                with tab3:
                    action_items = analysis.get("action_items", [])
                    if action_items:
                        for item in action_items:
                            st.markdown(f"""
                            - **{item.get('task')}**
                              - Owner: {item.get('owner')}
                              - Deadline: {item.get('deadline')}
                              - Priority: {item.get('priority')}
                            """)
                    else:
                        st.write("No action items")

                # Quick actions
                st.markdown("### Quick Actions")
                col1, col2 = st.columns(2)

                with col1:
                    email_recipients = st.text_input(
                        "Send email to (comma-separated)",
                        placeholder="alice@example.com, bob@example.com"
                    )
                    if st.button("📧 Send Email", type="secondary"):
                        recipients = [e.strip() for e in email_recipients.split(",") if e.strip()]
                        if recipients:
                            with st.spinner("Sending..."):
                                result = send_meeting_email(meeting_id, recipients)
                                if result.get("sent"):
                                    st.success("Email sent!")
                                else:
                                    st.error(f"Failed: {result.get('error')}")
                        else:
                            st.error("Please enter recipient email addresses")

                with col2:
                    if st.button("📋 Create Tasks", type="secondary"):
                        with st.spinner("Creating tasks..."):
                            result = create_meeting_tasks(meeting_id)
                            if result.get("tasks_created"):
                                st.success(f"Created {result.get('tasks_count', 0)} tasks!")
                            else:
                                st.warning(result.get("message", "No tasks created"))

            else:
                st.error("Meeting data not found")

# ─────────────────────────────────────────
# Page 3: Search Past Meetings
# ─────────────────────────────────────────
elif page == "🔍 Search Past Meetings":
    st.title("🔍 Search Past Meetings")
    st.markdown("Use semantic search to find insights from previous meetings.")

    query = st.text_input(
        "What do you want to find?",
        placeholder="E.g., 'budget discussion', 'project timeline', 'John's tasks'"
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        k = st.number_input("Number of results", min_value=1, max_value=20, value=5)
    with col2:
        st.write("")  # Spacer

    if st.button("🔍 Search", type="primary", disabled=not query):
        with st.spinner("Searching..."):
            results = search_meetings(query, k=k)

            if results:
                st.success(f"Found {results['count']} relevant snippets")

                for r in results['results']:
                    similarity_pct = r['similarity'] * 100
                    metadata = r.get('metadata', {})
                    meeting_id = metadata.get('meeting_id', 'Unknown')
                    summary = metadata.get('summary', 'No summary')

                    with st.container():
                        st.markdown(f"""
                        <div style="padding: 10px; border-left: 3px solid #4CAF50; background-color: #f9f9f9; margin-bottom: 10px;">
                        <strong>Meeting:</strong> `{meeting_id}`<br>
                        <strong>Relevance:</strong> {similarity_pct:.1f}%<br>
                        <strong>Snippet:</strong> {r['text'][:300]}...
                        </div>
                        """, unsafe_allow_html=True)

                        if st.button(f"📖 View Full Meeting", key=f"search_{r['chunk_id']}"):
                            st.session_state.selected_meeting = meeting_id

            else:
                st.info("No results found. Try a different search query.")

# ─────────────────────────────────────────
# Page 4: Settings
# ─────────────────────────────────────────
elif page == "⚙️ Settings":
    st.title("⚙️ Settings & Status")
    st.markdown("Check API status and credential configuration.")

    # API Health Check
    st.markdown("### 🔌 API Connection")
    if st.button("Test Connection"):
        health = call_api("/health")
        if health:
            st.success("✅ API is running!")
            col1, col2 = st.columns(2)
            with col1:
                st.write("**Status:**", health.get("status"))
                st.write("**Memory Available:**", "✅" if health.get("memory_available") else "❌")
            with col2:
                st.write("**Outputs Dir:**", "✅" if health.get("outputs_dir_exists") else "❌")

    st.markdown("---")
    st.markdown("### 🔑 Credentials")

    credentials = {
        "AZURE_OPENAI_ENDPOINT": "Azure OpenAI endpoint",
        "AZURE_OPENAI_API_KEY": "Azure OpenAI API key",
        "AZURE_TRANSCRIBE_ENDPOINT": "Azure Transcription endpoint",
        "AZURE_TRANSCRIBE_API_KEY": "Azure Transcription API key",
        "AZURE_STORAGE_CONNECTION_STRING": "Azure Blob Storage connection string",
        "NOTION_API_KEY": "Notion integration token",
        "NOTION_DATABASE_ID": "Notion database ID"
    }

    for env_var, description in credentials.items():
        status = "✅ Set" if os.getenv(env_var) else "❌ Not set"
        st.write(f"- **{description}**: {status}")

    st.markdown("---")
    st.markdown("### 📖 About")
    st.markdown("""
    **Meeting Copilot v1.0**

    An AI-powered meeting assistant that:
    - Transcribes audio using Azure OpenAI
    - Extracts summaries, action items, decisions
    - Creates tasks in Notion
    - Sends email summaries via Gmail
    - Stores meetings for semantic search

    [View on GitHub](https://github.com/yourusername/meeting-copilot)
    """)

# ─────────────────────────────────────────
# Footer
# ─────────────────────────────────────────
st.markdown("---")
st.caption("🤖 Powered by FastAPI + Streamlit | Meeting Copilot 2024")
