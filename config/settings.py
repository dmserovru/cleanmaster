from pathlib import Path
from pydantic import BaseSettings, Field

class Settings(BaseSettings):
    app_name: str = "CleanDownloader"
    max_parallel_downloads: int = 5
    download_folder: Path = Path.home() / "Downloads"
    virus_total_key: str = Field(..., env="VIRUSTOTAL_API_KEY")
    telegram_token: str = Field(..., env="TELEGRAM_BOT_TOKEN")
    
    class Config:
        env_file = ".env"

config = Settings()
