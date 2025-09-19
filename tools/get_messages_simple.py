#!/usr/bin/env python3
"""
Простая функция для получения сообщений из Avito
Автоматически получает токен и скачивает все чаты + сообщения
"""

import os
import sys
import json
import requests
import time
from datetime import datetime

def get_avito_messages(client_id, client_secret, account_id=None):
    """
    Получить все сообщения из Avito одной функцией
    
    Args:
        client_id: ID приложения Avito
        client_secret: Секрет приложения
        account_id: ID аккаунта (если None - попробует получить автоматически)
    
    Returns:
        dict: {'chats': [...], 'messages': {...}, 'account_info': {...}}
    """
    
    # 1. Получить токен (используем client_credentials для простоты)
    print("🔑 Получение токена...")
    token_url = "https://api.avito.ru/token"
    token_data = {
        'grant_type': 'client_credentials',
        'client_id': client_id,
        'client_secret': client_secret,
        'scope': 'messages.read messages.write'
    }
    
    try:
        token_response = requests.post(token_url, data=token_data, timeout=30)
        token_response.raise_for_status()
        token_info = token_response.json()
        access_token = token_info['access_token']
        print(f"✅ Токен получен: {access_token[:20]}...")
    except Exception as e:
        print(f"❌ Ошибка получения токена: {e}")
        return None
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    # 2. Получить информацию об аккаунте если нужно
    if not account_id:
        print("👤 Получение ID аккаунта...")
        # Попробуем несколько возможных endpoints
        possible_endpoints = [
            "https://api.avito.ru/messenger/v1/accounts",
            "https://api.avito.ru/messenger/v1/account",
            "https://api.avito.ru/core/v1/accounts",
            "https://api.avito.ru/core/v1/account",
            "https://api.avito.ru/user/v1/accounts"
        ]
        
        for endpoint in possible_endpoints:
            try:
                print(f"🔍 Пробую endpoint: {endpoint}")
                account_response = requests.get(endpoint, headers=headers, timeout=30)
                
                if account_response.status_code == 200:
                    try:
                        accounts = account_response.json()
                        print(f"📝 Ответ от {endpoint}: {json.dumps(accounts, ensure_ascii=False, indent=2)[:500]}...")
                        
                        # Попробуем извлечь account_id из разных структур
                        if isinstance(accounts, list) and len(accounts) > 0:
                            if 'id' in accounts[0]:
                                account_id = accounts[0]['id']
                                print(f"✅ ID аккаунта найден (список): {account_id}")
                                break
                        elif isinstance(accounts, dict):
                            if 'id' in accounts:
                                account_id = accounts['id']
                                print(f"✅ ID аккаунта найден (объект): {account_id}")
                                break
                            elif 'accounts' in accounts and len(accounts['accounts']) > 0:
                                account_id = accounts['accounts'][0]['id']
                                print(f"✅ ID аккаунта найден (вложенный): {account_id}")
                                break
                    except json.JSONDecodeError:
                        print(f"❌ Неверный JSON от {endpoint}")
                        continue
                else:
                    print(f"❌ {endpoint}: {account_response.status_code}")
                    
            except Exception as e:
                print(f"❌ Ошибка {endpoint}: {e}")
                continue
        
        if not account_id:
            print("❌ Не удалось найти ID аккаунта автоматически")
            print("💡 Попробуйте указать AVITO_ACCOUNT_ID в переменных окружения")
            print("💡 Или найдите account_id в личном кабинете Avito")
            
            # Предложим ввести вручную
            try:
                manual_id = input("\n🔢 Введите account_id вручную (или Enter для пропуска): ").strip()
                if manual_id:
                    account_id = manual_id
                    print(f"✅ Используем ID: {account_id}")
                else:
                    return None
            except (KeyboardInterrupt, EOFError):
                print("\n❌ Отменено пользователем")
                return None
    
    # 3. Получить список чатов
    print("💬 Получение списка чатов...")
    all_chats = []
    offset = 0
    limit = 100
    
    while True:
        try:
            chats_url = f"https://api.avito.ru/messenger/v1/accounts/{account_id}/chats"
            params = {'limit': limit, 'offset': offset}
            
            chats_response = requests.get(chats_url, headers=headers, params=params, timeout=30)
            chats_response.raise_for_status()
            chats_data = chats_response.json()
            
            if 'chats' in chats_data and chats_data['chats']:
                all_chats.extend(chats_data['chats'])
                print(f"📝 Получено чатов: {len(chats_data['chats'])}, всего: {len(all_chats)}")
                offset += limit
                
                # Если получили меньше чем limit, значит это последняя страница
                if len(chats_data['chats']) < limit:
                    break
            else:
                break
                
        except Exception as e:
            print(f"❌ Ошибка получения чатов: {e}")
            break
    
    print(f"✅ Всего чатов найдено: {len(all_chats)}")
    
    # 4. Получить сообщения из каждого чата
    print("📨 Получение сообщений из чатов...")
    all_messages = {}
    
    for i, chat in enumerate(all_chats, 1):
        chat_id = chat['id']
        print(f"📨 Чат {i}/{len(all_chats)}: {chat_id}")
        
        chat_messages = []
        offset = 0
        limit = 100
        
        while True:
            try:
                messages_url = f"https://api.avito.ru/messenger/v1/accounts/{account_id}/chats/{chat_id}/messages"
                params = {'limit': limit, 'offset': offset}
                
                messages_response = requests.get(messages_url, headers=headers, params=params, timeout=30)
                messages_response.raise_for_status()
                messages_data = messages_response.json()
                
                if 'messages' in messages_data and messages_data['messages']:
                    chat_messages.extend(messages_data['messages'])
                    offset += limit
                    
                    if len(messages_data['messages']) < limit:
                        break
                else:
                    break
                    
            except Exception as e:
                print(f"❌ Ошибка получения сообщений из чата {chat_id}: {e}")
                break
        
        if chat_messages:
            all_messages[chat_id] = chat_messages
            print(f"✅ Получено сообщений: {len(chat_messages)}")
        
        # Небольшая пауза между запросами
        time.sleep(0.5)
    
    # 5. Собрать результат
    result = {
        'account_id': account_id,
        'access_token': access_token[:20] + "...",  # Частично скрыт для безопасности
        'timestamp': datetime.now().isoformat(),
        'total_chats': len(all_chats),
        'total_messages': sum(len(msgs) for msgs in all_messages.values()),
        'chats': all_chats,
        'messages': all_messages
    }
    
    print(f"🎉 Готово! Чатов: {result['total_chats']}, сообщений: {result['total_messages']}")
    return result

