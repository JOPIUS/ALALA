# avito_paid_cvs_save_v_12.py
# -*- coding: utf-8 -*-
"""
Avito: Купленные резюме → XLSX с анализом статусов чатов и сообщений.

v12 = v11 + ЛИСТ "КОМУ НЕ ПИСАЛИ" С ССЫЛКАМИ НА ЧАТЫ
  • Новый лист "Кому_не_писали" с кандидатами у которых chat_status = "Не высылали сообщения"
  • Все данные как в листе "Для_звонков" плюс ссылка на чат
  • Включает кандидатов из стоп-листа тоже
  • Приоритизация по готовности к работе

v11: Типизированные статусы чатов и сообщений
v10: Параллельная обработка API + географическая фильтрация
v9: Базовая функциональность с Playwright

CLI:
  python avito_paid_cvs_save_v_12.py --limit 100 --tz Europe/Moscow --threads 8

Зависимости:
  pip install playwright pandas openpyxl requests tzdata
  python -m playwright install chromium
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright, Error as PwError
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
from typing import List, Dict, Optional, Tuple
import re, time, json, sys, os
import pandas as pd

# ========== ТИПИЗАЦИЯ СТАТУСОВ ЧАТОВ ==========

class ChatStatus(Enum):
    """Статусы чатов на основе анализа сообщений"""
    READ_NO_REPLY = "Прочитал/не ответил"           # Кандидат прочитал, но не ответил
    READ_REPLIED = "Прочитал/Ответил"               # Кандидат прочитал и ответил
    NO_MESSAGES_SENT = "Не высылали сообщения"      # Мы не отправляли сообщения
    NOT_INTERESTED = "Не интересно"                 # Кандидат написал, что не интересно
    NO_CHAT = "Чат отсутствует"                     # Нет чата с кандидатом
    UNKNOWN = "Неопределенный"                      # Не удалось определить статус

class MessageDirection(Enum):
    """Направление сообщения"""
    IN = "in"               # Входящее (от кандидата)
    OUT = "out"             # Исходящее (от нас)

# ========== НАСТРОЙКИ ==========

# Константы API
API_BASE = "https://api.avito.ru"
CLIENT_ID = "Dm4ruLMEr9MFsV72dN95"
CLIENT_SECRET = "f73lNoAJLzuqwoGtVaMnByhQfSlwcyIN_m7wyOeT"

# Настройки производительности
DEFAULT_THREADS = 8
TIMEOUT = 30

# Пути к файлам
OUTPUT_DIR = r"C:\ManekiNeko\AVITO_API\output"
BROWSER_PROFILE_PATH = r".\avito_browser_profile"
STOPLIST_DIR = r".\Stoplist"

# ========== ВРЕМЕННЫЕ ЗОНЫ ==========

def get_timezone_info(tz_name: str = "Europe/Moscow") -> timezone:
    """
    Возвращает объект timezone для указанной зоны.
    Поддерживает как zoneinfo (Python 3.9+), так и простое смещение.
    """
    try:
        # Попытка использовать zoneinfo (Python 3.9+)
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz_name)
    except ImportError:
        # Fallback для старых версий Python
        if tz_name == "Europe/Moscow":
            return timezone(timedelta(hours=3))
        elif tz_name == "Europe/Kiev":
            return timezone(timedelta(hours=2))
        else:
            # По умолчанию возвращаем московское время
            return timezone(timedelta(hours=3))

# ========== ЗАГРУЗКА СТОП-ЛИСТА ==========

def load_stoplist() -> set:
    """Загружает стоп-лист из Excel-файлов в папке Stoplist"""
    stoplist = set()
    stoplist_path = Path(STOPLIST_DIR)
    
    if not stoplist_path.exists():
        print(f"📁 Папка {STOPLIST_DIR} не найдена. Стоп-лист пуст.")
        return stoplist
    
    excel_files = list(stoplist_path.glob("*.xlsx"))
    if not excel_files:
        print(f"📁 Excel файлы в {STOPLIST_DIR} не найдены. Стоп-лист пуст.")
        return stoplist
    
    print(f"📋 Загружаю стоп-лист из {len(excel_files)} файлов...")
    
    for file_path in excel_files:
        try:
            print(f"  📄 Читаю {file_path.name}")
            df = pd.read_excel(file_path)
            
            # Ищем столбцы с ID
            id_columns = [col for col in df.columns if 'id' in col.lower() or 'айди' in col.lower()]
            
            for col in id_columns:
                ids = df[col].dropna().astype(str)
                stoplist.update(ids)
                print(f"    ✅ Добавлено {len(ids)} записей из столбца '{col}'")
                
        except Exception as e:
            print(f"    ❌ Ошибка при чтении {file_path.name}: {e}")
    
    print(f"📋 Загружен стоп-лист: {len(stoplist)} записей")
    return stoplist

# ========== ФУНКЦИИ API ==========

def get_access_token() -> str:
    """Получает access token для Avito API"""
    import requests
    
    auth_url = "https://api.avito.ru/token"
    
    payload = {
        'grant_type': 'client_credentials',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    }
    
    response = requests.post(auth_url, data=payload, timeout=TIMEOUT)
    
    if response.status_code == 200:
        token_data = response.json()
        return token_data['access_token']
    else:
        raise Exception(f"Ошибка получения токена: {response.status_code} - {response.text}")

def _respect_rate_limit():
    """Пауза для соблюдения rate limits"""
    time.sleep(0.1)  # 100ms между запросами

def fetch_resume_data(resume_id: str, token: str) -> Optional[Dict]:
    """Получает данные резюме через API"""
    import requests
    
    _respect_rate_limit()
    
    url = f"{API_BASE}/job/v2/resumes/{resume_id}"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        
        if response.status_code == 401:
            # Токен истек, получаем новый
            new_token = get_access_token()
            headers = {"Authorization": f"Bearer {new_token}"}
            response = requests.get(url, headers=headers, timeout=TIMEOUT)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Ошибка API для резюме {resume_id}: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ Исключение при запросе резюме {resume_id}: {e}")
        return None

def fetch_resume_contacts(resume_id: str, token: str) -> Optional[Dict]:
    """Получает контакты резюме через API"""
    import requests
    
    _respect_rate_limit()
    
    url = f"{API_BASE}/job/v1/resumes/{resume_id}/contacts"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        
        if response.status_code == 401:
            # Токен истек, получаем новый
            new_token = get_access_token()
            headers = {"Authorization": f"Bearer {new_token}"}
            response = requests.get(url, headers=headers, timeout=TIMEOUT)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Ошибка API контактов для резюме {resume_id}: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ Исключение при запросе контактов {resume_id}: {e}")
        return None

def fetch_chats_batch(token: str, offset: int = 0, limit: int = 100, unread_only: Optional[bool] = None) -> List[Dict]:
    """
    Получает чаты через messenger API v2 с обходом ограничения offset=1000
    
    Многоуровневая стратегия:
    1. Основная загрузка до offset=1000
    2. Дополнительная загрузка с unread_only=True 
    3. Попытка загрузки через v1 API
    4. Попытка загрузки по типам чатов
    """
    import requests
    
    _respect_rate_limit()
    
    # Получаем user_id из первого запроса без него
    user_id = get_user_id(token)
    if not user_id:
        return []
    
    url = f"{API_BASE}/messenger/v2/accounts/{user_id}/chats"
    headers = {"Authorization": f"Bearer {token}"}
    
    params = {
        "offset": offset,
        "limit": min(limit, 100)  # API максимум 100
    }
    
    if unread_only is not None:
        params["unread_only"] = str(unread_only).lower()
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        
        if response.status_code == 401:
            # Токен истек, получаем новый
            new_token = get_access_token()
            headers = {"Authorization": f"Bearer {new_token}"}
            response = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            return data.get('chats', [])
        else:
            print(f"❌ Ошибка API чатов (offset={offset}): {response.status_code}")
            return []
            
    except Exception as e:
        print(f"❌ Исключение при запросе чатов (offset={offset}): {e}")
        return []

def get_user_id(token: str) -> Optional[str]:
    """Получает user_id для API запросов"""
    import requests
    
    # Простой способ получить user_id - запросить профиль пользователя
    url = f"{API_BASE}/core/v1/accounts/self"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            return str(data.get('id', ''))
        else:
            # Fallback - пробуем получить из чатов
            chat_url = f"{API_BASE}/messenger/v2/accounts/self/chats"
            response = requests.get(chat_url, headers=headers, params={"limit": 1}, timeout=TIMEOUT)
            
            if response.status_code == 200:
                # Извлекаем user_id из URL ответа или других метаданных
                return "self"  # API поддерживает "self" вместо конкретного ID
            
    except Exception as e:
        print(f"❌ Исключение при получении user_id: {e}")
    
    return "self"  # Fallback

def load_all_chats_optimized(token: str) -> Tuple[List[Dict], Dict]:
    """
    Оптимизированная загрузка всех чатов с обходом ограничения offset=1000
    
    Стратегия:
    1. Основная загрузка через v2 API до лимита offset=1000
    2. Дополнительная загрузка с unread_only=True для пропущенных
    3. Попытка загрузки через v1 API как fallback
    4. Загрузка по типам чатов если есть поддержка
    
    Возвращает: (список_чатов, статистика)
    """
    print("🔄 Загружаю все чаты из messenger API...")
    
    all_chats = []
    chat_ids_seen = set()
    stats = {
        "v2_main_loaded": 0,
        "v2_unread_loaded": 0, 
        "v1_fallback_loaded": 0,
        "chat_types_loaded": 0,
        "unique_chats": 0,
        "offset_limit_reached": False
    }
    
    # 1. Основная загрузка через v2 API
    offset = 0
    batch_size = 100
    consecutive_empty = 0
    
    while offset < 1000:  # Ограничение API
        print(f"  📥 Загружаю чаты: offset={offset}, limit={batch_size}")
        
        batch = fetch_chats_batch(token, offset=offset, limit=batch_size)
        
        if not batch:
            consecutive_empty += 1
            if consecutive_empty >= 3:
                print(f"    ⏹️ Пустые ответы подряд: {consecutive_empty}, завершаю основную загрузку")
                break
        else:
            consecutive_empty = 0
        
        new_chats = 0
        for chat in batch:
            chat_id = chat.get('id')
            if chat_id and chat_id not in chat_ids_seen:
                all_chats.append(chat)
                chat_ids_seen.add(chat_id)
                new_chats += 1
        
        stats["v2_main_loaded"] += new_chats
        print(f"    ✅ Новых чатов в batch: {new_chats} (всего уникальных: {len(all_chats)})")
        
        if len(batch) < batch_size:
            print(f"    🏁 Получен неполный batch ({len(batch)} < {batch_size}), основная загрузка завершена")
            break
            
        offset += batch_size
        time.sleep(0.1)  # Rate limiting
    
    if offset >= 1000:
        stats["offset_limit_reached"] = True
        print(f"  ⚠️ Достигнут лимит offset=1000, применяю дополнительные стратегии")
        
        # 2. Дополнительная загрузка с unread_only=True
        print(f"  🔄 Стратегия 2: Загрузка только непрочитанных чатов")
        
        unread_offset = 0
        while unread_offset < 1000:
            batch = fetch_chats_batch(token, offset=unread_offset, limit=batch_size, unread_only=True)
            
            if not batch:
                break
            
            new_chats = 0
            for chat in batch:
                chat_id = chat.get('id')
                if chat_id and chat_id not in chat_ids_seen:
                    all_chats.append(chat)
                    chat_ids_seen.add(chat_id)
                    new_chats += 1
            
            stats["v2_unread_loaded"] += new_chats
            
            if new_chats > 0:
                print(f"    ✅ Новых непрочитанных чатов: {new_chats}")
            
            if len(batch) < batch_size:
                break
                
            unread_offset += batch_size
            time.sleep(0.1)
        
        # 3. Попытка v1 API как fallback
        print(f"  🔄 Стратегия 3: Пробую v1 API как fallback")
        try:
            v1_chats = fetch_chats_v1_fallback(token)
            
            new_chats = 0
            for chat in v1_chats:
                chat_id = chat.get('id')
                if chat_id and chat_id not in chat_ids_seen:
                    all_chats.append(chat)
                    chat_ids_seen.add(chat_id)
                    new_chats += 1
            
            stats["v1_fallback_loaded"] = new_chats
            if new_chats > 0:
                print(f"    ✅ Новых чатов через v1 API: {new_chats}")
        except Exception as e:
            print(f"    ❌ v1 API недоступен: {e}")
        
        # 4. Загрузка по типам чатов (если поддерживается)
        print(f"  🔄 Стратегия 4: Пробую загрузку по типам чатов")
        chat_types = ["job_response", "job_invite", "other"]
        
        for chat_type in chat_types:
            try:
                type_chats = fetch_chats_by_type(token, chat_type)
                
                new_chats = 0
                for chat in type_chats:
                    chat_id = chat.get('id')
                    if chat_id and chat_id not in chat_ids_seen:
                        all_chats.append(chat)
                        chat_ids_seen.add(chat_id)
                        new_chats += 1
                
                stats["chat_types_loaded"] += new_chats
                if new_chats > 0:
                    print(f"    ✅ Новых чатов типа '{chat_type}': {new_chats}")
                    
            except Exception as e:
                print(f"    ❌ Загрузка чатов типа '{chat_type}' неудачна: {e}")
    
    stats["unique_chats"] = len(all_chats)
    
    print(f"📊 Статистика загрузки чатов:")
    print(f"  📥 Основная загрузка v2: {stats['v2_main_loaded']}")
    print(f"  📥 Непрочитанные v2: {stats['v2_unread_loaded']}")
    print(f"  📥 Fallback v1: {stats['v1_fallback_loaded']}")
    print(f"  📥 По типам чатов: {stats['chat_types_loaded']}")
    print(f"  🎯 Всего уникальных чатов: {stats['unique_chats']}")
    
    return all_chats, stats

def fetch_chats_v1_fallback(token: str) -> List[Dict]:
    """Fallback загрузка через v1 API"""
    import requests
    
    user_id = get_user_id(token)
    url = f"{API_BASE}/messenger/v1/accounts/{user_id}/chats"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            return data.get('chats', [])
        else:
            return []
            
    except Exception:
        return []

def fetch_chats_by_type(token: str, chat_type: str) -> List[Dict]:
    """Загрузка чатов по типу (если поддерживается API)"""
    import requests
    
    user_id = get_user_id(token)
    url = f"{API_BASE}/messenger/v2/accounts/{user_id}/chats"
    headers = {"Authorization": f"Bearer {token}"}
    
    params = {
        "chat_type": chat_type,
        "limit": 100
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            return data.get('chats', [])
        else:
            return []
            
    except Exception:
        return []

def fetch_chat_messages(chat_id: str, token: str, limit: int = 20) -> List[Dict]:
    """Получает сообщения из чата"""
    import requests
    
    _respect_rate_limit()
    
    user_id = get_user_id(token)
    url = f"{API_BASE}/messenger/v1/accounts/{user_id}/chats/{chat_id}/messages"
    headers = {"Authorization": f"Bearer {token}"}
    
    params = {"limit": limit}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        
        if response.status_code == 401:
            # Токен истек, получаем новый
            new_token = get_access_token()
            headers = {"Authorization": f"Bearer {new_token}"}
            response = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            return data.get('messages', [])
        else:
            return []
            
    except Exception:
        return []

# ========== АНАЛИЗ СТАТУСОВ ЧАТОВ ==========

def analyze_chat_status(chat_data: Dict, messages: List[Dict]) -> Tuple[ChatStatus, MessageDirection, str]:
    """
    Анализирует статус чата на основе сообщений
    
    Возвращает: (статус_чата, направление_последнего_сообщения, текст_последнего_сообщения)
    """
    if not messages:
        return ChatStatus.NO_MESSAGES_SENT, MessageDirection.OUT, ""
    
    # Сортируем сообщения по времени (самые новые первые)
    sorted_messages = sorted(messages, key=lambda x: x.get('created', ''), reverse=True)
    
    # Анализируем последнее сообщение
    last_message = sorted_messages[0]
    last_direction = MessageDirection(last_message.get('direction', 'out'))
    last_text = last_message.get('content', {}).get('text', '')
    
    # Ищем отказы и негативные ответы в тексте сообщений
    refusal_patterns = [
        r'не\s*интересно',
        r'не\s*подходит',
        r'нашел\s*(другую)?\s*работу',
        r'уже\s*трудоустроен',
        r'спасибо.*не\s*нужно',
        r'отказываю',
        r'не\s*рассматриваю'
    ]
    
    for msg in sorted_messages[:5]:  # Проверяем последние 5 сообщений
        text = msg.get('content', {}).get('text', '').lower()
        direction = MessageDirection(msg.get('direction', 'out'))
        
        if direction == MessageDirection.IN:  # Входящее от кандидата
            for pattern in refusal_patterns:
                if re.search(pattern, text):
                    return ChatStatus.NOT_INTERESTED, last_direction, last_text
    
    # Определяем статус на основе последовательности сообщений
    our_messages = [msg for msg in sorted_messages if MessageDirection(msg.get('direction', 'out')) == MessageDirection.OUT]
    their_messages = [msg for msg in sorted_messages if MessageDirection(msg.get('direction', 'out')) == MessageDirection.IN]
    
    if not our_messages:
        return ChatStatus.NO_MESSAGES_SENT, last_direction, last_text
    
    if not their_messages:
        return ChatStatus.READ_NO_REPLY, last_direction, last_text
    
    # Сравниваем время последних сообщений
    last_our_message = max(our_messages, key=lambda x: x.get('created', ''))
    last_their_message = max(their_messages, key=lambda x: x.get('created', ''))
    
    our_time = last_our_message.get('created', '')
    their_time = last_their_message.get('created', '')
    
    if their_time > our_time:
        return ChatStatus.READ_REPLIED, last_direction, last_text
    else:
        return ChatStatus.READ_NO_REPLY, last_direction, last_text

# ========== ФУНКЦИИ ПАРСИНГА ==========

def parse_status_and_location(text: str) -> Tuple[str, str, str]:
    """Парсит статус готовности, город и регион из текста резюме"""
    
    # Паттерны для статуса готовности  
    status_patterns = {
        "Активно ищу работу": r"Активно ищу работу",
        "Готов выйти завтра": r"Готов выйти завтра",
        "Буду искать работу через 2-3 месяца": r"Буду искать работу через 2-3 месяца",
        "Готов выйти в течение 2-х недель": r"Готов выйти в течение 2-х недель",
        "Готов выйти в течение месяца": r"Готов выйти в течение месяца"
    }
    
    status = "Не указан"
    for status_text, pattern in status_patterns.items():
        if re.search(pattern, text):
            status = status_text
            break
    
    # Паттерны для поиска города и региона
    location_patterns = [
        r"🏠\s*([^📞]+?)(?=📞|$)",  # После домика до телефона
        r"Местоположение[:\s]*([^📞\n]+)",
        r"Город[:\s]*([^📞\n]+)",
        r"([А-Я][а-я]+(?:\s+[А-Я][а-я]+)*)\s*область",
        r"г\.\s*([А-Я][а-я]+(?:\s+[А-Я][а-я]+)*)",
    ]
    
    city = "Не указан"
    region = "Не указан"
    
    for pattern in location_patterns:
        match = re.search(pattern, text)
        if match:
            location_text = match.group(1).strip()
            
            # Попытка парсинга "Город, Регион"
            if ',' in location_text:
                parts = [part.strip() for part in location_text.split(',')]
                if len(parts) >= 2:
                    city = parts[0]
                    region = parts[1]
                else:
                    city = parts[0]
            else:
                # Проверяем, есть ли слово "область" в тексте
                if "область" in location_text.lower():
                    region = location_text
                else:
                    city = location_text
            break
    
    return status, city, region

def process_resume_with_api(resume_data: Dict, token: str, chats_by_resume: Dict) -> Dict:
    """
    Обрабатывает одно резюме с получением данных через API и анализом чатов
    """
    resume_id = resume_data.get('resume_id', '')
    
    # Получаем данные резюме через API
    api_data = fetch_resume_data(resume_id, token)
    contacts_data = fetch_resume_contacts(resume_id, token)
    
    # Базовые данные из скрапинга
    result = {
        'resume_id': resume_id,
        'name': resume_data.get('name', ''),
        'age': resume_data.get('age', ''),
        'experience': resume_data.get('experience', ''),
        'position': resume_data.get('position', ''),
        'salary': resume_data.get('salary', ''),
        'raw_text': resume_data.get('raw_text', ''),
        'purchase_date': resume_data.get('purchase_date', ''),
        'update_date': resume_data.get('update_date', ''),
    }
    
    # Данные из API
    if api_data:
        result.update({
            'api_position': api_data.get('position', ''),
            'api_experience_months': api_data.get('experience_months', ''),
            'api_salary_from': api_data.get('salary', {}).get('from', ''),
            'api_salary_to': api_data.get('salary', {}).get('to', ''),
            'api_education': api_data.get('education', [{}])[0].get('name', '') if api_data.get('education') else '',
            'api_skills': ', '.join(api_data.get('skills', [])),
        })
    
    # Контактные данные
    if contacts_data:
        result.update({
            'phone': contacts_data.get('phone', ''),
            'email': contacts_data.get('email', ''),
        })
    
    # Парсинг статуса и местоположения
    raw_text = result['raw_text']
    status, city, region = parse_status_and_location(raw_text)
    result.update({
        'status': status,
        'city': city,
        'region': region,
    })
    
    # Анализ чата
    chat_data = chats_by_resume.get(resume_id, {})
    if chat_data:
        chat_id = chat_data.get('id', '')
        messages = fetch_chat_messages(chat_id, token) if chat_id else []
        
        chat_status, last_msg_direction, last_msg_text = analyze_chat_status(chat_data, messages)
        
        result.update({
            'chat_id': chat_id,
            'chat_status': chat_status.value,
            'last_message_direction': last_msg_direction.value,
            'last_message_text': last_msg_text[:100] + '...' if len(last_msg_text) > 100 else last_msg_text,
            'chat_url': f"https://www.avito.ru/profile/messenger/{chat_id}" if chat_id else ""
        })
    else:
        result.update({
            'chat_id': '',
            'chat_status': ChatStatus.NO_CHAT.value,
            'last_message_direction': '',
            'last_message_text': '',
            'chat_url': ''
        })
    
    return result

# ========== ФУНКЦИИ ОБРАБОТКИ ==========

def process_resumes_parallel(resume_list: List[Dict], token: str, chats_by_resume: Dict, max_workers: int = 8) -> List[Dict]:
    """
    Параллельная обработка резюме с API-запросами и анализом чатов
    """
    print(f"🚀 Начинаю параллельную обработку {len(resume_list)} резюме (потоков: {max_workers})")
    
    processed_resumes = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Создаем задачи
        future_to_resume = {
            executor.submit(process_resume_with_api, resume_data, token, chats_by_resume): resume_data
            for resume_data in resume_list
        }
        
        # Обрабатываем результаты
        for future in as_completed(future_to_resume):
            resume_data = future_to_resume[future]
            try:
                result = future.result()
                processed_resumes.append(result)
                
                if len(processed_resumes) % 10 == 0:
                    print(f"  ✅ Обработано: {len(processed_resumes)}/{len(resume_list)}")
                    
            except Exception as e:
                print(f"❌ Ошибка обработки резюме {resume_data.get('resume_id', 'unknown')}: {e}")
    
    print(f"🏁 Параллельная обработка завершена: {len(processed_resumes)} резюме")
    return processed_resumes

def create_priority_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Создает приоритизированный DataFrame для звонков"""
    
    # Приоритеты по статусу готовности
    status_priority = {
        "Активно ищу работу": 1,
        "Готов выйти завтра": 2,
        "Готов выйти в течение 2-х недель": 3,
        "Готов выйти в течение месяца": 4,
        "Буду искать работу через 2-3 месяца": 5,
        "Не указан": 6
    }
    
    # Приоритеты по статусу чата
    chat_priority = {
        "Прочитал/Ответил": 1,
        "Прочитал/не ответил": 2,  
        "Не высылали сообщения": 3,
        "Чат отсутствует": 4,
        "Не интересно": 5,
        "Неопределенный": 6
    }
    
    # Копируем DataFrame
    priority_df = df.copy()
    
    # Добавляем приоритеты
    priority_df['status_priority'] = priority_df['status'].map(status_priority).fillna(6)
    priority_df['chat_priority'] = priority_df['chat_status'].map(chat_priority).fillna(6)
    
    # Комбинированный приоритет (меньше = выше приоритет)
    priority_df['combined_priority'] = priority_df['status_priority'] + priority_df['chat_priority'] * 0.1
    
    # Сортируем по приоритету
    priority_df = priority_df.sort_values(['combined_priority', 'update_date'], ascending=[True, False])
    
    # Убираем служебные столбцы
    priority_df = priority_df.drop(['status_priority', 'chat_priority', 'combined_priority'], axis=1)
    
    return priority_df

