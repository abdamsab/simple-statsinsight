# backend/config/settings.py

# Centralized application settings management using Pydantic Settings.

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

# Define your application settings class
class Settings(BaseSettings):
    # --- Environment Variables loaded by Pydantic Settings ---
    # These fields correspond to environment variables (e.g., in your .env file)
    # Pydantic Settings will automatically load and validate these.
    MONGODB_URI: str
    GEMINI_API_KEY: str
    DB_NAME: str # <--- Add this field for the database name
    # Add other environment variables your app needs here
    # e.g., APP_ENV: str = "development" # Example with a default value

    # --- New Fields for JWT (Add these three lines) ---
    SECRET_KEY: str ="StatInsighT"  # Critical: Needs to be a strong, random string
    ALGORITHM: str = "HS256" # Default JWT algorithm (HS256 is common for symmetric keys)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30 # Default access token expiration time

    # --- New Fields for Authentication / Trials ---
    EMAIL_CONFIRM_TOKEN_EXPIRE_HOURS: int = 24 # Default email confirmation token expiry in hours
    DEFAULT_NEW_USER_TRIAL_DAYS: int = 7 # Default trial period in days if not found in parameters

    # --- Configuration for Pydantic Settings ---
    model_config = SettingsConfigDict(
        env_file='.env',  # Instruct Pydantic Settings to load from .env file
        env_file_encoding='utf-8', # Specify encoding
        # case_sensitive is False by default, which is usually what you want for env vars
    )

# Create a settings instance that loads values on import
settings = Settings()