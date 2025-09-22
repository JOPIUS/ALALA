# avito_chats_advanced_collector.py
# -*- coding: utf-8 -*-
"""
Продвинутый сборщик чатов Avito с использованием множественных стратегий
для обхода ограничения offset=1000
"""

import requests
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
import threading

# === КОНФИГУРАЦИЯ ===
API_BASE = "https://api.avito.ru"
TIMEOUT = 30

# Авторизация
CLIENT_ID = "Dm4ruLMEr9MFsV72dN95"
CLIENT_SECRET = "f73lNoAJLzuqwoGtVaMnByhQfSlwcyIN_m7wyOeT"

# Настройки запросов
BATCH_SIZE = 100  # Размер пакета чатов
MAX_OFFSET = 1000  # Максимальный offset API
DELAY_BETWEEN_REQUESTS = 0.1  # Задержка между запросами
DELAY_BETWEEN_BATCHES = 2.0  # Задержка между большими пакетами

# === ИНИЦИАЛИЗАЦИЯ СЕССИИ ===
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Avito Chat Collector / Python",
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
        print(f"✅ Токен обновлен, истекает через {data.get('expires_in', 3600)} сек")

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

def load_chats_basic(user_id: int, chat_types: List[str] = None, unread_only: bool = None) -> Dict[str, Dict]:
    """
    Базовая загрузка чатов с использованием стандартного API
    """
    print(f"📥 Базовая загрузка чатов (types: {chat_types}, unread_only: {unread_only})")
    
    token = _tok.get()
    headers = {"Authorization": f"Bearer {token}"}
    
    all_chats = {}
    offset = 0
    
    while offset <= MAX_OFFSET:
        params = {
            "limit": BATCH_SIZE,
            "offset": offset
        }
        
        if chat_types:
            params["chat_types"] = ",".join(chat_types)
        if unread_only is not None:
            params["unread_only"] = str(unread_only).lower()
        
        print(f"  📡 Запрос: offset={offset}, limit={BATCH_SIZE}")
        
        try:
            resp = SESSION.get(
                f"{API_BASE}/messenger/v2/accounts/{user_id}/chats",
                headers=headers,
                params=params,
                timeout=TIMEOUT
            )
            
            if resp.status_code != 200:
                print(f"  ⚠️ Ошибка: {resp.status_code} - {resp.text[:200]}")
                break
            
            data = resp.json()
            chats = data.get("chats", [])
            
            if not chats:
                print(f"  📭 Больше чатов нет (offset={offset})")
                break
            
            # Добавляем чаты в общий словарь
            for chat in chats:
                chat_id = chat.get("id")
                if chat_id:
                    all_chats[chat_id] = chat
            
            print(f"  ✅ Загружено {len(chats)} чатов, всего: {len(all_chats)}")
            
            # Если получили меньше чем лимит - больше чатов нет
            if len(chats) < BATCH_SIZE:
                print(f"  🏁 Получен неполный пакет - загрузка завершена")
                break
            
            offset += BATCH_SIZE
            time.sleep(DELAY_BETWEEN_REQUESTS)
            
        except Exception as e:
            print(f"  ❌ Ошибка запроса: {e}")
            break
    
    print(f"📊 Базовая загрузка завершена: {len(all_chats)} чатов")
    return all_chats

def load_chats_by_item_ids(user_id: int, item_ids: List[int]) -> Dict[str, Dict]:
    """
    Загрузка чатов по конкретным item_id (если известны)
    """
    print(f"📥 Загрузка чатов по item_ids ({len(item_ids)} позиций)")
    
    token = _tok.get()
    headers = {"Authorization": f"Bearer {token}"}
    
    all_chats = {}
    
    # Разбиваем item_ids на пакеты для избежания слишком длинных URL
    batch_size = 50
    for i in range(0, len(item_ids), batch_size):
        batch_item_ids = item_ids[i:i + batch_size]
        
        params = {
            "limit": BATCH_SIZE,
            "item_ids": ",".join(map(str, batch_item_ids))
        }
        
        print(f"  📡 Запрос для item_ids: {batch_item_ids[:5]}... ({len(batch_item_ids)} шт)")
        
        try:
            resp = SESSION.get(
                f"{API_BASE}/messenger/v2/accounts/{user_id}/chats",
                headers=headers,
                params=params,
                timeout=TIMEOUT
            )
            
            if resp.status_code != 200:
                print(f"  ⚠️ Ошибка: {resp.status_code}")
                continue
            
            data = resp.json()
            chats = data.get("chats", [])
            
            for chat in chats:
                chat_id = chat.get("id")
                if chat_id:
                    all_chats[chat_id] = chat
            
            print(f"  ✅ Загружено {len(chats)} чатов для этих item_ids")
            time.sleep(DELAY_BETWEEN_REQUESTS)
            
        except Exception as e:
            print(f"  ❌ Ошибка запроса: {e}")
    
    print(f"📊 Загрузка по item_ids завершена: {len(all_chats)} чатов")
    return all_chats

