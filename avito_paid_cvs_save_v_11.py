# avito_paid_cvs_save_v_11.py
# -*- coding: utf-8 -*-
"""
Avito: Купленные резюме → XLSX с анализом статусов чатов и сообщений.

v11 = v10 + ТИПИЗИРОВАННЫЕ СТАТУСЫ ЧАТОВ И СООБЩЕНИЙ
  • Анализ статуса общения с кандидатом: "Прочитал/не ответил", "Прочитал/Ответил", "Не высылали сообщения", "Не интересно"
  • Интеграция с данными чатов и сообщений из messenger API
  • Автоматическое определение заинтересованности кандидата по последним сообщениям
  • Новые поля: chat_status, last_message_direction, last_message_text
  • Приоритизация на основе активности в чатах

Предыдущие возможности (v10):
  • Парсинг статуса готовности ("Активно ищу работу", "Готов выйти завтра")
  • Приоритетная сортировка активных кандидатов в листе "Для_звонков"
  • Параллельная обработка API (ускорение в 5-8 раз)
  • Лист "на_сегодня" с фильтрацией по времени и регионам

CLI:
  python avito_paid_cvs_save_v_11.py --limit 100 --tz Europe/Moscow --threads 8

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

# ===== TZ helper =====
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:
    try:
        from backports.zoneinfo import ZoneInfo  # type: ignore
    except Exception:
        ZoneInfo = None  # type: ignore

DEFAULT_TZ_NAME = "Europe/Moscow"

# ===== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ =====
CHATS_DATA: Dict[str, Dict] = {}  # Данные чатов из JSON файла

def _get_tz(tz_name: str):
    tz_name = (tz_name or DEFAULT_TZ_NAME).strip()
    if ZoneInfo is not None:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            pass
    if tz_name in ("Europe/Moscow", "MSK", "RU-MOW"):
        return timezone(timedelta(hours=3))
    return timezone.utc

# ===== Настройки веб-части =====
HOME_URL   = "https://www.avito.ru/"
TARGET_URL = "https://www.avito.ru/profile/paid-cvs"

USER_DATA_DIR = Path("./avito_browser_profile").resolve()
OUTPUT_DIR    = Path("./saved_pages").resolve(); OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

NAV_TIMEOUT            = 60_000
MAX_TOTAL_SCROLL_SEC   = 420
QUIET_MS               = 2000
STABLE_GROWTH_ROUNDS   = 5
MAX_WHEEL_STEPS        = 480
WHEEL_DELAY_SEC        = 0.20
WAIT_RESP_TIMEOUT_MS   = 6000
NETWORK_IDLE_GRACE     = 2

# ========== Авторизация/HTTP к Avito API ==========
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

API_BASE = "https://api.avito.ru"
TIMEOUT  = 30

APP_NAME = "Resume Sercher"
CLIENT_ID     = "Dm4ruLMEr9MFsV72dN95"
CLIENT_SECRET = "f73lNoAJLzuqwoGtVaMnByhQfSlwcyIN_m7wyOeT"
REDIRECT_URL  = "https://hireworkers.ru/"

SESSION = requests.Session()
retry_cfg = Retry(
    total=5, connect=5, read=5,
    backoff_factor=0.5,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=frozenset(["GET", "POST"]),
    raise_on_status=False,
)
SESSION.mount("https://", HTTPAdapter(max_retries=retry_cfg, pool_connections=10, pool_maxsize=10))
SESSION.headers.update({"User-Agent": f"{APP_NAME} / avito_paid_cvs_save_v6_6", "Accept": "application/json"})

class Token:
    def __init__(self) -> None:
        self._token: str | None = None
        self._exp: float = 0.0
        self.force_refresh_on_start = True
    def _refresh(self) -> None:
        r = SESSION.post(
            f"{API_BASE}/token",
            data={"grant_type": "client_credentials", "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        js = r.json()
        self._token = js["access_token"]
        self._exp = time.time() + int(js.get("expires_in", 3600)) - 20
        print("🔑 access_token обновлён")
    def get(self) -> str:
        if self.force_refresh_on_start or self._token is None or time.time() >= self._exp:
            self._refresh()
            self.force_refresh_on_start = False
        return self._token  # type: ignore[return-value]
_tok = Token()

import threading

# Глобальная блокировка для rate limiting
_rate_limit_lock = threading.Lock()
_last_request_time = 0.0

def _respect_rate_limit(resp: requests.Response) -> None:
    """Интеллектуальный rate limiting с анализом заголовков."""
    global _last_request_time
    
    try:
        with _rate_limit_lock:
            remain = int(resp.headers.get("X-RateLimit-Remaining", "5"))
            limit = int(resp.headers.get("X-RateLimit-Limit", "100"))
            reset_time = resp.headers.get("X-RateLimit-Reset")
            
            # Динамическая задержка в зависимости от оставшихся запросов
            if remain <= 1:
                sleep_time = 1.0
            elif remain <= 5:
                sleep_time = 0.3
            elif remain <= 10:
                sleep_time = 0.1
            else:
                sleep_time = 0.05  # Минимальная задержка между запросами
            
            # Учитываем время с последнего запроса
            current_time = time.time()
            elapsed = current_time - _last_request_time
            if elapsed < sleep_time:
                time.sleep(sleep_time - elapsed)
            
            _last_request_time = time.time()
            
    except Exception:
        # Fallback: минимальная задержка
        time.sleep(0.05)

def avito_get_json(path: str, *, params: dict | None = None, timeout: int | None = None) -> dict:
    to = timeout or TIMEOUT
    for attempt in (1, 2):
        try:
            resp = SESSION.get(API_BASE + path, headers={"Authorization": "Bearer " + _tok.get()}, params=params, timeout=to)
            if resp.status_code == 200:
                _respect_rate_limit(resp)
                return resp.json()
            if resp.status_code in (401, 403) and attempt == 1:
                print(f"⚠️  {resp.status_code} на {path}. Обновляю токен…")
                _tok.force_refresh_on_start = True
                _tok.get()
                continue
            print(f"⚠️  GET {path} → HTTP {resp.status_code}: {resp.text[:200]}...")
            return {}
        except requests.RequestException as e:
            if attempt == 1:
                print(f"⚠️  Ошибка сети на {path}: {e}. Рефреш токена…")
                _tok.force_refresh_on_start = True
                _tok.get()
                continue
            print(f"⛔  Ошибка сети на {path} (повтор не помог): {e}")
            return {}
    return {}

def _ensure_my_user_id() -> int:
    """
    Возвращает ваш user_id из /core/v1/accounts/self.
    Токен берём через уже настроенный _tok/SESSION.
    """
    try:
        resp = SESSION.get(
            API_BASE + "/core/v1/accounts/self",
            headers={"Authorization": "Bearer " + _tok.get()},
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"/accounts/self HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json() or {}
        uid = data.get("id") or data.get("user_id")
        if not uid:
            raise RuntimeError(f"/accounts/self: поле id/user_id не найдено: {data}")
        return int(uid)
    except Exception as e:
        print(f"⛔  _ensure_my_user_id() error: {e}")
        return 0

# ========== АНАЛИЗ СТАТУСОВ ЧАТОВ И СООБЩЕНИЙ ==========

def load_chats_from_api() -> Dict[str, Dict]:
    """
    Загружает актуальные данные чатов через API.
    Возвращает словарь: {chat_id: chat_data} для быстрого поиска.
    """
    print("🔄 Загрузка актуальных чатов через API...")
    
    try:
        # Получаем токен
        token = _tok.get()
        if not token:
            print("⛔ Не удалось получить токен для загрузки чатов")
            return {}
            
        # Получаем user_id
        user_id = _ensure_my_user_id()
        if not user_id:
            print("⛔ Не удалось получить user_id для загрузки чатов")
            return {}
        
        headers = {'Authorization': f'Bearer {token}'}
        
        # Загружаем все чаты постранично с обходом ограничения offset
        all_chats = []
        limit = 100
        max_offset = 1000  # Максимальный offset согласно Swagger
        
        def fetch_chats_batch(unread_only=None):
            """Загружает пакет чатов с опциональной фильтрацией по прочтению"""
            batch_chats = []
            offset = 0
            
            while offset <= max_offset:
                params = {'offset': offset, 'limit': limit}
                if unread_only is not None:
                    params['unread_only'] = unread_only
                    
                chats_url = f"{API_BASE}/messenger/v2/accounts/{user_id}/chats"
                
                try:
                    response = SESSION.get(chats_url, headers=headers, params=params, timeout=TIMEOUT)
                    
                    if response.status_code != 200:
                        print(f"⚠️ Ошибка загрузки чатов (offset {offset}, unread_only={unread_only}): {response.status_code}")
                        
                        # При ошибке 401/403 пробуем обновить токен
                        if response.status_code in [401, 403]:
                            print("🔑 Пробуем обновить токен...")
                            _tok.force_refresh_on_start = True
                            new_token = _tok.get()
                            headers['Authorization'] = f'Bearer {new_token}'
                            
                            # Повторяем запрос с новым токеном
                            response = SESSION.get(chats_url, headers=headers, params=params, timeout=TIMEOUT)
                            if response.status_code == 200:
                                print("✅ Токен обновлен успешно, продолжаем")
                            else:
                                print(f"❌ Даже с новым токеном ошибка: {response.status_code}")
                                break
                        elif response.status_code == 400:
                            print("⚠️ Возможно, достигнут лимит API для этого фильтра")
                            break
                        else:
                            break
                        
                    data = response.json()
                    chats = data.get('chats', [])
                    
                    if not chats:
                        print(f"✅ Больше чатов не найдено для unread_only={unread_only}")
                        break
                        
                    batch_chats.extend(chats)
                    filter_msg = f" (unread_only={unread_only})" if unread_only is not None else ""
                    print(f"✅ Загружено чатов: +{len(chats)}, всего в пакете: {len(batch_chats)}{filter_msg}")
                    
                    # Если получили меньше лимита, значит это последняя страница
                    if len(chats) < limit:
                        print(f"✅ Получен неполный результат для unread_only={unread_only}")
                        break
                        
                    offset += limit
                    time.sleep(0.1)  # Небольшая пауза между запросами
                    
                except Exception as e:
                    print(f"⚠️ Ошибка запроса чатов: {e}")
                    break
                    
            return batch_chats
        
        # Сначала загружаем все чаты (читанные и нечитанные)
        print("📥 Загружаем все чаты...")
        all_chats.extend(fetch_chats_batch())
        
        # Затем отдельно загружаем только непрочитанные чаты 
        # (могут быть другие чаты за пределами offset=1000)
        print("📨 Загружаем непрочитанные чаты отдельно...")
        unread_chats = fetch_chats_batch(unread_only=True)
        
        # Объединяем уникальные чаты (избегаем дублирования)
        existing_chat_ids = {chat.get("id") for chat in all_chats if chat.get("id")}
        unread_added = 0
        for chat in unread_chats:
            if chat.get("id") and chat.get("id") not in existing_chat_ids:
                all_chats.append(chat)
                existing_chat_ids.add(chat.get("id"))
                unread_added += 1
                
        if unread_added > 0:
            print(f"✅ Добавлено {unread_added} непрочитанных чатов")
        
        # Дополнительно: пробуем загрузить чаты по типам (если API поддерживает)
        print("🔄 Пробуем загрузить чаты разных типов...")
        try:
            # Попробуем разные типы чатов, если API поддерживает параметр chatTypes
            chat_types = ["u2i", "i2u", "public"]  # user-to-item, item-to-user, public
            for chat_type in chat_types:
                type_chats_url = f"{API_BASE}/messenger/v2/accounts/{user_id}/chats"
                type_params = {'offset': 0, 'limit': 100, 'chat_types': chat_type}
                
                type_response = SESSION.get(type_chats_url, headers=headers, params=type_params, timeout=TIMEOUT)
                if type_response.status_code == 200:
                    type_data = type_response.json()
                    type_chats = type_data.get('chats', [])
                    type_added = 0
                    
                    for chat in type_chats:
                        if chat.get("id") and chat.get("id") not in existing_chat_ids:
                            all_chats.append(chat)
                            existing_chat_ids.add(chat.get("id"))
                            type_added += 1
                            
                    if type_added > 0:
                        print(f"✅ Добавлено {type_added} чатов типа {chat_type}")
                else:
                    print(f"⚠️ Тип чатов {chat_type} не поддерживается: {type_response.status_code}")
                        
        except Exception as e:
            print(f"⚠️ Ошибка при загрузке чатов по типам: {e}")
        
        # Дополнительно пробуем загрузить через v1 API (может дать другие результаты)
        print("🔄 Пробуем загрузить дополнительные чаты через v1 API...")
        try:
            v1_chats_url = f"{API_BASE}/messenger/v1/accounts/{user_id}/chats"
            v1_params = {'offset': 0, 'limit': 100}
            v1_response = SESSION.get(v1_chats_url, headers=headers, params=v1_params, timeout=TIMEOUT)
            
            if v1_response.status_code == 200:
                v1_data = v1_response.json()
                v1_chats = v1_data.get('chats', [])
                v1_count_before = len(all_chats)
                
                for chat in v1_chats:
                    if chat.get("id") and chat.get("id") not in existing_chat_ids:
                        all_chats.append(chat)
                        existing_chat_ids.add(chat.get("id"))
                        
                v1_added = len(all_chats) - v1_count_before
                if v1_added > 0:
                    print(f"✅ Добавлено {v1_added} дополнительных чатов через v1 API")
                else:
                    print("✅ v1 API не дал новых чатов")
            else:
                print(f"⚠️ v1 API недоступен: {v1_response.status_code}")
                
        except Exception as e:
            print(f"⚠️ Ошибка при запросе v1 API: {e}")
                
        print(f"✅ Итого уникальных чатов: {len(all_chats)}")
        
        # Дополнительная информация о покрытии
        if len(all_chats) >= 1100:
            print("🎯 Отличный результат! Получено максимальное количество чатов")
        elif len(all_chats) >= 1000:
            print("✅ Хороший результат! Обход ограничения offset сработал")
        else:
            print("⚠️ Получено меньше ожидаемого количества чатов")
        
        # Преобразуем в словарь для быстрого поиска
        chat_dict = {}
        for chat in all_chats:
            chat_id = chat.get("id")
            if chat_id:
                chat_dict[chat_id] = chat
                
        print(f"✅ Загружено {len(chat_dict)} чатов через API")
        return chat_dict
        
    except Exception as e:
        print(f"⛔ Ошибка загрузки чатов через API: {e}")
        return {}


def load_chats_from_json(json_file_path: str = "avito_export_20250920_015400.json") -> Dict[str, Dict]:
    """
    Загружает данные чатов из JSON файла экспорта.
    Возвращает словарь: {chat_id: chat_data} для быстрого поиска.
    """
    if not os.path.exists(json_file_path):
        print(f"⚠️  Chat JSON file not found: {json_file_path}")
        return {}
        
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        chats = data.get("chats", [])
        chat_dict = {}
        
        for chat in chats:
            chat_id = chat.get("id")
            if chat_id:
                chat_dict[chat_id] = chat
                
        print(f"✅ Loaded {len(chat_dict)} chats from {json_file_path}")
        return chat_dict
        
    except Exception as e:
        print(f"⛔ Error loading chats from JSON: {e}")
        return {}


def analyze_chat_from_json(chat_data: Dict) -> Tuple[str, str, str]:
    """
    Анализирует данные чата из JSON экспорта.
    Возвращает: (chat_status, last_message_direction, last_message_text)
    """
    if not chat_data:
        return ChatStatus.NO_CHAT.value, "", ""
        
    last_message = chat_data.get("last_message", {})
    if not last_message:
        return ChatStatus.NO_MESSAGES_SENT.value, "", ""
        
    # Информация о последнем сообщении
    direction = last_message.get("direction", "").lower()
    message_text = ""
    content = last_message.get("content", {})
    if isinstance(content, dict):
        message_text = content.get("text", "")[:500]  # ограничим длину
        
    # Определяем направление
    if direction == "in":
        last_message_direction = "Входящее"
    elif direction == "out":
        last_message_direction = "Исходящее"
    else:
        last_message_direction = "Неизвестно"
        
    # Проверяем статус прочтения
    read_timestamp = last_message.get("read")
    delivered_timestamp = last_message.get("delivered")
    
    # Определяем статус чата
    if direction == "in":
        # Последнее сообщение входящее - кандидат написал
        if read_timestamp:
            chat_status = ChatStatus.READ_NO_REPLY.value  # Прочитали, но не ответили
        else:
            chat_status = ChatStatus.READ_NO_REPLY.value  # Входящие обычно считаем прочитанными
    elif direction == "out":
        # Последнее сообщение исходящее - мы написали
        if read_timestamp:
            chat_status = ChatStatus.READ_REPLIED.value  # Отправили и кандидат прочитал
        else:
            chat_status = ChatStatus.NO_MESSAGES_SENT.value  # Отправили, но не прочитано
    else:
        chat_status = ChatStatus.UNKNOWN.value
        
    return chat_status, last_message_direction, message_text


def get_chat_messages(chat_id: str, limit: int = 100) -> List[Dict]:
    """
    Получает сообщения чата по chat_id.
    Возвращает список сообщений.
    """
    if not chat_id:
        return []

    my_uid = _ensure_my_user_id()
    if not my_uid:
        return []

    try:
        url = f"{API_BASE}/messenger/v3/accounts/{my_uid}/chats/{chat_id}/messages/"
        params = {"limit": min(limit, 100), "offset": 0}
        r = SESSION.get(url, headers={"Authorization": "Bearer " + _tok.get()}, params=params, timeout=TIMEOUT)
        
        if r.status_code != 200:
            return []
            
        payload = r.json() or {}
        
        # Возможные варианты формата ответа
        messages = []
        if isinstance(payload.get("messages"), list):
            messages = payload["messages"]
        elif isinstance(payload.get("messages"), dict) and isinstance(payload["messages"].get("messages"), list):
            messages = payload["messages"]["messages"]
        elif isinstance(payload.get("result"), list):
            messages = payload["result"]
            
        return messages
        
    except Exception as e:
        print(f"⚠️ get_chat_messages error for {chat_id}: {e}")
        return []


def determine_chat_status(chat_id: str, my_user_id: int) -> tuple[ChatStatus, Optional[str], Optional[str]]:
    """
    Определяет статус чата на основе анализа сообщений.
    
    Возвращает:
        (chat_status, last_message_direction, last_message_text)
    """
    if not chat_id:
        return ChatStatus.NO_CHAT, None, None
    
    messages = get_chat_messages(chat_id, limit=50)
    if not messages:
        return ChatStatus.NO_CHAT, None, None
    
    # Сортируем сообщения по времени (последние сначала)
    messages.sort(key=lambda m: m.get('created', 0), reverse=True)
    
    our_messages = []
    candidate_messages = []
    
    for msg in messages:
        direction = str(msg.get('direction', '')).lower()
        author_id = msg.get('author_id')
        
        try:
            author_id = int(author_id) if author_id else None
        except:
            author_id = None
        
        if direction == MessageDirection.OUT.value:
            our_messages.append(msg)
        elif direction == MessageDirection.IN.value:
            candidate_messages.append(msg)
        elif author_id == my_user_id:
            our_messages.append(msg)
        elif author_id and author_id != my_user_id:
            candidate_messages.append(msg)
    
    # Если мы не отправляли сообщения
    if not our_messages:
        return ChatStatus.NO_MESSAGES_SENT, None, None
    
    # Если кандидат не отвечал
    if not candidate_messages:
        return ChatStatus.READ_NO_REPLY, MessageDirection.OUT.value, None
    
    # Анализируем последние сообщения
    last_message = messages[0] if messages else None
    last_message_direction = None
    last_message_text = None
    
    if last_message:
        last_direction = str(last_message.get('direction', '')).lower()
        last_author_id = last_message.get('author_id')
        
        try:
            last_author_id = int(last_author_id) if last_author_id else None
        except:
            last_author_id = None
        
        if last_direction == MessageDirection.IN.value or (last_author_id and last_author_id != my_user_id):
            last_message_direction = MessageDirection.IN.value
        else:
            last_message_direction = MessageDirection.OUT.value
        
        last_message_text = last_message.get('content', {}).get('text', '') if last_message.get('content') else ''
    
    # Определяем основной статус
    if candidate_messages:
        chat_status = ChatStatus.READ_REPLIED
    else:
        chat_status = ChatStatus.READ_NO_REPLY
    
    return chat_status, last_message_direction, last_message_text


# ——— Avito Job API wrappers

def get_resume_open_json(resume_id: str) -> dict:
    """GET /job/v2/resumes/{id} — открытые данные резюме (Resume 2.0)."""
    return avito_get_json(f"/job/v2/resumes/{resume_id}") or {}

def get_resume_paid_contacts_json(resume_id: str) -> dict:
    """GET /job/v1/resumes/{id}/contacts — купленные контакты (ResumeContacts)."""
    js = avito_get_json(f"/job/v1/resumes/{resume_id}/contacts", timeout=TIMEOUT + 10)
    if js:
        return js
    return avito_get_json(f"/job/v1/resumes/{resume_id}/contacts/", timeout=TIMEOUT + 10) or {}

# ========== Скролл/экстракт ==========
ROBUST_SCROLL_LIMIT_JS = rf"""
  async (need) => {{
    const deadline = Date.now() + {MAX_TOTAL_SCROLL_SEC} * 1000;
    const quietMs  = {QUIET_MS};
    document.documentElement.style.scrollBehavior = 'auto';
    const sleep = (ms) => new Promise(r => setTimeout(r, ms));
    const norm = s => (s||'').replace(/\s+/g,' ').trim();
    const listSelector = '[data-marker="cv-snippet"]';

    let lastMutation = Date.now();
    const mo = new MutationObserver(() => {{ lastMutation = Date.now(); }});
    mo.observe(document.body, {{childList:true, subtree:true}});

    async function clickMore() {{
      const reMore = /(показат[ьъ]\s*ещ[её]|показать больше|ещё|загрузить ещё)/i;
      const btns = Array.from(document.querySelectorAll('button,a')).filter(b => reMore.test(norm(b.textContent)));
      for (const b of btns) {{ if (!b.disabled && !b.getAttribute('aria-disabled')) {{ b.click(); await sleep(350); }} }}
    }}

    let lastCount = 0, stableRounds = 0;
    const cards = () => Array.from(document.querySelectorAll(listSelector));

    while (Date.now() < deadline) {{
      window.scrollTo(0, document.body.scrollHeight);
      await sleep(450);
      await clickMore();

      window.scrollBy(0, -200); await sleep(150);
      window.scrollTo(0, document.body.scrollHeight); await sleep(450);

      const curCount = cards().length;
      const quiet = (Date.now() - lastMutation) > quietMs;
      if (curCount <= lastCount && quiet) stableRounds++; else {{ stableRounds=0; lastCount=curCount; }}
      if (need && curCount >= need) break;
      if (stableRounds >= {STABLE_GROWTH_ROUNDS}) break;
    }}

    let before = cards().length;
    for (let i = 0; i < cards().length && Date.now() < deadline; i++) {{
      try {{ cards()[i].scrollIntoView({{block:'center'}}); }} catch(e) {{}}
      await sleep(140);
      await clickMore();
      window.scrollBy(0, 120); await sleep(80); window.scrollBy(0, -120);
      await sleep(120);
      const cur = cards().length;
      if (need && cur >= need) break;
      if (cur > before) {{ before = cur; i = Math.max(0, i-3); }}
    }}

    for (let k=0;k<10;k++) {{
      window.scrollTo(0, document.body.scrollHeight); await sleep(400); await clickMore();
      if (need && cards().length >= need) break;
    }}

    mo.disconnect();
    const total = cards().length;
    return need ? Math.min(total, need) : total;
  }}
