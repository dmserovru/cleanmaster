import os
import requests
import hashlib
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class VirusTotalScanner:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://www.virustotal.com/vtapi/v2"
        self.headers = {
            "apikey": self.api_key
        }
        
    def scan_file(self, file_path: Path) -> Optional[Dict]:
        """Отправляет файл на сканирование в VirusTotal"""
        if not file_path.exists():
            logger.error(f"File {file_path} does not exist")
            return None
            
        try:
            # Сначала проверим, есть ли уже результаты по хешу файла
            file_hash = self._calculate_hash(file_path)
            existing_report = self.get_report_by_hash(file_hash)
            if existing_report:
                return existing_report
                
            # Если отчета нет, отправляем файл на сканирование
            url = f"{self.base_url}/file/scan"
            files = {"file": (file_path.name, open(file_path, "rb"))}
            response = requests.post(url, headers=self.headers, files=files)
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"File {file_path} sent for scanning. Scan ID: {result.get('scan_id')}")
                return result
            else:
                logger.error(f"Error scanning file: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error scanning file {file_path}: {str(e)}")
            return None
            
    def get_report_by_hash(self, file_hash: str) -> Optional[Dict]:
        """Получает отчет по хешу файла"""
        try:
            url = f"{self.base_url}/file/report"
            params = {
                "apikey": self.api_key,
                "resource": file_hash
            }
            response = requests.get(url, params=params)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("response_code") == 1:  # Файл найден в базе
                    return result
            return None
            
        except Exception as e:
            logger.error(f"Error getting report for hash {file_hash}: {str(e)}")
            return None
            
    def _calculate_hash(self, file_path: Path) -> str:
        """Вычисляет SHA-256 хеш файла"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest() 