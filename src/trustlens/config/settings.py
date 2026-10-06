import os
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TrustLensSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRUSTLENS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    # API Keys without prefix
    serpapi_api_key: str = Field(default="", validation_alias="SERPAPI_API_KEY")
    gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")
    
    # Gemini
    gemini_model: str = Field(default="gemini-3.5-flash-lite", validation_alias="GEMINI_MODEL")
    
    # Search config
    max_search_calls: int = 20
    max_results_per_query: int = 10
    search_timeout_seconds: int = 30
    
    # Investigation
    enable_targeted_second_search: bool = True
    max_second_search_calls: int = 5
    
    # Logging
    log_level: str = "INFO"

# Settings should be instantiated explicitly where needed.
