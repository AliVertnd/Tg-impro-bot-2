# 🚀 Руководство по настройке TG Ninja Bot

Это подробное руководство поможет вам развернуть и настроить TG Ninja Bot для работы с Telegram.

## 📋 Предварительные требования

### 1. Получение Telegram API credentials

1. **Перейдите на https://my.telegram.org/**
2. **Войдите в аккаунт** используя ваш номер телефона
3. **Перейдите в "API development tools"**
4. **Создайте новое приложение:**
   - App title: `TG Ninja Bot`
   - Short name: `tg-ninja-bot`
   - URL: (оставьте пустым)
   - Platform: `Desktop`
   - Description: `Telegram bot for parsing and broadcasting`

5. **Сохраните полученные данные:**
   - `api_id` - числовой идентификатор
   - `api_hash` - строка из букв и цифр

### 2. Создание Telegram бота

1. **Найдите @BotFather в Telegram**
2. **Отправьте команду** `/newbot`
3. **Введите имя бота:** `TG Ninja Bot`
4. **Введите username:** `your_ninja_bot` (должен заканчиваться на `bot`)
5. **Сохраните Bot Token** - строка вида `1234567890:ABCdefGHIjklMNOpqrSTUvwxyz`

### 3. Получение OpenAI API Key (опционально)

1. **Зарегистрируйтесь на https://platform.openai.com/**
2. **Перейдите в API Keys**
3. **Создайте новый ключ**
4. **Сохраните API Key** - строка вида `sk-...`

## 🛠 Установка и настройка

### Шаг 1: Клонирование репозитория

```bash
git clone https://github.com/yourusername/tg-ninja-bot.git
cd tg-ninja-bot
```

### Шаг 2: Создание виртуального окружения

```bash
# Создание виртуального окружения
python3 -m venv venv

# Активация (Linux/Mac)
source venv/bin/activate

# Активация (Windows)
venv\Scripts\activate
```

### Шаг 3: Установка зависимостей

```bash
pip install -r requirements.txt
```

### Шаг 4: Настройка конфигурации

```bash
# Копирование примера конфигурации
cp .env.example .env
```

Отредактируйте файл `.env`:

```env
# ===========================================
# TELEGRAM API НАСТРОЙКИ (ОБЯЗАТЕЛЬНО)
# ===========================================
API_ID=1234567                    # Ваш API ID от my.telegram.org
API_HASH=abcdef1234567890         # Ваш API Hash от my.telegram.org
BOT_TOKEN=1234567890:ABCdef...    # Token от @BotFather

# ===========================================
# БАЗА ДАННЫХ
# ===========================================
DATABASE_URL=sqlite:///data/bot.db

# Для PostgreSQL (рекомендуется для продакшена):
# DATABASE_URL=postgresql://user:password@localhost:5432/tg_ninja_bot

# ===========================================
# БЕЗОПАСНОСТЬ
# ===========================================
SECRET_KEY=your-very-secret-key-here-change-this

# ===========================================
# OPENAI (для нейрокомментирования)
# ===========================================
OPENAI_API_KEY=sk-your-openai-key-here

# ===========================================
# FLASK WEB INTERFACE
# ===========================================
FLASK_PORT=5000
DEBUG=False

# ===========================================
# ЛОГИРОВАНИЕ
# ===========================================
LOG_LEVEL=INFO
```

### Шаг 5: Создание необходимых директорий

```bash
mkdir -p data logs
```

### Шаг 6: Инициализация базы данных

```bash
python -c "from database.database import db_manager; db_manager.init_database()"
```

### Шаг 7: Тестирование установки

```bash
python test_bot.py
```

Вы должны увидеть:
```
🎉 All tests passed! Bot is ready for deployment.
```

## 🚀 Запуск бота

### Локальный запуск (для тестирования)

```bash
python main.py
```

### Запуск в фоне (Linux)

```bash
# Запуск в фоне
nohup python main.py > logs/bot.log 2>&1 &

# Проверка процесса
ps aux | grep main.py

# Остановка
pkill -f main.py
```

### Systemd сервис (рекомендуется для Linux)

```bash
# Копирование сервис файла
sudo cp tg-ninja-bot.service /etc/systemd/system/

# Редактирование путей в сервис файле
sudo nano /etc/systemd/system/tg-ninja-bot.service

# Обновление systemd
sudo systemctl daemon-reload

# Включение автозапуска
sudo systemctl enable tg-ninja-bot

# Запуск сервиса
sudo systemctl start tg-ninja-bot

# Проверка статуса
sudo systemctl status tg-ninja-bot

# Просмотр логов
sudo journalctl -u tg-ninja-bot -f
```

