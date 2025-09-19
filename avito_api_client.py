#!/usr/bin/env python3
"""
Скрипт для работы с API Авито
Получение данных по купленным резюме с непрочитанными сообщениями
"""
import requests
import json
from datetime import datetime

class AvitoAPIClient:
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
    
    def get_account_info(self):
        """Получение информации об аккаунте"""
        url = f"{self.base_url}/core/v1/accounts/self"
        response = requests.get(url, headers=self.get_headers())
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Ошибка получения информации об аккаунте: {response.status_code} - {response.text}")
            return None
    
    def try_endpoints(self):
        """Тестирование различных endpoints"""
        endpoints = [
            "/messenger/v1/accounts/self/chats",
            "/messenger/v2/accounts/self/chats", 
            "/messenger/chats",
            "/job/v1/applications",
            "/job/v1/resumes",
            "/job/v1/vacancies",
            "/job/applications",
            "/job/resumes",
            "/core/v1/accounts/self/operations",
            "/core/v1/accounts/self/balance",
            "/core/v1/operations",
            "/user/operations",
            "/user/balance"
        ]
        
        working_endpoints = []
        
        for endpoint in endpoints:
            url = f"{self.base_url}{endpoint}"
            try:
                response = requests.get(url, headers=self.get_headers())
                print(f"🔍 {endpoint}: {response.status_code}")
                
                if response.status_code == 200:
                    working_endpoints.append(endpoint)
                    print(f"✅ {endpoint} - РАБОТАЕТ")
                    try:
                        data = response.json()
                        print(f"   Данные: {json.dumps(data, ensure_ascii=False)[:200]}...")
                    except:
                        print(f"   Ответ: {response.text[:200]}...")
                elif response.status_code == 401:
                    print(f"❌ {endpoint} - Ошибка авторизации")
                elif response.status_code == 403:
                    print(f"❌ {endpoint} - Доступ запрещен")
                elif response.status_code == 404:
                    print(f"⚠️ {endpoint} - Не найден")
                else:
                    print(f"❓ {endpoint} - {response.status_code}: {response.text[:100]}")
                    
            except Exception as e:
                print(f"💥 {endpoint} - Ошибка: {e}")
                
        return working_endpoints
    
    def get_messenger_chats(self):
        """Получение списка чатов из мессенджера"""
        # Попробуем различные варианты URL
        urls = [
            f"{self.base_url}/messenger/v1/accounts/self/chats",
            f"{self.base_url}/messenger/v2/accounts/self/chats",
            f"{self.base_url}/messenger/chats"
        ]
        
        for url in urls:
            try:
                response = requests.get(url, headers=self.get_headers())
                if response.status_code == 200:
                    print(f"✅ Чаты получены через: {url}")
                    return response.json()
                else:
                    print(f"❌ {url}: {response.status_code} - {response.text}")
            except Exception as e:
                print(f"💥 Ошибка для {url}: {e}")
        
        return None
    
    def analyze_unread_resumes(self):
        """Анализ резюме с непрочитанными сообщениями"""
        print("🔍 Начинаю поиск купленных резюме с непрочитанными сообщениями...")
        
        # Получаем информацию об аккаунте
        account_info = self.get_account_info()
        if account_info:
            print(f"👤 Аккаунт: {account_info.get('name', 'Неизвестно')}")
            print(f"📧 Email: {account_info.get('email', 'Неизвестно')}")
        
        # Тестируем endpoints
        print("\n🔍 Тестирование доступных endpoints...")
        working_endpoints = self.try_endpoints()
        
        if working_endpoints:
            print(f"\n✅ Рабочие endpoints: {working_endpoints}")
        else:
            print("\n❌ Не найдено рабочих endpoints для данной задачи")
        
        # Попробуем получить чаты
        print("\n📱 Попытка получения чатов...")
        chats = self.get_messenger_chats()
        
        if chats:
            print(f"💬 Найдено чатов: {len(chats) if isinstance(chats, list) else 'N/A'}")
            return chats
        else:
            print("❌ Не удалось получить чаты")
            return None

def main():
    # Данные авторизации
    CLIENT_ID = "pEm43bT2JX47aeb8OxNV"
    CLIENT_SECRET = "pURVGURY6Mt95xTPxrTHJ_SpzL7sBPNRfTt7qQkw"
    
    print("🚀 Запуск Avito API Client")
    print("=" * 50)
    
    # Создаем клиент
    client = AvitoAPIClient(CLIENT_ID, CLIENT_SECRET)
    
    # Получаем токен
    if not client.get_access_token():
        print("❌ Не удалось получить токен. Завершение работы.")
        return
    
    # Анализируем резюме
    result = client.analyze_unread_resumes()
    
    if result:
        print("\n📊 РЕЗУЛЬТАТ:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("\n❌ Не удалось получить данные о резюме с непрочитанными сообщениями")
        print("\n💡 Возможные причины:")
        print("- API endpoints могут быть недоступны для данного типа авторизации")
        print("- Требуется персональная авторизация вместо client credentials")
        print("- Необходимо дополнительные разрешения для доступа к мессенджеру и резюме")

if __name__ == "__main__":
    main()