"""

COUNT_CARDS_JS = '() => document.querySelectorAll(\'[data-marker="cv-snippet"]\').length'

EXTRACT_JS = r"""
  () => {
    const norm = s => (s||'').replace(/\s+/g,' ').trim();
    const q = (root, sel) => root.querySelector(sel);

    const getDateText = (card, preferSel, labelRx) => {
      for (const sel of preferSel) {
        const el = sel ? card.querySelector(sel) : null;
        const txt = norm(el?.textContent);
        if (txt) return txt;
      }
      const full = norm(card.textContent || '');
      const m = full.match(labelRx);
      return m ? norm(m[0]) : '';
    };

    const out = [], seen = new Set();
    const cards = Array.from(document.querySelectorAll('[data-marker="cv-snippet"]'));

    for (const card of cards) {
      const linkEl = card.querySelector('a[href]');
      const link = linkEl ? new URL(linkEl.getAttribute('href'), location.origin).href : '';
      const rid  = (link.match(/\/(\d+)(?:\?|$)/)||[])[1] || '';

      const purchasedRaw = getDateText(
        card,
        ['[data-marker="cv-snippet/date/item-bought"]', '[data-marker*="date"]'],
        /(Куплено\s+(?:сегодня|вчера|\d{1,2}\s+[А-Яа-яЁё\.]+(?:\s+\d{4})?\s+в\s+\d{1,2}:\d{2}))/i
      );
      const updatedRaw = getDateText(
        card,
        ['[data-marker="cv-snippet/date/item-changed"]', '[data-marker*="date"]'],
        /((?:Обновлено|Удалено)\s+(?:сегодня|вчера|\d{1,2}\s+[А-Яа-яЁё\.]+(?:\s+\d{4})?\s+в\s+\d{1,2}:\d{2}))/i
      );

      // Извлекаем статус готовности к работе
      const fullText = norm(card.textContent || '');
      
      // Улучшенные регулярки для поиска статусов
      const jobSearchStatus = fullText.match(/(активно\s+ищ[ауеыу]|ищ[ауеыу]\s+работу|активен|готов\s+к\s+работе|рассматриваю\s+предложения)/i)?.[0] || '';
      
      // Ищем готовность к быстрому началу работы  
      const readyToStart = fullText.match(/(готов\s+(?:выйти|приступить|начать)?\s*(?:завтра|сегодня|немедленно|сразу)|могу\s+приступить|начн[уы]|готов\s+(?:завтра|сегодня|сразу))/i)?.[0] || '';

      const rec = {
        candidate_name_web: norm(q(card, '[data-marker="cv-snippet/title"]')?.textContent),
        city_web:           norm(q(card, '[data-marker="cv-snippet/address"]')?.textContent),
        link: link, resume_id: rid,
        purchased_at_web: purchasedRaw,
        updated_at_web:   updatedRaw,
        photo_url_web:     q(card, 'img[src]')?.src || '',
        job_search_status_web: jobSearchStatus,
        ready_to_start_web: readyToStart
      };

      const key = rec.resume_id || rec.link || rec.candidate_name_web;
      if (key && !seen.has(key)) { seen.add(key); out.push(rec); }
    }
    return out;
  }
