# avito_chats_mega_collector.py
# -*- coding: utf-8 -*-
"""
МЕГА-сборщик чатов Avito с экстремальными стратегиями
для получения максимального количества чатов
"""

import requests
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# === КОНФИГУРАЦИЯ ===
API_BASE = "https://api.avito.ru"
TIMEOUT = 30

# Авторизация
CLIENT_ID = "Dm4ruLMEr9MFsV72dN95"
CLIENT_SECRET = "f73lNoAJLzuqwoGtVaMnByhQfSlwcyIN_m7wyOeT"

# Настройки запросов
BATCH_SIZE = 100
MAX_OFFSET = 1000
DELAY_BETWEEN_REQUESTS = 0.05
DELAY_BETWEEN_BATCHES = 1.0

# === ИНИЦИАЛИЗАЦИЯ СЕССИИ ===
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Avito Mega Chat Collector / Python",
    "Accept": "application/json"
})

class Token:
    def __init__(self) -> None:
        self._token: str | None = None
        self._exp: float = 0.0

    def _refresh(self) -> None:
        print("🔑 Обновление access_token...")
        r = SESSION.post(
            f"{API_BASE}/token",
            data={
                "grant_type": "client_credentials",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET
            },
            timeout=TIMEOUT
        )
        if r.status_code != 200:
            raise RuntimeError(f"Ошибка получения токена: {r.status_code} {r.text}")
        data = r.json()
        self._token = data["access_token"]
        self._exp = time.time() + data.get("expires_in", 3600) - 60
        print(f"✅ Токен обновлен")

    def get(self) -> str:
        if not self._token or time.time() >= self._exp:
            self._refresh()
        return self._token

_tok = Token()

def get_user_id() -> int:
    """Получает ID текущего пользователя"""
    token = _tok.get()
    headers = {"Authorization": f"Bearer {token}"}
    
    resp = SESSION.get(f"{API_BASE}/core/v1/accounts/self", headers=headers, timeout=TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f"Ошибка получения user_id: {resp.status_code} {resp.text}")
    
    data = resp.json()
    user_id = data.get("id") or data.get("user_id")
    if not user_id:
        raise RuntimeError(f"user_id не найден в ответе: {data}")
    
    print(f"👤 User ID: {user_id}")
    return int(user_id)

def load_chats_with_params(user_id: int, **params) -> Dict[str, Dict]:
    """
    Универсальная загрузка чатов с любыми параметрами
    """
    token = _tok.get()
    headers = {"Authorization": f"Bearer {token}"}
    
    all_chats = {}
    offset = 0
    
    # Добавляем базовые параметры
    params.setdefault("limit", BATCH_SIZE)
    
    while offset <= MAX_OFFSET:
        params["offset"] = offset
        
        try:
            resp = SESSION.get(
                f"{API_BASE}/messenger/v2/accounts/{user_id}/chats",
                headers=headers,
                params=params,
                timeout=TIMEOUT
            )
            
            if resp.status_code != 200:
                break
            
            data = resp.json()
            chats = data.get("chats", [])
            
            if not chats:
                break
            
            for chat in chats:
                chat_id = chat.get("id")
                if chat_id:
                    all_chats[chat_id] = chat
            
            if len(chats) < BATCH_SIZE:
                break
            
            offset += BATCH_SIZE
            time.sleep(DELAY_BETWEEN_REQUESTS)
            
        except Exception as e:
            break
    
    return all_chats

def load_chats_time_based(user_id: int) -> Dict[str, Dict]:
    """
    СТРАТЕГИЯ: Загрузка чатов с временными фильтрами
    Пытаемся найти скрытые параметры API
    """
    print("📅 Загрузка чатов с временными фильтрами")
    
    all_chats = {}
    
    # Попробуем различные временные диапазоны
    time_ranges = [
        {"created_after": "2024-01-01"},
        {"created_before": "2025-12-31"},
        {"updated_after": "2024-01-01"},
        {"updated_before": "2025-12-31"},
    ]
    
    for time_params in time_ranges:
        try:
            chats = load_chats_with_params(user_id, **time_params)
            new_chats = {k: v for k, v in chats.items() if k not in all_chats}
            all_chats.update(new_chats)
            print(f"  ⏰ {time_params}: +{len(new_chats)} новых чатов")
        except:
            pass
    
    return all_chats

