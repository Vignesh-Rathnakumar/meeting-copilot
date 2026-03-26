# utils/azure_clients.py
# Central place for all Azure connections — lazy initialization to avoid import-time errors

import os
from dotenv import load_dotenv

load_dotenv()

# Import clients only when needed
try:
    from openai import AzureOpenAI
    from azure.storage.blob import BlobServiceClient
    DEPENDENCIES_AVAILABLE = True
except ImportError as e:
    DEPENDENCIES_AVAILABLE = False
    IMPORT_ERROR = str(e)

# ─────────────────────────────────────────
# Lazy client getters
# ─────────────────────────────────────────
_gpt_client = None
_transcribe_client = None
_blob_client = None

def get_gpt_client():
    """Get or create GPT-4o client"""
    global _gpt_client
    if _gpt_client is None:
        if not DEPENDENCIES_AVAILABLE:
            raise ImportError(f"Required dependencies not available: {IMPORT_ERROR}")
        _gpt_client = AzureOpenAI(
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        )
    return _gpt_client

def get_transcribe_client():
    """Get or create transcription client"""
    global _transcribe_client
    if _transcribe_client is None:
        if not DEPENDENCIES_AVAILABLE:
            raise ImportError(f"Required dependencies not available: {IMPORT_ERROR}")
        _transcribe_client = AzureOpenAI(
            azure_endpoint=os.getenv("AZURE_TRANSCRIBE_ENDPOINT"),
            api_key=os.getenv("AZURE_TRANSCRIBE_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        )
    return _transcribe_client

def get_blob_client():
    """Get or create blob storage client"""
    global _blob_client
    if _blob_client is None:
        if not DEPENDENCIES_AVAILABLE:
            raise ImportError(f"Required dependencies not available: {IMPORT_ERROR}")
        connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if not connection_string:
            raise ValueError("AZURE_STORAGE_CONNECTION_STRING not set")
        _blob_client = BlobServiceClient.from_connection_string(connection_string)
    return _blob_client

def get_container_client(container_name: str = None):
    """Get container client for blob operations"""
    name = container_name or os.getenv("AZURE_STORAGE_CONTAINER_NAME")
    if not name:
        raise ValueError("AZURE_STORAGE_CONTAINER_NAME not set")
    return get_blob_client().get_container_client(name)

# ─────────────────────────────────────────
# Quick connection test
# ─────────────────────────────────────────
if __name__ == "__main__":
    print("Testing Azure connections...\n")

    # Test GPT-4o
    try:
        client = get_gpt_client()
        response = client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
            messages=[{"role": "user", "content": "Say hello"}],
            max_tokens=10,
        )
        print("✅ GPT-4o connected:", response.choices[0].message.content)
    except Exception as e:
        print("❌ GPT-4o failed:", e)

    # Test Transcription client
    try:
        client = get_transcribe_client()
        models = client.models.list()
        print("✅ Transcription client connected")
    except Exception as e:
        print("❌ Transcription client failed:", e)

    # Test Blob Storage
    try:
        client = get_blob_client()
        containers = list(client.list_containers())
        print(f"✅ Blob Storage connected — {len(containers)} container(s) found")
    except Exception as e:
        print("❌ Blob Storage failed:", e)