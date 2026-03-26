# integrations/notion.py
# Notion API client for creating tasks from action items

import os
import json
from datetime import datetime
from dotenv import load_dotenv
import requests
from typing import Optional, Dict, Any

load_dotenv()


class NotionClient:
    """
    Simple Notion API client for creating pages in a database.

    Setup:
    1. Create integration at https://www.notion.so/my-integrations
    2. Get the Internal Integration Token
    3. Share your database with the integration (add as member)
    4. Get database ID from URL: https://www.notion.so/your workspace/{DATABASE_ID}
    5. Add to .env: NOTION_API_KEY=secret_xxx, NOTION_DATABASE_ID=xxx
    """

    def __init__(self, api_key: str = None, database_id: str = None):
        self.api_key = api_key or os.getenv("NOTION_API_KEY")
        self.database_id = database_id or os.getenv("NOTION_DATABASE_ID")
        self.base_url = "https://api.notion.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }

        if not self.api_key:
            raise ValueError("NOTION_API_KEY not set in environment variables")
        if not self.database_id:
            raise ValueError("NOTION_DATABASE_ID not set in environment variables")

    def test_connection(self) -> bool:
        """Test if Notion API credentials are valid"""
        try:
            response = requests.get(
                f"{self.base_url}/databases/{self.database_id}",
                headers=self.headers
            )
            return response.status_code == 200
        except Exception as e:
            print(f"❌ Notion connection test failed: {e}")
            return False

    def create_task_page(
        self,
        title: str,
        task_description: str,
        assignee: str = None,
        due_date: str = None,
        priority: str = "Medium",
        meeting_link: str = None,
        meeting_summary: str = None
    ) -> Optional[str]:
        """
        Create a new task page in the Notion database.

        Args:
            title: Task title (typically the action item)
            task_description: Detailed description
            assignee: Person responsible (name)
            due_date: Due date string (e.g., "2024-04-01" or "Not specified")
            priority: High/Medium/Low
            meeting_link: Link to meeting recording/transcript
            meeting_summary: Brief summary of meeting

        Returns:
            Page URL if successful, None otherwise
        """
        try:
            # Prepare properties based on Notion database schema
            # Common schema: Title (title), Task (rich_text), Status (select), Priority (select),
            # Assignee (people or rich_text), Due (date), Meeting (url), Created (date)

            properties = {
                "Name": {  # Title property (adjust name if your DB uses different title field)
                    "title": [
                        {
                            "text": {
                                "content": title[:100]  # Notion title max 100 chars
                            }
                        }
                    ]
                },
                "Status": {
                    "select": {
                        "name": "To Do"  # Default status
                    }
                },
                "Priority": {
                    "select": {
                        "name": priority if priority in ["High", "Medium", "Low"] else "Medium"
                    }
                },
                "Created": {
                    "date": {
                        "start": datetime.now().isoformat()
                    }
                }
            }

            if assignee:
                properties["Assignee"] = {
                    "rich_text": [
                        {
                            "text": {
                                "content": assignee
                            }
                        }
                    ]
                }

            if due_date and due_date != "Not specified":
                # Try to parse various date formats
                try:
                    # Handle ISO format or simple YYYY-MM-DD
                    clean_date = due_date.split("T")[0] if "T" in due_date else due_date
                    properties["Due"] = {
                        "date": {
                            "start": clean_date
                        }
                    }
                except Exception:
                    pass  # Skip date if unparseable

            if meeting_link:
                properties["Meeting Link"] = {
                    "url": meeting_link
                }

            if meeting_summary:
                properties["Notes"] = {
                    "rich_text": [
                        {
                            "text": {
                                "content": meeting_summary[:2000]
                            }
                        }
                    ]
                }

            page_content = []
            if task_description:
                page_content.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": task_description
                                }
                            }
                        ]
                    }
                })

            payload = {
                "parent": {"database_id": self.database_id},
                "properties": properties,
                "children": page_content
            }

            response = requests.post(
                f"{self.base_url}/pages",
                headers=self.headers,
                json=payload
            )

            if response.status_code == 200:
                page_data = response.json()
                page_id = page_data.get("id")
                page_url = page_data.get("url")
                print(f"✅ Notion task created: {title[:50]}...")
                return page_url
            else:
                print(f"❌ Notion API error {response.status_code}: {response.text[:200]}")
                return None

        except Exception as e:
            print(f"❌ Error creating Notion task: {e}")
            return None


def create_task(
    action_item: Dict[str, Any],
    meeting_context: Dict[str, Any] = None,
    api_key: str = None,
    database_id: str = None
) -> Optional[str]:
    """
    Create a task in Notion from an action item dictionary.

    Args:
        action_item: Dict with keys: owner, task, deadline, priority
        meeting_context: Optional dict with meeting info (file_name, summary, meeting_id)
        api_key: Override NOTION_API_KEY
        database_id: Override NOTION_DATABASE_ID

    Returns:
        URL of created Notion page, or None if failed
    """
    try:
        client = NotionClient(api_key=api_key, database_id=database_id)

        title = action_item.get("task", "Untitled Task")
        assignee = action_item.get("owner")
        deadline = action_item.get("deadline", "Not specified")
        priority = action_item.get("priority", "Medium")

        # Build meeting link (if you have a web UI, this would be the full URL)
        meeting_link = None
        if meeting_context:
            meeting_id = meeting_context.get("meeting_id")
            if meeting_id:
                # In a real deployment, this would be your actual hosted URL
                meeting_link = f"meeting://{meeting_id}"

        meeting_summary = None
        if meeting_context:
            meeting_summary = meeting_context.get("summary", "")

        return client.create_task_page(
            title=title,
            task_description=f"From meeting: {meeting_context.get('file_name', 'Unknown') if meeting_context else ''}\n\n{title}",
            assignee=assignee,
            due_date=deadline,
            priority=priority,
            meeting_link=meeting_link,
            meeting_summary=meeting_summary
        )

    except ValueError as e:
        if "NOTION_API_KEY" in str(e) or "NOTION_DATABASE_ID" in str(e):
            print("⚠️  Notion credentials not configured. Skipping task creation.")
            print("   Set NOTION_API_KEY and NOTION_DATABASE_ID in .env to enable.")
        return None
    except Exception as e:
        print(f"❌ Failed to create Notion task: {e}")
        return None


if __name__ == "__main__":
    print("Testing Notion integration...\n")

    api_key = os.getenv("NOTION_API_KEY")
    database_id = os.getenv("NOTION_DATABASE_ID")

    if not api_key or not database_id:
        print("❌ Please set NOTION_API_KEY and NOTION_DATABASE_ID in .env")
    else:
        client = NotionClient(api_key, database_id)
        if client.test_connection():
            print("✅ Notion connection successful!")

            # Test creating a sample task
            test_item = {
                "owner": "John Doe",
                "task": "Review meeting notes and update project plan",
                "deadline": "2024-04-15",
                "priority": "High"
            }
            url = create_task(test_item, {"file_name": "test_meeting", "summary": "Test meeting summary"})
            if url:
                print(f"✅ Test task created: {url}")
        else:
            print("❌ Notion connection failed. Check credentials.")
