#!/usr/bin/env python3
"""
Поиск рабочих endpoints для мессенджера и резюме Авито
"""
import requests
import json
from datetime import datetime

class AvitoEndpointExplorer:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.base_url = "https://api.avito.ru"
        
    def get_access_token(self):
        """Получение access token"""
        url = f"{self.base_url}/token"
        data = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret
        }
        
        response = requests.post(url, data=data)
        if response.status_code == 200:
            result = response.json()
            self.access_token = result['access_token']
            print(f"✅ Токен получен: {self.access_token[:20]}...")
            return True
        else:
            print(f"❌ Ошибка получения токена: {response.status_code} - {response.text}")
            return False
    
    def get_headers(self):
        """Получение заголовков для запросов"""
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
    
    def explore_messenger_endpoints(self):
        """Исследование endpoints мессенджера"""
        print("\n🔍 Исследую endpoints мессенджера...")
        
        endpoints = [
            # Основные endpoints мессенджера
            "/messenger/v1/accounts/self/chats",
            "/messenger/v2/accounts/self/chats",
            "/messenger/v3/accounts/self/chats",
            "/messenger/chats",
            "/messenger/v1/chats",
            "/messenger/v2/chats",
            "/messenger/v3/chats",
            
            # Альтернативные варианты
            "/core/v1/messenger/chats",
            "/core/v1/accounts/self/messenger/chats",
            "/api/messenger/chats",
            "/v1/messenger/chats",
            "/v2/messenger/chats",
            
            # Попытки через job API
            "/job/v1/messenger/chats",
            "/job/v1/accounts/self/chats",
            "/job/v1/communications",
            "/job/v1/messages",
            
            # Другие варианты
            "/user/chats",
            "/user/messages",
            "/communications/chats",
            "/communications/messages"
        ]
        
        working_endpoints = []
        
        for endpoint in endpoints:
            url = f"{self.base_url}{endpoint}"
            try:
                response = requests.get(url, headers=self.get_headers(), timeout=10)
                
                if response.status_code == 200:
                    working_endpoints.append(endpoint)
                    print(f"✅ {endpoint} - РАБОТАЕТ!")
                    try:
                        data = response.json()
                        print(f"   📄 Структура ответа: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                        if isinstance(data, dict) and 'chats' in data:
                            print(f"   💬 Количество чатов: {len(data['chats'])}")
                        elif isinstance(data, list):
                            print(f"   💬 Количество элементов: {len(data)}")
                    except:
                        print(f"   📄 Ответ: {response.text[:100]}...")
                        
                elif response.status_code == 401:
                    print(f"❌ {endpoint} - Ошибка авторизации")
                elif response.status_code == 403:
                    print(f"❌ {endpoint} - Доступ запрещен (нет прав)")
                elif response.status_code == 404:
                    # Не выводим 404 для краткости
                    pass
                else:
                    print(f"⚠️ {endpoint} - {response.status_code}: {response.text[:50]}...")
                    
            except requests.exceptions.Timeout:
                print(f"⏰ {endpoint} - Таймаут")
            except Exception as e:
                print(f"💥 {endpoint} - Ошибка: {e}")
                
        return working_endpoints
    
    def explore_job_endpoints(self):
        """Исследование endpoints для работы с резюме"""
        print("\n🔍 Исследую endpoints для резюме...")
        
        endpoints = [
            "/job/v1/applications",
            "/job/v1/applications/received",
            "/job/v1/applications/sent", 
            "/job/v1/responses",
            "/job/v1/responses/received",
            "/job/v1/responses/sent",
            "/job/v1/contacts",
            "/job/v1/purchased-contacts",
            "/job/v1/purchases",
            "/job/v1/purchased-resumes",
            "/job/v1/bought-resumes",
            "/job/v1/contacts/purchased",
            "/job/v1/cv/purchased",
            "/job/v1/employer/applications",
            "/job/v1/employer/responses"
        ]
        
        working_endpoints = []
        
        for endpoint in endpoints:
            url = f"{self.base_url}{endpoint}"
            try:
                response = requests.get(url, headers=self.get_headers(), timeout=10)
                
                if response.status_code == 200:
                    working_endpoints.append(endpoint)
                    print(f"✅ {endpoint} - РАБОТАЕТ!")
                    try:
                        data = response.json()
                        print(f"   📄 Структура: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                        if isinstance(data, dict):
                            for key, value in data.items():
                                if isinstance(value, list):
                                    print(f"   📋 {key}: {len(value)} элементов")
                    except:
                        print(f"   📄 Ответ: {response.text[:100]}...")
                        
                elif response.status_code == 401:
                    print(f"❌ {endpoint} - Ошибка авторизации")
                elif response.status_code == 403:
                    print(f"❌ {endpoint} - Доступ запрещен")
                elif response.status_code == 404:
                    pass  # Не выводим 404
                else:
                    print(f"⚠️ {endpoint} - {response.status_code}: {response.text[:50]}...")
                    
            except requests.exceptions.Timeout:
                print(f"⏰ {endpoint} - Таймаут")
            except Exception as e:
                pass
                
        return working_endpoints
    
    def explore_user_endpoints(self):
        """Исследование пользовательских endpoints"""
        print("\n🔍 Исследую пользовательские endpoints...")
        
        endpoints = [
            "/user/operations",
            "/user/purchases", 
            "/user/bought-resumes",
            "/user/contacts",
            "/user/balance",
            "/user/transactions",
            "/user/history",
            "/core/v1/accounts/self/purchases",
            "/core/v1/accounts/self/transactions",
            "/core/v1/accounts/self/orders",
            "/core/v1/user/purchases"
        ]
        
        working_endpoints = []
        
        for endpoint in endpoints:
            url = f"{self.base_url}{endpoint}"
            try:
                response = requests.get(url, headers=self.get_headers(), timeout=10)
                
                if response.status_code == 200:
                    working_endpoints.append(endpoint)
                    print(f"✅ {endpoint} - РАБОТАЕТ!")
                    try:
                        data = response.json()
                        print(f"   📄 Ответ: {json.dumps(data, ensure_ascii=False)[:200]}...")
                    except:
                        print(f"   📄 Ответ: {response.text[:100]}...")
                        
                elif response.status_code == 401:
                    print(f"❌ {endpoint} - Ошибка авторизации")
                elif response.status_code == 403:
                    print(f"❌ {endpoint} - Доступ запрещен")
                elif response.status_code == 404:
                    pass
                else:
                    print(f"⚠️ {endpoint} - {response.status_code}: {response.text[:50]}...")
                    
            except requests.exceptions.Timeout:
                print(f"⏰ {endpoint} - Таймаут")
            except Exception as e:
                pass
                
        return working_endpoints

def main():
    CLIENT_ID = "pEm43bT2JX47aeb8OxNV"
    CLIENT_SECRET = "pURVGURY6Mt95xTPxrTHJ_SpzL7sBPNRfTt7qQkw"
    
    print("🕵️ Исследователь API Endpoints Авито")
    print("=" * 50)
    
    explorer = AvitoEndpointExplorer(CLIENT_ID, CLIENT_SECRET)
    
    if not explorer.get_access_token():
        print("❌ Не удалось получить токен")
        return
    
    # Исследуем все возможные endpoints
    messenger_endpoints = explorer.explore_messenger_endpoints()
    job_endpoints = explorer.explore_job_endpoints()
    user_endpoints = explorer.explore_user_endpoints()
    
    print(f"\n📊 ИТОГИ ИССЛЕДОВАНИЯ:")
    print(f"💬 Рабочие endpoints мессенджера: {len(messenger_endpoints)}")
    for ep in messenger_endpoints:
        print(f"   ✅ {ep}")
        
    print(f"👔 Рабочие endpoints резюме: {len(job_endpoints)}")
    for ep in job_endpoints:
        print(f"   ✅ {ep}")
        
    print(f"👤 Рабочие пользовательские endpoints: {len(user_endpoints)}")
    for ep in user_endpoints:
        print(f"   ✅ {ep}")

if __name__ == "__main__":
    main()