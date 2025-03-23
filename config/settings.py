import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field
import logging
import json

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    """Настройки приложения"""
    app_name: str = "CleanDownloader"
    app_version: str = "1.0.0"
    max_workers: int = Field(
        default=5,
        description="Максимальное количество одновременных загрузок"
    )
    download_folder: str = Field(
        default="Downloads",
        description="Папка для загрузок"
    )
    telegram_bot_token: str = Field(
        default="",
        description="Токен Telegram бота"
    )
    virustotal_api_key: str = Field(
        default="",
        description="API ключ VirusTotal"
    )
    telegram_proxy: str = Field(
        default="",
        description="Прокси для Telegram бота"
    )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def __init__(self):
        super().__init__()
        self.load()

    def load(self):
        """Загрузка настроек из файла"""
        config_file = Path("config/settings.json")
        if config_file.exists():
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                for key, value in data.items():
                    if hasattr(self, key):
                        setattr(self, key, value)
            except Exception as e:
                logger.error(f"Error loading settings: {e}")
                
    def save(self):
        """Сохранение настроек в файл"""
        config_file = Path("config/settings.json")
        config_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(self.__dict__, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving settings: {e}")

try:
    config = Settings()
    
    # Проверка API-ключей
    if not config.virustotal_api_key:
        logger.warning("VirusTotal API ключ не найден. Проверка файлов будет отключена.")
    
    if not config.telegram_bot_token:
        logger.warning("Telegram бот токен не найден. Telegram бот будет отключен.")

except Exception as e:
    logger.error(f"Ошибка загрузки настроек: {e}")
    config = Settings(
        app_name="CleanDownloader",
        app_version="1.0.0",
        max_workers=5,
        download_folder="Downloads",
        virustotal_api_key="",
        telegram_bot_token="",
        telegram_proxy=""
    )

settings = config
