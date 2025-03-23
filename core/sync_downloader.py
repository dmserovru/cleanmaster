import os
import requests
import hashlib
import threading
import uuid
from urllib.parse import urlparse, unquote
from typing import Dict, List, Optional
from pathlib import Path
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
import re

logger = logging.getLogger(__name__)

def sanitize_filename(filename: str) -> str:
    """Очистка имени файла от недопустимых символов"""
    # Декодируем URL-кодированные символы
    filename = unquote(filename)
    
    # Удаляем параметры запроса
    filename = filename.split("?")[0]
    
    # Заменяем недопустимые символы на подчеркивание
    filename = re.sub(r'[<>:"/\\|?*]', "_", filename)
    
    # Если имя файла пустое, используем значение по умолчанию
    if not filename:
        filename = "downloaded_file"
    
    return filename

def format_size(size: int) -> str:
    """Форматирование размера файла"""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"

def format_speed(speed: float) -> str:
    """Форматирование скорости загрузки"""
    if speed < 1024:
        return f"{speed:.2f} B/s"
    elif speed < 1024**2:
        return f"{speed/1024:.2f} KB/s"
    else:
        return f"{speed/(1024**2):.2f} MB/s"

def calculate_hash(file_path: Path, algorithm: str = "md5") -> str:
    """Вычисление контрольной суммы файла"""
    if not file_path.exists():
        return ""
    
    hash_obj = hashlib.new(algorithm)
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_obj.update(chunk)
    return hash_obj.hexdigest()

class Download:
    """Класс для представления загрузки"""
    def __init__(self, url: str, path: Path, filename: str = None):
        self.id = str(uuid.uuid4())
        self.url = url
        self.path = path
        self.name = filename or sanitize_filename(os.path.basename(urlparse(url).path)) or "noname"
        self.size = 0
        self.progress = 0
        self.speed = "0 B/s"
        self.status = "В очереди"
        self.created = time.time()
        self.bytes_downloaded = 0
        self.is_paused = False
        self.is_canceled = False
        self.thread = None
        self.md5 = ""
        self.sha1 = ""
        
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "url": self.url,
            "path": str(self.path),
            "name": self.name,
            "size": format_size(self.size),
            "progress": self.progress,
            "speed": self.speed,
            "status": self.status,
            "created": self.created,
            "md5": self.md5,
            "sha1": self.sha1
        }

    def __repr__(self):
        return f"Download({self.name}, {self.status}, {self.progress}%)"

