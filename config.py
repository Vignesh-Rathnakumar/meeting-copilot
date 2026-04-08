# config.py
# Centralized configuration management using Pydantic Settings
# Validates environment variables and provides typed access to all config

import os
from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from dotenv import load_dotenv

# Load .env file first
load_dotenv()


class AzureOpenAIConfig(BaseSettings):
    """Azure OpenAI (GPT-4o) configuration"""

    endpoint: str = Field(..., alias="AZURE_OPENAI_ENDPOINT")
    api_key: str = Field(..., alias="AZURE_OPENAI_API_KEY")
    deployment: str = Field(..., alias="AZURE_OPENAI_DEPLOYMENT")
    api_version: str = Field(..., alias="AZURE_OPENAI_API_VERSION")

    model_config = SettingsConfigDict(extra="ignore")


class AzureTranscriptionConfig(BaseSettings):
    """Azure OpenAI Transcription (gpt-4o-transcribe) configuration"""

    endpoint: str = Field(..., alias="AZURE_TRANSCRIBE_ENDPOINT")
    api_key: str = Field(..., alias="AZURE_TRANSCRIBE_API_KEY")
    deployment: str = Field(..., alias="AZURE_TRANSCRIBE_DEPLOYMENT")
    # Uses same API version as regular OpenAI

    model_config = SettingsConfigDict(extra="ignore")


class AzureStorageConfig(BaseSettings):
    """Azure Blob Storage configuration"""

    connection_string: str = Field(..., alias="AZURE_STORAGE_CONNECTION_STRING")
    container_name: str = Field(default="meetings", alias="AZURE_STORAGE_CONTAINER_NAME")

    model_config = SettingsConfigDict(extra="ignore")


class NotionConfig(BaseSettings):
    """Notion integration configuration"""

    api_key: Optional[str] = Field(default=None, alias="NOTION_API_KEY")
    database_id: Optional[str] = Field(default=None, alias="NOTION_DATABASE_ID")

    model_config = SettingsConfigDict(extra="ignore")

    @property
    def is_configured(self) -> bool:
        """Check if both required credentials are set"""
        return bool(self.api_key and self.database_id)


class GmailConfig(BaseSettings):
    """Gmail integration configuration"""

    # Using file-based OAuth; no env vars required
    # This config just checks for the credentials file
    credentials_file: str = Field(default="gmail_credentials.json")
    token_file: str = Field(default="gmail_token.json")

    model_config = SettingsConfigDict(extra="ignore")

    @property
    def has_credentials_file(self) -> bool:
        """Check if Gmail OAuth credentials file exists"""
        return os.path.exists(self.credentials_file)

    @property
    def is_configured(self) -> bool:
        """Check if Gmail integration is usable"""
        return self.has_credentials_file


class APIConfig(BaseSettings):
    """FastAPI server configuration"""

    api_key: str = Field(..., alias="API_KEY")
    allowed_origins: List[str] = Field(
        default=["http://localhost:8501"],
        alias="ALLOWED_ORIGINS"
    )
    host: str = Field(default="0.0.0.0", alias="API_HOST")
    port: int = Field(default=8000, alias="API_PORT")

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v):
        """Parse comma-separated string into list"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        if isinstance(v, list):
            return v
        return ["http://localhost:8501"]

    model_config = SettingsConfigDict(extra="ignore")


class RAGConfig(BaseSettings):
    """RAG / vector memory configuration"""

    db_path: str = Field(default="memory/chroma_db")
    embedding_model: str = Field(default="all-MiniLM-L6-v2")
    chunk_size: int = Field(default=500)
    chunk_overlap: int = Field(default=50)

    model_config = SettingsConfigDict(extra="ignore")


class OutputConfig(BaseSettings):
    """Output storage configuration"""

    outputs_dir: str = Field(default="outputs")
    temp_uploads_dir: str = Field(default="temp_uploads")

    model_config = SettingsConfigDict(extra="ignore")


class Settings(BaseSettings):
    """
    Main settings object that aggregates all configuration.
    Access via: settings = Settings()
    """

    # Nested configs
    azure_openai: AzureOpenAIConfig
    azure_transcribe: AzureTranscriptionConfig
    azure_storage: AzureStorageConfig
    notion: NotionConfig = NotionConfig()
    gmail: GmailConfig = GmailConfig()
    api: APIConfig
    rag: RAGConfig = RAGConfig()
    output: OutputConfig = OutputConfig()

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("azure_openai", "azure_transcribe", "azure_storage", "api", mode="before")
    @classmethod
    def initialize_nested_configs(cls, v, info):
        """Ensure nested configs are initialized from env"""
        if v is None:
            # Get the field name from info
            field_name = info.field_name
            if field_name == "azure_openai":
                return AzureOpenAIConfig()
            elif field_name == "azure_transcribe":
                return AzureTranscriptionConfig()
            elif field_name == "azure_storage":
                return AzureStorageConfig()
            elif field_name == "api":
                return APIConfig()
        return v


def get_settings() -> Settings:
    """
    Get application settings singleton.

    Returns:
        Settings object with validated configuration

    Raises:
        ValueError: If required environment variables are missing
    """
    try:
        settings = Settings(
            azure_openai=AzureOpenAIConfig(),
            azure_transcribe=AzureTranscriptionConfig(),
            azure_storage=AzureStorageConfig(),
            notion=NotionConfig(),
            gmail=GmailConfig(),
            api=APIConfig(),
            rag=RAGConfig(),
            output=OutputConfig(),
        )

        # Ensure output directories exist
        os.makedirs(settings.output.outputs_dir, exist_ok=True)
        os.makedirs(settings.output.temp_uploads_dir, exist_ok=True)
        os.makedirs(settings.rag.db_path, exist_ok=True)

        return settings

    except Exception as e:
        raise ValueError(f"Configuration error: {e}")


def get_azure_openai_config() -> AzureOpenAIConfig:
    """Get Azure OpenAI config"""
    return AzureOpenAIConfig()


def get_azure_transcribe_config() -> AzureTranscriptionConfig:
    """Get Azure Transcription config"""
    return AzureTranscriptionConfig()


def get_azure_storage_config() -> AzureStorageConfig:
    """Get Azure Storage config"""
    return AzureStorageConfig()


def get_notion_config() -> NotionConfig:
    """Get Notion config"""
    return NotionConfig()


def get_gmail_config() -> GmailConfig:
    """Get Gmail config"""
    return GmailConfig()


def get_api_config() -> APIConfig:
    """Get API config"""
    return APIConfig()


def get_rag_config() -> RAGConfig:
    """Get RAG config"""
    return RAGConfig()


__all__ = [
    "Settings",
    "get_settings",
    "AzureOpenAIConfig",
    "AzureTranscriptionConfig",
    "AzureStorageConfig",
    "NotionConfig",
    "GmailConfig",
    "APIConfig",
    "RAGConfig",
    "OutputConfig",
]
