#!/usr/bin/env python3
"""
Умная функция для получения сообщений Avito
Сначала пробует Client Credentials, затем Authorization Code если нужно
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
from urllib.parse import urlparse, parse_qs

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

def get_client_credentials_token(client_id, client_secret):
    """Client Credentials токен (без браузера)"""
    print("🔑 Получение Client Credentials токена...")
    
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
        print(f"✅ Client Credentials токен: {access_token[:20]}...")
        return access_token
    except Exception as e:
        print(f"❌ Ошибка Client Credentials: {e}")
        return None

def get_authorization_code_token(client_id, client_secret):
    """Authorization Code токен (с браузером)"""
    print("🔑 Получение Authorization Code токена...")
    
    # Получить код авторизации
    print("🌐 Открываю браузер для авторизации...")
    redirect_uri = "http://localhost:8080"
    
    server = HTTPServer(('localhost', 8080), CallbackHandler)
    server.auth_code = None
    
    auth_url = f"https://avito.ru/oauth?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}&scope=messenger:read+messenger:write"
    print(f"🔗 {auth_url}")
    webbrowser.open(auth_url)
    
    def wait_for_code():
        server.handle_request()
    
    thread = threading.Thread(target=wait_for_code)
    thread.start()
    thread.join(timeout=60)
    
    if not server.auth_code:
        print("❌ Не удалось получить код авторизации")
        return None
    
    print(f"✅ Код получен: {server.auth_code[:20]}...")
    
    # Обменять код на токен
    token_url = "https://api.avito.ru/token"
    data = {
        'grant_type': 'authorization_code',
        'client_id': client_id,
        'client_secret': client_secret,
        'code': server.auth_code,
        'redirect_uri': redirect_uri
    }
    
    try:
        response = requests.post(token_url, data=data, timeout=30)
        response.raise_for_status()
        token_info = response.json()
        access_token = token_info['access_token']
        print(f"✅ Authorization Code токен: {access_token[:20]}...")
        return access_token
    except Exception as e:
        print(f"❌ Ошибка обмена кода на токен: {e}")
        return None

def find_user_id(access_token):
    """Найти user_id"""
    print("🔍 Поиск user_id...")
    
    headers = {'Authorization': f'Bearer {access_token}'}
    
    try:
        response = requests.get("https://api.avito.ru/core/v1/accounts/self", headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            user_id = data.get('id')
            if user_id:
                print(f"✅ User ID: {user_id}")
                return user_id
    except Exception as e:
        print(f"❌ Ошибка поиска user_id: {e}")
    
    return None

def get_all_messages(access_token, user_id):
    """Получить все сообщения"""
    print(f"📨 Получение всех сообщений для user_id {user_id}...")
    
    headers = {'Authorization': f'Bearer {access_token}'}
    
    # 1. Получить чаты
    print("💬 Получение чатов...")
    chats_url = f"https://api.avito.ru/messenger/v2/accounts/{user_id}/chats"
    
    try:
        chats_response = requests.get(chats_url, headers=headers, timeout=30)
        if chats_response.status_code != 200:
            print(f"❌ Ошибка получения чатов: {chats_response.status_code}")
            print(f"   Ответ: {chats_response.text[:300]}")
            return None
        
        chats_data = chats_response.json()
        chats = chats_data.get('chats', [])
        print(f"✅ Найдено чатов: {len(chats)}")
        
        # 2. Получить сообщения из каждого чата
        all_messages = {}
        total_messages = 0
        
        for i, chat in enumerate(chats[:10], 1):  # Ограничим первыми 10 чатами для теста
            chat_id = chat['id']
            print(f"📝 Чат {i}/10: {chat_id}")
            
            messages_url = f"https://api.avito.ru/messenger/v1/accounts/{user_id}/chats/{chat_id}/messages"
            
            try:
                messages_response = requests.get(messages_url, headers=headers, timeout=30)
                
                if messages_response.status_code == 200:
                    messages_data = messages_response.json()
                    messages = messages_data.get('messages', [])
                    all_messages[chat_id] = messages
                    total_messages += len(messages)
                    print(f"   ✅ Сообщений: {len(messages)}")
                elif messages_response.status_code == 405:
                    print(f"   ❌ 405 - нужен Authorization Code токен")
                    return None
                else:
                    print(f"   ❌ {messages_response.status_code}: {messages_response.text[:100]}")
                    
            except Exception as e:
                print(f"   ❌ Ошибка: {e}")
            
            time.sleep(0.5)  # Пауза между запросами
        
        return {
            'chats': chats,
            'messages': all_messages,
            'total_chats': len(chats),
            'total_messages': total_messages
        }
        
    except Exception as e:
        print(f"❌ Ошибка получения чатов: {e}")
        return None

def smart_get_messages():
    """Умное получение сообщений - сначала Client Credentials, потом Authorization Code"""
    print("🧠 Умное получение сообщений Avito")
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
    
    # Стратегия 1: Попробовать Client Credentials
    print("\n🔄 Стратегия 1: Client Credentials (без браузера)")
    access_token = get_client_credentials_token(client_id, client_secret)
    
    if access_token:
        # Найти user_id если нужно
        if not user_id:
            user_id = find_user_id(access_token)
            if not user_id:
                print("❌ Не удалось найти user_id")
                return None
        
        # Попробовать получить сообщения
        messages_data = get_all_messages(access_token, user_id)
        
        if messages_data:
            print("\n🎉 Client Credentials сработал!")
        else:
            print("\n⚠️ Client Credentials не даёт доступ к сообщениям")
            
            # Стратегия 2: Authorization Code
            print("\n🔄 Стратегия 2: Authorization Code (с браузером)")
            access_token = get_authorization_code_token(client_id, client_secret)
            
            if access_token:
                messages_data = get_all_messages(access_token, user_id)
                if messages_data:
                    print("\n🎉 Authorization Code сработал!")
                else:
                    print("\n❌ Даже Authorization Code не помог")
                    return None
            else:
                print("\n❌ Не удалось получить Authorization Code токен")
                return None
    else:
        print("\n❌ Не удалось получить даже Client Credentials токен")
        return None
    
    # Сохранить результат
    if messages_data:
        result = {
            'user_id': user_id,
            'timestamp': datetime.now().isoformat(),
            'access_token': access_token[:20] + "...",
            **messages_data
        }
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"avito_messages_smart_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"\n📊 Результат:")
        print(f"👤 User ID: {result['user_id']}")
        print(f"💬 Чатов: {result['total_chats']}")
        print(f"📨 Сообщений: {result['total_messages']}")
        print(f"💾 Файл: {filename}")
        
        return result
    
    return None

if __name__ == "__main__":
    smart_get_messages()