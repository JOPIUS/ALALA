#!/usr/bin/env python3
"""
🎯 ФИНАЛЬНАЯ ФУНКЦИЯ - ПОЛНАЯ РАБОТА С AVITO БЕЗ БРАУЗЕРА
Экспорт всех чатов + поиск + анализ + CSV экспорт
"""

import os
import sys
import json
import csv
import requests
import time
from datetime import datetime

def avito_full_export():
    """Полный экспорт и анализ Avito чатов"""
    print("🚀 ПОЛНЫЙ ЭКСПОРТ AVITO (БЕЗ БРАУЗЕРА)")
    print("=" * 50)
    
    # Получить креды
    client_id = os.getenv('AVITO_CLIENT_ID')
    client_secret = os.getenv('AVITO_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        print("❌ Установите переменные окружения:")
        print("$env:AVITO_CLIENT_ID = 'ваш_client_id'")
        print("$env:AVITO_CLIENT_SECRET = 'ваш_client_secret'")
        return None
    
    # 1. Получить токен
    print("🔑 Получение токена...")
    token_url = "https://api.avito.ru/token"
    data = {
        'grant_type': 'client_credentials',
        'client_id': client_id,
        'client_secret': client_secret
    }
    
    try:
        response = requests.post(token_url, data=data, timeout=30)
        response.raise_for_status()
        token_info = response.json()
        access_token = token_info['access_token']
        print(f"✅ Токен получен")
    except Exception as e:
        print(f"❌ Ошибка получения токена: {e}")
        return None
    
    headers = {'Authorization': f'Bearer {access_token}'}
    
    # 2. Получить информацию о пользователе
    print("👤 Получение информации о пользователе...")
    try:
        response = requests.get("https://api.avito.ru/core/v1/accounts/self", headers=headers, timeout=30)
        if response.status_code == 200:
            user_info = response.json()
            user_id = user_info['id']
            print(f"✅ {user_info['name']} (ID: {user_id})")
        else:
            print(f"❌ Ошибка получения user info: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None
    
    # 3. Получить ВСЕ чаты
    print("💬 Получение всех чатов...")
    all_chats = []
    offset = 0
    limit = 100
    
    while True:
        print(f"📄 Страница {offset//limit + 1} (offset {offset})...")
        
        chats_url = f"https://api.avito.ru/messenger/v2/accounts/{user_id}/chats"
        params = {'limit': limit, 'offset': offset}
        
        try:
            response = requests.get(chats_url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                chats = data.get('chats', [])
                
                if not chats:
                    break
                
                all_chats.extend(chats)
                print(f"   ✅ +{len(chats)}, всего: {len(all_chats)}")
                
                if len(chats) < limit:
                    break
                
                offset += limit
                time.sleep(0.5)
            else:
                print(f"   ❌ Ошибка: {response.status_code}")
                break
                
        except Exception as e:
            print(f"   ❌ Исключение: {e}")
            break
    
    print(f"🎉 Получено чатов: {len(all_chats)}")
    
    # 4. Создать CSV с контактами
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_file = f"avito_contacts_{timestamp}.csv"
    
    print(f"📊 Создание CSV с контактами...")
    
    contacts = set()  # Избежать дубликатов
    
    for chat in all_chats:
        # Извлечь пользователей
        users = chat.get('users', [])
        for user in users:
            if user.get('id') != user_id:  # Не включать себя
                contacts.add((
                    user.get('id', ''),
                    user.get('name', 'Unknown'),
                    chat.get('id', ''),
                    datetime.fromtimestamp(chat.get('updated', 0)).strftime('%Y-%m-%d %H:%M:%S') if chat.get('updated') else '',
                    'Входящие' if chat.get('last_message', {}).get('direction') == 'in' else 'Исходящие',
                    chat.get('last_message', {}).get('content', {}).get('text', '')[:100]
                ))
    
    # Записать CSV
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['User_ID', 'Имя', 'Chat_ID', 'Последнее_обновление', 'Направление', 'Последнее_сообщение'])
        
        # Сортировать по времени обновления
        sorted_contacts = sorted(contacts, key=lambda x: x[3], reverse=True)
        writer.writerows(sorted_contacts)
    
    # 5. Создать JSON экспорт
    json_file = f"avito_export_{timestamp}.json"
    
    export_data = {
        'export_info': {
            'timestamp': datetime.now().isoformat(),
            'method': 'client_credentials_full',
            'total_chats': len(all_chats),
            'unique_contacts': len(contacts)
        },
        'user_info': user_info,
        'chats': all_chats,
        'summary': {
            'total_chats': len(all_chats),
            'unique_contacts': len(contacts),
            'active_last_30_days': len([c for c in all_chats if c.get('updated', 0) > (time.time() - 30*24*3600)]),
            'unread_chats': len([c for c in all_chats if c.get('unread_count', 0) > 0])
        }
    }
    
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    
    # 6. Показать результаты
    print(f"\n🎉 ЭКСПОРТ ЗАВЕРШЁН!")
    print(f"=" * 40)
    print(f"👤 Пользователь: {user_info['name']}")
    print(f"📧 Email: {user_info['email']}")
    print(f"📞 Phone: {user_info['phone']}")
    print(f"💬 Всего чатов: {len(all_chats)}")
    print(f"👥 Уникальных контактов: {len(contacts)}")
    print(f"🔥 Активных за 30 дней: {export_data['summary']['active_last_30_days']}")
    
    print(f"\n💾 Созданные файлы:")
    print(f"📊 CSV с контактами: {csv_file}")
    print(f"📄 JSON экспорт: {json_file}")
    
    # 7. Показать топ-10 последних контактов
    print(f"\n🔥 Топ-10 последних контактов:")
    for i, contact in enumerate(sorted_contacts[:10], 1):
        print(f"   {i}. {contact[1]} ({contact[4]}) - {contact[3]}")
        if contact[5]:
            print(f"      💬 {contact[5]}")
    
    return {
        'files': {'csv': csv_file, 'json': json_file},
        'stats': export_data['summary']
    }

if __name__ == "__main__":
    avito_full_export()