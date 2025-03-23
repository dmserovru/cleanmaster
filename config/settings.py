import os
from pathlib import Path
from pydantic import BaseSettings, Field
import logging

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    app_name: str = "CleanDownloader"
    app_version: str = "1.0.0"
    max_parallel_downloads: int = 5
    download_folder: Path = Path.home() / "Downloads"
    virus_total_key: str = Field(default="", env="VIRUSTOTAL_API_KEY")
    telegram_token: str = Field(default="", env="TELEGRAM_BOT_TOKEN")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

try:
    config = Settings()
    
    # Проверка API-ключей
    if not config.virus_total_key:
        logger.warning("VirusTotal API key не найден. Проверка на вирусы не будет работать.")
    
    if not config.telegram_token:
        logger.warning("Telegram Bot token не найден. Telegram-бот не будет работать.")

except Exception as e:
    logger.error(f"Ошибка загрузки настроек: {e}")
    config = Settings(
        app_name="CleanDownloader",
        app_version="1.0.0",
        max_parallel_downloads=5,
        download_folder=Path.home() / "Downloads",
        virus_total_key="",
        telegram_token=""
    )