def load_chats_sorting_based(user_id: int) -> Dict[str, Dict]:
    """
    СТРАТЕГИЯ: Загрузка с различными сортировками
    """
    print("🔄 Загрузка чатов с различными сортировками")
    
    all_chats = {}
    
    # Попробуем различные варианты сортировки
    sort_options = [
        {"sort": "created_asc"},
        {"sort": "created_desc"},
        {"sort": "updated_asc"},
        {"sort": "updated_desc"},
        {"order": "asc"},
        {"order": "desc"},
        {"sort_by": "created"},
        {"sort_by": "updated"},
    ]
    
    for sort_params in sort_options:
        try:
            chats = load_chats_with_params(user_id, **sort_params)
            new_chats = {k: v for k, v in chats.items() if k not in all_chats}
            all_chats.update(new_chats)
            print(f"  🔄 {sort_params}: +{len(new_chats)} новых чатов")
        except:
            pass
    
    return all_chats

def load_chats_status_based(user_id: int) -> Dict[str, Dict]:
    """
    СТРАТЕГИЯ: Загрузка по статусам чатов
    """
    print("📊 Загрузка чатов по статусам")
    
    all_chats = {}
    
    # Попробуем различные статусы
    status_options = [
        {"status": "active"},
        {"status": "archived"},
        {"status": "deleted"},
        {"status": "read"},
        {"status": "unread"},
        {"read": "true"},
        {"read": "false"},
        {"archived": "true"},
        {"archived": "false"},
        {"active": "true"},
        {"active": "false"},
    ]
    
    for status_params in status_options:
        try:
            chats = load_chats_with_params(user_id, **status_params)
            new_chats = {k: v for k, v in chats.items() if k not in all_chats}
            all_chats.update(new_chats)
            print(f"  📊 {status_params}: +{len(new_chats)} новых чатов")
        except:
            pass
    
    return all_chats

def load_chats_pagination_tricks(user_id: int) -> Dict[str, Dict]:
    """
    СТРАТЕГИЯ: Хитрости с пагинацией
    """
    print("🎯 Хитрости с пагинацией")
    
    all_chats = {}
    
    # Попробуем различные размеры страниц
    for limit in [1, 5, 25, 50, 150, 200]:
        try:
            chats = load_chats_with_params(user_id, limit=limit)
            new_chats = {k: v for k, v in chats.items() if k not in all_chats}
            all_chats.update(new_chats)
            print(f"  📄 limit={limit}: +{len(new_chats)} новых чатов")
        except:
            pass
    
    # Попробуем начинать с разных offset
    for start_offset in [0, 50, 99, 999, 1001]:
        try:
            chats = load_chats_with_params(user_id, offset=start_offset, limit=50)
            new_chats = {k: v for k, v in chats.items() if k not in all_chats}
            all_chats.update(new_chats)
            print(f"  🔢 start_offset={start_offset}: +{len(new_chats)} новых чатов")
        except:
            pass
    
    return all_chats

def try_messenger_v1_api(user_id: int) -> Dict[str, Dict]:
    """
    СТРАТЕГИЯ: Попытка использовать старый API v1
    """
    print("🔙 Попытка использовать Messenger API v1")
    
    token = _tok.get()
    headers = {"Authorization": f"Bearer {token}"}
    
    all_chats = {}
    
    try:
        # Пробуем v1 API
        resp = SESSION.get(
            f"{API_BASE}/messenger/v1/accounts/{user_id}/chats",
            headers=headers,
            params={"limit": 100},
            timeout=TIMEOUT
        )
        
        if resp.status_code == 200:
            data = resp.json()
            chats = data.get("chats", [])
            
            for chat in chats:
                chat_id = chat.get("id")
                if chat_id:
                    all_chats[chat_id] = chat
            
            print(f"  📞 API v1: получено {len(all_chats)} чатов")
        else:
            print(f"  📞 API v1: недоступен ({resp.status_code})")
            
    except Exception as e:
        print(f"  📞 API v1: ошибка ({e})")
    
    return all_chats

