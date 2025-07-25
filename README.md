# bot_baatyr

Telegram-бот для организации походов

## Быстрый старт

1. Установите Poetry (если не установлен):
   ```bash
   pip install poetry
   ```
2. Установите зависимости:
   ```bash
   poetry install
   ```
3. Создайте файл `.env` в корне и добавьте туда:
   ```env
   BOT_TOKEN=ваш_токен_бота
   DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/botbaatyr
   ADMINS=123456789,987654321
   OWNER_ID=123456789  # Telegram ID владельца (доступ к редактированию статистики)
   ```
   - BOT_TOKEN — токен Telegram-бота (получить у BotFather)
   - DATABASE_URL — строка подключения к PostgreSQL
   - ADMINS — список Telegram ID админов через запятую

4. Запустите бота:
   ```bash
   poetry run python bot/main.py
   ```

## Структура проекта
- `bot/` — исходный код бота
- `migrations/` — миграции базы данных

---

## Требования
- Python 3.9+
- PostgreSQL 