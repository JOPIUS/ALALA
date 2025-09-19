#!/usr/bin/env python3
"""
Анализ купленных резюме с непрочитанными сообщениями из CSV файла
"""
import requests
import json
import csv
import os
from datetime import datetime
from pathlib import Path

class AvitoResumeAnalyzer:
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
    
    def read_bought_resumes_csv(self, csv_path):
        """Чтение ID купленных резюме из CSV файла"""
        bought_ids = []
        
        if not os.path.exists(csv_path):
            print(f"❌ Файл {csv_path} не найден")
            return bought_ids
            
        try:
            with open(csv_path, 'r', encoding='utf-8-sig') as file:
                # Пробуем разные варианты чтения CSV
                content = file.read().strip()
                
                # Проверяем первые строки для понимания формата
                lines = content.split('\n')
                print(f"📄 Первые строки файла:")
                for i, line in enumerate(lines[:5]):
                    print(f"   {i+1}: {line}")
                
                # Если есть заголовки, ищем колонку с ID
                if len(lines) > 0:
                    first_line = lines[0].lower()
                    if 'id' in first_line or 'resume' in first_line:
                        # Есть заголовки
                        reader = csv.DictReader(lines)
                        for row in reader:
                            # Ищем колонку с ID резюме
                            for key, value in row.items():
                                if 'id' in key.lower() and value.strip().isdigit():
                                    bought_ids.append(int(value.strip()))
                                    break
                    else:
                        # Нет заголовков, каждая строка - это ID
                        for line in lines:
                            line = line.strip()
                            if line.isdigit():
                                bought_ids.append(int(line))
                            elif ',' in line:
                                # Может быть CSV с разделителем
                                parts = line.split(',')
                                for part in parts:
                                    part = part.strip()
                                    if part.isdigit():
                                        bought_ids.append(int(part))
                                        
            print(f"📋 Найдено {len(bought_ids)} купленных резюме: {bought_ids[:10]}{'...' if len(bought_ids) > 10 else ''}")
            return bought_ids
            
        except Exception as e:
            print(f"❌ Ошибка чтения файла {csv_path}: {e}")
            return bought_ids
    
    def get_resume_details(self, resume_id):
        """Получение детальной информации о резюме по ID"""
        url = f"{self.base_url}/job/v1/resumes/{resume_id}"
        
        try:
            response = requests.get(url, headers=self.get_headers())
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                print(f"⚠️ Резюме {resume_id} не найдено")
                return None
            else:
                print(f"❌ Ошибка получения резюме {resume_id}: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"💥 Исключение при получении резюме {resume_id}: {e}")
            return None
    
    def check_resume_messages(self, resume_id):
        """Проверка сообщений для резюме (пробуем разные endpoints)"""
        # Возможные endpoints для сообщений
        endpoints = [
            f"/messenger/v1/resumes/{resume_id}/chats",
            f"/messenger/v2/resumes/{resume_id}/chats", 
            f"/job/v1/resumes/{resume_id}/messages",
            f"/job/v1/resumes/{resume_id}/chat",
            f"/messenger/chats?resume_id={resume_id}",
            f"/messenger/v1/chats?resume_id={resume_id}"
        ]
        
        for endpoint in endpoints:
            url = f"{self.base_url}{endpoint}"
            try:
                response = requests.get(url, headers=self.get_headers())
                if response.status_code == 200:
                    print(f"✅ Найден рабочий endpoint для сообщений: {endpoint}")
                    return response.json()
                elif response.status_code not in [404, 400]:
                    print(f"🔍 {endpoint}: {response.status_code} - {response.text[:100]}")
            except Exception as e:
                continue
                
        return None
    
    def analyze_bought_resumes(self, csv_path):
        """Основной метод анализа купленных резюме"""
        print("🚀 Начинаю анализ купленных резюме...")
        print("=" * 60)
        
        # Читаем ID купленных резюме
        bought_ids = self.read_bought_resumes_csv(csv_path)
        
        if not bought_ids:
            print("❌ Не найдено купленных резюме для анализа")
            return
        
        results = []
        
        print(f"\n🔍 Анализирую {len(bought_ids)} купленных резюме...")
        
        for i, resume_id in enumerate(bought_ids[:10]):  # Ограничиваем первые 10 для тестирования
            print(f"\n📋 Резюме {i+1}/{min(len(bought_ids), 10)}: ID {resume_id}")
            
            # Получаем детали резюме
            resume_details = self.get_resume_details(resume_id)
            
            if resume_details:
                print(f"   👤 {resume_details.get('title', 'Без названия')}")
                print(f"   📍 {resume_details.get('location', {}).get('title', 'Неизвестно')}")
                print(f"   💰 Зарплата: {resume_details.get('salary', 'Не указана')}")
                
                # Проверяем сообщения
                messages = self.check_resume_messages(resume_id)
                
                result = {
                    'resume_id': resume_id,
                    'title': resume_details.get('title', ''),
                    'age': resume_details.get('age', 0),
                    'location': resume_details.get('location', {}).get('title', ''),
                    'salary': resume_details.get('salary', 0),
                    'has_messages': messages is not None,
                    'messages_data': messages,
                    'created_at': resume_details.get('created_at', ''),
                    'updated_at': resume_details.get('updated_at', '')
                }
                
                results.append(result)
                
                if messages:
                    print(f"   💬 Найдены сообщения!")
                else:
                    print(f"   📭 Сообщения не найдены или недоступны")
            else:
                print(f"   ❌ Не удалось получить детали резюме")
        
        # Сохраняем результаты
        self.save_results(results)
        
        return results
    
    def save_results(self, results):
        """Сохранение результатов анализа"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Сохраняем в JSON
        json_filename = f"avito_resume_analysis_{timestamp}.json"
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        # Сохраняем в CSV для удобства
        csv_filename = f"avito_resume_analysis_{timestamp}.csv"
        with open(csv_filename, 'w', newline='', encoding='utf-8-sig') as f:
            if results:
                writer = csv.DictWriter(f, fieldnames=['resume_id', 'title', 'age', 'location', 'salary', 'has_messages', 'created_at', 'updated_at'])
                writer.writeheader()
                for result in results:
                    # Убираем сложные объекты для CSV
                    csv_row = {k: v for k, v in result.items() if k != 'messages_data'}
                    writer.writerow(csv_row)
        
        print(f"\n💾 Результаты сохранены:")
        print(f"   📄 JSON: {json_filename}")
        print(f"   📊 CSV: {csv_filename}")

def main():
    # Данные авторизации
    CLIENT_ID = "pEm43bT2JX47aeb8OxNV"
    CLIENT_SECRET = "pURVGURY6Mt95xTPxrTHJ_SpzL7sBPNRfTt7qQkw"
    
    # Путь к файлу с купленными резюме
    CSV_PATH = r"C:\ManekiNeko\AVITO_API\output\already_bought_id.csv"
    
    print("🎯 Анализатор купленных резюме Avito")
    print("=" * 50)
    
    # Создаем анализатор
    analyzer = AvitoResumeAnalyzer(CLIENT_ID, CLIENT_SECRET)
    
    # Получаем токен
    if not analyzer.get_access_token():
        print("❌ Не удалось получить токен. Завершение работы.")
        return
    
    # Анализируем купленные резюме
    results = analyzer.analyze_bought_resumes(CSV_PATH)
    
    if results:
        print(f"\n📊 ИТОГИ АНАЛИЗА:")
        print(f"🔢 Всего проанализировано: {len(results)}")
        with_messages = sum(1 for r in results if r['has_messages'])
        print(f"💬 С найденными сообщениями: {with_messages}")
        print(f"📭 Без сообщений: {len(results) - with_messages}")
        
        if with_messages > 0:
            print(f"\n✅ Резюме с сообщениями:")
            for result in results:
                if result['has_messages']:
                    print(f"   📋 ID {result['resume_id']}: {result['title']}")
    else:
        print("\n❌ Анализ не дал результатов")

if __name__ == "__main__":
    main()