### Docker (рекомендуется)

```bash
# Сборка образа
docker build -t tg-ninja-bot .

# Запуск контейнера
docker run -d \
  --name tg-ninja-bot \
  -p 5000:5000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/.env:/app/.env:ro \
  tg-ninja-bot

# Проверка логов
docker logs -f tg-ninja-bot
```

### Docker Compose (полная инфраструктура)

```bash
# Запуск всех сервисов
docker-compose up -d

# Проверка статуса
docker-compose ps

# Просмотр логов
docker-compose logs -f tg-ninja-bot
```

## 🔧 Первоначальная настройка

### 1. Проверка работы бота

1. **Найдите вашего бота в Telegram** по username
2. **Отправьте команду** `/start`
3. **Убедитесь, что бот отвечает** интерактивным меню

### 2. Доступ к веб-интерфейсу

1. **Откройте браузер** и перейдите на `http://localhost:5000`
2. **Проверьте доступность** панели управления

### 3. Добавление первого аккаунта

1. **В Telegram боте** выберите "📱 Аккаунты"
2. **Нажмите "Добавить аккаунт"**
3. **Введите номер телефона** в международном формате (+7XXXXXXXXXX)
4. **Введите код подтверждения** из SMS
5. **При необходимости введите пароль** двухфакторной аутентификации

### 4. Тестирование функций

1. **Парсинг:** Попробуйте спарсить участников публичной группы
2. **Рассылка:** Создайте тестовую рассылку с большим интервалом
3. **Нейрокомментирование:** Настройте комментирование для тестового канала

## 🔒 Настройки безопасности

### 1. Firewall настройки

```bash
# Разрешить только необходимые порты
sudo ufw allow 22    # SSH
sudo ufw allow 5000  # Web interface (только если нужен внешний доступ)
sudo ufw enable
```

### 2. Nginx reverse proxy (для продакшена)

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 3. SSL сертификат

```bash
# Установка Certbot
sudo apt install certbot python3-certbot-nginx

# Получение сертификата
sudo certbot --nginx -d your-domain.com
```

## 📊 Мониторинг и обслуживание

### Просмотр логов

```bash
# Логи приложения
tail -f logs/bot.log

# Системные логи (systemd)
sudo journalctl -u tg-ninja-bot -f

# Docker логи
docker logs -f tg-ninja-bot
```

### Резервное копирование

```bash
# Создание бэкапа базы данных
cp data/bot.db backups/bot_$(date +%Y%m%d_%H%M%S).db

# Бэкап конфигурации
tar -czf backups/config_$(date +%Y%m%d_%H%M%S).tar.gz .env data/ logs/
```

### Обновление

```bash
# Остановка бота
sudo systemctl stop tg-ninja-bot

# Обновление кода
git pull origin main

# Установка новых зависимостей
pip install -r requirements.txt

# Миграция базы данных (если необходимо)
python -c "from database.database import db_manager; db_manager.migrate()"

# Запуск бота
sudo systemctl start tg-ninja-bot
```

## 🐛 Устранение неполадок

### Частые проблемы

**1. Ошибка "Module not found"**
```bash
# Убедитесь, что виртуальное окружение активировано
source venv/bin/activate

# Переустановите зависимости
pip install -r requirements.txt
```

**2. Ошибка подключения к базе данных**
```bash
# Проверьте DATABASE_URL в .env
# Убедитесь, что директория data/ существует и доступна для записи
mkdir -p data
chmod 755 data
```

**3. Бот не отвечает**
```bash
# Проверьте BOT_TOKEN
# Убедитесь, что бот не заблокирован
# Проверьте логи на наличие ошибок
tail -f logs/bot.log
```

**4. Аккаунт заблокирован**
```bash
# Уменьшите частоту операций
# Используйте VPN
# Проверьте лимиты Telegram API
```

### Получение помощи

1. **Проверьте логи** на наличие ошибок
2. **Убедитесь в правильности конфигурации**
3. **Проверьте статус всех сервисов**
4. **Обратитесь к документации Telegram API**

## 📞 Поддержка

- 📧 **Email:** support@example.com
- 💬 **Telegram:** @support_bot
- 🐛 **Issues:** [GitHub Issues](https://github.com/yourusername/tg-ninja-bot/issues)

---

**🎉 Поздравляем! Ваш TG Ninja Bot готов к работе!**

