import os
import asyncio
import aiohttp
import hashlib
import threading
import uuid
from urllib.parse import urlparse
from typing import Dict, List, Optional, Set, Callable
from pathlib import Path
import logging
import time
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

class Download:
    """Класс для представления загрузки"""
    def __init__(self, url: str, path: Path, filename: str = None):
        self.id = str(uuid.uuid4())
        self.url = url
        self.path = path
        self.name = filename or os.path.basename(urlparse(url).path) or "noname"
        self.size = 0
        self.progress = 0
        self.speed = "0 B/s"
        self.status = "В очереди"
        self.created = time.time()
        self.bytes_downloaded = 0
        self.is_paused = False
        self.is_canceled = False
        self.tasks = []
        self.md5 = ""
        self.sha1 = ""
        
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'url': self.url,
            'path': str(self.path),
            'name': self.name,
            'size': format_size(self.size),
            'progress': self.progress,
            'speed': self.speed,
            'status': self.status,
            'created': self.created,
            'md5': self.md5,
            'sha1': self.sha1
        }

    def __repr__(self):
        return f"Download({self.name}, {self.status}, {self.progress}%)"

def format_size(size: int) -> str:
    """Форматирование размера файла"""
    for unit in ['B', 'KB', 'MB', 'GB']:
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

def calculate_hash(file_path: Path, algorithm: str = 'md5') -> str:
    """Вычисление контрольной суммы файла"""
    if not file_path.exists():
        return ""
    
    hash_obj = hashlib.new(algorithm)
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_obj.update(chunk)
    return hash_obj.hexdigest()

