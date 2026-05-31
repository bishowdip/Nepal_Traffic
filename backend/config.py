from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./nepal_traffic.db"
    CAMERA_SOURCES: str = ""  # comma-separated RTSP URLs or video file paths
    DOTM_API_KEY: str = "mock-dotm-key-2024"
    CONFIDENCE_THRESHOLD: float = 0.65
    CHECKPOINT_NAME: str = "Thankot Checkpoint"
    CHECKPOINT_LOCATION: str = "Thankot, Kathmandu"
    LOG_LEVEL: str = "INFO"
    MOCK_MODE: bool = True
    SECRET_KEY: str = "nepal-traffic-ai-secret-2024"
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080"

    @property
    def camera_source_list(self) -> List[str]:
        if not self.CAMERA_SOURCES:
            return []
        return [s.strip() for s in self.CAMERA_SOURCES.split(",") if s.strip()]

    @property
    def cors_origin_list(self) -> List[str]:
        return [s.strip() for s in self.CORS_ORIGINS.split(",") if s.strip()]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