def save_messages_to_file(messages_data, filename=None):
    """Сохранить данные в JSON файл"""
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"avito_messages_{timestamp}.json"
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(messages_data, f, ensure_ascii=False, indent=2)
    
    print(f"💾 Данные сохранены в: {filename}")
    return filename

def main():
    """Основная функция для запуска из командной строки"""
    client_id = os.getenv('AVITO_CLIENT_ID')
    client_secret = os.getenv('AVITO_CLIENT_SECRET')
    account_id = os.getenv('AVITO_ACCOUNT_ID')  # Опционально
    
    if not client_id or not client_secret:
        print("❌ Установите переменные окружения AVITO_CLIENT_ID и AVITO_CLIENT_SECRET")
        print("Пример:")
        print("$env:AVITO_CLIENT_ID = 'ваш_client_id'")
        print("$env:AVITO_CLIENT_SECRET = 'ваш_client_secret'")
        sys.exit(1)
    
    print("🚀 Запуск получения сообщений Avito...")
    
    # Получить сообщения
    messages_data = get_avito_messages(client_id, client_secret, account_id)
    
    if messages_data:
        # Сохранить в файл
        filename = save_messages_to_file(messages_data)
        
        # Показать краткую статистику
        print("\n📊 Статистика:")
        print(f"Аккаунт ID: {messages_data['account_id']}")
        print(f"Всего чатов: {messages_data['total_chats']}")
        print(f"Всего сообщений: {messages_data['total_messages']}")
        print(f"Файл: {filename}")
        
        # Показать первые несколько чатов
        if messages_data['chats']:
            print("\n💬 Первые чаты:")
            for chat in messages_data['chats'][:5]:
                print(f"  - {chat.get('id', 'N/A')}: {chat.get('title', 'Без названия')}")
    else:
        print("❌ Не удалось получить сообщения")

if __name__ == "__main__":
    main()