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
from config.settings import settings
import json
from core.virus_scanner import VirusScanner

logger = logging.getLogger(__name__)

def get_softportal_direct_url(url: str) -> str:
    """Получение прямой ссылки на скачивание с softportal.com"""
    try:
        # Создаем сессию для сохранения cookies
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # Получаем страницу
        response = session.get(url)
        response.raise_for_status()
        
        # Ищем ID файла в HTML
        file_id_match = re.search(r'getsoft-(\d+)', url)
        if not file_id_match:
            raise Exception("Не удалось найти ID файла в URL")
            
        file_id = file_id_match.group(1)
        
        # Получаем информацию о файле через API
        api_url = f"https://www.softportal.com/api/file/{file_id}"
        response = session.get(api_url)
        response.raise_for_status()
        file_info = response.json()
        
        if "download_url" not in file_info:
            raise Exception("Не удалось получить ссылку на скачивание")
            
        return file_info["download_url"]
        
    except Exception as e:
        logger.error(f"Ошибка при получении прямой ссылки с softportal.com: {e}")
        raise

def get_microsoft_store_url(url: str) -> str:
    """Получение прямой ссылки на скачивание из Microsoft Store"""
    try:
        # Создаем сессию для сохранения cookies и обработки редиректов
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Referer': 'https://apps.microsoft.com/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
            'Origin': 'https://apps.microsoft.com'
        })
        
        logger.info(f"Получение информации из Microsoft Store: {url}")
        
        # Проверяем URL и определяем тип действия
        if '9N' in url.upper():
            # Ищем ID продукта
            product_id = None
            for part in url.split('/'):
                if '9N' in part.upper():
                    product_id = part.split('?')[0]
                    break
            
            if product_id:
                logger.info(f"Найден ID продукта Microsoft Store: {product_id}")
                
                # Для Microsoft Store мы не можем напрямую скачать файл
                # Возвращаем специальный URL для уведомления пользователя
                return f"ms-windows-store://pdp/?productid={product_id}"
            
        # Попробуем открыть URL напрямую
        response = session.get(url, allow_redirects=True, stream=True)
        response.raise_for_status()
        
        # Проверяем Content-Type
        content_type = response.headers.get('Content-Type', '')
        if 'application/octet-stream' in content_type or 'application/x-msdownload' in content_type:
            logger.info(f"Успешно получена прямая ссылка: {response.url}")
            return response.url
        elif 'text/html' in content_type:
            logger.warning(f"URL вернул HTML вместо файла. Попытка поиска ссылки в HTML.")
            
            # Попытка найти ссылку на файл в HTML
            download_match = re.search(r'href=[\'"]([^\'"]+\.(?:exe|msi|appx|msix|zip))[\'"]', response.text)
            if download_match:
                direct_url = download_match.group(1)
                if not direct_url.startswith('http'):
                    base_url = response.url
                    direct_url = f"{base_url.split('/')[0]}//{base_url.split('/')[2]}{direct_url}"
                
                logger.info(f"Найдена ссылка на скачивание в HTML: {direct_url}")
                return direct_url
        
        # Если не смогли найти прямую ссылку
        logger.warning(f"Не удалось получить прямую ссылку из Microsoft Store. Content-Type: {content_type}")
        return url
        
    except Exception as e:
        logger.error(f"Ошибка при получении ссылки из Microsoft Store: {e}")
        # В случае ошибки возвращаем исходный URL
        return url

def get_direct_url(url: str) -> str:
    """Получение прямой ссылки на скачивание в зависимости от сайта"""
    if "softportal.com" in url:
        return get_softportal_direct_url(url)
    elif "get.microsoft.com" in url or "apps.microsoft.com" in url:
        return get_microsoft_store_url(url)
    return url

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
        self.progress = 0  # Теперь храним как число
        self.speed = "0 B/s"
        self.status = "В очереди"
        self.created = time.time()
        self.bytes_downloaded = 0
        self.is_paused = False
        self.is_canceled = False
        self.thread = None
        self.md5 = ""
        self.sha1 = ""
        self.virus_scan_result = {}  # Результаты сканирования на вирусы
        
    def to_dict(self) -> Dict:
        # Убеждаемся, что прогресс - числовой тип
        progress_value = float(self.progress) if not isinstance(self.progress, (int, float)) else self.progress
        
        result = {
            "id": self.id,
            "url": self.url,
            "path": str(self.path),
            "name": self.name,
            "size": format_size(self.size),
            "progress": f"{progress_value:.1f}%",  # Форматируем как строку с процентом
            "speed": self.speed,
            "status": self.status,
            "created": self.created,
            "md5": self.md5,
            "sha1": self.sha1
        }
        
        # Добавляем информацию о проверке на вирусы, если она доступна
        if self.virus_scan_result:
            result["virus_scan"] = self.virus_scan_result
            
        return result

    def __repr__(self):
        return f"Download({self.name}, {self.status}, {self.progress:.1f}%)"

