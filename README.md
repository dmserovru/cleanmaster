# CleanDownloader

Современный менеджер загрузок с открытым исходным кодом, аналог Download Master.

## Возможности

- **Многопоточная загрузка** - Значительно ускоряет скачивание файлов
- **Возобновление загрузок** - Продолжение загрузки после обрыва соединения
- **Встроенная проверка на вирусы** - Интеграция с сервисом VirusTotal
- **Telegram-бот** - Управление загрузками через мессенджер
- **Гибкая настройка** - Управление количеством потоков, папкой загрузки и другими параметрами
- **Темная тема** - Для комфортной работы ночью

## Системные требования

- Windows 7/8/10/11
- Python 3.8 или выше

## Установка

### Из исходного кода

1. Клонируйте репозиторий:
   ```
   git clone https://github.com/yourusername/cleandownloader.git
   cd cleandownloader
   ```

2. Установите зависимости:
   ```
   pip install -r requirements.txt
   ```

3. Создайте файл `.env` с вашими API-ключами:
   ```
   VIRUSTOTAL_API_KEY=your_virustotal_api_key
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   ```

4. Запустите приложение:
   ```
   python main.py
   ```

### Скачать готовую сборку

1. Скачайте последнюю версию с [страницы релизов](https://github.com/dmserovru/cleanmaster/releases)
2. Распакуйте архив
3. Запустите `CleanDownloader.exe`

## Сборка исполняемого файла

Для создания автономного .exe файла используйте PyInstaller:

```
pyinstaller --onefile --windowed --icon=resources/app_icon.ico --name=CleanDownloader main.py
```

## Структура проекта

- `core/` - Основная логика приложения
  - `downloader.py` - Менеджер загрузок
  - `virus_check.py` - Интеграция с VirusTotal
- `gui/` - Пользовательский интерфейс
  - `main_window.py` - Главное окно приложения
- `plugins/` - Плагины
  - `telegram_bot.py` - Бот для управления через Telegram
- `config/` - Конфигурация
  - `settings.py` - Настройки приложения
- `resources/` - Ресурсы (иконки, изображения)

## Использование

1. Введите URL файла в поле ввода
2. Нажмите кнопку "Добавить"
3. Выберите место для сохранения файла
4. Отслеживайте процесс загрузки в таблице

Доступные команды:
/start - Начать работу с ботом
/help - Показать это сообщение
/check <url> - Проверить ссылку на безопасность
/about - Информация о боте

## Сравнение с Download Master

| Функция | CleanDownloader | Download Master |
|---------|----------------|----------------|
| Многопоточная загрузка | ✅ | ✅ |
| Возобновление загрузок | ✅ | ✅ |
| Проверка на вирусы | ✅ | ✅ |
| Открытый исходный код | ✅ | ❌ |
| Интеграция с Telegram | ✅ | ✅ |
| Реклама | ❌ | ✅ |

## Лицензия

Проект распространяется под лицензией MIT. См. файл LICENSE для подробностей.

## Разработка

Вклады в проект приветствуются! Пожалуйста, прочитайте [руководство по участию](CONTRIBUTING.md) прежде чем начинать.

## Контакты

- Email: 1@dmserov.ru
- Telegram: @yanis111111
