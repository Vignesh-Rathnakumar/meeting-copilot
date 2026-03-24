# utils/azure_clients.py
# Central place for all Azure connections — every agent imports from here

import os
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

# ─────────────────────────────────────────
# GPT-4o client (analysis, email drafting)
# ─────────────────────────────────────────
gpt_client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
)

# ─────────────────────────────────────────
# Transcription client (gpt-4o-transcribe-diarize)
# ─────────────────────────────────────────
transcribe_client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_TRANSCRIBE_ENDPOINT"),
    api_key=os.getenv("AZURE_TRANSCRIBE_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
)

# ─────────────────────────────────────────
# Azure Blob Storage client
# ─────────────────────────────────────────
from azure.storage.blob import BlobServiceClient

blob_client = BlobServiceClient.from_connection_string(
    os.getenv("AZURE_STORAGE_CONNECTION_STRING")
)

def get_container_client(container_name: str = None):
    name = container_name or os.getenv("AZURE_STORAGE_CONTAINER_NAME")
    return blob_client.get_container_client(name)

# ─────────────────────────────────────────
# Quick connection test
# ─────────────────────────────────────────
if __name__ == "__main__":
    print("Testing Azure connections...\n")

    # Test GPT-4o
    try:
        response = gpt_client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
            messages=[{"role": "user", "content": "Say hello"}],
            max_tokens=10,
        )
        print("✅ GPT-4o connected:", response.choices[0].message.content)
    except Exception as e:
        print("❌ GPT-4o failed:", e)

    # Test Transcription client
    try:
        models = transcribe_client.models.list()
        print("✅ Transcription client connected")
    except Exception as e:
        print("❌ Transcription client failed:", e)

    # Test Blob Storage
    try:
        containers = list(blob_client.list_containers())
        print(f"✅ Blob Storage connected — {len(containers)} container(s) found")
    except Exception as e:
        print("❌ Blob Storage failed:", e)