def filter_today_updates(df: pd.DataFrame, tz: timezone) -> pd.DataFrame:
    """Фильтрует резюме, обновленные сегодня"""
    today = datetime.now(tz).date()
    
    def is_today(date_str):
        if pd.isna(date_str) or date_str == '':
            return False
        try:
            # Парсим дату обновления
            if 'сегодня' in str(date_str).lower():
                return True
            elif 'вчера' in str(date_str).lower():
                return False
            
            # Пытаемся распарсить как дату
            date_obj = pd.to_datetime(date_str).date()
            return date_obj == today
        except:
            return False
    
    return df[df['update_date'].apply(is_today)]

def create_not_contacted_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Создает DataFrame с кандидатами, кому не писали
    Включает всех кандидатов с chat_status = "Не высылали сообщения"
    """
    # Фильтруем кандидатов, кому не писали
    not_contacted = df[df['chat_status'] == ChatStatus.NO_MESSAGES_SENT.value].copy()
    
    if not_contacted.empty:
        return not_contacted
    
    # Приоритеты по статусу готовности (для сортировки)
    status_priority = {
        "Активно ищу работу": 1,
        "Готов выйти завтра": 2,
        "Готов выйти в течение 2-х недель": 3,
        "Готов выйти в течение месяца": 4,
        "Буду искать работу через 2-3 месяца": 5,
        "Не указан": 6
    }
    
    # Добавляем приоритет для сортировки
    not_contacted['status_priority'] = not_contacted['status'].map(status_priority).fillna(6)
    
    # Сортируем по приоритету готовности и дате обновления
    not_contacted = not_contacted.sort_values(['status_priority', 'update_date'], ascending=[True, False])
    
    # Убираем служебный столбец
    not_contacted = not_contacted.drop(['status_priority'], axis=1)
    
    return not_contacted

# ========== СКРАПИНГ С PLAYWRIGHT ==========

def scrape_resumes_with_playwright(limit: int = 100, headless: bool = True) -> List[Dict]:
    """Скрапинг резюме с помощью Playwright"""
    
    print(f"🎭 Запускаю Playwright для скрапинга {limit} резюме...")
    
    resumes = []
    
    with sync_playwright() as p:
        # Запускаем браузер с персистентным профилем
        browser = p.chromium.launch_persistent_context(
            user_data_dir=BROWSER_PROFILE_PATH,
            headless=headless,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        
        try:
            page = browser.new_page()
            page.set_default_timeout(30000)
            
            # Переходим на страницу купленных резюме
            print("🌐 Перехожу на страницу купленных резюме...")
            page.goto("https://www.avito.ru/profile/paid-cvs")
            page.wait_for_load_state('networkidle')
            
            # Ждем загрузки контента
            page.wait_for_selector('[data-marker="item"]', timeout=10000)
            
            print("📊 Начинаю скроллинг и сбор данных...")
            
            # Скроллинг с обнаружением новых элементов
            resume_count = 0
            scroll_attempts = 0
            max_scroll_attempts = 50
            
            while resume_count < limit and scroll_attempts < max_scroll_attempts:
                # Ищем все элементы резюме на странице
                resume_elements = page.query_selector_all('[data-marker="item"]')
                
                if len(resume_elements) > resume_count:
                    # Обрабатываем новые элементы
                    for i in range(resume_count, min(len(resume_elements), limit)):
                        element = resume_elements[i]
                        
                        try:
                            resume_data = extract_resume_data(element)
                            if resume_data and resume_data['resume_id']:
                                resumes.append(resume_data)
                                print(f"  ✅ {len(resumes)}. {resume_data['name']} (ID: {resume_data['resume_id']})")
                        except Exception as e:
                            print(f"  ❌ Ошибка обработки резюме {i+1}: {e}")
                    
                    resume_count = len(resumes)
                
                if resume_count >= limit:
                    break
                
                # Скроллим вниз
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1)
                
                # Проверяем, появились ли новые элементы
                new_elements = page.query_selector_all('[data-marker="item"]')
                if len(new_elements) == len(resume_elements):
                    scroll_attempts += 1
                else:
                    scroll_attempts = 0
                
                print(f"  📄 Элементов на странице: {len(new_elements)}, собрано: {resume_count}")
            
            print(f"🏁 Скрапинг завершен: {len(resumes)} резюме")
            
        except Exception as e:
            print(f"❌ Ошибка скрапинга: {e}")
        finally:
            browser.close()
    
    return resumes

def extract_resume_data(element) -> Optional[Dict]:
    """Извлекает данные резюме из DOM-элемента"""
    try:
        # ID резюме из ссылки
        link_element = element.query_selector('a[href*="/resume/"]')
        resume_id = ""
        if link_element:
            href = link_element.get_attribute('href')
            if href:
                match = re.search(r'/resume/(\w+)', href)
                if match:
                    resume_id = match.group(1)
        
        if not resume_id:
            return None
        
        # Текст всего элемента для дальнейшего парсинга
        raw_text = element.inner_text()
        
        # Базовая информация
        name_element = element.query_selector('[data-marker="item-title"]')
        name = name_element.inner_text().strip() if name_element else ""
        
        # Извлекаем остальные данные из текста
        age = extract_age(raw_text)
        experience = extract_experience(raw_text)
        position = extract_position(raw_text)
        salary = extract_salary(raw_text)
        purchase_date = extract_purchase_date(raw_text)
        update_date = extract_update_date(raw_text)
        
        return {
            'resume_id': resume_id,
            'name': name,
            'age': age,
            'experience': experience,
            'position': position,
            'salary': salary,
            'raw_text': raw_text,
            'purchase_date': purchase_date,
            'update_date': update_date,
        }
        
    except Exception as e:
        print(f"❌ Ошибка извлечения данных резюме: {e}")
        return None

def extract_age(text: str) -> str:
    """Извлекает возраст из текста"""
    patterns = [
        r'(\d+)\s*лет',
        r'(\d+)\s*года',
        r'(\d+)\s*год',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    
    return ""

def extract_experience(text: str) -> str:
    """Извлекает опыт работы из текста"""
    patterns = [
        r'Опыт работы[:\s]*([^\n]+)',
        r'(\d+\s*(?:лет|года|год))\s*опыта',
        r'Стаж[:\s]*([^\n]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    
    return ""

def extract_position(text: str) -> str:
    """Извлекает желаемую должность из текста"""
    lines = text.split('\n')
    
    # Ищем строку с должностью (обычно одна из первых строк)
    for i, line in enumerate(lines[:5]):
        line = line.strip()
        if line and not re.match(r'^\d+\s*(лет|года|год)', line) and len(line) > 5:
            # Проверяем, что это не имя и не другая служебная информация
            if not re.match(r'^[А-Я][а-я]+\s+[А-Я][а-я]+$', line):
                return line
    
    return ""

def extract_salary(text: str) -> str:
    """Извлекает зарплату из текста"""
    patterns = [
        r'(\d+\s*(?:\d+\s*)*\d+)\s*₽',
        r'от\s*(\d+\s*(?:\d+\s*)*\d+)',
        r'до\s*(\d+\s*(?:\d+\s*)*\d+)',
        r'Зарплата[:\s]*([^\n]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    
    return ""

def extract_purchase_date(text: str) -> str:
    """Извлекает дату покупки из текста"""
    patterns = [
        r'Куплено[:\s]*([^\n]+)',
        r'Покупка[:\s]*([^\n]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    
    return ""

def extract_update_date(text: str) -> str:
    """Извлекает дату обновления из текста"""
    patterns = [
        r'Обновлено[:\s]*([^\n]+)',
        r'сегодня|вчера|\d+\s+\w+\s+назад',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).strip()
    
    return ""

# ========== СОЗДАНИЕ EXCEL ==========

def create_excel_output(resumes: List[Dict], stoplist: set, tz: timezone) -> str:
    """Создает Excel файл с несколькими листами"""
    
    timestamp = datetime.now(tz).strftime("%Y%m%d_%H%M%S")
    output_file = Path(OUTPUT_DIR) / f"avito_paid_cvs_{timestamp}.xlsx"
    
    # Создаем папку если не существует
    output_file.parent.mkdir(exist_ok=True)
    
    print(f"📊 Создаю Excel файл: {output_file}")
    
    # Основной DataFrame
    df = pd.DataFrame(resumes)
    
    # Разделяем на включенные и исключенные
    included_df = df[~df['resume_id'].isin(stoplist)].copy()
    excluded_df = df[df['resume_id'].isin(stoplist)].copy()
    
    # Создаем приоритизированный лист для звонков
    priority_df = create_priority_dataframe(included_df)
    
    # Создаем лист с обновлениями за сегодня
    today_df = filter_today_updates(included_df, tz)
    
    # Создаем лист с кандидатами, кому не писали (включая из стоп-листа)
    not_contacted_df = create_not_contacted_dataframe(df)  # Используем весь df, включая стоп-лист
    
    # Статистика
    stats = {
        'Показатель': [
            'Всего резюме собрано',
            'Включено в обработку',
            'Исключено по стоп-листу',
            'Приоритетных для звонков',
            'Обновлено сегодня',
            'Кому не писали',
            'Активно ищут работу',
            'Готовы выйти завтра',
            'Прочитали и ответили',
            'Прочитали, не ответили',
            'Не интересно',
        ],
        'Количество': [
            len(df),
            len(included_df),
            len(excluded_df),
            len(priority_df),
            len(today_df),
            len(not_contacted_df),
            len(df[df['status'] == 'Активно ищу работу']),
            len(df[df['status'] == 'Готов выйти завтра']),
            len(df[df['chat_status'] == 'Прочитал/Ответил']),
            len(df[df['chat_status'] == 'Прочитал/не ответил']),
            len(df[df['chat_status'] == 'Не интересно']),
        ]
    }
    
    stats_df = pd.DataFrame(stats)
    
    # Записываем в Excel
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        # Лист 1: Все данные с JSON
        df.to_excel(writer, sheet_name='paid_cvs', index=False)
        
        # Лист 2: Приоритизированные для звонков
        priority_df.to_excel(writer, sheet_name='Для_звонков', index=False)
        
        # Лист 3: Обновления за сегодня
        today_df.to_excel(writer, sheet_name='на_сегодня', index=False)
        
        # Лист 4: Исключенные по стоп-листу
        excluded_df.to_excel(writer, sheet_name='Исключено_по_стоплисту', index=False)
        
        # Лист 5: Кому не писали (включая стоп-лист)
        not_contacted_df.to_excel(writer, sheet_name='Кому_не_писали', index=False)
        
        # Лист 6: Статистика
        stats_df.to_excel(writer, sheet_name='summary', index=False)
    
    print(f"✅ Excel файл создан: {output_file}")
    print(f"📋 Листы:")
    print(f"  • paid_cvs: {len(df)} резюме (все данные)")
    print(f"  • Для_звонков: {len(priority_df)} резюме (приоритетные)")
    print(f"  • на_сегодня: {len(today_df)} резюме (обновлено сегодня)")
    print(f"  • Исключено_по_стоплисту: {len(excluded_df)} резюме")
    print(f"  • Кому_не_писали: {len(not_contacted_df)} резюме (с ссылками на чаты)")
    print(f"  • summary: статистика")
    
    return str(output_file)

# ========== ОСНОВНОЙ ПРОЦЕСС ==========

def main():
    """Основная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Avito: Скрапинг купленных резюме v12')
    parser.add_argument('--limit', type=int, default=100, help='Лимит резюме для скрапинга')
    parser.add_argument('--threads', type=int, default=DEFAULT_THREADS, help='Количество потоков')
    parser.add_argument('--tz', type=str, default='Europe/Moscow', help='Временная зона')
    parser.add_argument('--headless', action='store_true', help='Запуск браузера в headless режиме')
    
    args = parser.parse_args()
    
    print("🚀 Avito: Скрапинг купленных резюме v12")
    print(f"📊 Лимит: {args.limit} резюме")
    print(f"🧵 Потоков: {args.threads}")
    print(f"🕐 Временная зона: {args.tz}")
    print(f"👻 Headless: {args.headless}")
    
    tz = get_timezone_info(args.tz)
    
    try:
        # 1. Загружаем стоп-лист
        stoplist = load_stoplist()
        
        # 2. Получаем токен API
        print("🔑 Получаю токен API...")
        token = get_access_token()
        print("✅ Токен получен")
        
        # 3. Загружаем все чаты
        all_chats, chat_stats = load_all_chats_optimized(token)
        
        # 4. Создаем словарь чатов по resume_id
        chats_by_resume = {}
        for chat in all_chats:
            chat_context = chat.get('context', {})
            if chat_context.get('type') == 'resume':
                resume_id = chat_context.get('value')
                if resume_id:
                    chats_by_resume[resume_id] = chat
        
        print(f"🔗 Найдено {len(chats_by_resume)} чатов связанных с резюме")
        
        # 5. Скрапинг резюме
        resumes = scrape_resumes_with_playwright(args.limit, args.headless)
        
        if not resumes:
            print("❌ Резюме не найдены")
            return
        
        # 6. Параллельная обработка с API
        processed_resumes = process_resumes_parallel(resumes, token, chats_by_resume, args.threads)
        
        # 7. Создание Excel
        output_file = create_excel_output(processed_resumes, stoplist, tz)
        
        print(f"🎉 Готово! Файл: {output_file}")
        
    except KeyboardInterrupt:
        print("\n⏹️ Прервано пользователем")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()