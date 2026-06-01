from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./nepal_traffic.db"
    CAMERA_SOURCES: str = ""  # comma-separated RTSP URLs or video file paths
    DOTM_API_KEY: str = ""        # provide via environment / .env — never hardcode a real key
    CONFIDENCE_THRESHOLD: float = 0.65
    CHECKPOINT_NAME: str = "Thankot Checkpoint"
    CHECKPOINT_LOCATION: str = "Thankot, Kathmandu"
    LOG_LEVEL: str = "INFO"
    MOCK_MODE: bool = True
    SECRET_KEY: str = ""          # provide via environment in production — never hardcode
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080"

    # ── OCR ───────────────────────────────────────────────────────────────────
    # OCR_ENGINE: "easyocr" | "paddle" | "mock" | "" (auto).
    # Auto resolves to "mock" when MOCK_MODE is on, otherwise "easyocr".
    OCR_ENGINE: str = ""
    OCR_GPU: bool = True               # use Apple MPS / CUDA if available
    OCR_PLATE_LANGS: str = "en"        # EasyOCR langs for license plates
    OCR_ROUTE_LANGS: str = "ne,en"     # EasyOCR langs for Devanagari bus routes
    OCR_MIN_CONF: float = 0.30         # drop OCR tokens below this confidence

    @property
    def camera_source_list(self) -> List[str]:
        if not self.CAMERA_SOURCES:
            return []
        return [s.strip() for s in self.CAMERA_SOURCES.split(",") if s.strip()]

    @property
    def ocr_plate_lang_list(self) -> List[str]:
        return [s.strip() for s in self.OCR_PLATE_LANGS.split(",") if s.strip()] or ["en"]

    @property
    def ocr_route_lang_list(self) -> List[str]:
        return [s.strip() for s in self.OCR_ROUTE_LANGS.split(",") if s.strip()] or ["ne", "en"]

    @property
    def cors_origin_list(self) -> List[str]:
        return [s.strip() for s in self.CORS_ORIGINS.split(",") if s.strip()]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
