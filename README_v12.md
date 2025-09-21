# Avito API Client v12 - Анализ купленных резюме с чатами

## Что нового в v12

### 🆕 Лист "Кому не писали"
- **Новый лист "Кому_не_писали"** с кандидатами у которых `chat_status = "Не высылали сообщения"`
- **Включает всех кандидатов** - даже тех кто в стоп-листе
- **Все данные как в листе "Для_звонков"** плюс ссылка на чат
- **Приоритизация по готовности** к работе (активно ищут -> готовы завтра -> и т.д.)
- **Прямые ссылки на чаты** в формате `https://www.avito.ru/profile/messenger/{chat_id}`

### 📊 Структура Excel файла v12

```
📄 avito_paid_cvs_YYYYMMDD_HHMMSS.xlsx
├── 📋 paid_cvs              # Все данные с JSON
├── 📋 Для_звонков           # Приоритетные кандидаты  
├── 📋 на_сегодня            # Обновленные сегодня
├── 📋 Исключено_по_стоплисту # Отфильтрованные
├── 🆕 Кому_не_писали        # Кандидаты без наших сообщений + ссылки
└── 📋 summary               # Статистика
```

## Установка и запуск

```bash
# Установка зависимостей
pip install playwright pandas openpyxl requests tzdata
python -m playwright install chromium

# Запуск
python avito_paid_cvs_save_v_12.py --limit 500 --threads 12 --tz Europe/Moscow

# Headless режим
python avito_paid_cvs_save_v_12.py --limit 1000 --headless
```

## Основные возможности

### 🎯 Анализ статусов чатов
```python
class ChatStatus(Enum):
    READ_NO_REPLY = "Прочитал/не ответил"
    READ_REPLIED = "Прочитал/Ответил"  
    NO_MESSAGES_SENT = "Не высылали сообщения"  # ← Для листа "Кому_не_писали"
    NOT_INTERESTED = "Не интересно"
    NO_CHAT = "Чат отсутствует"
```

### 📋 Лист "Кому_не_писали"
- **Фильтр**: `chat_status == "Не высылали сообщения"`
- **Включает**: Кандидатов из стоп-листа тоже
- **Сортировка**: По готовности к работе
- **Столбцы**: Все как в "Для_звонков" + `chat_url`

```python
def create_not_contacted_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Создает DataFrame с кандидатами, кому не писали"""
    not_contacted = df[df['chat_status'] == ChatStatus.NO_MESSAGES_SENT.value].copy()
    
    # Приоритизация по статусу готовности
    status_priority = {
        "Активно ищу работу": 1,
        "Готов выйти завтра": 2,
        "Готов выйти в течение 2-х недель": 3,
        # ...
    }
    
    return not_contacted.sort_values(['status_priority', 'update_date'])
```

### 🔗 Ссылки на чаты
Формат: `https://www.avito.ru/profile/messenger/{chat_id}`

```python
result.update({
    'chat_url': f"https://www.avito.ru/profile/messenger/{chat_id}" if chat_id else ""
})
```

## Архитектура v12

### 🔄 Процесс обработки
1. **Загрузка стоп-листа** из Excel файлов
2. **Получение API токена** OAuth2 client_credentials
3. **Загрузка всех чатов** с обходом offset=1000 limit
4. **Скрапинг резюме** через Playwright
5. **Параллельная обработка** с API + анализ чатов
6. **Создание 6 листов** включая новый "Кому_не_писали"

### 🧵 Многопоточность
```python
def process_resumes_parallel(resume_list, token, chats_by_resume, max_workers=8):
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Параллельная обработка API + чаты
```

### 📊 Статистика загрузки чатов
```python
stats = {
    "v2_main_loaded": 800,      # Основная загрузка v2 API
    "v2_unread_loaded": 200,    # Непрочитанные чаты  
    "v1_fallback_loaded": 50,   # Fallback через v1 API
    "chat_types_loaded": 50,    # По типам чатов
    "unique_chats": 1100        # Всего уникальных
}
```

## Изменения по версиям

### v12 ← v11
- ✅ Новый лист "Кому_не_писали" с прямыми ссылками на чаты
- ✅ Включение кандидатов из стоп-листа в анализ непроконтактированных
- ✅ Приоритизация по готовности к работе

### v11 ← v10  
- ✅ Типизированные статусы чатов (`ChatStatus`, `MessageDirection`)
- ✅ Анализ последних сообщений и определение заинтересованности
- ✅ Обход ограничения offset=1000 для чатов

### v10 ← v9
- ✅ Параллельная обработка API (ускорение в 5-8 раз)
- ✅ Географическая фильтрация и временные зоны
- ✅ Лист "на_сегодня" с фильтрацией по времени

## API Endpoints

```
🌐 Avito API Base: https://api.avito.ru

📊 Резюме:
  GET /job/v2/resumes/{id}           # Данные резюме
  GET /job/v1/resumes/{id}/contacts  # Контактная информация

💬 Чаты:  
  GET /messenger/v2/accounts/{user_id}/chats              # Список чатов
  GET /messenger/v1/accounts/{user_id}/chats/{id}/messages # Сообщения

🔐 Авторизация:
  POST /token  # OAuth2 client_credentials
```

## Примеры использования

### Базовый запуск
```bash
python avito_paid_cvs_save_v_12.py --limit 100
```

### Продакшн режим
```bash
python avito_paid_cvs_save_v_12.py \
  --limit 1000 \
  --threads 16 \
  --tz Europe/Moscow \
  --headless
```

### Анализ результатов
```python
import pandas as pd

# Читаем результаты
df = pd.read_excel('avito_paid_cvs_20241221_120000.xlsx', sheet_name='Кому_не_писали')

# Топ кандидаты для первого контакта
priority_candidates = df[df['status'] == 'Активно ищу работу'].head(10)

# Переходим по ссылкам на чаты
for _, candidate in priority_candidates.iterrows():
    print(f"{candidate['name']}: {candidate['chat_url']}")
```

## Troubleshooting

### 🔧 Распространенные проблемы

**1. Ошибка авторизации API**
```python
# Проверьте переменные среды
CLIENT_ID = "Dm4ruLMEr9MFsV72dN95"  
CLIENT_SECRET = "f73lNoAJLzuqwoGtVaMnByhQfSlwcyIN_m7wyOeT"
```

**2. Пустой лист "Кому_не_писали"**  
- Проверьте что есть чаты со статусом "Не высылали сообщения"
- Убедитесь что загрузка чатов прошла успешно
- Проверьте логи загрузки чатов

**3. Медленная обработка**
```bash
# Увеличьте количество потоков
python avito_paid_cvs_save_v_12.py --threads 16
```

**4. Ограничение offset=1000**
- v12 автоматически обходит это ограничение
- Использует множественные стратегии загрузки
- Логирует статистику обхода

### 📞 Поддержка
- Версия: **v12** (декабрь 2024)
- Автор: GitHub Copilot
- Репозиторий: [ALALA](https://github.com/JOPIUS/ALALA)