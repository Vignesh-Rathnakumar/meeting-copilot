# integrations/gmail.py
# Gmail API client for sending meeting summaries with OAuth2 authentication

import os
import json
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_APIS_AVAILABLE = True
except ImportError:
    GOOGLE_APIS_AVAILABLE = False
    print("⚠️  Google API libraries not installed. Gmail integration disabled.")
    print("   Install with: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")


# SCOPES for Gmail API (read-write access)
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose"
]

TOKEN_FILE = "gmail_token.json"
CREDENTIALS_FILE = "gmail_credentials.json"  # Download from Google Cloud Console


def authenticate():
    """
    Authenticate with Gmail API using OAuth2.

    Returns:
        Credentials object or None if authentication fails
    """
    if not GOOGLE_APIS_AVAILABLE:
        print("❌ Google API libraries not available")
        return None

    creds = None

    # Load existing token if exists
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r") as f:
                creds = Credentials.from_authorized_user_info(json.load(f), SCOPES)
        except Exception as e:
            print(f"⚠️  Error loading token: {e}")

    # If no valid credentials, perform OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                print("🔄 Gmail token refreshed")
            except Exception as e:
                print(f"⚠️  Token refresh failed: {e}")
                creds = None

        if not creds:
            if not os.path.exists(CREDENTIALS_FILE):
                print("❌ Gmail credentials file not found!")
                print(f"   Please download OAuth 2.0 credentials from Google Cloud Console")
                print(f"   and save as '{CREDENTIALS_FILE}' in the project root.")
                return None

            print("🔒 Starting OAuth flow...")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)

            # For local development, use console flow
            creds = flow.run_local_server(port=0)

        # Save token for future use
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
            print(f"💾 Token saved to {TOKEN_FILE}")

    return creds


def create_message(
    to: list,
    subject: str,
    html_body: str = None,
    text_body: str = None
) -> dict:
    """
    Create an email message.

    Args:
        to: List of recipient email addresses
        subject: Email subject
        html_body: HTML formatted body (if None, uses text_body)
        text_body: Plain text body

    Returns:
        Dictionary with raw message ready for Gmail API
    """
    if html_body:
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["To"] = ", ".join(to)

        # Attach plain text and HTML versions
        text_part = MIMEText(text_body or html_body.replace("<br>", "\n"), "plain")
        html_part = MIMEText(html_body, "html")

        message.attach(text_part)
        message.attach(html_part)
    else:
        message = MIMEText(text_body)
        message["Subject"] = subject
        message["To"] = ", ".join(to)

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {"raw": raw_message}


def send_message(service, user_id: str, message: dict) -> Optional[str]:
    """
    Send an email via Gmail API.

    Args:
        service: Gmail API service instance
        user_id: User's email address or 'me' for authenticated user
        message: Message dictionary (from create_message)

    Returns:
        Message ID if successful, None otherwise
    """
    try:
        sent_message = service.users().messages().send(userId=user_id, body=message).execute()
        message_id = sent_message.get("id")
        print(f"📨 Email sent! Message ID: {message_id}")
        return message_id
    except HttpError as error:
        print(f"❌ Gmail API error: {error}")
        return None


def send_email(
    to: list,
    subject: str,
    html_body: str = None,
    text_body: str = None
) -> dict:
    """
    Send an email using Gmail API.

    Args:
        to: List of recipient email addresses
        subject: Email subject
        html_body: HTML formatted body (optional)
        text_body: Plain text body (optional)

    Returns:
        Dictionary with sent status, message_id, and optional error
    """
    result = {"sent": False, "message_id": None, "error": None}

    if not GOOGLE_APIS_AVAILABLE:
        result["error"] = "Google API libraries not installed"
        return result

    if not to:
        result["error"] = "No recipients provided"
        return result

    try:
        # Authenticate
        creds = authenticate()
        if not creds:
            result["error"] = "Authentication failed"
            return result

        # Build Gmail service
        service = build("gmail", "v1", credentials=creds)

        # Create message
        message = create_message(to=to, subject=subject, html_body=html_body, text_body=text_body)

        # Send
        message_id = send_message(service, "me", message)

        if message_id:
            result["sent"] = True
            result["message_id"] = message_id
        else:
            result["error"] = "Failed to send message"

    except Exception as e:
        result["error"] = str(e)

    return result