class DownloadManager:
    def __init__(self, max_workers: int = 5):
        self.downloads: List[Download] = []
        self.is_paused = False
        self.max_workers = max_workers
        
        # Пул потоков для загрузок
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        
        # Пул потоков для вычисления хешей и сканирования
        self.hash_executor = ThreadPoolExecutor(max_workers=2)
        
        # Очередь для коммуникации между потоками
        self.queue = Queue()
        
        # Запускаем обработчик очереди
        self.queue_thread = threading.Thread(target=self._queue_processor, daemon=True)
        self.queue_thread.start()
        
        # Инициализируем сканер вирусов
        self.virus_scanner = VirusScanner()
        
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

    def _download(self, url: str, path: Path) -> None:
        """Скачивает файл по указанному URL"""
        try:
            # Получаем прямую ссылку на скачивание
            direct_url = get_direct_url(url)
            
            # Проверяем, не является ли это Microsoft Store URL
            if direct_url.startswith("ms-windows-store://"):
                # Создаем объект загрузки с информацией о Microsoft Store
                product_id = direct_url.split("productid=")[1]
                filename = f"MicrosoftStore_{product_id}.appx"
                file_path = path if isinstance(path, Path) else Path(path)
                
                # Если путь - это директория, добавляем имя файла
                if file_path.is_dir():
                    file_path = file_path / filename
                
                # Создаем загрузку, но отмечаем её как "Не поддерживается"
                download = Download(url, file_path, filename)
                download.status = "Не поддерживается"
                download.virus_scan_result = {
                    "status": "info",
                    "message": "Загрузка из Microsoft Store не поддерживается напрямую. Используйте приложение Microsoft Store.",
                    "link": f"https://www.microsoft.com/store/productId/{product_id}"
                }
                self.downloads.append(download)
                return
            
            # Создаем сессию для скачивания
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Referer': 'https://apps.microsoft.com/'
            })
            
            # Обрабатываем Microsoft Store URL
            if "microsoft.com" in url:
                # Пытаемся получить ID из URL
                ms_id = ""
                
                # Проверяем на наличие 9N ID (типичный формат для Microsoft Store)
                for part in url.split('/'):
                    if '9N' in part.upper():
                        # Удаляем query параметры из ID
                        ms_id = part.split('?')[0]
                        break
                
                if ms_id:
                    filename = f"MicrosoftStore_{ms_id}.appx"
                    logger.info(f"Использую имя файла для Microsoft Store: {filename}")
                else:
                    filename = f"MicrosoftStore_app_{int(time.time())}.appx"
                    logger.info(f"Использую сгенерированное имя файла для Microsoft Store: {filename}")
            else:
                # Обычная ссылка - получаем имя файла из неё
                filename = sanitize_filename(os.path.basename(urlparse(url).path))
                if not filename or filename == "download":
                    filename = f"download_{int(time.time())}"
            
            # Обрабатываем путь для сохранения файла
            file_path = path if isinstance(path, Path) else Path(path)
            
            # Если path - это директория, добавляем имя файла
            if file_path.is_dir():
                file_path = file_path / filename
            # Если path не имеет расширения, это может быть директория, которой нет, или неполный путь
            elif not file_path.suffix:
                # Проверяем существует ли родительская директория
                if file_path.parent.exists():
                    # Если родительская директория существует, значит это полный путь без расширения
                    # Проверяем, это файл или директория
                    if file_path.exists() and file_path.is_dir():
                        file_path = file_path / filename
                    else:
                        # Используем указанное имя и добавляем расширение из оригинала
                        _, ext = os.path.splitext(filename)
                        if ext:  # Если у оригинала есть расширение
                            file_path = Path(f"{file_path}{ext}")
                        else:
                            file_path = file_path
                else:
                    # Родительская директория не существует, создаем нужные директории
                    os.makedirs(file_path.parent, exist_ok=True)
                    if '.' in file_path.name:  # Если в имени есть точка, вероятно это файл
                        pass  # Оставляем как есть
                    else:
                        # Это директория - добавляем имя файла
                        file_path = file_path / filename
            
            logger.info(f"Путь для сохранения файла: {file_path}")
            
            download = Download(url, file_path, filename)
            self.downloads.append(download)
            
            def download_worker():
                try:
                    # Обработка случая, когда файл уже существует или занят
                    original_path = download.path
                    retry_count = 0
                    max_retries = 5
                    
                    while retry_count < max_retries:
                        if os.path.exists(download.path):
                            try:
                                # Пытаемся открыть файл для проверки доступности
                                with open(download.path, 'a+b') as f:
                                    pass
                                # Если файл доступен и можно перезаписать, удаляем его
                                os.remove(download.path)
                                break
                            except (PermissionError, OSError):
                                # Если файл занят, создаем новый путь с уникальным именем
                                base, ext = os.path.splitext(str(original_path))
                                unique_suffix = uuid.uuid4().hex[:8]
                                download.path = Path(f"{base}_{unique_suffix}{ext}")
                                download.name = os.path.basename(str(download.path))
                                retry_count += 1
                        else:
                            # Файл не существует, можно продолжать
                            break
                    
                    # Создаем родительские директории, если они не существуют
                    parent_dir = os.path.dirname(download.path)
                    if parent_dir:
                        os.makedirs(parent_dir, exist_ok=True)
                    
                    # Получаем размер файла
                    try:
                        response = session.head(direct_url)
                        total_size = int(response.headers.get('content-length', 0))
                        download.size = total_size
                    except Exception as e:
                        logger.warning(f"Не удалось получить размер файла: {e}")
                        total_size = 0
                        download.size = 0
                    
                    # Устанавливаем начальные значения
                    download.status = "Загрузка"
                    download.progress = 0
                    download.bytes_downloaded = 0
                    
                    # Открываем файл для записи
                    with open(download.path, 'wb') as f:
                        # Скачиваем файл с отображением прогресса
                        try:
                            response = session.get(direct_url, stream=True, timeout=30)
                            response.raise_for_status()
                            
                            # Если это бинарный контент, сохраняем
                            content_type = response.headers.get('Content-Type', '')
                            if 'text/html' in content_type and 'microsoft.com' in url:
                                # Для Microsoft Store может потребоваться дополнительная обработка
                                logger.warning(f"Получен HTML контент для Microsoft Store URL. Content-Type: {content_type}")
                                
                                # Проверяем содержимое на наличие сообщения об ошибке Microsoft Store
                                ms_store_error = re.search(r"ms-windows-store://", response.text)
                                if ms_store_error:
                                    logger.error("Требуется приложение Microsoft Store для загрузки")
                                    download.status = "Не поддерживается"
                                    download.virus_scan_result = {
                                        "status": "info",
                                        "message": "Требуется приложение Microsoft Store для загрузки",
                                        "link": f"https://www.microsoft.com/store/productId/{ms_id}" if ms_id else ""
                                    }
                                    return
                                
                                # Ищем ссылку на скачивание в HTML
                                download_match = re.search(r'href=[\'"]([^\'"]+\.(?:exe|msi|appx|msix|zip))[\'"]', response.text)
                                if download_match:
                                    direct_url = download_match.group(1)
                                    if not direct_url.startswith('http'):
                                        base_url = response.url
                                        direct_url = f"{base_url.split('/')[0]}//{base_url.split('/')[2]}{direct_url}"
                                    
                                    logger.info(f"Найдена ссылка на скачивание в HTML: {direct_url}")
                                    
                                    # Повторяем запрос с найденной ссылкой
                                    response = session.get(direct_url, stream=True, timeout=30)
                                    response.raise_for_status()
                                else:
                                    logger.error("Не найдена ссылка на скачивание в HTML")
                                    download.status = "Ошибка"
                                    return
                            
                            # Проверяем Content-Type после перенаправлений
                            final_content_type = response.headers.get('Content-Type', '')
                            if 'text/html' in final_content_type:
                                logger.error(f"Получен HTML вместо файла. Content-Type: {final_content_type}")
                                download.status = "Ошибка формата"
                                return
                            
                            downloaded_size = 0
                            start_time = time.time()
                            last_update_time = start_time
                            chunk_size = 8192 * 4  # Увеличен размер чанка для оптимизации
                            
                            for chunk in response.iter_content(chunk_size=chunk_size):
                                if download.is_canceled or download.status == "Отменено":
                                    if os.path.exists(download.path):
                                        os.remove(download.path)
                                    return
                                    
                                if download.is_paused or download.status == "Пауза":
                                    while download.is_paused or download.status == "Пауза":
                                        time.sleep(0.1)
                                        if download.is_canceled or download.status == "Отменено":
                                            if os.path.exists(download.path):
                                                os.remove(download.path)
                                            return
                                        
                                if chunk:
                                    f.write(chunk)
                                    downloaded_size += len(chunk)
                                    download.bytes_downloaded = downloaded_size
                                    
                                    # Прогресс
                                    if total_size > 0:
                                        download.progress = (downloaded_size / total_size) * 100
                                    
                                    # Обновляем скорость каждую секунду
                                    current_time = time.time()
                                    if current_time - last_update_time >= 1:
                                        elapsed = current_time - start_time
                                        if elapsed > 0:
                                            speed = downloaded_size / elapsed
                                            download.speed = format_speed(speed)
                                        last_update_time = current_time
                            
                            # Завершаем загрузку
                            if downloaded_size > 0:
                                if total_size > 0 and downloaded_size >= total_size * 0.99:  # учитываем погрешность
                                    download.progress = 100
                                    download.status = "Завершено"
                                    # Вычисляем хеши файла
                                    self._calculate_hashes(download)
                                else:
                                    # Если размер файла неизвестен, но данные были загружены
                                    download.status = "Завершено"
                                    self._calculate_hashes(download)
                            else:
                                download.status = "Ошибка: пустой файл"
                        except requests.exceptions.Timeout:
                            logger.error(f"Тайм-аут при скачивании {url}")
                            download.status = "Ошибка: тайм-аут"
                        except requests.exceptions.SSLError:
                            logger.error(f"Ошибка SSL при скачивании {url}")
                            download.status = "Ошибка: SSL"
                    
                except requests.exceptions.RequestException as e:
                    logger.error(f"Ошибка сети при скачивании {url}: {e}")
                    download.status = "Ошибка сети"
                    download.progress = 0
                except (PermissionError, OSError) as e:
                    logger.error(f"Ошибка доступа к файлу при скачивании {url}: {e}")
                    download.status = "Ошибка доступа к файлу"
                    download.progress = 0
                except Exception as e:
                    logger.error(f"Ошибка при скачивании {url}: {e}")
                    download.status = "Ошибка"
                    download.progress = 0
            
            # Запускаем загрузку в отдельном потоке
            download.thread = self.executor.submit(download_worker)
            
        except Exception as e:
            logger.error(f"Ошибка при добавлении загрузки {url}: {e}")
            raise

    def _calculate_hashes(self, download: Download):
        """Вычисление контрольных сумм файла и проверка на вирусы"""
        download.status = "Проверка файла..."
        
        try:
            download.md5 = calculate_hash(download.path, "md5")
            download.sha1 = calculate_hash(download.path, "sha1")
            
            # После вычисления хешей проверяем файл на вирусы
            self._scan_for_viruses(download)
            
            download.status = "Завершено"
        except Exception as e:
            logger.error(f"Error calculating hashes for {download.path}: {e}")
            download.status = "Завершено (ошибка проверки)"

    def _scan_for_viruses(self, download: Download):
        """Проверка файла на вирусы"""
        try:
            # Проверяем файл на вирусы
            if getattr(settings, 'virustotal_api_key', ''):
                # Если есть API ключ, используем реальное сканирование
                scan_result = self.virus_scanner.scan_file(str(download.path))
            else:
                # Иначе используем имитацию сканирования
                scan_result = self.virus_scanner.mock_scan_result(str(download.path))
                
            # Сохраняем результат сканирования
            download.virus_scan_result = scan_result
            
            # Добавляем информацию о сканировании в лог
            logger.info(f"Virus scan result for {download.name}: {scan_result['status']} - {scan_result['message']}")
            
        except Exception as e:
            logger.error(f"Error scanning file {download.path} for viruses: {e}")
            download.virus_scan_result = {
                "status": "error",
                "message": f"Ошибка при проверке файла: {e}"
            }

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

    def clear_completed_downloads(self):
        """Очистка завершенных загрузок"""
        self.downloads = [d for d in self.downloads if d.status not in [
            "Завершено", "Ошибка", "Отменено", "Ошибка доступа к файлу", "Ошибка сети"
        ]]
        
    def clear_all_downloads(self):
        """Очистка всех загрузок"""
        # Сначала отменяем все активные загрузки
        for download in self.downloads:
            if download.status in ["Загрузка", "Приостановлено", "В очереди"]:
                self.cancel_download(download.id)
        
        # Затем очищаем список
        self.downloads = [] 