class DownloadManager:
    def __init__(self, max_workers: int = 5):
        self.downloads: List[Download] = []
        self.is_paused = False
        self.max_workers = max_workers
        
        # Создаем отдельный поток для асинхронного цикла
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self.thread.start()
        
        # Пул потоков для вычисления хешей
        self.executor = ThreadPoolExecutor(max_workers=2)
        
        # Создаем семафор для ограничения количества одновременных загрузок
        self.semaphore = asyncio.Semaphore(max_workers)
        
        # Очередь для коммуникации между потоками
        self.queue = asyncio.Queue()
        
        # Сессия для HTTP-запросов
        self.session = None
        self.session_ready = threading.Event()
        
        # Запускаем обработчик очереди
        asyncio.run_coroutine_threadsafe(self._queue_processor(), self.loop)
        
        # Ждем инициализации сессии
        self.session_ready.wait(timeout=5)
        
        logger.info(f"Download Manager initialized with {max_workers} workers")

    def _run_event_loop(self):
        """Запуск цикла обработки событий в отдельном потоке"""
        asyncio.set_event_loop(self.loop)
        
        async def init_session():
            self.session = aiohttp.ClientSession()
            self.session_ready.set()
        
        self.loop.run_until_complete(init_session())
        self.loop.run_forever()

    async def _queue_processor(self):
        """Обработчик очереди загрузок"""
        while True:
            item = await self.queue.get()
            action, data = item
            
            try:
                if action == "add":
                    url, path = data
                    asyncio.create_task(self._download(url, path))
                elif action == "pause":
                    download_id = data
                    await self._pause_download(download_id)
                elif action == "resume":
                    download_id = data
                    await self._resume_download(download_id)
                elif action == "cancel":
                    download_id = data
                    await self._cancel_download(download_id)
            except Exception as e:
                logger.error(f"Error processing queue item {item}: {e}")
            finally:
                self.queue.task_done()

    async def _download(self, url: str, path: Path):
        """Асинхронная загрузка файла"""
        download = Download(url, path)
        self.downloads.append(download)

        try:
            async with self.semaphore:
                if download.is_canceled:
                    return

                # Получаем информацию о файле
                async with self.session.head(url, allow_redirects=True) as response:
                    if response.status != 200:
                        download.status = f"Ошибка: HTTP {response.status}"
                        return

                    download.size = int(response.headers.get('content-length', 0))

                download.status = "Загрузка"

                # Проверяем, существует ли файл для возобновления загрузки
                if path.exists():
                    resume_pos = path.stat().st_size
                    if resume_pos >= download.size and download.size > 0:
                        download.progress = 100
                        download.status = "Завершено"
                        download.bytes_downloaded = download.size
                        await self._calculate_hashes(download)
                        return
                else:
                    resume_pos = 0
                    # Создаем файл и папку, если нужно
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.touch()

                # Устанавливаем размер чанка в зависимости от размера файла
                if download.size > 100 * 1024 * 1024:  # Более 100MB
                    chunk_size = 5 * 1024 * 1024  # 5MB
                else:
                    chunk_size = 1 * 1024 * 1024  # 1MB

                # Инициализация для расчета скорости
                start_time = time.time()
                prev_downloaded = resume_pos
                download.bytes_downloaded = resume_pos

                # Создаем задачи для загрузки кусков файла
                tasks = []

                # Если размер 0, просто создаем пустой файл
                if download.size == 0:
                    download.progress = 100
                    download.status = "Завершено"
                    await self._calculate_hashes(download)
                    return
                
                # Создаем задачи для каждого куска
                for start_pos in range(resume_pos, download.size, chunk_size):
                    end_pos = min(start_pos + chunk_size - 1, download.size - 1)
                    task = asyncio.create_task(
                        self._download_chunk(download, url, path, start_pos, end_pos)
                    )
                    tasks.append(task)
                
                # Сохраняем задачи в загрузке для возможности паузы/отмены
                download.tasks = tasks
                
                # Обновляем прогресс и скорость каждую секунду
                progress_updater = asyncio.create_task(
                    self._update_progress(download, start_time, prev_downloaded)
                )
                
                # Ожидаем завершения всех задач
                try:
                    await asyncio.gather(*tasks)
                    download.progress = 100
                    download.status = "Завершено"
                    download.speed = "0 B/s"
                    
                    # Вычисляем хеши в фоне
                    await self._calculate_hashes(download)
                    
                except asyncio.CancelledError:
                    # Загрузка была отменена
                    if download.is_canceled:
                        download.status = "Отменено"
                    else:
                        download.status = "Приостановлено"
                finally:
                    # Отменяем обновление прогресса
                    progress_updater.cancel()
                
        except aiohttp.ClientError as e:
            download.status = f"Ошибка: {str(e)}"
            logger.error(f"Error downloading {url}: {e}")
        except asyncio.CancelledError:
            # Обрабатываем отмену загрузки
            if download.is_canceled:
                download.status = "Отменено"
                # Удаляем недозагруженный файл при отмене
                if path.exists():
                    os.unlink(path)
            else:
                download.status = "Приостановлено"
        except Exception as e:
            download.status = f"Ошибка: {str(e)}"
            logger.error(f"Error downloading {url}: {e}")

    async def _download_chunk(self, download: Download, url: str, path: Path, start: int, end: int):
        """Загрузка куска файла"""
        headers = {'Range': f'bytes={start}-{end}'}
        
        while not download.is_canceled:
            if download.is_paused:
                await asyncio.sleep(0.5)
                continue
                
            try:
                async with self.session.get(url, headers=headers, allow_redirects=True) as response:
                    if response.status not in (200, 206):
                        raise Exception(f"HTTP error: {response.status}")
                    
                    chunk = await response.read()
                    
                    # Записываем кусок в файл
                    async with asyncio.to_thread(self._write_chunk, path, start, chunk):
                        pass
                    
                    # Обновляем количество загруженных байт
                    download.bytes_downloaded += len(chunk)
                    
                    return
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error downloading chunk {start}-{end}: {e}")
                # Повторяем попытку через 5 секунд
                if not download.is_canceled:
                    await asyncio.sleep(5)
                else:
                    raise

    def _write_chunk(self, path: Path, position: int, data: bytes):
        """Запись куска в файл в отдельном потоке"""
        try:
            with open(path, 'rb+') as f:
                f.seek(position)
                f.write(data)
        except Exception as e:
            logger.error(f"Error writing to file {path}: {e}")
            raise
    
    async def _update_progress(self, download: Download, start_time: float, prev_downloaded: int):
        """Обновление прогресса и скорости загрузки"""
        while True:
            await asyncio.sleep(1.0)  # Обновление каждую секунду
            
            if download.is_canceled:
                break
                
            # Рассчитываем прогресс
            if download.size > 0:
                download.progress = int((download.bytes_downloaded / download.size) * 100)
            
            # Рассчитываем скорость
            current_time = time.time()
            elapsed = current_time - start_time
            
            if elapsed > 0:
                speed = (download.bytes_downloaded - prev_downloaded) / elapsed
                download.speed = format_speed(speed)
                
                # Сбрасываем счетчики для следующего измерения
                start_time = current_time
                prev_downloaded = download.bytes_downloaded

    async def _calculate_hashes(self, download: Download):
        """Вычисление контрольных сумм файла в отдельном потоке"""
        download.status = "Проверка файла..."
        
        try:
            # Используем ThreadPoolExecutor для запуска IO-bound задачи
            loop = asyncio.get_event_loop()
            download.md5 = await loop.run_in_executor(
                self.executor, calculate_hash, download.path, 'md5'
            )
            download.sha1 = await loop.run_in_executor(
                self.executor, calculate_hash, download.path, 'sha1'
            )
            download.status = "Завершено"
        except Exception as e:
            logger.error(f"Error calculating hashes for {download.path}: {e}")
            download.status = "Завершено (ошибка проверки)"

    async def _pause_download(self, download_id: str):
        """Пауза загрузки"""
        for download in self.downloads:
            if download.id == download_id:
                download.is_paused = True
                if download.status == "Загрузка":
                    download.status = "Приостановлено"
                return

    async def _resume_download(self, download_id: str):
        """Возобновление загрузки"""
        for download in self.downloads:
            if download.id == download_id:
                download.is_paused = False
                if download.status == "Приостановлено":
                    download.status = "Загрузка"
                return

    async def _cancel_download(self, download_id: str):
        """Отмена загрузки"""
        for download in self.downloads:
            if download.id == download_id:
                download.is_canceled = True
                download.is_paused = False
                
                # Отменяем все задачи загрузки
                for task in download.tasks:
                    if not task.done():
                        task.cancel()
                        
                if download.status in ("Загрузка", "Приостановлено", "В очереди"):
                    download.status = "Отменено"
                return

    # Публичные методы для взаимодействия с менеджером

    def add_download(self, url: str, path: Path):
        """Добавление новой загрузки"""
        future = asyncio.run_coroutine_threadsafe(
            self.queue.put(("add", (url, path))), 
            self.loop
        )
        return future.result(timeout=1.0)

    def pause_download(self, download_id: str):
        """Приостановка загрузки"""
        future = asyncio.run_coroutine_threadsafe(
            self.queue.put(("pause", download_id)), 
            self.loop
        )
        return future.result(timeout=1.0)

    def resume_download(self, download_id: str):
        """Возобновление загрузки"""
        future = asyncio.run_coroutine_threadsafe(
            self.queue.put(("resume", download_id)), 
            self.loop
        )
        return future.result(timeout=1.0)

    def cancel_download(self, download_id: str):
        """Отмена загрузки"""
        future = asyncio.run_coroutine_threadsafe(
            self.queue.put(("cancel", download_id)), 
            self.loop
        )
        return future.result(timeout=1.0)

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
        
        async def close_session():
            if self.session:
                await self.session.close()
        
        asyncio.run_coroutine_threadsafe(close_session(), self.loop)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=2.0)
        self.executor.shutdown(wait=False)
        logger.info("Download Manager shut down")