def load_chats_individual(user_id: int, chat_ids: List[str]) -> Dict[str, Dict]:
    """
    Загрузка отдельных чатов по их ID
    """
    print(f"📥 Индивидуальная загрузка чатов ({len(chat_ids)} шт)")
    
    token = _tok.get()
    headers = {"Authorization": f"Bearer {token}"}
    
    loaded_chats = {}
    
    for i, chat_id in enumerate(chat_ids):
        print(f"  📡 Загрузка чата {i+1}/{len(chat_ids)}: {chat_id}")
        
        try:
            resp = SESSION.get(
                f"{API_BASE}/messenger/v2/accounts/{user_id}/chats/{chat_id}",
                headers=headers,
                timeout=TIMEOUT
            )
            
            if resp.status_code == 200:
                chat_data = resp.json()
                loaded_chats[chat_id] = chat_data
                print(f"  ✅ Чат загружен")
            elif resp.status_code == 404:
                print(f"  📭 Чат не найден")
            else:
                print(f"  ⚠️ Ошибка: {resp.status_code}")
            
            # Добавляем задержку каждые 100 запросов
            if (i + 1) % 100 == 0:
                print(f"  ⏸️ Пауза после {i+1} запросов...")
                time.sleep(DELAY_BETWEEN_BATCHES)
            else:
                time.sleep(DELAY_BETWEEN_REQUESTS)
                
        except Exception as e:
            print(f"  ❌ Ошибка запроса: {e}")
    
    print(f"📊 Индивидуальная загрузка завершена: {loaded_chats}/{len(chat_ids)} чатов")
    return loaded_chats

def collect_all_chats() -> Dict[str, Dict]:
    """
    Главная функция сбора всех возможных чатов
    """
    print("🚀 Начинаем продвинутый сбор чатов Avito")
    
    # Получаем user_id
    user_id = get_user_id()
    
    all_chats = {}
    
    # === СТРАТЕГИЯ 1: Базовая загрузка всех чатов ===
    print("\n📋 СТРАТЕГИЯ 1: Базовая загрузка всех чатов")
    basic_chats = load_chats_basic(user_id)
    all_chats.update(basic_chats)
    print(f"Собрано после стратегии 1: {len(all_chats)} чатов")
    
    # === СТРАТЕГИЯ 2: Загрузка только непрочитанных ===
    print("\n📋 СТРАТЕГИЯ 2: Загрузка непрочитанных чатов")
    unread_chats = load_chats_basic(user_id, unread_only=True)
    new_unread = {k: v for k, v in unread_chats.items() if k not in all_chats}
    all_chats.update(new_unread)
    print(f"Найдено новых непрочитанных: {len(new_unread)}")
    print(f"Собрано после стратегии 2: {len(all_chats)} чатов")
    
    # === СТРАТЕГИЯ 3: Загрузка по типам чатов ===
    print("\n📋 СТРАТЕГИЯ 3: Загрузка по типам чатов")
    
    for chat_type in ["u2i", "u2u"]:
        print(f"\n  📂 Тип чатов: {chat_type}")
        typed_chats = load_chats_basic(user_id, chat_types=[chat_type])
        new_typed = {k: v for k, v in typed_chats.items() if k not in all_chats}
        all_chats.update(new_typed)
        print(f"  Найдено новых чатов типа {chat_type}: {len(new_typed)}")
    
    print(f"Собрано после стратегии 3: {len(all_chats)} чатов")
    
    # === СТРАТЕГИЯ 4: Комбинированная загрузка ===
    print("\n📋 СТРАТЕГИЯ 4: Комбинированная загрузка (непрочитанные + типы)")
    
    for chat_type in ["u2i", "u2u"]:
        print(f"\n  📂 Непрочитанные чаты типа: {chat_type}")
        combo_chats = load_chats_basic(user_id, chat_types=[chat_type], unread_only=True)
        new_combo = {k: v for k, v in combo_chats.items() if k not in all_chats}
        all_chats.update(new_combo)
        print(f"  Найдено новых комбинированных: {len(new_combo)}")
    
    print(f"Собрано после стратегии 4: {len(all_chats)} чатов")
    
    # === ДОПОЛНИТЕЛЬНЫЕ СТРАТЕГИИ (если нужно) ===
    
    # Если у нас есть известные item_ids, можно попробовать:
    # item_ids = [...]  # Список известных ID объявлений
    # item_chats = load_chats_by_item_ids(user_id, item_ids)
    # all_chats.update(item_chats)
    
    # Если у нас есть известные chat_ids, можно попробовать:
    # missing_chat_ids = [...]  # Список известных но не найденных chat_id
    # individual_chats = load_chats_individual(user_id, missing_chat_ids)
    # all_chats.update(individual_chats)
    
    return all_chats

def save_chats_result(chats_dict: Dict[str, Dict]) -> str:
    """
    Сохраняет результат в JSON файл
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"avito_chats_advanced_{timestamp}.json"
    
    result_data = {
        "metadata": {
            "collected_at": datetime.now().isoformat(),
            "total_chats": len(chats_dict),
            "collection_method": "advanced_multi_strategy",
            "script_version": "advanced_collector_v1"
        },
        "chats": chats_dict
    }
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)
    
    print(f"💾 Результат сохранен в: {filename}")
    return filename

def main():
    """
    Основная функция
    """
    try:
        # Собираем все чаты
        all_chats = collect_all_chats()
        
        print(f"\n🎉 ИТОГОВЫЙ РЕЗУЛЬТАТ")
        print(f"📊 Всего собрано уникальных чатов: {len(all_chats)}")
        
        # Сохраняем результат
        filename = save_chats_result(all_chats)
        
        # Показываем примеры чатов
        if all_chats:
            print(f"\n📋 Примеры собранных chat_id:")
            for i, chat_id in enumerate(list(all_chats.keys())[:5]):
                print(f"  {i+1}. {chat_id}")
            if len(all_chats) > 5:
                print(f"  ... и еще {len(all_chats) - 5} чатов")
        
        print(f"\n✅ Сбор чатов завершен успешно!")
        
    except Exception as e:
        print(f"\n❌ Ошибка во время сбора чатов: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()