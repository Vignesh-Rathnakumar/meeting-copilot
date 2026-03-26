#!/usr/bin/env python3
"""
Quick verification script to check Meeting Copilot installation and configuration.
Run this to diagnose issues before starting the application.
"""

import os
import sys
from pathlib import Path

print("="*60)
print("🔍 Meeting Copilot Verification")
print("="*60)

errors = []
warnings = []

# 1. Check Python version
print("\n1. Python version:")
print(f"   {sys.version}")
if sys.version_info < (3, 9):
    errors.append("Python 3.9+ recommended")

# 2. Check critical .env variables
print("\n2. Environment variables:")
env_vars = [
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_TRANSCRIBE_ENDPOINT",
    "AZURE_TRANSCRIBE_API_KEY",
    "AZURE_STORAGE_CONNECTION_STRING"
]
for var in env_vars:
    value = os.getenv(var)
    if value:
        print(f"   ✅ {var}: set")
    else:
        print(f"   ❌ {var}: NOT SET")
        errors.append(f"Missing {var}")

# 3. Check optional integrations
print("\n3. Optional integrations:")
if os.path.exists("gmail_credentials.json"):
    print("   ✅ Gmail credentials file found")
else:
    warnings.append("Gmail credentials not found - email will print to console only")
    print("   ⚠️  Gmail credentials not found (optional)")

if os.getenv("NOTION_API_KEY") and os.getenv("NOTION_DATABASE_ID"):
    print("   ✅ Notion credentials set")
else:
    warnings.append("Notion credentials not set - task creation disabled")
    print("   ⚠️  Notion credentials not set (optional)")

# 4. Check directories
print("\n4. Project directories:")
for dir_path in ["outputs", "memory/chroma_db", "temp_uploads"]:
    p = Path(dir_path)
    p.mkdir(parents=True, exist_ok=True)
    if p.exists():
        print(f"   ✅ {dir_path}/ exists (writable)")
    else:
        errors.append(f"Cannot create {dir_path}/")

# 5. Check test audio file
print("\n5. Test data:")
if any(Path(".").glob("test_meeting.*")):
    test_files = list(Path(".").glob("test_meeting.*"))
    print(f"   ✅ Found test files: {', '.join(f.name for f in test_files)}")
else:
    warnings.append("No test audio file found")
    print("   ⚠️  No test_meeting.wav/.mp3 found")

# 6. Try importing critical modules
print("\n6. Import checks:")
try:
    from agents.orchestrator import process_meeting
    print("   ✅ agents.orchestrator")
except Exception as e:
    errors.append(f"Failed to import orchestrator: {e}")
    print(f"   ❌ agents.orchestrator: {e}")

try:
    from utils.azure_clients import get_gpt_client, get_transcribe_client, get_blob_client
    print("   ✅ utils.azure_clients")
except Exception as e:
    errors.append(f"Failed to import Azure clients: {e}")
    print(f"   ❌ utils.azure_clients: {e}")

try:
    from memory.rag import MeetingMemory
    print("   ✅ memory.rag")
except Exception as e:
    warnings.append(f"RAG dependencies not installed: {e}")
    print(f"   ⚠️  memory.rag: {e}")

try:
    import streamlit
    print("   ✅ streamlit (dashboard)")
except Exception as e:
    errors.append(f"Streamlit not installed: {e}")
    print(f"   ❌ streamlit: {e}")

try:
    from fastapi import FastAPI
    print("   ✅ fastapi")
except Exception as e:
    errors.append(f"FastAPI not installed: {e}")
    print(f"   ❌ fastapi: {e}")

# 7. Test Azure connection (optional)
print("\n7. Azure connection (optional test):")
test_azure = input("   Test Azure connections? (y/N): ").lower().strip()
if test_azure == 'y':
    try:
        from utils.azure_clients import get_gpt_client
        # Simple health check request
        model = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
        gpt_client = get_gpt_client()
        response = gpt_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=5
        )
        print("   ✅ Azure OpenAI connection OK")
    except Exception as e:
        errors.append(f"Azure connection failed: {e}")
        print(f"   ❌ Azure connection failed: {e}")

# Summary
print("\n" + "="*60)
print("📊 Verification Summary")
print("="*60)

if errors:
    print(f"\n❌ {len(errors)} ERRORS found:")
    for e in errors:
        print(f"   - {e}")
    print("\n🔧 Fix errors before running the application.")
else:
    print("\n✅ No critical errors!")

if warnings:
    print(f"\n⚠️  {len(warnings)} warnings:")
    for w in warnings:
        print(f"   - {w}")
    print("\n💡 Warnings won't prevent operation but may limit functionality.")

if not errors:
    print("\n🎉 System looks good! You can now run:")
    print("   API: uvicorn main:app --reload")
    print("   Dashboard: streamlit run dashboard/app.py")

print("="*60)
