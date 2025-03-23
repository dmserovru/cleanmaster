import os
import asyncio
import aiohttp
import hashlib
from urllib.parse import urlparse
from typing import Dict, List
from pathlib import Path
import logging
import time

logger = logging.getLogger(__name__)

class DownloadManager:
    def __init__(self, max_workers: int = 5):
        self.downloads: List[Dict] = []
        self.is_paused = False
        self.max_workers = max_workers
        self.semaphore = asyncio.Semaphore(max_workers)
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.session = aiohttp.ClientSession(loop=self.loop)

    async def _download_chunk(self, url: str, path: Path, start: int, end: int):
        headers = {'Range': f'bytes={start}-{end}'}
        async with self.session.get(url, headers=headers) as response:
            chunk = await response.read()
            with open(path, 'rb+') as f:
                f.seek(start)
                f.write(chunk)

    async def download_file(self, url: str, path: Path):
        """Многопоточная загрузка с докачкой"""
        try:
            async with self.session.head(url) as response:
                total = int(response.headers.get('content-length', 0))
                
            file_name = os.path.basename(urlparse(url).path) or "noname"
            download = {
                'url': url,
                'path': str(path),
                'name': file_name,
                'size': self._format_size(total),
                'progress': 0,
                'speed': "0 B/s",
                'status': 'Queued',
                'created': time.time()
            }
            self.downloads.append(download)
            
            if path.exists():
                resume_pos = path.stat().st_size
            else:
                resume_pos = 0
                path.touch()

            start_time = time.time()
            chunk_size = 1_048_576  # 1MB
            tasks = []
            
            for start in range(resume_pos, total, chunk_size):
                end = min(start + chunk_size - 1, total - 1)
                tasks.append(
                    self._download_chunk(url, path, start, end)
                )

            for future in asyncio.as_completed(tasks):
                await future
                downloaded = sum(chunk_size for t in tasks if t.done())
                elapsed = time.time() - start_time
                speed = downloaded / elapsed if elapsed > 0 else 0
                
                download.update({
                    'progress': int((downloaded / total) * 100),
                    'speed': self._format_speed(speed),
                    'status': 'Downloading'
                })
                
            download['status'] = 'Completed'
            logger.info(f"Downloaded {url} to {path}")

        except Exception as e:
            download['status'] = f'Error: {str(e)}'
            logger.error(f"Failed to download {url}: {e}")
            raise

    def add_download(self, url: str, path: Path):
        """Добавить загрузку в очередь"""
        task = self.loop.create_task(self.download_file(url, path))
        task.add_done_callback(self._download_complete)

    def _download_complete(self, task):
        """Коллбек при завершении"""
        if task.exception():
            logger.error(f"Download failed: {task.exception()}")
        else:
            logger.info("Download completed successfully")

    @staticmethod
    def _format_size(size: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} TB"

    @staticmethod
    def _format_speed(speed: float) -> str:
        if speed < 1024:
            return f"{speed:.2f} B/s"
        elif speed < 1024**2:
            return f"{speed/1024:.2f} KB/s"
        else:
            return f"{speed/(1024**2):.2f} MB/s"