def print_email_preview(
    to: list,
    subject: str,
    html_body: str = None,
    text_body: str = None
):
    """
    Print email content to console (fallback when Gmail credentials unavailable).

    Args:
        to: List of recipients
        subject: Email subject
        html_body: HTML formatted body
        text_body: Plain text body
    """
    print("\n" + "="*60)
    print("📧 EMAIL PREVIEW (credentials not configured)")
    print("="*60)
    print(f"To: {', '.join(to)}")
    print(f"Subject: {subject}")
    print("-"*60)
    if html_body:
        # Strip HTML tags for plain preview
        import re
        text = re.sub(r'<[^>]+>', '', html_body)
        text = text.replace("  ", " ").strip()
    else:
        text = text_body
    print(text)
    print("="*60 + "\n")


def send_meeting_summary_fallback(
    analysis: dict,
    recipients: list,
    meeting_data: dict = None
) -> dict:
    """
    Fallback: Format and print meeting summary to console instead of sending email.

    Args:
        analysis: Analysis dictionary with summary, action_items, decisions, attendees
        recipients: List of email addresses
        meeting_data: Optional additional meeting context

    Returns:
        Same format as send_email() but always unsent
    """
    summary = analysis.get("summary", "No summary available")
    decisions = analysis.get("decisions", [])
    action_items = analysis.get("action_items", [])
    attendees = analysis.get("attendees", [])

    # Format email content
    subject = f" Meeting Summary: {summary[:50]}..."

    body = f"""
    <h2>Meeting Summary</h2>
    <p>{summary}</p>

    <h3>Attendees</h3>
    <p>{', '.join(attendees) if attendees else 'None recorded'}</p>

    <h3>Decisions Made</h3>
    <ul>
    """
    for decision in decisions:
        body += f"<li>{decision}</li>"
    body += "</ul>"

    body += """
    <h3>Action Items</h3>
    <table border="1" cellpadding="8" cellspacing="0">
      <tr style="background-color: #f0f0f0;">
        <th>Owner</th>
        <th>Task</th>
        <th>Deadline</th>
        <th>Priority</th>
      </tr>
    """
    for item in action_items:
        priority_colors = {"High": "#ffcccc", "Medium": "#ffffcc", "Low": "#ccffcc"}
        color = priority_colors.get(item.get("priority", "Medium"), "#ffffff")
        body += f"""
      <tr style="background-color: {color};">
        <td>{item.get('owner', 'Unassigned')}</td>
        <td>{item.get('task', 'N/A')}</td>
        <td>{item.get('deadline', 'Not specified')}</td>
        <td>{item.get('priority', 'Medium')}</td>
      </tr>
        """
    body += "</table>"

    body += """
    <p><em>This email was generated by Meeting Copilot.</em></p>
    """

    # Print to console
    print_email_preview(to=recipients, subject=subject, html_body=body)

    return {
        "sent": False,
        "message_id": None,
        "error": "Gmail credentials not configured - printed to console instead"
    }


if __name__ == "__main__":
    print("Testing Gmail integration...\n")

    if not GOOGLE_APIS_AVAILABLE:
        print("❌ Install dependencies first: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
    else:
        # Test authentication
        creds = authenticate()
        if creds:
            print("✅ Gmail authentication successful!")

            # Test sending a sample email to self
            test_result = send_email(
                to=["your-email@example.com"],  # Replace with your email
                subject="Test from Meeting Copilot",
                html_body="<h1>Hello!</h1><p>This is a test email from Meeting Copilot.</p>",
                text_body="Hello! This is a test email from Meeting Copilot."
            )

            if test_result["sent"]:
                print(f"✅ Test email sent! Message ID: {test_result['message_id']}")
            else:
                print(f"❌ Test email failed: {test_result.get('error')}")
        else:
            print("❌ Gmail authentication failed")
