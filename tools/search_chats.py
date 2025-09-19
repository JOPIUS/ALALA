#!/usr/bin/env python3
"""
Поиск и фильтрация в экспортированных чатах Avito
"""

import json
import os
import sys
from datetime import datetime, timedelta
import re

def load_latest_export():
    """Загрузить последний экспорт чатов"""
    # Найти последний файл summary
    summary_files = [f for f in os.listdir('.') if f.startswith('avito_chats_summary_') and f.endswith('.json')]
    
    if not summary_files:
        print("❌ Не найдены файлы экспорта чатов")
        return None
    
    latest_file = sorted(summary_files)[-1]
    print(f"📄 Загружаю: {latest_file}")
    
    try:
        with open(latest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"✅ Загружено: {data['analysis']['total_chats']} чатов")
        return data
    except Exception as e:
        print(f"❌ Ошибка загрузки: {e}")
        return None

def search_users(data, query):
    """Поиск пользователей по имени"""
    print(f"🔍 Поиск пользователей: '{query}'")
    
    users = data['analysis']['users']
    found = []
    
    for user_id, name in users.items():
        if query.lower() in name.lower():
            found.append({'id': user_id, 'name': name})
    
    if found:
        print(f"✅ Найдено пользователей: {len(found)}")
        for user in found[:10]:  # Показать первых 10
            print(f"   👤 {user['name']} (ID: {user['id']})")
        if len(found) > 10:
            print(f"   ... и ещё {len(found) - 10}")
    else:
        print("❌ Пользователи не найдены")
    
    return found

def filter_recent_chats(data, days=7):
    """Фильтр чатов за последние N дней"""
    print(f"📅 Активные чаты за последние {days} дней...")
    
    cutoff_time = datetime.now() - timedelta(days=days)
    cutoff_timestamp = cutoff_time.timestamp()
    
    recent_messages = []
    for msg in data['analysis']['last_messages']:
        if msg.get('created', 0) > cutoff_timestamp:
            recent_messages.append(msg)
    
    # Группировать по чатам
    recent_chats = {}
    for msg in recent_messages:
        chat_id = msg['chat_id']
        if chat_id not in recent_chats:
            recent_chats[chat_id] = []
        recent_chats[chat_id].append(msg)
    
    print(f"✅ Активных чатов: {len(recent_chats)}")
    
    # Показать топ-10 самых активных
    sorted_chats = sorted(recent_chats.items(), 
                         key=lambda x: max(msg.get('created', 0) for msg in x[1]), 
                         reverse=True)
    
    print(f"🔥 Топ-10 самых недавних:")
    for i, (chat_id, messages) in enumerate(sorted_chats[:10], 1):
        last_msg = max(messages, key=lambda x: x.get('created', 0))
        last_time = datetime.fromtimestamp(last_msg.get('created', 0))
        direction = {'in': '⬅️', 'out': '➡️'}.get(last_msg.get('direction'), '❓')
        print(f"   {i}. {last_time.strftime('%d.%m %H:%M')} {direction} {chat_id[:20]}...")
    
    return recent_chats

def search_by_message_content(data, query):
    """Поиск по содержимому последних сообщений"""
    print(f"💬 Поиск в сообщениях: '{query}'")
    
    found_messages = []
    for msg in data['analysis']['last_messages']:
        content = msg.get('content', {})
        text = content.get('text', '')
        
        if query.lower() in text.lower():
            found_messages.append(msg)
    
    if found_messages:
        print(f"✅ Найдено сообщений: {len(found_messages)}")
        sorted_msgs = sorted(found_messages, key=lambda x: x.get('created', 0), reverse=True)
        
        for i, msg in enumerate(sorted_msgs[:5], 1):
            created = datetime.fromtimestamp(msg.get('created', 0))
            direction = {'in': '⬅️', 'out': '➡️'}.get(msg.get('direction'), '❓')
            text = msg.get('content', {}).get('text', '')[:50]
            print(f"   {i}. {created.strftime('%d.%m %H:%M')} {direction} {text}...")
    else:
        print("❌ Сообщения не найдены")
    
    return found_messages

