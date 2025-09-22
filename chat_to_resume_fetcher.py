# -*- coding: utf-8 -*-
"""
Скрипт для получения ссылок на резюме из чатов Avito через API в многопотоке.

Что делает:
- Читает результаты подсчета чатов из JSON файла
- Извлекает user_id из chat_id для каждого чата
- Через API Avito ищет резюме по user_id в 20 потоков
- Сохраняет найденные ссылки на резюме в Excel и JSON

Зависимости:
  pip install requests pandas openpyxl

Использование:
  python chat_to_resume_fetcher.py
  python chat_to_resume_fetcher.py --input avito_chat_count_20250922_032645.json
  python chat_to_resume_fetcher.py --threads 30
"""

from __future__ import annotations

import json
import re
import time
import requests
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Any
import pandas as pd
import sys


# ========== Конфиг ==========
CLIENT_ID = "Dm4ruLMEr9MFsV72dN95"
CLIENT_SECRET = "f73lNoAJLzuqwoGtVaMnByhQfSlwcyIN_m7wyOeT"
API_BASE = "https://api.avito.ru"

DEFAULT_THREADS = 20
REQUEST_TIMEOUT = 15
RATE_LIMIT_DELAY = 0.1  # Задержка между запросами

# Глобальные переменные для статистики
stats = {
    'processed': 0,
    'found_resumes': 0,
    'errors': 0,
    'rate_limited': 0
}


def log(msg: str) -> None:
    print(f"📋 [{datetime.now().strftime('%H:%M:%S')}] {msg}")


