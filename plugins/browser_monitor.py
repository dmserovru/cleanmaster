import logging
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)

class DownloadHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.download_callback = kwargs.pop('download_callback')
        super().__init__(*args, **kwargs)
        
    def do_OPTIONS(self):
        """Обработка CORS preflight запросов"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        
    def do_POST(self):
        try:
            self.send_header('Access-Control-Allow-Origin', '*')
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            # Обрабатываем данные о скачивании
            if data.get('type') == 'download':
                url = data.get('url')
                filename = data.get('filename')
                if url and filename:
                    self.download_callback(url, filename)
                    
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')
            
        except Exception as e:
            logger.error(f"Ошибка при обработке запроса: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode())

class BrowserMonitor:
    def __init__(self, download_callback: Callable[[str, str], None], port: int = 8080):
        self.port = port
        self.download_callback = download_callback
        self.server = None
        self.server_thread = None
        
    def start(self):
        """Запуск сервера для приема уведомлений от браузера"""
        try:
            # Создаем сервер с нашим обработчиком
            self.server = HTTPServer(
                ('localhost', self.port),
                lambda *args, **kwargs: DownloadHandler(*args, download_callback=self.download_callback, **kwargs)
            )
            
            # Запускаем сервер в отдельном потоке
            self.server_thread = Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()
            
            logger.info(f"Browser monitor started on port {self.port}")
            
        except Exception as e:
            logger.error(f"Ошибка при запуске монитора браузера: {e}")
            raise
            
    def stop(self):
        """Остановка сервера"""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            logger.info("Browser monitor stopped") 