def show_statistics(data):
    """Показать детальную статистику"""
    analysis = data['analysis']
    
    print("📊 СТАТИСТИКА ЧАТОВ")
    print("=" * 40)
    print(f"💬 Всего чатов: {analysis['total_chats']}")
    print(f"📨 Непрочитанных: {analysis['unread_chats']}")
    print(f"🔥 Активных (30 дней): {analysis['active_chats']}")
    print(f"👥 Уникальных пользователей: {len(analysis['users'])}")
    
    # Статистика по типам сообщений
    msg_types = {}
    directions = {'in': 0, 'out': 0}
    
    for msg in analysis['last_messages']:
        msg_type = msg.get('type', 'unknown')
        msg_types[msg_type] = msg_types.get(msg_type, 0) + 1
        
        direction = msg.get('direction')
        if direction in directions:
            directions[direction] += 1
    
    print(f"\n📨 Типы последних сообщений:")
    for msg_type, count in sorted(msg_types.items(), key=lambda x: x[1], reverse=True):
        print(f"   {msg_type}: {count}")
    
    print(f"\n↔️ Направления:")
    print(f"   ⬅️ Входящие: {directions['in']}")
    print(f"   ➡️ Исходящие: {directions['out']}")
    
    # Активность по дням
    recent_days = {}
    now = datetime.now()
    
    for msg in analysis['last_messages']:
        created = datetime.fromtimestamp(msg.get('created', 0))
        days_ago = (now - created).days
        
        if days_ago <= 30:
            recent_days[days_ago] = recent_days.get(days_ago, 0) + 1
    
    if recent_days:
        print(f"\n📅 Активность за последние дни:")
        for day in sorted(recent_days.keys())[:7]:
            count = recent_days[day]
            if day == 0:
                print(f"   Сегодня: {count}")
            elif day == 1:
                print(f"   Вчера: {count}")
            else:
                print(f"   {day} дней назад: {count}")

def interactive_search():
    """Интерактивный поиск"""
    data = load_latest_export()
    if not data:
        return
    
    print(f"\n🔍 ИНТЕРАКТИВНЫЙ ПОИСК ЧАТОВ")
    print("=" * 40)
    print("Команды:")
    print("  stats - показать статистику")
    print("  user <имя> - поиск пользователей")
    print("  recent <дни> - активные чаты за N дней")
    print("  search <текст> - поиск в сообщениях")
    print("  exit - выход")
    print()
    
    while True:
        try:
            cmd = input("🔍 Введите команду: ").strip()
            
            if cmd.lower() in ['exit', 'quit', 'выход']:
                break
            elif cmd.lower() == 'stats':
                show_statistics(data)
            elif cmd.startswith('user '):
                query = cmd[5:].strip()
                search_users(data, query)
            elif cmd.startswith('recent '):
                try:
                    days = int(cmd[7:].strip())
                    filter_recent_chats(data, days)
                except ValueError:
                    print("❌ Укажите количество дней числом")
            elif cmd.startswith('search '):
                query = cmd[7:].strip()
                search_by_message_content(data, query)
            else:
                print("❌ Неизвестная команда")
                
        except KeyboardInterrupt:
            print("\n👋 До свидания!")
            break
        except Exception as e:
            print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Командная строка
        cmd = sys.argv[1].lower()
        data = load_latest_export()
        if not data:
            sys.exit(1)
            
        if cmd == 'stats':
            show_statistics(data)
        elif cmd == 'users' and len(sys.argv) > 2:
            search_users(data, ' '.join(sys.argv[2:]))
        elif cmd == 'recent' and len(sys.argv) > 2:
            days = int(sys.argv[2])
            filter_recent_chats(data, days)
        elif cmd == 'search' and len(sys.argv) > 2:
            search_by_message_content(data, ' '.join(sys.argv[2:]))
        else:
            print("Использование:")
            print("  python search_chats.py stats")
            print("  python search_chats.py users <имя>")
            print("  python search_chats.py recent <дни>")
            print("  python search_chats.py search <текст>")
    else:
        # Интерактивный режим
        interactive_search()