def brute_force_parameters(user_id: int) -> Dict[str, Dict]:
    """
    СТРАТЕГИЯ: Брутфорс скрытых параметров API
    """
    print("💥 Брутфорс скрытых параметров API")
    
    all_chats = {}
    
    # Список возможных параметров для брутфорса
    param_tests = [
        {"include_archived": "true"},
        {"include_deleted": "true"},
        {"include_hidden": "true"},
        {"show_all": "true"},
        {"all": "true"},
        {"full": "true"},
        {"detailed": "true"},
        {"extended": "true"},
        {"with_messages": "true"},
        {"with_context": "true"},
        {"include_system": "true"},
        {"include_auto": "true"},
        {"type": "all"},
        {"category": "all"},
        {"filter": "none"},
        {"mode": "all"},
        {"scope": "all"},
    ]
    
    for test_params in param_tests:
        try:
            chats = load_chats_with_params(user_id, **test_params)
            new_chats = {k: v for k, v in chats.items() if k not in all_chats}
            all_chats.update(new_chats)
            if new_chats:
                print(f"  💥 {test_params}: +{len(new_chats)} новых чатов ✨")
        except:
            pass
    
    return all_chats

def mega_collect_chats() -> Dict[str, Dict]:
    """
    МЕГА-сборщик всех возможных чатов
    """
    print("🚀 МЕГА-СБОРЩИК ЧАТОВ ЗАПУЩЕН!")
    
    user_id = get_user_id()
    all_chats = {}
    
    strategies = [
        ("Базовая загрузка", lambda: load_chats_with_params(user_id)),
        ("Непрочитанные", lambda: load_chats_with_params(user_id, unread_only="true")),
        ("Тип u2i", lambda: load_chats_with_params(user_id, chat_types="u2i")),
        ("Тип u2u", lambda: load_chats_with_params(user_id, chat_types="u2u")),
        ("Временные фильтры", lambda: load_chats_time_based(user_id)),
        ("Сортировки", lambda: load_chats_sorting_based(user_id)),
        ("Статусы", lambda: load_chats_status_based(user_id)),
        ("Пагинация", lambda: load_chats_pagination_tricks(user_id)),
        ("API v1", lambda: try_messenger_v1_api(user_id)),
        ("Брутфорс", lambda: brute_force_parameters(user_id)),
    ]
    
    for strategy_name, strategy_func in strategies:
        print(f"\n📋 СТРАТЕГИЯ: {strategy_name}")
        try:
            strategy_chats = strategy_func()
            new_chats = {k: v for k, v in strategy_chats.items() if k not in all_chats}
            all_chats.update(new_chats)
            print(f"✅ {strategy_name}: +{len(new_chats)} новых, всего: {len(all_chats)}")
        except Exception as e:
            print(f"❌ {strategy_name}: ошибка - {e}")
    
    return all_chats

def main():
    """
    Основная функция МЕГА-сборщика
    """
    try:
        # Собираем ВСЕ возможные чаты
        all_chats = mega_collect_chats()
        
        print(f"\n🎉 МЕГА-РЕЗУЛЬТАТ")
        print(f"📊 Всего собрано уникальных чатов: {len(all_chats)}")
        
        # Сохраняем результат
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"avito_chats_MEGA_{timestamp}.json"
        
        result_data = {
            "metadata": {
                "collected_at": datetime.now().isoformat(),
                "total_chats": len(all_chats),
                "collection_method": "MEGA_EXTREME_COLLECTOR",
                "script_version": "mega_v1"
            },
            "chats": all_chats
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        
        print(f"💾 МЕГА-результат сохранен в: {filename}")
        
        # Показываем примеры
        if all_chats:
            print(f"\n📋 Примеры собранных chat_id:")
            for i, chat_id in enumerate(list(all_chats.keys())[:10]):
                print(f"  {i+1:2d}. {chat_id}")
            if len(all_chats) > 10:
                print(f"  ... и еще {len(all_chats) - 10} чатов")
        
        print(f"\n✅ МЕГА-сбор завершен!")
        
    except Exception as e:
        print(f"\n❌ МЕГА-ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()