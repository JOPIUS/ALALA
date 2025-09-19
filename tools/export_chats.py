#!/usr/bin/env python3
"""
Получение всех чатов через Client Credentials (без браузера)
Использует только то, что доступно без Authorization Code
"""

import os
import sys
import json
import requests
import time
from datetime import datetime

def get_client_credentials_token(client_id, client_secret):
    """Получить токен через Client Credentials"""
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
        print(f"✅ Токен получен: {access_token[:20]}...")
        return access_token, token_info
    except Exception as e:
        print(f"❌ Ошибка получения токена: {e}")
        return None, None

def get_user_info(access_token):
    """Получить информацию о пользователе"""
    print("👤 Получение информации о пользователе...")
    
    headers = {'Authorization': f'Bearer {access_token}'}
    
    try:
        response = requests.get("https://api.avito.ru/core/v1/accounts/self", headers=headers, timeout=30)
        if response.status_code == 200:
            user_info = response.json()
            user_id = user_info.get('id')
            print(f"✅ User ID: {user_id}")
            print(f"📧 Email: {user_info.get('email', 'N/A')}")
            print(f"📞 Phone: {user_info.get('phone', 'N/A')}")
            print(f"👤 Name: {user_info.get('name', 'N/A')}")
            return user_id, user_info
        else:
            print(f"❌ Ошибка получения user info: {response.status_code}")
            return None, None
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None, None