def get_access_token() -> Optional[str]:
    """Получает access token для API"""
    try:
        log("🔑 Получаем access token...")
        
        auth_url = f"{API_BASE}/token/"
        auth_data = {
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET
        }
        
        response = requests.post(auth_url, data=auth_data, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        
        token_data = response.json()
        access_token = token_data.get("access_token")
        
        if access_token:
            log("✅ Access token получен успешно")
            return access_token
        else:
            log("❌ Не удалось получить access token")
            return None
            
    except Exception as e:
        log(f"❌ Ошибка получения токена: {e}")
        return None


def extract_user_id_from_chat(chat_id: str) -> Optional[str]:
    """Извлекает user_id из chat_id"""
    # Паттерны для разных типов chat_id:
    # a2u-145964554-316615541 -> 145964554
    # u2i-v~kNKwsHHlFCmuU7R30s8g -> оставляем как есть
    
    if chat_id.startswith('a2u-'):
        # Формат a2u-USER_ID-ANOTHER_ID
        match = re.match(r'a2u-(\d+)-\d+', chat_id)
        if match:
            return match.group(1)
    elif chat_id.startswith('u2i-'):
        # Формат u2i-ENCODED_ID -> возможно это уже user_id в зашифрованном виде
        # Возвращаем часть после u2i-
        return chat_id[4:]  # убираем "u2i-"
    
    # Если не распознали формат, возвращаем как есть
    return chat_id


def search_resume_by_user(user_id: str, access_token: str) -> Optional[Dict[str, Any]]:
    """Ищет резюме пользователя через API"""
    try:
        # Пробуем разные API endpoints для поиска резюме
        search_endpoints = [
            f"{API_BASE}/job/v1/resumes?user_id={user_id}",
            f"{API_BASE}/job/v2/resumes?user_id={user_id}",
            f"{API_BASE}/job/v1/resumes/search?user_id={user_id}",
        ]
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        for endpoint in search_endpoints:
            try:
                time.sleep(RATE_LIMIT_DELAY)  # Rate limiting
                
                response = requests.get(endpoint, headers=headers, timeout=REQUEST_TIMEOUT)
                
                if response.status_code == 429:
                    # Rate limited
                    stats['rate_limited'] += 1
                    time.sleep(2)
                    continue
                    
                if response.status_code == 200:
                    data = response.json()
                    if data and 'results' in data and data['results']:
                        # Нашли резюме
                        resume = data['results'][0]  # Берем первое резюме
                        return {
                            'user_id': user_id,
                            'resume_id': resume.get('id'),
                            'resume_url': f"https://www.avito.ru/resumes/{resume.get('id')}",
                            'title': resume.get('title', ''),
                            'salary': resume.get('salary', {}),
                            'experience': resume.get('experience', {}),
                            'education': resume.get('education', {}),
                            'api_endpoint': endpoint,
                            'found_at': datetime.now().isoformat()
                        }
                elif response.status_code == 404:
                    # Резюме не найдено для этого пользователя
                    continue
                    
            except requests.exceptions.Timeout:
                log(f"⏰ Timeout для user_id: {user_id}")
                continue
            except Exception as e:
                log(f"⚠️ Ошибка запроса для {user_id}: {e}")
                continue
        
        return None
        
    except Exception as e:
        log(f"❌ Общая ошибка для user_id {user_id}: {e}")
        stats['errors'] += 1
        return None


def process_chat_batch(chat_batch: List[Dict], access_token: str, thread_id: int) -> List[Dict[str, Any]]:
    """Обрабатывает батч чатов в одном потоке"""
    results = []
    
    for chat in chat_batch:
        try:
            chat_id = chat.get('chat_id', '')
            user_id = extract_user_id_from_chat(chat_id)
            
            if not user_id:
                continue
                
            # Ищем резюме для пользователя
            resume_data = search_resume_by_user(user_id, access_token)
            
            if resume_data:
                # Добавляем информацию о чате
                resume_data.update({
                    'chat_id': chat_id,
                    'chat_title': chat.get('title', ''),
                    'chat_type': chat.get('type', ''),
                    'last_message': chat.get('last_message', ''),
                    'chat_timestamp': chat.get('timestamp', ''),
                    'thread_id': thread_id
                })
                results.append(resume_data)
                stats['found_resumes'] += 1
                
                if len(results) % 5 == 0:
                    log(f"🧵 Поток {thread_id}: найдено {len(results)} резюме")
            
            stats['processed'] += 1
            
            # Прогресс каждые 50 обработанных чатов
            if stats['processed'] % 50 == 0:
                log(f"📊 Обработано: {stats['processed']} | Найдено резюме: {stats['found_resumes']} | Ошибки: {stats['errors']}")
                
        except Exception as e:
            log(f"❌ Ошибка обработки чата {chat_id}: {e}")
            stats['errors'] += 1
    
    return results


def parse_cli_args(argv: List[str]) -> tuple[Optional[str], int]:
    """Парсит аргументы командной строки"""
    input_file = None
    threads = DEFAULT_THREADS
    
    try:
        if "--input" in argv:
            input_file = argv[argv.index("--input") + 1]
        if "--threads" in argv:
            threads = int(argv[argv.index("--threads") + 1])
    except (IndexError, ValueError):
        pass
    
    return input_file, threads


def find_latest_chat_file() -> Optional[str]:
    """Находит последний файл с результатами чатов"""
    chat_files = list(Path(".").glob("avito_chat_count_*.json"))
    if not chat_files:
        return None
    
    # Сортируем по времени изменения и берем последний
    latest_file = max(chat_files, key=lambda f: f.stat().st_mtime)
    return str(latest_file)


def main() -> None:
    input_file, num_threads = parse_cli_args(sys.argv)
    
    # Определяем входной файл
    if not input_file:
        input_file = find_latest_chat_file()
        if not input_file:
            log("❌ Не найден файл с результатами чатов")
            log("   Используйте: python chat_to_resume_fetcher.py --input avito_chat_count_XXXXXX.json")
            return
        log(f"📁 Используем последний файл: {input_file}")
    
    # Загружаем данные чатов
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            chat_data = json.load(f)
        
        all_chat_ids = chat_data.get('all_chat_ids', [])
        chat_details = chat_data.get('chat_data', [])
        
        log(f"📊 Загружено {len(all_chat_ids)} chat_id и {len(chat_details)} детальных записей")
        
        # Создаем полный список чатов для обработки
        chat_list = []
        
        # Сначала используем все chat_ids
        if all_chat_ids:
            log(f"📋 Используем все {len(all_chat_ids)} chat_id")
            chat_list = [{'chat_id': cid, 'title': '', 'type': 'unknown'} for cid in all_chat_ids]
            
            # Дополняем детальной информацией если есть
            if chat_details:
                details_dict = {item.get('chat_id'): item for item in chat_details}
                for chat in chat_list:
                    chat_id = chat['chat_id']
                    if chat_id in details_dict:
                        chat.update(details_dict[chat_id])
        elif chat_details:
            # Используем только детальные данные если нет списка chat_ids
            chat_list = chat_details
        
        log(f"🎯 Будем обрабатывать {len(chat_list)} чатов в {num_threads} потоков")
        
    except Exception as e:
        log(f"❌ Ошибка загрузки файла {input_file}: {e}")
        return
    
    # Получаем access token
    access_token = get_access_token()
    if not access_token:
        log("❌ Не удалось получить access token. Проверьте CLIENT_ID и CLIENT_SECRET")
        return
    
    # Разбиваем чаты на батчи для потоков
    batch_size = len(chat_list) // num_threads + 1
    chat_batches = [chat_list[i:i + batch_size] for i in range(0, len(chat_list), batch_size)]
    
    log(f"🚀 Запускаем {len(chat_batches)} потоков по ~{batch_size} чатов каждый")
    
    # Запускаем многопоточную обработку
    all_results = []
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        # Отправляем задачи в потоки
        future_to_thread = {
            executor.submit(process_chat_batch, batch, access_token, i+1): i+1 
            for i, batch in enumerate(chat_batches)
        }
        
        # Собираем результаты
        for future in as_completed(future_to_thread):
            thread_id = future_to_thread[future]
            try:
                batch_results = future.result()
                all_results.extend(batch_results)
                log(f"✅ Поток {thread_id} завершен: {len(batch_results)} резюме найдено")
            except Exception as e:
                log(f"❌ Ошибка в потоке {thread_id}: {e}")
    
    end_time = time.time()
    
    # Финальная статистика
    log(f"🏁 Обработка завершена за {end_time - start_time:.1f} секунд")
    log(f"📊 Итого обработано чатов: {stats['processed']}")
    log(f"🎯 Найдено резюме: {stats['found_resumes']}")
    log(f"⚠️ Ошибок: {stats['errors']}")
    log(f"🕐 Rate limit задержек: {stats['rate_limited']}")
    
    if not all_results:
        log("😞 Резюме не найдены")
        return
    
    # Сохраняем результаты
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # JSON файл
    json_file = f"chat_resumes_{timestamp}.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump({
            'timestamp': timestamp,
            'source_file': input_file,
            'parameters': {
                'threads': num_threads,
                'total_chats_processed': stats['processed'],
                'resumes_found': stats['found_resumes']
            },
            'statistics': stats,
            'results': all_results
        }, f, ensure_ascii=False, indent=2)
    
    # Excel файл
    try:
        df = pd.DataFrame(all_results)
        excel_file = f"chat_resumes_{timestamp}.xlsx"
        df.to_excel(excel_file, index=False, engine='openpyxl')
        log(f"📁 Результаты сохранены в {excel_file}")
    except Exception as e:
        log(f"⚠️ Ошибка сохранения Excel: {e}")
    
    log(f"💾 JSON результаты сохранены в {json_file}")
    log(f"🎉 Готово! Найдено {len(all_results)} резюме из {stats['processed']} чатов")


if __name__ == "__main__":
    main()