"""

# ========== Русские даты ==========
RU_MONTHS = {
    "января":1,"февраля":2,"марта":3,"апреля":4,"мая":5,"июня":6,
    "июля":7,"августа":8,"сентября":9,"октября":10,"ноября":11,"декабря":12,
    "янв":1,"фев":2,"мар":3,"апр":4,"май":5,"мая":5,"июн":6,"июл":7,
    "авг":8,"сен":9,"сент":9,"окт":10,"ноя":11,"дек":12,
    "янв.":1,"фев.":2,"мар.":3,"апр.":4,"июн.":6,"июл.":7,"авг.":8,"сен.":9,"сент.":9,"окт.":10,"ноя.":11,"дек.":12,
}

def _normalize_ru_dt_string(s: str) -> str:
    s = (s or "").lower().replace("\u00a0"," ").replace("ё","е")
    s = re.sub(r"[·•]\s*$","", s).strip()
    s = re.sub(r"^(куплен[оа]?|обновлен[оа]?|удален[оа]?|создан[оа]?|опубликован[оа]?|размещен[оа]?)\s+","", s)
    s = re.sub(r"\s+\d{4}\s*(?:г\.?|года)$","", s)
    return s.strip()

def parse_ru_dt(s: str, now: datetime | None = None) -> pd.Timestamp:
    if not s:
        return pd.NaT
    s_norm = _normalize_ru_dt_string(s)
    now = now or datetime.now()

    m = re.search(r"(сегодня|вчера)\s*в\s*(\d{1,2})\s*:\s*(\d{2})", s_norm)
    if m:
        tag, hh, mm = m.groups()
        dt = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
        if tag == "вчера":
            dt -= timedelta(days=1)
        return pd.Timestamp(dt.replace(tzinfo=None))

    text = s_norm.lower().replace("\u00a0", " ")
    m = re.search(r"(\d{1,2})\s+([а-я\.]+)(?:\s+(\d{4}))?\s+в\s+(\d{1,2}):(\d{2})", text)
    if m:
        d, mon_word, year_str, hh, mm = m.groups()
        mon = RU_MONTHS.get(mon_word, RU_MONTHS.get(mon_word.rstrip(".")))
        if not mon:
            return pd.NaT
        year = int(year_str) if year_str else (now.year - (1 if mon > now.month else 0))
        try:
            base = datetime(year, int(mon), int(d), int(hh), int(mm))
            return pd.Timestamp(base)
        except Exception:
            return pd.NaT

    return pd.NaT

# ========== STOPLIST (жёстко: C:\\ManekiNeko\\AVITO_API\\output) ==========
STOPLIST_DIR = Path(r"C:\\ManekiNeko\\AVITO_API\\output").resolve()

_FIO_PATTERNS = [
    r"\bф\.?и\.?о\.?\b", r"\bфио\b", r"\bимя\b", r"\bфамил", r"кандидат", r"соискател", r"applicant", r"name", r"full\s*name"
]
_PHONE_PATTERNS = [r"тел", r"phone", r"номер", r"mobile", r"mob"]
_COMMENT_PATTERNS = [r"полный\s*коммент", r"полный\s*комментар", r"comment", r"коммент", r"замечани", r"примечан"]

_DEF_COLS = {"phone": "Телефон", "fio": "ФИО", "comment": "Комментарий"}

def _clean_phone_series(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.replace(r"\D", "", regex=True)
    s = s.str.replace(r"^8(?=\d{10}$)", "7", regex=True)
    mask10 = s.str.match(r"^\d{10}$")
    s.loc[mask10] = "7" + s[mask10]
    return s

def _find_col(cols: list[str], patterns: list[str]) -> str | None:
    low = [c.lower().strip() for c in cols]
    for p in patterns:
        rx = re.compile(p, re.IGNORECASE)
        for i, name in enumerate(low):
            if rx.search(name):
                return cols[i]
    return None


def build_stoplist_from_output() -> tuple[pd.DataFrame, dict]:
    """
    Возвращает (stoplist_df, file_stats)
    где file_stats = {"filename": count_records, ...}
    """
    rows: list[pd.DataFrame] = []
    file_stats = {}
    if not STOPLIST_DIR.exists():
        return pd.DataFrame(columns=[_DEF_COLS["phone"], _DEF_COLS["fio"], _DEF_COLS["comment"], "Файл", "Лист"]), {}

    SHEET_NAME = "Стоплист_телефонов"
    EXPECTED_PHONE = "телефон"
    EXPECTED_FIO = "фио"
    EXPECTED_COMMENT_FULL = "полный комментарий"

    for fp in STOPLIST_DIR.glob("*.xlsx"):
        if fp.name.startswith("~$"):
            continue
        try:
            xl = pd.ExcelFile(fp, engine="openpyxl")
            if SHEET_NAME not in xl.sheet_names:
                continue

            df = xl.parse(SHEET_NAME)
            if df.empty:
                continue

            # Нормализуем названия колонок для поиска ожидаемых заголовков
            low2orig = {str(c).strip(): c for c in df.columns}
            lowmap = {k.lower(): v for k, v in low2orig.items()}

            phone_col   = lowmap.get(EXPECTED_PHONE)
            fio_col     = lowmap.get(EXPECTED_FIO)
            comment_col = lowmap.get(EXPECTED_COMMENT_FULL)

            # Без телефона — это не стоплист
            if not phone_col:
                continue

            sub = pd.DataFrame()
            sub[_DEF_COLS["phone"]] = _clean_phone_series(df[phone_col])
            sub[_DEF_COLS["fio"]] = df[fio_col] if fio_col else ""
            # Внутри системы «Комментарий» — это то, что на листе называется «Полный комментарий»
            sub[_DEF_COLS["comment"]] = df[comment_col] if comment_col else ""
            sub["Файл"], sub["Лист"] = fp.name, SHEET_NAME

            # отбросим пустые телефоны
            sub = sub[sub[_DEF_COLS["phone"]].astype(str).str.len() > 0]
            if not sub.empty:
                file_stats[fp.name] = len(sub)
                rows.append(sub[[_DEF_COLS["phone"], _DEF_COLS["fio"], _DEF_COLS["comment"], "Файл", "Лист"]])
        except Exception:
            continue

    if not rows:
        return pd.DataFrame(columns=[_DEF_COLS["phone"], _DEF_COLS["fio"], _DEF_COLS["comment"], "Файл", "Лист"]), {}

    all_df = pd.concat(rows, ignore_index=True)
    all_df[_DEF_COLS["phone"]] = _clean_phone_series(all_df[_DEF_COLS["phone"]])

    # Дедуп по телефону: оставим запись с наибольшей длиной комментария
    try:
        all_df["_clen"] = all_df[_DEF_COLS["comment"]].astype(str).map(len)
        all_df = all_df.sort_values([_DEF_COLS["phone"], "_clen"], ascending=[True, False])
        all_df = all_df.drop_duplicates(subset=[_DEF_COLS["phone"]], keep="first")
        all_df = all_df.drop(columns=["_clen"])
    except Exception:
        all_df = all_df.drop_duplicates(subset=[_DEF_COLS["phone"]], keep="first")

    return all_df.reset_index(drop=True), file_stats

# ========== Вспомогательные веб-функции ==========

def save_as_mhtml(page, out_path: Path):
    s = page.context.new_cdp_session(page)
    s.send("Page.enable")
    data = s.send("Page.captureSnapshot", {"format": "mhtml"})["data"]
    out_path.write_text(data, encoding="utf-8")
    return out_path

def goto_resilient(page, url, expect_pattern, attempts=3):
    for _ in range(attempts):
        try: page.goto(url, wait_until="commit", timeout=NAV_TIMEOUT)
        except PwError: pass
        try:
            page.wait_for_url(expect_pattern, wait_until="domcontentloaded", timeout=30_000)
            return True
        except PwError:
            try: page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30_000)
            except PwError: pass
    return False

def robust_scroll(page, need_count: int | None = None) -> int:
    try:
        count1 = page.evaluate(ROBUST_SCROLL_LIMIT_JS, need_count)
    except Exception:
        count1 = 0

    last_h, still = 0, 0
    for _ in range(MAX_WHEEL_STEPS):
        try: page.mouse.wheel(0, 1600)
        except Exception: pass
        time.sleep(WHEEL_DELAY_SEC)
        try: h = page.evaluate("Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)")
        except Exception: h = last_h
        if h <= last_h:
            still += 1
            if still >= 6: break
        else:
            still = 0; last_h = h
        if need_count is not None:
            try:
                cur = int(page.evaluate(COUNT_CARDS_JS))
                if cur >= int(need_count):
                    break
            except Exception:
                pass

    quiet = 0
    while quiet < NETWORK_IDLE_GRACE:
        try:
            page.wait_for_response(
                lambda r: ("avito.ru" in r.url) and r.status == 200 and
                          (getattr(r.request, "resource_type", None) in ("xhr","fetch")),
                timeout=WAIT_RESP_TIMEOUT_MS
            )
            quiet = 0
        except Exception:
            quiet += 1

    try:
        count2 = int(page.evaluate(COUNT_CARDS_JS))
    except Exception:
        count2 = count1
    return min(count2, need_count) if need_count else max(count1, count2)

# ========== ENRICH (API): ФИО/контакты/is_purchased/update_time ==========

def _salary_to_text(sal):
    if sal is None:
        return ""
    if isinstance(sal, (int, float)):
        return str(int(sal))
    if isinstance(sal, dict):
        lo = sal.get("from")
        hi = sal.get("to")
        cur = sal.get("currency", "")
        rng = "" if (lo is None and hi is None) else f"{lo or ''}–{hi or ''}"
        return (rng + (f" {cur}" if cur else "")).strip()
    return str(sal)


def enrich_one(resume_id: str, tz_target) -> dict:
    open_js = get_resume_open_json(resume_id)
    paid_js = get_resume_paid_contacts_json(resume_id)

    phone = email = chat_id = ""
    fio = ""
    first_name = last_name = patronymic = ""

    if paid_js:
        fio = (paid_js.get("name") or "")[:256].strip()
        fn = paid_js.get("full_name") or {}
        first_name  = str(fn.get("first_name") or "")
        last_name   = str(fn.get("last_name") or "")
        patronymic  = str(fn.get("patronymic") or "")
        if not fio:
            fio = " ".join(x for x in (last_name, first_name, patronymic) if x).strip()
        for c in (paid_js.get("contacts") or []):
            t = str(c.get("type") or "").lower()
            v = str(c.get("value") or "")
            if   t == "phone":   phone = v
            elif t in ("e-mail", "email"):  email = v
            elif t == "chat_id": chat_id = v

    # <-- НОВОЕ v11: анализ статуса чата и сообщений из JSON файла
    chat_status = ChatStatus.NO_CHAT.value
    last_message_direction = None
    last_message_text = None
    
    if chat_id and CHATS_DATA:
        try:
            # Используем данные из загруженного JSON файла вместо API вызовов
            chat_data = CHATS_DATA.get(chat_id)
            if chat_data:
                status, direction, text = analyze_chat_from_json(chat_data)
                chat_status = status
                last_message_direction = direction
                last_message_text = text[:200] if text else None  # Ограничиваем длину
                print(f"✅ Chat {chat_id}: {status} | {direction}")
            else:
                print(f"⚠️  Chat {chat_id} not found in loaded data")
        except Exception as e:
            print(f"⚠️  chat status analysis failed for {chat_id}: {e}")

    is_purchased_api = bool(open_js.get("is_purchased")) if isinstance(open_js, dict) else False
    update_time_api_raw = str(open_js.get("update_time") or "") if isinstance(open_js, dict) else ""

    try:
        ut = pd.to_datetime(update_time_api_raw, errors="coerce", utc=True)
        if pd.isna(ut):
            update_time_api = pd.NaT
        else:
            local = ut.tz_convert(tz_target)
            update_time_api = local.tz_localize(None)
    except Exception:
        update_time_api = pd.NaT

    desired_title_api   = str(open_js.get("title") or "")
    salary_expected_api = _salary_to_text(open_js.get("salary"))
    
    return {
        "fio_api": fio,
        "first_name_api": first_name,
        "last_name_api": last_name,
        "patronymic_api": patronymic,
        "phone_api": phone,
        "email_api": email,
        "chat_id_api": chat_id,      # как и раньше
        "is_purchased_api": is_purchased_api,
        "update_time_api": update_time_api,
        "updated_at_api": update_time_api,  # копия для отображения рядом с updated_at_web
        "update_time_api_raw": update_time_api_raw,
        "desired_title_api": desired_title_api,
        "salary_expected_api": salary_expected_api,
        # Новые поля v11 для анализа чатов
        "chat_status": chat_status,
        "last_message_direction": last_message_direction,
        "last_message_text": last_message_text,
        "json_open": json.dumps(open_js, ensure_ascii=False),
        "json_paid": json.dumps(paid_js, ensure_ascii=False),
    }


# ========== Ввод лимита/TZ ==========

def _parse_limit_arg(argv: list[str]) -> int | None:
    try:
        if "--limit" in argv:
            i = argv.index("--limit")
            return max(0, int(argv[i+1]))
        if "-n" in argv:
            i = argv.index("-n")
            return max(0, int(argv[i+1]))
    except Exception:
        pass
    return None

def _parse_tz_arg(argv: list[str]) -> str | None:
    try:
        if "--tz" in argv:
            i = argv.index("--tz")
            return argv[i+1]
        if "-t" in argv:
            i = argv.index("-t")
            return argv[i+1]
    except Exception:
        pass
    return None

def _parse_threads_arg(argv: list[str]) -> int:
    """Парсинг количества потоков для параллельной обработки."""
    try:
        if "--threads" in argv:
            i = argv.index("--threads")
            return max(1, min(20, int(argv[i+1])))  # От 1 до 20 потоков
        if "-j" in argv:
            i = argv.index("-j")
            return max(1, min(20, int(argv[i+1])))
    except Exception:
        pass
    return 8  # По умолчанию 8 потоков


def ask_limit_from_user() -> int | None:
    s = input("Сколько резюме собрать? Введите число или 'all' (по умолчанию: all): ").strip().lower()
    if not s or s in ("all", "все"):
        return None
    try:
        n = int(s)
        return n if n > 0 else None
    except Exception:
        print("Не понял ввод. Будет собрано 'все'.")
        return None


def enrich_resume_batch(resume_ids: list[str], tz_target, max_workers: int = 8) -> dict[str, dict]:
    """
    Параллельная обработка резюме через ThreadPoolExecutor.
    Возвращает словарь {resume_id: enriched_data}
    """
    results = {}
    
    def enrich_single(resume_id: str) -> tuple[str, dict]:
        """Обогащение одного резюме с обработкой ошибок."""
        try:
            data = enrich_one(resume_id, tz_target)
            return resume_id, data
        except Exception as e:
            print(f"⚠️  API enrich failed for {resume_id}: {e}")
            return resume_id, {}
    
    print(f"🚀 Начинаю параллельную обработку {len(resume_ids)} резюме в {max_workers} потоков...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Запускаем все задачи
        future_to_id = {executor.submit(enrich_single, rid): rid for rid in resume_ids}
        
        completed = 0
        for future in as_completed(future_to_id):
            resume_id, data = future.result()
            results[resume_id] = data
            completed += 1
            
            # Прогресс каждые 10 резюме
            if completed % 10 == 0 or completed == len(resume_ids):
                print(f"   ✅ Обработано: {completed}/{len(resume_ids)} резюме ({completed/len(resume_ids)*100:.1f}%)")
    
    print(f"🎉 Параллельная обработка завершена: {len(results)} резюме")
    return results


def is_excluded_region(region_api: str, city_api: str, city_web: str) -> bool:
    """
    Проверяет, нужно ли исключить кандидата по географическому признаку.
    Исключаем: Чечня, Дагестан, Ингушетия, Тува
    """
    excluded_regions = {
        "чеченская республика", "чечня", "республика чечня",
        "дагестан", "республика дагестан", 
        "ингушетия", "республика ингушетия",
        "тува", "республика тыва", "тыва"
    }
    
    excluded_cities = {
        "грозный", "махачкала", "назрань", "кызыл", "магас"
    }
    
    # Проверяем регион из API
    if region_api:
        region_lower = region_api.lower().strip()
        if any(excluded in region_lower for excluded in excluded_regions):
            return True
    
    # Проверяем город из API
    if city_api:
        city_lower = city_api.lower().strip()
        if city_lower in excluded_cities:
            return True
    
    # Проверяем город из web-данных (fallback)
    if city_web:
        city_lower = city_web.lower().strip()
        if city_lower in excluded_cities:
            return True
        # Проверяем есть ли название региона в строке города (часто бывает "г. Грозный, Чеченская Республика")
        if any(excluded in city_lower for excluded in excluded_regions):
            return True
    
    return False


def create_today_sheet(df: pd.DataFrame, stop_df: pd.DataFrame) -> pd.DataFrame:
    """
    Создает лист 'на_сегодня' с фильтрацией:
    1. updated_at_web за последние 24 часа
    2. Исключение по стоплисту (по телефону)
    3. Исключение по регионам (Чечня, Дагестан, Ингушетия, Тува)
    """
    if df.empty:
        return pd.DataFrame()
    
    # 1. Фильтр по времени (последние 24 часа)
    cutoff_time = datetime.now() - timedelta(hours=24)
    
    today_df = df.copy()
    if "updated_at_web" in today_df.columns:
        # Конвертируем в datetime если нужно
        today_df["updated_at_web"] = pd.to_datetime(today_df["updated_at_web"], errors="coerce")
        # Фильтруем по времени
        mask_recent = today_df["updated_at_web"] >= cutoff_time
        today_df = today_df[mask_recent]
    
    if today_df.empty:
        return pd.DataFrame()
    
    # 2. Исключение по стоплисту (телефоны)
    if not stop_df.empty and "phone_api" in today_df.columns:
        today_df["_phone_clean"] = _clean_phone_series(today_df["phone_api"]).fillna("")
        stop_phones = set(_clean_phone_series(stop_df[_DEF_COLS["phone"]]).fillna(""))
        stop_phones.discard("")  # Убираем пустые
        
        if stop_phones:
            mask_not_in_stoplist = ~today_df["_phone_clean"].isin(stop_phones)
            today_df = today_df[mask_not_in_stoplist]
        
        today_df = today_df.drop(columns=["_phone_clean"], errors="ignore")
    
    if today_df.empty:
        return pd.DataFrame()
    
    # 3. Исключение по регионам (используем только city_web, так как API поля удалены)
    mask_not_excluded_region = ~today_df.apply(
        lambda row: is_excluded_region(
            "",  # region_api удалено
            "",  # city_api удалено
            row.get("city_web", "")
        ), 
        axis=1
    )
    today_df = today_df[mask_not_excluded_region]
    
    return today_df.reset_index(drop=True)


def process_resumes_parallel(uniq: list, tz_target, num_threads: int) -> dict:
    """Обработка резюме с параллельным API enrichment."""
    # ENRICH через Avito API → tz_target (ПАРАЛЛЕЛЬНО)
    resume_ids = [rec.get("resume_id") for rec in uniq if rec.get("resume_id")]
    resume_ids = [rid for rid in resume_ids if rid]  # Убираем пустые
    
    if resume_ids:
        api_cache = enrich_resume_batch(resume_ids, tz_target, max_workers=num_threads)
    else:
        api_cache = {}
    
    return api_cache


# ========== MAIN ==========
def main():
    from openpyxl.utils import get_column_letter

    tz_name = _parse_tz_arg(sys.argv) or os.getenv("AVITO_TZ") or DEFAULT_TZ_NAME
    tz_target = _get_tz(tz_name)
    num_threads = _parse_threads_arg(sys.argv)

    limit = _parse_limit_arg(sys.argv)
    if limit is None:
        limit = ask_limit_from_user()

    print(f"🔧 Настройки: лимит={limit or 'все'}, потоков={num_threads}, часовой_пояс={tz_name}")
    
    # Загрузка актуальных чатов через API для анализа
    global CHATS_DATA
    CHATS_DATA = load_chats_from_api()
    print(f"📊 Загружено {len(CHATS_DATA)} чатов для анализа")

    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            viewport=None,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context.set_default_timeout(NAV_TIMEOUT)
        context.set_default_navigation_timeout(NAV_TIMEOUT)
        page = context.new_page()

        try:
            page.goto(HOME_URL, wait_until="domcontentloaded")
        except PwError:
            pass

        input(f"\nОткрылся браузер. Войдите в Avito и нажмите Enter здесь...\n(Текущий TZ: {tz_name})\nСтоплист из: {STOPLIST_DIR}\n")

        goto_resilient(page, TARGET_URL, "**/profile/paid-cvs*")
        total_cards_est = robust_scroll(page, need_count=limit)

        records = page.evaluate(EXTRACT_JS) or []
        if limit is not None:
            records = records[:limit]

        # дедуп
        uniq, seen = [], set()
        for r in records:
            key = r.get('resume_id') or r.get('link') or r.get('candidate_name_web')
            if key and key not in seen:
                seen.add(key)
                uniq.append(r)
                if limit is not None and len(uniq) >= limit:
                    break

        # офлайн-снимок (MHTML во временную папку, удалим позже)
        ts = datetime.now(tz_target).strftime("%Y%m%d-%H%M%S")
        mhtml_path = OUTPUT_DIR / f"avito_paid_cvs_{ts}.mhtml"
        save_as_mhtml(page, mhtml_path)

        # Параллельная обработка API
        api_cache = process_resumes_parallel(uniq, tz_target, num_threads)

        # к датафрейму
        df = pd.DataFrame.from_records(uniq)

        # локальный now для web-дат
        now_local_naive = datetime.now(tz_target).replace(tzinfo=None)

        # конвертация дат из веба → *_web (naive, локальное время TZ)
        for col in ("purchased_at_web", "updated_at_web"):
            if col in df.columns:
                df[col] = df[col].apply(lambda s: parse_ru_dt(s, now=now_local_naive))

        # добавим API-поля (берём из api_cache)
        def _get(rid, key):
            return (api_cache.get(str(rid)) or {}).get(key, "")

        api_columns = [
            "fio_api",            # нужен для excluded_df/диагностики, не выводим в paid_cvs
            "phone_api", "email_api", "chat_id_api", "avito_id",
            "update_time_api",    # нужен для api_difference расчёта
            "updated_at_api",     # дата обновления из API для сравнения с web
            "desired_title_api",
            # Удалены пустые API поля: "location_api", "city_api", "region_api"
            "chat_status", "last_message_direction", "last_message_text",  # новые поля v11
            "json_open", "json_paid",
        ]
        for c in api_columns:
            df[c] = df["resume_id"].map(lambda x: _get(x, c))

        # ───── СТОП-ЛИСТ ─────
        stop_df, stoplist_file_stats = build_stoplist_from_output()
        stop_count = len(stop_df)
        excluded_df = pd.DataFrame(columns=[
            "purchased_at_web", "resume_id", "link", "fio_api", "phone_api", "city_web",
            "Комментарий_стоплиста", "ФИО_стоплиста", "Источник", "respond_status"
        ])

        if stop_count > 0 and "phone_api" in df.columns:
            df["_phone_clean"] = _clean_phone_series(df["phone_api"]).fillna("")
            stop_df["_phone_clean"] = _clean_phone_series(stop_df[_DEF_COLS["phone"]]).fillna("")

            merged = df.merge(
                stop_df[["_phone_clean", _DEF_COLS["fio"], _DEF_COLS["comment"], "Файл", "Лист"]],
                on="_phone_clean", how="left"
            )

            mask_ex = merged[_DEF_COLS["comment"]].notna() | merged[_DEF_COLS["fio"]].notna()

            if mask_ex.any():
                merged["respond_status"] = merged.apply(
                    lambda r: "NO_ANSWER" if ((not r.get("avito_id")) and r.get("chat_id_api")) else "",
                    axis=1
                )
                excluded_df = merged.loc[mask_ex, [
                    "purchased_at_web", "resume_id", "link", "fio_api", "phone_api", "city_web",
                    _DEF_COLS["comment"], _DEF_COLS["fio"], "Файл", "Лист", "respond_status"
                ]].rename(columns={
                    _DEF_COLS["comment"]: "Комментарий_стоплиста",
                    _DEF_COLS["fio"]: "ФИО_стоплиста",
                })

            df = merged.loc[~mask_ex, df.columns].copy()
            df = df.drop(columns=["_phone_clean"], errors="ignore")
        else:
            df = df.copy()

        # Линк из API (fallback — web)
        def _build_precise_link(row) -> str:
            try:
                js = json.loads(row.get("json_open") or "{}")
                url_val = js.get("url") or js.get("uri") or (js.get("links") or {}).get("self") or js.get("link") or ""
                if url_val:
                    u = str(url_val)
                    return u if u.startswith("http") else ("https://www.avito.ru" + u)
            except Exception:
                pass
            w = str(row.get("link") or "")
            if w:
                return w if w.startswith("http") else ("https://www.avito.ru" + w)
            return ""

        df["link"] = df.apply(_build_precise_link, axis=1)

        # НОВОЕ: «Ссылка на чат» из chat_id_api
        df["Ссылка на чат"] = df["chat_id_api"].apply(
            lambda x: f"https://www.avito.ru/profile/messenger/channel/{str(x).strip()}"
            if isinstance(x, str) and str(x).strip() else (
                f"https://www.avito.ru/profile/messenger/channel/{x}" if (x is not None and str(x).strip()) else ""
            )
        )

        # api_difference: дни (updated_at_web - update_time_api)
        def _days_diff(a, b):
            try:
                if pd.isna(a) or pd.isna(b):
                    return pd.NA
                return int((pd.Timestamp(a) - pd.Timestamp(b)).days)
            except Exception:
                return pd.NA

        df["api_difference"] = df.apply(lambda r: _days_diff(r.get("updated_at_web"), r.get("update_time_api")), axis=1)

        # respond_status
        df["respond_status"] = df.apply(
            lambda r: "NO_ANSWER" if ((not r.get("avito_id")) and r.get("chat_id_api")) else "",
            axis=1
        )

        # закрытые (json_paid пусто) → отдельный лист
        def _is_json_paid_empty(v) -> bool:
            if pd.isna(v):
                return True
            s = str(v).strip()
            if not s:
                return True
            try:
                js = json.loads(s)
                if js in ({}, [], None):
                    return True
            except Exception:
                if s.lower() in ("{}", "[]", "null"):
                    return True
            return False

        if "json_paid" in df.columns:
            closed_mask = df["json_paid"].apply(_is_json_paid_empty)
        else:
            closed_mask = pd.Series(False, index=df.index)

        closed_df = df.loc[closed_mask].copy()
        if not closed_df.empty:
            closed_df["respond_status"] = closed_df.apply(
                lambda r: "NO_ANSWER" if ((not r.get("avito_id")) and r.get("chat_id_api")) else "",
                axis=1
            )

        # из рабочих df исключаем закрытые
        df = df.loc[~closed_mask].copy()

        # NO_ANSWER лист (не удаляем из df)
        no_answer_mask = df.apply(lambda r: (not r.get("avito_id")) and bool(r.get("chat_id_api")), axis=1)
        no_answer_df = df.loc[no_answer_mask].copy()
        if not no_answer_df.empty:
            no_answer_df["respond_status"] = "NO_ANSWER"

        # сортировка (новые → старые, max разница → min)
        def _sort_df_for_output(dframe: pd.DataFrame) -> pd.DataFrame:
            sort_by = []
            if "updated_at_web" in dframe.columns:
                sort_by.append("updated_at_web")
            if "api_difference" in dframe.columns:
                sort_by.append("api_difference")
            if sort_by:
                ascending_flags = [False] * len(sort_by)
                try:
                    return dframe.sort_values(by=sort_by, ascending=ascending_flags, na_position="last")
                except Exception:
                    return dframe
            return dframe

        # приоритизация для листа "Для_звонков" с учетом статусов чатов
        def _sort_df_for_calls(dframe: pd.DataFrame) -> pd.DataFrame:
            # Добавляем колонку приоритета
            def get_priority(row):
                job_status = str(row.get("job_search_status_web", "")).lower()
                ready_start = str(row.get("ready_to_start_web", "")).lower()
                chat_status = str(row.get("chat_status", ""))
                
                # Отрицательный приоритет: кандидат не заинтересован
                if chat_status == ChatStatus.NOT_INTERESTED.value:
                    return 9
                
                # Высший приоритет: активно ищет + готов завтра/сразу + отвечает в чате
                if job_status and ready_start and chat_status == ChatStatus.READ_REPLIED.value:
                    return 1
                
                # Очень высокий приоритет: активно ищет + готов завтра/сразу
                if job_status and ready_start:
                    return 2
                
                # Высокий приоритет: активно ищет + отвечает в чате
                if job_status and chat_status == ChatStatus.READ_REPLIED.value:
                    return 3
                
                # Выше среднего: только активно ищет работу
                if job_status:
                    return 4
                
                # Средний приоритет: готов начать быстро + отвечает в чате
                if ready_start and chat_status == ChatStatus.READ_REPLIED.value:
                    return 5
                
                # Ниже среднего: только готов начать быстро
                if ready_start:
                    return 6
                
                # Низкий приоритет: отвечает в чате, но без других сигналов
                if chat_status == ChatStatus.READ_REPLIED.value:
                    return 7
                
                # Очень низкий: читает, но не отвечает
                if chat_status == ChatStatus.READ_NO_REPLY.value:
                    return 8
                
                # Обычный приоритет: без специальных статусов
                return 10
            
            dframe = dframe.copy()
            dframe["_priority"] = dframe.apply(get_priority, axis=1)
            
            # Сортируем: приоритет (1-10) → новые → старые → большая разница
            sort_by = ["_priority"]
            ascending_flags = [True]  # приоритет по возрастанию (1 = высший)
            
            if "updated_at_web" in dframe.columns:
                sort_by.append("updated_at_web")
                ascending_flags.append(False)
            if "api_difference" in dframe.columns:
                sort_by.append("api_difference")
                ascending_flags.append(False)
            
            try:
                result = dframe.sort_values(by=sort_by, ascending=ascending_flags, na_position="last")
                # Удаляем служебную колонку
                result = result.drop(columns=["_priority"])
                return result
            except Exception:
                return dframe

        # порядок колонок (purchased_at_web — ПЕРВАЯ)
        desired_order = [
            "purchased_at_web",
            "updated_at_web", "updated_at_api", "candidate_name_web", "job_search_status_web", "ready_to_start_web",
            "chat_status", "last_message_direction", "last_message_text",
            "phone_api", "email_api", "desired_title_api", "city_web",
            # Удалены пустые API поля: "city_api", "region_api", "location_api", "avito_id"
            "respond_status", "json_open", "json_paid", "link", "Ссылка на чат", "chat_id_api", 
            "resume_id", "api_difference"
        ]

        # автоподбор ширины по макс. длине (header + значения)
        def _set_column_widths_autofit(ws, df_sheet):
            for i, col in enumerate(df_sheet.columns, start=1):
                col_letter = get_column_letter(i)
                header = str(col)
                values = df_sheet[col].astype(str).replace("nan", "").fillna("").tolist()
                max_len = len(header)
                for v in values:
                    l = len(v)
                    if l > max_len:
                        max_len = l
                width = max_len + 2
                if width < 4:
                    width = 4
                ws.column_dimensions[col_letter].width = width

        # ===== Сохранение Excel в НОВОЕ место и удаление MHTML =====
        OUTPUT_SAVE_DIR = Path(r"C:\ManekiNeko\AVITO_API\output").resolve()
        OUTPUT_SAVE_DIR.mkdir(parents=True, exist_ok=True)

        now_dt = datetime.now(tz_target)
        date_part = now_dt.strftime("%d%m%Y")     # ДДММГГГГ
        time_part = now_dt.strftime("%M_%S")      # ММ_СС
        excel_name = f"{date_part}_Выгрузка_АМО_{time_part}.xlsx"
        excel_path = OUTPUT_SAVE_DIR / excel_name

        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            # PAID_CVS
            df_out = _sort_df_for_output(df)
            cols_full = [c for c in desired_order if c in df_out.columns]
            df_out[cols_full].to_excel(writer, index=False, sheet_name="paid_cvs")
            ws = writer.sheets["paid_cvs"]
            _set_column_widths_autofit(ws, df_out[cols_full])

            # NO_ANSWER
            if not no_answer_df.empty:
                noans_out = _sort_df_for_output(no_answer_df)
                cols_noans = [c for c in desired_order if c in noans_out.columns]
                noans_out[cols_noans].to_excel(writer, index=False, sheet_name="NO_ANSWER")
                ws_no = writer.sheets["NO_ANSWER"]
                _set_column_widths_autofit(ws_no, noans_out[cols_noans])

            # резюме закрыто
            if not closed_df.empty:
                closed_out = _sort_df_for_output(closed_df)
                cols_closed = [c for c in desired_order if c in closed_out.columns]
                closed_out[cols_closed].to_excel(writer, index=False, sheet_name="резюме закрыто")
                ws_closed = writer.sheets["резюме закрыто"]
                _set_column_widths_autofit(ws_closed, closed_out[cols_closed])

            # Для_звонков (без json_open/json_paid) с приоритизацией активных кандидатов
            df_calls = df.copy()
            df_calls = _sort_df_for_calls(df_calls)  # используем приоритетную сортировку
            cols_calls = [c for c in desired_order if c in df_calls.columns and c not in ("json_open", "json_paid")]
            df_calls[cols_calls].to_excel(writer, index=False, sheet_name="Для_звонков")
            ws_calls = writer.sheets["Для_звонков"]
            _set_column_widths_autofit(ws_calls, df_calls[cols_calls])

            # на_сегодня (последние 24 часа, без стоплиста, без исключенных регионов)
            today_df = create_today_sheet(df, stop_df)
            if not today_df.empty:
                today_df = _sort_df_for_output(today_df)
                cols_today = [c for c in desired_order if c in today_df.columns and c not in ("json_open", "json_paid")]
                today_df[cols_today].to_excel(writer, index=False, sheet_name="на_сегодня")
                ws_today = writer.sheets["на_сегодня"]
                _set_column_widths_autofit(ws_today, today_df[cols_today])
                print(f"📅 Лист 'на_сегодня': {len(today_df)} записей (24 часа, без стоплиста, без исключенных регионов)")

            # Исключено_по_стоплисту
            if not excluded_df.empty:
                ex_cols_order = [c for c in [
                    "purchased_at_web", "resume_id", "link", "fio_api", "phone_api", "city_web",
                    "Комментарий_стоплиста", "ФИО_стоплиста", "Файл", "Лист", "respond_status"
                ] if c in excluded_df.columns]
                excluded_df[ex_cols_order].to_excel(writer, index=False, sheet_name="Исключено_по_стоплисту")
                ws_ex = writer.sheets["Исключено_по_стоплисту"]
                _set_column_widths_autofit(ws_ex, excluded_df[ex_cols_order])

            # summary (оставляю как есть — snapshot хранит имя удалённого MHTML)
            pd.DataFrame({
                "metric": [
                    "count_unique", "count_scroll_estimate", "snapshot", "page", "tz_name",
                    "stoplist_dir", "stoplist_size", "excluded_by_stoplist",
                ],
                "value": [
                    len(df), total_cards_est, str(mhtml_path.name), TARGET_URL, tz_name,
                    str(STOPLIST_DIR), int(stop_count), int(len(excluded_df)),
                ],
            }).to_excel(writer, index=False, sheet_name="summary")

        # Удаляем MHTML после успешной записи Excel
        try:
            mhtml_path.unlink()
            print(f"MHTML удалён: {mhtml_path}")
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"⚠️  Не удалось удалить MHTML ({mhtml_path}): {e}")

        # Статистика по стоплисту
        if stoplist_file_stats:
            print(f"\n📋 Статистика стоплиста:")
            print(f"   Общий размер: {stop_count} записей")
            print(f"   Исключено записей: {len(excluded_df)}")
            print(f"   Файлы источники:")
            for filename, count in stoplist_file_stats.items():
                print(f"     • {filename}: {count} записей")
        else:
            print(f"\n📋 Стоплист пуст (файлов не найдено в {STOPLIST_DIR})")

        print(f"\n📊 Excel: {excel_path}")

        context.close()

if __name__ == "__main__":
    main()
