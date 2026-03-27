# agents/task_agent.py
# Creates actionable tasks from extracted action items using integrations (Notion, Google Tasks, etc.)

import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from integrations.notion import create_task as notion_create_task
# Optional: Uncomment when Google Calendar integration is implemented
# from integrations.google_calendar import create_task as google_create_task

load_dotenv()


def create_tasks(action_items: list, meeting_data: dict) -> dict:
    """
    Create tasks from a list of action items.

    Args:
        action_items: List of dicts with keys: owner, task, deadline, priority
        meeting_data: Dict with meeting context (meeting_id, file_name, summary)

    Returns:
        Dictionary with task creation results: {task_description: task_url or None}
    """
    if not action_items:
        logger.warning("⚠️  No action items to create tasks from.")
        return {}

    logger.info(f"\n📋 Creating {len(action_items)} tasks from action items...")

    results = {}
    created_count = 0
    failed_count = 0

    # Detect which task system is available (check Notion credentials)
    notion_available = all([
        os.getenv("NOTION_API_KEY"),
        os.getenv("NOTION_DATABASE_ID")
    ])

    # Optional: check Google Calendar
    # google_available = all([...])

    if not notion_available:
        logger.warning("⚠️  Notion credentials not configured. Tasks will not be created.")
        logger.warning("   Set NOTION_API_KEY and NOTION_DATABASE_ID in .env to enable task creation.")
        for item in action_items:
            results[item.get("task", "Untitled")] = None
        return results

    for i, item in enumerate(action_items, 1):
        task_desc = item.get("task", "Untitled Task")
        owner = item.get("owner", "")
        deadline = item.get("deadline", "Not specified")
        priority = item.get("priority", "Medium")

        logger.info(f"  {i}. Creating task: {task_desc[:50]}... (owner: {owner or 'Unassigned'})")

        try:
            # Create task in Notion
            task_url = notion_create_task(
                action_item=item,
                meeting_context=meeting_data
            )

            if task_url:
                results[task_desc] = {"url": task_url, "system": "notion"}
                created_count += 1
            else:
                results[task_desc] = {"url": None, "error": "Notion creation failed"}
                failed_count += 1

        except Exception as e:
            logger.error(f"    ❌ Failed to create task: {e}")
            results[task_desc] = {"url": None, "error": str(e)}
            failed_count += 1

    logger.info(f"\n✅ Task creation complete: {created_count} created, {failed_count} failed\n")

    return results


if __name__ == "__main__":
    logger.info("🧪 Testing task agent with sample action items...\n")

    # Ensure .env is loaded
    load_dotenv()

    test_action_items = [
        {
            "owner": "John",
            "task": "Review PR #123 and provide feedback",
            "deadline": "2024-04-10",
            "priority": "High"
        },
        {
            "owner": "Sarah",
            "task": "Update project documentation",
            "deadline": "Not specified",
            "priority": "Medium"
        }
    ]

    test_meeting_data = {
        "meeting_id": "test_123",
        "file_name": "test_meeting.wav",
        "summary": "Weekly sync review"
    }

    results = create_tasks(test_action_items, test_meeting_data)

    logger.info("\n📊 Results:")
    for task, result in results.items():
        if result.get("url"):
            logger.info(f"  ✅ {task}: {result['url']}")
        else:
            logger.info(f"  ❌ {task}: {result.get('error', 'Failed')}")
