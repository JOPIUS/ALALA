#!/usr/bin/env python3
"""
Простая функция для получения сообщений без браузера
Использует Client Credentials flow для авторизации
"""

import os
import sys
import json
import requests
import time
from datetime import datetime

def get_client_credentials_token(client_id, client_secret):
    """Получить токен через Client Credentials (без браузера)"""
    print("🔑 Получение токена через Client Credentials...")
    
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
        print(f"✅ Токен получен: {access_token[:20]}...")
        return access_token
    except Exception as e:
        print(f"❌ Ошибка получения токена: {e}")
        if hasattr(e, 'response'):
            print(f"   Ответ: {e.response.text[:300]}")
        return None

def try_get_user_id(access_token):
    """Попробовать найти user_id разными способами"""
    print("🔍 Поиск user_id...")
    
    headers = {'Authorization': f'Bearer {access_token}'}
    
    # Попробуем разные endpoints
    endpoints = [
        "https://api.avito.ru/core/v1/accounts/self",
        "https://api.avito.ru/core/v1/accounts/me", 
        "https://api.avito.ru/user/v1/self",
        "https://api.avito.ru/user/v1/me",
        "https://api.avito.ru/core/v1/accounts",
        "https://api.avito.ru/messenger/v1/accounts"
    ]
    
    for endpoint in endpoints:
        try:
            print(f"  🔗 {endpoint}")
            response = requests.get(endpoint, headers=headers, timeout=30)
            
            print(f"    Статус: {response.status_code}")
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"    ✅ Ответ: {json.dumps(data, ensure_ascii=False)[:300]}...")
                    
                    # Попробуем извлечь ID
                    if isinstance(data, list) and data:
                        user_id = data[0].get('id') or data[0].get('user_id')
                        if user_id:
                            print(f"✅ User ID найден: {user_id}")
                            return user_id
                    elif isinstance(data, dict):
                        user_id = data.get('id') or data.get('user_id') or data.get('account_id')
                        if user_id:
                            print(f"✅ User ID найден: {user_id}")
                            return user_id
                except json.JSONDecodeError:
                    print(f"    ❌ Неверный JSON")
            else:
                print(f"    ❌ Ошибка: {response.text[:200]}")
                
        except Exception as e:
            print(f"    ❌ Исключение: {e}")
    
    return None

def try_get_chats(access_token, user_id):
    """Попробовать получить чаты"""
    print(f"💬 Попытка получить чаты для user_id {user_id}...")
    
    headers = {'Authorization': f'Bearer {access_token}'}
    
    # Попробуем разные версии API
    chat_endpoints = [
        f"https://api.avito.ru/messenger/v2/accounts/{user_id}/chats",
        f"https://api.avito.ru/messenger/v1/accounts/{user_id}/chats"
    ]
    
    for endpoint in chat_endpoints:
        try:
            print(f"  🔗 {endpoint}")
            response = requests.get(endpoint, headers=headers, timeout=30)
            
            print(f"    Статус: {response.status_code}")
            if response.status_code == 200:
                try:
                    data = response.json()
                    chats = data.get('chats', [])
                    print(f"    ✅ Найдено чатов: {len(chats)}")
                    
                    if chats:
                        # Попробуем получить сообщения из первого чата
                        chat_id = chats[0]['id']
                        print(f"    📨 Пробуем получить сообщения из чата {chat_id}...")
                        
                        messages_endpoint = f"https://api.avito.ru/messenger/v1/accounts/{user_id}/chats/{chat_id}/messages"
                        messages_response = requests.get(messages_endpoint, headers=headers, timeout=30)
                        
                        print(f"      Статус сообщений: {messages_response.status_code}")
                        if messages_response.status_code == 200:
                            messages_data = messages_response.json()
                            messages = messages_data.get('messages', [])
                            print(f"      ✅ Сообщений в чате: {len(messages)}")
                        else:
                            print(f"      ❌ Ошибка сообщений: {messages_response.text[:200]}")
                    
                    return data
                except json.JSONDecodeError:
                    print(f"    ❌ Неверный JSON")
            else:
                print(f"    ❌ Ошибка: {response.text[:300]}")
                
        except Exception as e:
            print(f"    ❌ Исключение: {e}")
    
    return None

def test_messages_api():
    """Протестировать Messages API без браузера"""
    print("🚀 Тест Messages API без браузера")
    print("=" * 50)
    
    # Получить креды
    client_id = os.getenv('AVITO_CLIENT_ID')
    client_secret = os.getenv('AVITO_CLIENT_SECRET')
    user_id = os.getenv('AVITO_USER_ID') or os.getenv('AVITO_ACCOUNT_ID')
    
    if not client_id or not client_secret:
        print("❌ Установите переменные окружения:")
        print("$env:AVITO_CLIENT_ID = 'ваш_client_id'")
        print("$env:AVITO_CLIENT_SECRET = 'ваш_client_secret'")
        return None
    
    # 1. Получить токен Client Credentials
    access_token = get_client_credentials_token(client_id, client_secret)
    if not access_token:
        return None
    
    # 2. Попробовать найти user_id если не указан
    if not user_id:
        user_id = try_get_user_id(access_token)
        if not user_id:
            print("❌ Не удалось найти user_id автоматически")
            user_id = input("🔢 Введите user_id вручную (или Enter для пропуска): ").strip()
            if not user_id:
                print("💡 Продолжаем без user_id для тестирования endpoints...")
                user_id = "123456789"  # Фиктивный ID для тестирования
    
    # 3. Тестируем доступ к Messages API
    chats_data = try_get_chats(access_token, user_id)
    
    # 4. Сохраним результаты теста
    result = {
        'timestamp': datetime.now().isoformat(),
        'access_token': access_token[:20] + "...",
        'user_id': user_id,
        'test_results': {
            'token_obtained': access_token is not None,
            'chats_accessible': chats_data is not None,
            'chats_data': chats_data
        }
    }
    
    # Сохранить в файл
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"avito_messages_test_{timestamp}.json"
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"\n📊 Результаты теста:")
    print(f"🔑 Токен получен: {'✅' if result['test_results']['token_obtained'] else '❌'}")
    print(f"💬 Чаты доступны: {'✅' if result['test_results']['chats_accessible'] else '❌'}")
    print(f"💾 Лог сохранён: {filename}")
    
    if not result['test_results']['chats_accessible']:
        print("\n💡 Возможные причины:")
        print("• Client Credentials токен не даёт доступ к Messages API")
        print("• Нужен Authorization Code токен (с браузером)")
        print("• Неправильный user_id")
        print("• API требует дополнительных разрешений")
    
    return result

if __name__ == "__main__":
    test_messages_api()