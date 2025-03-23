import os
import requests
import hashlib
import time
import logging
from pathlib import Path
from config.settings import settings

logger = logging.getLogger(__name__)

class VirusScanner:
    """Класс для проверки файлов на вирусы через VirusTotal API"""
    
    def __init__(self, api_key=None):
        # Используем ключ из настроек, если не указан
        self.api_key = api_key or getattr(settings, 'virustotal_api_key', '')
        self.base_url = "https://www.virustotal.com/api/v3"
        self.headers = {
            "x-apikey": self.api_key,
            "accept": "application/json"
        }
    
    def calculate_file_hash(self, file_path):
        """Вычисляет SHA-256 хеш файла"""
        try:
            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                # Читаем файл блоками для экономии памяти
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            logger.error(f"Ошибка при вычислении хеша файла {file_path}: {e}")
            return None
    
    def check_file_by_hash(self, file_path):
        """Проверяет файл по хешу в базе VirusTotal"""
        if not self.api_key:
            return {"status": "error", "message": "API ключ VirusTotal не настроен"}
            
        try:
            file_hash = self.calculate_file_hash(file_path)
            if not file_hash:
                return {"status": "error", "message": "Не удалось вычислить хеш файла"}
                
            url = f"{self.base_url}/files/{file_hash}"
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                data = response.json()
                stats = data.get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
                
                malicious = stats.get("malicious", 0)
                suspicious = stats.get("suspicious", 0)
                undetected = stats.get("undetected", 0)
                total = malicious + suspicious + undetected
                
                if total > 0:
                    threat_level = (malicious + suspicious) / total
                    
                    if threat_level > 0.1:  # Больше 10% антивирусов считают файл опасным
                        status = "danger"
                    elif threat_level > 0:
                        status = "warning"
                    else:
                        status = "safe"
                else:
                    status = "unknown"
                    
                return {
                    "status": status,
                    "message": f"Результат проверки: {malicious} вредоносных, {suspicious} подозрительных, {undetected} безопасных",
                    "details": stats,
                    "link": f"https://www.virustotal.com/gui/file/{file_hash}/detection"
                }
            elif response.status_code == 404:
                # Файл не найден в VirusTotal, нужно загрузить
                return {"status": "not_found", "message": "Файл не найден в базе VirusTotal"}
            else:
                return {"status": "error", "message": f"Ошибка API VirusTotal: {response.status_code}"}
        except Exception as e:
            logger.error(f"Ошибка при проверке файла {file_path} через VirusTotal: {e}")
            return {"status": "error", "message": f"Ошибка при проверке: {e}"}
    
    def scan_file(self, file_path):
        """Сканирует файл через VirusTotal API"""
        if not self.api_key:
            return {"status": "error", "message": "API ключ VirusTotal не настроен"}
            
        # Сначала проверяем по хешу
        check_result = self.check_file_by_hash(file_path)
        
        if check_result["status"] == "not_found" and os.path.getsize(file_path) < 32 * 1024 * 1024:
            # Если файл не найден и его размер меньше 32MB, загружаем его для анализа
            try:
                url = f"{self.base_url}/files"
                with open(file_path, "rb") as file:
                    files = {"file": (os.path.basename(file_path), file)}
                    response = requests.post(url, headers=self.headers, files=files)
                    
                if response.status_code == 200:
                    data = response.json()
                    analysis_id = data.get("data", {}).get("id")
                    
                    # Ждем результатов анализа (это может занять время)
                    return {"status": "pending", "message": "Файл отправлен на анализ. Проверьте результаты позже.", "id": analysis_id}
                else:
                    return {"status": "error", "message": f"Ошибка при загрузке файла: {response.status_code}"}
            except Exception as e:
                logger.error(f"Ошибка при загрузке файла {file_path} в VirusTotal: {e}")
                return {"status": "error", "message": f"Ошибка при загрузке файла: {e}"}
        
        return check_result
    
    def check_scan_result(self, analysis_id):
        """Проверяет результаты сканирования по ID анализа"""
        if not self.api_key:
            return {"status": "error", "message": "API ключ VirusTotal не настроен"}
            
        try:
            url = f"{self.base_url}/analyses/{analysis_id}"
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                data = response.json()
                status = data.get("data", {}).get("attributes", {}).get("status")
                
                if status == "completed":
                    stats = data.get("data", {}).get("attributes", {}).get("stats", {})
                    malicious = stats.get("malicious", 0)
                    suspicious = stats.get("suspicious", 0)
                    undetected = stats.get("undetected", 0)
                    total = malicious + suspicious + undetected
                    
                    if total > 0:
                        threat_level = (malicious + suspicious) / total
                        
                        if threat_level > 0.1:  # Больше 10% антивирусов считают файл опасным
                            status = "danger"
                        elif threat_level > 0:
                            status = "warning"
                        else:
                            status = "safe"
                    else:
                        status = "unknown"
                        
                    return {
                        "status": status,
                        "message": f"Результат проверки: {malicious} вредоносных, {suspicious} подозрительных, {undetected} безопасных",
                        "details": stats
                    }
                else:
                    return {"status": "pending", "message": f"Анализ в процессе: {status}"}
            else:
                return {"status": "error", "message": f"Ошибка API VirusTotal: {response.status_code}"}
        except Exception as e:
            logger.error(f"Ошибка при проверке результатов анализа {analysis_id}: {e}")
            return {"status": "error", "message": f"Ошибка при проверке результатов: {e}"}
    
    def mock_scan_result(self, file_path):
        """Имитирует результат проверки файла (для тестирования без API ключа)"""
        file_extension = os.path.splitext(file_path)[1].lower()
        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        
        # Имитируем разные результаты в зависимости от расширения и размера файла
        if file_extension in ['.exe', '.dll', '.bat', '.msi']:
            status = "warning"
            message = "Исполняемый файл. Рекомендуется проверить перед запуском."
        elif file_size > 100 * 1024 * 1024:  # Больше 100 MB
            status = "info"
            message = "Крупный файл. Проверка не выполнялась."
        else:
            status = "safe"
            message = "Файл безопасен (имитация)."
            
        return {
            "status": status,
            "message": message,
            "details": {"malicious": 0, "suspicious": 0, "undetected": 50},
            "is_mock": True
        } 