class DownloadManager:
    def __init__(self, max_workers: int = 5):
        self.downloads: List[Download] = []
        self.is_paused = False
        self.max_workers = max_workers
        
        # Пул потоков для загрузок
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        
        # Пул потоков для вычисления хешей
        self.hash_executor = ThreadPoolExecutor(max_workers=2)
        
        # Очередь для коммуникации между потоками
        self.queue = Queue()
        
        # Запускаем обработчик очереди
        self.queue_thread = threading.Thread(target=self._queue_processor, daemon=True)
        self.queue_thread.start()
        
        logger.info(f"Download Manager initialized with {max_workers} workers")

    def _queue_processor(self):
        """Обработчик очереди загрузок"""
        while True:
            try:
                item = self.queue.get()
                action, data = item
                
                if action == "add":
                    url, path = data
                    self._download(url, path)
                elif action == "pause":
                    download_id = data
                    self._pause_download(download_id)
                elif action == "resume":
                    download_id = data
                    self._resume_download(download_id)
                elif action == "cancel":
                    download_id = data
                    self._cancel_download(download_id)
            except Exception as e:
                logger.error(f"Error processing queue item {item}: {e}")
            finally:
                self.queue.task_done()

    def _download(self, url: str, path: Path):
        """Синхронная загрузка файла"""
        # Создаем имя файла из URL
        filename = sanitize_filename(os.path.basename(urlparse(url).path))
        path = path.parent / filename
        download = Download(url, path, filename)
        self.downloads.append(download)

        def download_worker():
            try:
                # Получаем информацию о файле
                response = requests.head(url, allow_redirects=True)
                if response.status_code != 200:
                    download.status = f"Ошибка: HTTP {response.status_code}"
                    return

                download.size = int(response.headers.get("content-length", 0))
                download.status = "Загрузка"

                # Проверяем, существует ли файл для возобновления загрузки
                if path.exists():
                    resume_pos = path.stat().st_size
                    if resume_pos >= download.size and download.size > 0:
                        download.progress = 100
                        download.status = "Завершено"
                        download.bytes_downloaded = download.size
                        self._calculate_hashes(download)
                        return
                else:
                    resume_pos = 0
                    # Создаем файл и папку, если нужно
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.touch()

                # Загружаем файл
                headers = {}
                if resume_pos > 0:
                    headers["Range"] = f"bytes={resume_pos}-"

                response = requests.get(url, headers=headers, stream=True)
                if response.status_code not in (200, 206):
                    download.status = f"Ошибка: HTTP {response.status_code}"
                    return

                # Инициализация для расчета скорости
                start_time = time.time()
                prev_downloaded = resume_pos
                download.bytes_downloaded = resume_pos

                # Открываем файл для записи
                with open(path, "ab") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if download.is_canceled:
                            if path.exists():
                                os.unlink(path)
                            download.status = "Отменено"
                            return
                        
                        if download.is_paused:
                            download.status = "Приостановлено"
                            while download.is_paused and not download.is_canceled:
                                time.sleep(0.5)
                            if download.is_canceled:
                                if path.exists():
                                    os.unlink(path)
                                download.status = "Отменено"
                                return
                            download.status = "Загрузка"
                        
                        if chunk:
                            f.write(chunk)
                            download.bytes_downloaded += len(chunk)
                            
                            # Обновляем прогресс
                            if download.size > 0:
                                download.progress = int((download.bytes_downloaded / download.size) * 100)
                            
                            # Обновляем скорость
                            current_time = time.time()
                            elapsed = current_time - start_time
                            if elapsed > 1:
                                speed = (download.bytes_downloaded - prev_downloaded) / elapsed
                                download.speed = format_speed(speed)
                                start_time = current_time
                                prev_downloaded = download.bytes_downloaded

                download.progress = 100
                download.status = "Завершено"
                download.speed = "0 B/s"
                
                # Вычисляем хеши
                self._calculate_hashes(download)

            except requests.RequestException as e:
                download.status = f"Ошибка: {str(e)}"
                logger.error(f"Error downloading {url}: {e}")
            except Exception as e:
                download.status = f"Ошибка: {str(e)}"
                logger.error(f"Error downloading {url}: {e}")

        # Запускаем загрузку в отдельном потоке
        download.thread = self.executor.submit(download_worker)

    def _calculate_hashes(self, download: Download):
        """Вычисление контрольных сумм файла"""
        download.status = "Проверка файла..."
        
        try:
            download.md5 = calculate_hash(download.path, "md5")
            download.sha1 = calculate_hash(download.path, "sha1")
            download.status = "Завершено"
        except Exception as e:
            logger.error(f"Error calculating hashes for {download.path}: {e}")
            download.status = "Завершено (ошибка проверки)"

    def _pause_download(self, download_id: str):
        """Пауза загрузки"""
        for download in self.downloads:
            if download.id == download_id:
                download.is_paused = True
                if download.status == "Загрузка":
                    download.status = "Приостановлено"
                return

    def _resume_download(self, download_id: str):
        """Возобновление загрузки"""
        for download in self.downloads:
            if download.id == download_id:
                download.is_paused = False
                if download.status == "Приостановлено":
                    download.status = "Загрузка"
                return

    def _cancel_download(self, download_id: str):
        """Отмена загрузки"""
        for download in self.downloads:
            if download.id == download_id:
                download.is_canceled = True
                download.is_paused = False
                if download.status in ("Загрузка", "Приостановлено", "В очереди"):
                    download.status = "Отменено"
                return

    # Публичные методы для взаимодействия с менеджером

    def add_download(self, url: str, path: Path):
        """Добавление новой загрузки"""
        self.queue.put(("add", (url, path)))

    def pause_download(self, download_id: str):
        """Приостановка загрузки"""
        self.queue.put(("pause", download_id))

    def resume_download(self, download_id: str):
        """Возобновление загрузки"""
        self.queue.put(("resume", download_id))

    def cancel_download(self, download_id: str):
        """Отмена загрузки"""
        self.queue.put(("cancel", download_id))

    def pause_all(self):
        """Приостановка всех загрузок"""
        self.is_paused = True
        for download in self.downloads:
            if download.status == "Загрузка":
                self.pause_download(download.id)

    def resume_all(self):
        """Возобновление всех загрузок"""
        self.is_paused = False
        for download in self.downloads:
            if download.status == "Приостановлено":
                self.resume_download(download.id)

    def get_download_by_id(self, download_id: str) -> Optional[Dict]:
        """Получение загрузки по идентификатору"""
        for download in self.downloads:
            if download.id == download_id:
                return download.to_dict()
        return None

    def get_download_info(self, index: int) -> Optional[Dict]:
        """Получение информации о загрузке по индексу"""
        if 0 <= index < len(self.downloads):
            return self.downloads[index].to_dict()
        return None

    def get_all_downloads(self) -> List[Dict]:
        """Получение списка всех загрузок"""
        return [download.to_dict() for download in self.downloads]

    def check_md5(self, download_id: str, expected_md5: str) -> bool:
        """Проверка MD5 хеша загрузки"""
        for download in self.downloads:
            if download.id == download_id:
                return download.md5.lower() == expected_md5.lower()
        return False

    def check_sha1(self, download_id: str, expected_sha1: str) -> bool:
        """Проверка SHA1 хеша загрузки"""
        for download in self.downloads:
            if download.id == download_id:
                return download.sha1.lower() == expected_sha1.lower()
        return False

    def shutdown(self):
        """Корректное завершение работы менеджера"""
        for download in self.downloads:
            if download.status == "Загрузка":
                download.is_paused = True
        
        self.executor.shutdown(wait=False)
        self.hash_executor.shutdown(wait=False)
        logger.info("Download Manager shut down") 