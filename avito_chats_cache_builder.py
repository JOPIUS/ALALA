# -*- coding: utf-8 -*-
"""
Инструмент для создания и поддержки кэша чатов Avito
Загружает все доступные чаты и сохраняет в JSON файл для быстрого доступа
"""

import json
import time
from datetime import datetime
from pathlib import Path
import requests
import sys
import os

# Импортируем необходимые модули из основного скрипта
from avito_paid_cvs_save_v_16 import (
    API_BASE, SESSION, TIMEOUT, _tok, _ensure_my_user_id
)

def load_all_chats_to_cache():
    """
    Загружает все доступные чаты через API и сохраняет в кэш файл
    """
    print("🔄 Загрузка всех чатов для создания кэша...")
    
    try:
        # Получаем токен
        token = _tok.get()
        if not token:
            print("⛔ Не удалось получить токен")
            return {}
            
        # Получаем user_id
        user_id = _ensure_my_user_id()
        if not user_id:
            print("⛔ Не удалось получить user_id")
            return {}
        
        headers = {'Authorization': f'Bearer {token}'}
        
        # Загружаем все чаты до лимита API
        all_chats = []
        limit = 100
        max_offset = 1000
        offset = 0
        
        print(f"📥 Загружаем чаты (до offset {max_offset})...")
        
        while offset <= max_offset:
            params = {'offset': offset, 'limit': limit}
            chats_url = f"{API_BASE}/messenger/v2/accounts/{user_id}/chats"
            
            try:
                response = SESSION.get(chats_url, headers=headers, params=params, timeout=TIMEOUT)
                
                if response.status_code != 200:
                    print(f"⚠️ Ошибка на offset {offset}: {response.status_code}")
                    break
                    
                data = response.json()
                chats = data.get('chats', [])
                
                if not chats:
                    print(f"✅ Больше чатов не найдено на offset {offset}")
                    break
                    
                all_chats.extend(chats)
                print(f"✅ Загружено: +{len(chats)}, всего: {len(all_chats)}")
                
                if len(chats) < limit:
                    print(f"✅ Последняя страница")
                    break
                    
                offset += limit
                time.sleep(0.1)
                
            except Exception as e:
                print(f"⚠️ Ошибка запроса: {e}")
                break
        
        print(f"✅ Загружено {len(all_chats)} чатов")
        
        # Преобразуем в словарь по chat_id
        chats_dict = {}
        for chat in all_chats:
            chat_id = chat.get("id")
            if chat_id:
                # Добавляем метаданные
                chat['_cached_at'] = datetime.now().isoformat()
                chat['_cache_version'] = 1
                chats_dict[chat_id] = chat
        
        return chats_dict
        
    except Exception as e:
        print(f"⚠️ Ошибка загрузки чатов: {e}")
        return {}

def save_chats_cache(chats_dict, cache_file="avito_chats_cache.json"):
    """
    Сохраняет чаты в кэш файл
    """
    cache_path = Path(cache_file)
    
    # Создаем метаданные кэша
    cache_data = {
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "total_chats": len(chats_dict),
            "version": 1
        },
        "chats": chats_dict
    }
    
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ Кэш сохранен: {cache_path}")
        print(f"📊 Всего чатов в кэше: {len(chats_dict)}")
        return True
    except Exception as e:
        print(f"⚠️ Ошибка сохранения кэша: {e}")
        return False

def load_chats_cache(cache_file="avito_chats_cache.json"):
    """
    Загружает чаты из кэш файла
    """
    cache_path = Path(cache_file)
    
    if not cache_path.exists():
        print(f"⚠️ Кэш файл не найден: {cache_path}")
        return {}
    
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        chats = cache_data.get("chats", {})
        metadata = cache_data.get("metadata", {})
        
        print(f"✅ Кэш загружен: {len(chats)} чатов")
        print(f"📅 Создан: {metadata.get('created_at', 'неизвестно')}")
        
        return chats
    except Exception as e:
        print(f"⚠️ Ошибка загрузки кэша: {e}")
        return {}

def update_chats_cache(new_chats_dict, cache_file="avito_chats_cache.json"):
    """
    Обновляет существующий кэш новыми чатами
    """
    # Загружаем существующий кэш
    existing_chats = load_chats_cache(cache_file)
    
    # Добавляем новые чаты
    added_count = 0
    updated_count = 0
    
    for chat_id, chat_data in new_chats_dict.items():
        if chat_id in existing_chats:
            # Обновляем существующий чат если он новее
            existing_updated = existing_chats[chat_id].get('updated', 0)
            new_updated = chat_data.get('updated', 0)
            
            if new_updated > existing_updated:
                existing_chats[chat_id] = chat_data
                updated_count += 1
        else:
            # Добавляем новый чат
            existing_chats[chat_id] = chat_data
            added_count += 1
    
    # Сохраняем обновленный кэш
    success = save_chats_cache(existing_chats, cache_file)
    
    if success:
        print(f"✅ Кэш обновлен: +{added_count} новых, ~{updated_count} обновленных")
    
    return success

if __name__ == "__main__":
    print("🚀 Создание кэша чатов Avito")
    
    # Загружаем все чаты
    chats = load_all_chats_to_cache()
    
    if chats:
        # Сохраняем в кэш
        save_chats_cache(chats)
        print("🎉 Кэш чатов успешно создан!")
    else:
        print("❌ Не удалось создать кэш чатов")