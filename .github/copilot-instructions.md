# Avito API Client Project Instructions

Этот проект содержит набор инструментов для работы с API Avito для автоматизации HR-процессов через анализ купленных резюме и коммуникаций с кандидатами.

## Архитектура проекта

### Основные компоненты
- **avito_paid_cvs_save_v14.py** - текущий главный модуль для извлечения и анализа купленных резюме с контрольной цифрой из избранного
- **avito_api_client.py** - базовый клиент API с методами аутентификации через Client Credentials
- **resume_messages_downloader.py** - загрузка сообщений из мессенджера Avito с прокси-поддержкой
- **tools/** - набор утилит для работы с API, аутентификации и отладки
- **proxies/** - менеджер прокси-серверов с автоматической ротацией и graceful fallback

### Структура данных
- Резюме экспортируются в многолистовые XLSX файлы с детализированной аналитикой
- Чаты и сообщения анализируются через Messenger API v1/v2 с типизированными статусами
- JSON-данные сохраняются для отладки и повторного анализа  
- Браузерные профили персистируются в `./avito_browser_profile/`

## Ключевые паттерны разработки

### API Authentication
```python
# Стандартная схема OAuth2 client_credentials
CLIENT_ID = "Dm4ruLMEr9MFsV72dN95"
CLIENT_SECRET = "f73lNoAJLzuqwoGtVaMnByhQfSlwcyIN_m7wyOeT"
API_BASE = "https://api.avito.ru"

# Двойная стратегия аутентификации:
# 1. Client Credentials (без браузера) - tools/smart_messages.py  
# 2. Authorization Code (с браузером) - tools/get_personal_token.py
```

### Версионирование скриптов
Проект использует инкрементальное версионирование (v7-v14) с обратной совместимостью:
- **v14** = Контрольная цифра из избранного + агрессивный парсинг до цели
- **v13** = Оптимизированная браузерная загрузка + улучшенные селекторы
- **v12** = Лист "Кому не писали" + расширенная аналитика 
- **v11** = Типизированные статусы чатов и анализ заинтересованности
- **v10** = Параллельная обработка + географическая фильтрация

### Многопоточность и Rate Limiting
```python
# Настройки по умолчанию для производительности
DEFAULT_THREADS = 8
TIMEOUT = 30
# Автоматический rate limiting через _respect_rate_limit()
# Глобальная блокировка и динамическая задержка по заголовкам API
```

### Обход ограничений API
```python
# Решение проблемы ограничения offset=1000 для чатов
# Многоуровневая стратегия загрузки:
def fetch_chats_batch(unread_only=None):
    # 1. Основная загрузка до offset=1000
    # 2. Дополнительная загрузка с unread_only=True
    # 3. Попытка загрузки через v1 API  
    # 4. Попытка загрузки по типам чатов
```

### Типизация статусов чатов
```python
class ChatStatus(Enum):
    READ_NO_REPLY = "Прочитал/не ответил"
    READ_REPLIED = "Прочитал/Ответил"  
    NO_MESSAGES_SENT = "Не высылали сообщения"
    NOT_INTERESTED = "Не интересно"
    NO_CHAT = "Чат отсутствует"
    UNKNOWN = "Неопределенный"
```

### Прокси-менеджер
```python
# Автоматическое чтение из proxies/proxy.txt
# Поддержка HTTP/SOCKS5 с ротацией
# Graceful fallback при отсутствии прокси
class ProxyManager:
    def get_session(): # Возвращает сессию с настроенной ротацией
    def next_proxy(): # Циклический доступ к следующему прокси
    def has_proxies(): # Проверка доступности прокси
```

### Tools экосистема
```python
# tools/smart_messages.py - умная аутентификация (Client Credentials → Authorization Code)
# tools/get_personal_token.py - получение персональных токенов через браузер
# tools/avito_final.py - полный экспорт чатов без браузера
# tools/export_chats.py - экспорт чатов с детальной аналитикой
# tools/get_messages_simple.py - простое получение сообщений одной функцией
```

## Рабочие процессы

### Запуск основного скрипта
```bash
# Стандартный запуск с контрольной цифрой из избранного (v14)
python avito_paid_cvs_save_v14.py --tz Europe/Moscow --threads 8

# С настройками производительности
python avito_paid_cvs_save_v14.py --limit 500 --threads 12 --tz Europe/Moscow

# Headless режим для автоматизации
python avito_paid_cvs_save_v14.py --limit 1000 --headless

# Альтернативные инструменты
python tools/smart_messages.py  # Умное получение сообщений
python tools/avito_final.py     # Полный экспорт без браузера
```

### Зависимости
```bash
pip install playwright pandas openpyxl requests tzdata
python -m playwright install chromium
```

### Структура Excel выходного файла
1. **paid_cvs** - полные данные с JSON
2. **Для_звонков** - приоритизированные кандидаты  
3. **Кому_не_писали** - кандидаты без отправленных сообщений (v12+)
4. **на_сегодня** - обновления за 24 часа
5. **Исключено_по_стоплисту** - отфильтрованные записи
6. **summary** - статистика

## Интеграционные точки

### Playwright для веб-скрапинга
- Использует персистентный профиль браузера для сохранения авторизации
- Автоматический скроллинг с обнаружением новых элементов
- Обработка AJAX-загрузки через network events

### Avito API Endpoints
- `/job/v2/resumes/{id}` - данные резюме
- `/job/v1/resumes/{id}/contacts` - контактная информация
- `/messenger/v1/accounts/{user_id}/chats` - список чатов
- `/messenger/v1/accounts/{user_id}/chats/{chat_id}/messages` - сообщения

### Обработка временных зон
```python
# Гибкая поддержка часовых поясов
def get_timezone_info(tz_name: str) -> timezone:
    # Поддержка zoneinfo (Python 3.9+) и fallback
```

## Соглашения и стандарты

### Конфигурация через переменные среды
```bash
$env:AVITO_CLIENT_ID = 'ваш_client_id'
$env:AVITO_CLIENT_SECRET = 'ваш_client_secret'  
$env:AVITO_TZ = 'Europe/Moscow'
```

### Обработка ошибок
- Retry с exponential backoff для HTTP-запросов
- Graceful degradation при недоступности API
- Подробное логирование с эмодзи для визуальной дифференциации
- Автоматическое обновление токенов при ошибках 401/403
- Обход ограничений Swagger (например, max offset=1000 для чатов)

### Выходные данные
- Все временные метки в указанной временной зоне
- JSON-данные сохраняются для отладки и повторного анализа
- CSV-совместимость для интеграции с внешними системами

Этот проект фокусируется на автоматизации HR-процессов через анализ коммуникаций с кандидатами в реальном времени.