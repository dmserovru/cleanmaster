import hashlib
import requests
from pathlib import Path
from typing import Optional

class VirusScanner:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://www.virustotal.com/api/v3"

    def scan_file(self, file_path: Path) -> dict:
        """Отправить файл на проверку в VirusTotal"""
        headers = {"x-apikey": self.api_key}
        
        with open(file_path, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
        
        # Проверка по хешу
        report = requests.get(
            f"{self.base_url}/files/{file_hash}",
            headers=headers
        )
        
        if report.status_code == 200:
            return report.json()
        
        # Если файла нет в базе - загружаем
        upload_url = f"{self.base_url}/files"
        files = {'file': open(file_path, 'rb')}
        upload_response = requests.post(upload_url, headers=headers, files=files)
        return upload_response.json()