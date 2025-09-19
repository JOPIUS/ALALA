#!/usr/bin/env python3
"""
Быстрая функция для получения сообщений из Avito
Автоматически получает Authorization Code токен и скачивает сообщения
"""

import os
import sys
import json
import requests
import time
import webbrowser
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode

class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.auth_code = None
        query = urlparse(self.path).query
        params = parse_qs(query)
        
        if 'code' in params:
            self.server.auth_code = params['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write("""
            <html><body style="font-family: Arial; text-align: center; margin-top: 100px;">
            <h2>✅ Авторизация успешна!</h2>
            <p>Код получен, можно закрыть это окно.</p>
            </body></html>
            """.encode('utf-8'))
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write("""
            <html><body style="font-family: Arial; text-align: center; margin-top: 100px;">
            <h2>❌ Ошибка авторизации</h2>
            <p>Код авторизации не получен.</p>
            </body></html>
            """.encode('utf-8'))

def get_auth_code(client_id, redirect_uri="http://localhost:8080"):
    """Получить код авторизации через браузер"""
    print("🔑 Получение кода авторизации...")
    
    # Запустить локальный сервер
    server = HTTPServer(('localhost', 8080), CallbackHandler)
    server.auth_code = None
    
    # Открыть браузер
    auth_url = f"https://avito.ru/oauth?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}&scope=messages.read+messages.write"
    print(f"🌐 Открываю браузер: {auth_url}")
    webbrowser.open(auth_url)
    
    # Ждать код в отдельном потоке
    def wait_for_code():
        server.handle_request()
    
    thread = threading.Thread(target=wait_for_code)
    thread.start()
    thread.join(timeout=60)  # Ждём максимум 60 секунд
    
    if server.auth_code:
        print(f"✅ Код авторизации получен: {server.auth_code[:20]}...")
        return server.auth_code
    else:
        print("❌ Не удалось получить код авторизации")
        return None

def exchange_code_for_token(client_id, client_secret, auth_code, redirect_uri="http://localhost:8080"):
    """Обменять код на токен"""
    print("🔄 Обмен кода на токен...")
    
    token_url = "https://api.avito.ru/token"
    data = {
        'grant_type': 'authorization_code',
        'client_id': client_id,
        'client_secret': client_secret,
        'code': auth_code,
        'redirect_uri': redirect_uri
    }
    
    try:
        response = requests.post(token_url, data=data, timeout=30)
        response.raise_for_status()
        token_info = response.json()
        print(f"✅ Токен получен: {token_info['access_token'][:20]}...")
        return token_info['access_token']
    except Exception as e:
        print(f"❌ Ошибка обмена кода на токен: {e}")
        return None

def find_account_id(access_token):
    """Найти user_id для Messages API"""
    print("🔍 Поиск user_id...")
    
    headers = {'Authorization': f'Bearer {access_token}'}
    
    # Попробуем разные endpoints для поиска user_id
    endpoints = [
        "https://api.avito.ru/core/v1/accounts/self",
        "https://api.avito.ru/core/v1/accounts/me", 
        "https://api.avito.ru/user/v1/self",
        "https://api.avito.ru/user/v1/me",
        "https://api.avito.ru/messenger/v1/accounts"
    ]
    
    for endpoint in endpoints:
        try:
            print(f"  🔗 {endpoint}")
            response = requests.get(endpoint, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                print(f"  ✅ Ответ: {json.dumps(data, ensure_ascii=False)[:200]}...")
                
                # Попробуем извлечь ID
                if isinstance(data, list) and data:
                    return data[0].get('id')
                elif isinstance(data, dict):
                    return data.get('id') or data.get('user_id') or data.get('account_id')
            else:
                print(f"  ❌ {response.status_code}")
                
        except Exception as e:
            print(f"  ❌ Ошибка: {e}")
    
    return None

def get_messages_from_account(access_token, user_id):
    """Получить все сообщения из аккаунта"""
    print(f"📨 Получение сообщений для user_id {user_id}...")
    
    headers = {'Authorization': f'Bearer {access_token}'}
    
    # Получить чаты через v2 API
    print("💬 Получение чатов...")
    chats_url = f"https://api.avito.ru/messenger/v2/accounts/{user_id}/chats"
    
    try:
        chats_response = requests.get(chats_url, headers=headers, timeout=30)
        
        if chats_response.status_code == 200:
            chats_data = chats_response.json()
            print(f"✅ Получено чатов: {len(chats_data.get('chats', []))}")
            
            # Получить сообщения из каждого чата через v1 API
            all_messages = {}
            for chat in chats_data.get('chats', []):
                chat_id = chat['id']
                print(f"  📝 Чат {chat_id}...")
                
                messages_url = f"https://api.avito.ru/messenger/v1/accounts/{user_id}/chats/{chat_id}/messages"
                try:
                    messages_response = requests.get(messages_url, headers=headers, timeout=30)
                    if messages_response.status_code == 200:
                        messages_data = messages_response.json()
                        all_messages[chat_id] = messages_data.get('messages', [])
                        print(f"    ✅ Сообщений: {len(all_messages[chat_id])}")
                    else:
                        print(f"    ❌ {messages_response.status_code}")
                        print(f"    Ответ: {messages_response.text[:200]}")
                except Exception as e:
                    print(f"    ❌ Ошибка: {e}")
                
                time.sleep(0.5)  # Пауза между запросами
            
            return {
                'chats': chats_data.get('chats', []),
                'messages': all_messages,
                'total_chats': len(chats_data.get('chats', [])),
                'total_messages': sum(len(msgs) for msgs in all_messages.values())
            }
        else:
            print(f"❌ Ошибка получения чатов: {chats_response.status_code}")
            print(f"   Ответ: {chats_response.text[:500]}")
            return None
            
    except Exception as e:
        print(f"❌ Ошибка получения чатов: {e}")
        return None

def quick_get_avito_messages():
    """Быстро получить все сообщения из Avito"""
    print("🚀 Быстрое получение сообщений Avito")
    print("=" * 50)
    
    # Получить креды из переменных окружения
    client_id = os.getenv('AVITO_CLIENT_ID')
    client_secret = os.getenv('AVITO_CLIENT_SECRET')
    user_id = os.getenv('AVITO_USER_ID') or os.getenv('AVITO_ACCOUNT_ID')  # Поддержка обеих переменных
    
    if not client_id or not client_secret:
        print("❌ Установите переменные окружения:")
        print("$env:AVITO_CLIENT_ID = 'ваш_client_id'")
        print("$env:AVITO_CLIENT_SECRET = 'ваш_client_secret'")
        return None
    
    # 1. Получить код авторизации
    auth_code = get_auth_code(client_id)
    if not auth_code:
        return None
    
    # 2. Обменять на токен
    access_token = exchange_code_for_token(client_id, client_secret, auth_code)
    if not access_token:
        return None
    
    # 3. Найти user_id если не указан
    if not user_id:
        user_id = find_account_id(access_token)
        if not user_id:
            user_id = input("🔢 Введите user_id вручную: ").strip()
            if not user_id:
                print("❌ user_id не указан")
                return None
    
    # 4. Получить сообщения
    messages_data = get_messages_from_account(access_token, user_id)
    if not messages_data:
        return None
    
    # 5. Сохранить результат
    result = {
        'user_id': user_id,
        'timestamp': datetime.now().isoformat(),
        **messages_data
    }
    
    # Сохранить в файл
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"avito_messages_quick_{timestamp}.json"
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print("\n🎉 Готово!")
    print(f"📊 User ID: {result['user_id']}")
    print(f"📊 Чатов: {result['total_chats']}")
    print(f"📨 Сообщений: {result['total_messages']}")
    print(f"💾 Файл: {filename}")
    
    return result

if __name__ == "__main__":
    quick_get_avito_messages()