def get_all_chats_detailed(access_token, user_id):
    """Получить ВСЕ чаты с полной информацией"""
    print(f"💬 Получение ВСЕХ чатов для user_id {user_id}...")
    
    headers = {'Authorization': f'Bearer {access_token}'}
    
    # Получаем все чаты постранично
    all_chats = []
    offset = 0
    limit = 100
    
    while True:
        print(f"📄 Страница с offset {offset}...")
        
        chats_url = f"https://api.avito.ru/messenger/v2/accounts/{user_id}/chats"
        params = {
            'limit': limit,
            'offset': offset
        }
        
        try:
            response = requests.get(chats_url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                chats = data.get('chats', [])
                
                if not chats:
                    print("📄 Больше чатов нет")
                    break
                
                all_chats.extend(chats)
                print(f"✅ Получено чатов на странице: {len(chats)}, всего: {len(all_chats)}")
                
                # Если получили меньше чем limit, значит это последняя страница
                if len(chats) < limit:
                    break
                
                offset += limit
                time.sleep(0.5)  # Пауза между запросами
                
            else:
                print(f"❌ Ошибка на offset {offset}: {response.status_code}")
                print(f"   Ответ: {response.text[:300]}")
                break
                
        except Exception as e:
            print(f"❌ Исключение на offset {offset}: {e}")
            break
    
    print(f"🎉 Всего получено чатов: {len(all_chats)}")
    return all_chats

def analyze_chats(chats):
    """Проанализировать чаты и извлечь полезную информацию"""
    print("🔍 Анализ чатов...")
    
    analysis = {
        'total_chats': len(chats),
        'chat_types': {},
        'users': {},
        'items': {},
        'last_messages': [],
        'unread_chats': 0,
        'active_chats': 0
    }
    
    for chat in chats:
        # Тип чата
        context = chat.get('context', {})
        chat_type = context.get('type', 'unknown')
        analysis['chat_types'][chat_type] = analysis['chat_types'].get(chat_type, 0) + 1
        
        # Пользователи
        users = chat.get('users', [])
        for user in users:
            user_id = user.get('id')
            user_name = user.get('name', 'Unknown')
            if user_id:
                analysis['users'][str(user_id)] = user_name
        
        # Объявления
        if context.get('type') == 'u2i' and 'value' in context:
            item_info = context['value']
            item_id = item_info.get('id')
            if item_id:
                analysis['items'][str(item_id)] = {
                    'title': item_info.get('title', 'No title'),
                    'url': item_info.get('url', ''),
                    'price': item_info.get('price', 0)
                }
        
        # Последние сообщения
        last_msg = chat.get('last_message')
        if last_msg:
            analysis['last_messages'].append({
                'chat_id': chat.get('id'),
                'author_id': last_msg.get('author_id'),
                'direction': last_msg.get('direction'),
                'type': last_msg.get('type'),
                'created': last_msg.get('created'),
                'content': last_msg.get('content', {})
            })
        
        # Непрочитанные
        if chat.get('unread_count', 0) > 0:
            analysis['unread_chats'] += 1
        
        # Активные (обновлялись за последние 30 дней)
        updated = chat.get('updated', 0)
        if updated > (time.time() - 30 * 24 * 3600):
            analysis['active_chats'] += 1
    
    return analysis

def save_complete_data(token_info, user_info, chats, analysis):
    """Сохранить все данные в детальный JSON"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    complete_data = {
        'export_info': {
            'timestamp': datetime.now().isoformat(),
            'method': 'client_credentials',
            'total_chats': len(chats)
        },
        'token_info': {
            'expires_in': token_info.get('expires_in'),
            'token_type': token_info.get('token_type'),
            'scope': token_info.get('scope', 'client_credentials')
        },
        'user_info': user_info,
        'analysis': analysis,
        'chats': chats
    }
    
    # Полный экспорт
    filename_full = f"avito_chats_complete_{timestamp}.json"
    with open(filename_full, 'w', encoding='utf-8') as f:
        json.dump(complete_data, f, ensure_ascii=False, indent=2)
    
    # Краткий отчёт
    summary = {
        'export_info': complete_data['export_info'],
        'user_info': user_info,
        'analysis': analysis,
        'sample_chats': chats[:5],  # Первые 5 чатов для примера
        'recent_messages': sorted(analysis['last_messages'], 
                                key=lambda x: x.get('created', 0), reverse=True)[:20]
    }
    
    filename_summary = f"avito_chats_summary_{timestamp}.json"
    with open(filename_summary, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    return filename_full, filename_summary

def export_all_chats():
    """Экспорт всех чатов через Client Credentials"""
    print("🚀 Полный экспорт чатов Avito (Client Credentials)")
    print("=" * 60)
    
    # Получить креды
    client_id = os.getenv('AVITO_CLIENT_ID')
    client_secret = os.getenv('AVITO_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        print("❌ Установите переменные окружения:")
        print("$env:AVITO_CLIENT_ID = 'ваш_client_id'")
        print("$env:AVITO_CLIENT_SECRET = 'ваш_client_secret'")
        return None
    
    # 1. Получить токен
    access_token, token_info = get_client_credentials_token(client_id, client_secret)
    if not access_token:
        return None
    
    # 2. Получить информацию о пользователе
    user_id, user_info = get_user_info(access_token)
    if not user_id:
        return None
    
    # 3. Получить все чаты
    all_chats = get_all_chats_detailed(access_token, user_id)
    if not all_chats:
        return None
    
    # 4. Проанализировать чаты
    analysis = analyze_chats(all_chats)
    
    # 5. Сохранить все данные
    filename_full, filename_summary = save_complete_data(token_info, user_info, all_chats, analysis)
    
    # 6. Показать результаты
    print(f"\n🎉 ЭКСПОРТ ЗАВЕРШЁН!")
    print(f"=" * 40)
    print(f"👤 Пользователь: {user_info.get('name')} (ID: {user_id})")
    print(f"📧 Email: {user_info.get('email')}")
    print(f"💬 Всего чатов: {analysis['total_chats']}")
    print(f"📨 Непрочитанных: {analysis['unread_chats']}")
    print(f"🔥 Активных (30 дней): {analysis['active_chats']}")
    
    print(f"\n📊 Типы чатов:")
    for chat_type, count in analysis['chat_types'].items():
        type_name = {'u2i': 'По объявлениям', 'u2u': 'Между пользователями'}.get(chat_type, chat_type)
        print(f"   {type_name}: {count}")
    
    print(f"\n👥 Уникальных пользователей: {len(analysis['users'])}")
    print(f"🏷️ Уникальных объявлений: {len(analysis['items'])}")
    
    print(f"\n💾 Файлы:")
    print(f"   📄 Полный экспорт: {filename_full}")
    print(f"   📋 Краткий отчёт: {filename_summary}")
    
    # Показать последние сообщения
    if analysis['last_messages']:
        print(f"\n📨 Последние сообщения:")
        recent = sorted(analysis['last_messages'], key=lambda x: x.get('created', 0), reverse=True)
        for i, msg in enumerate(recent[:5], 1):
            created = datetime.fromtimestamp(msg.get('created', 0)).strftime('%d.%m.%Y %H:%M')
            direction = {'in': '⬅️', 'out': '➡️'}.get(msg.get('direction'), '❓')
            msg_type = msg.get('type', 'unknown')
            print(f"   {i}. {created} {direction} {msg_type}")
    
    return {
        'user_info': user_info,
        'analysis': analysis,
        'files': {
            'full': filename_full,
            'summary': filename_summary
        }
    }

if __name__ == "__main__":
    export_all_chats()