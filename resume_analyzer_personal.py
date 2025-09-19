#!/usr/bin/env python3
"""
Анализ купленных резюме используя персональную OAuth2 авторизацию (Authorization Code Flow).

Процесс:
1. Сгенерировать URL авторизации и открыть в браузере.
2. Вставить полученный authorization code в программу.
3. Обменять код на access_token (и refresh_token).
4. Считать CSV с ID (большая выборка, по умолчанию 500).
5. Для каждого ID попытаться получить детали резюме и сообщения.
6. Сохранить результаты в JSON/CSV.

Примечания:
- По вашей заметке, поле "is_purchased" в ответе ненадежно; скрипт будет игнорировать его и работать с ID из вашего файла.
- Redirect URL в настройках приложения должен совпадать с `redirect_uri`.
"""

import requests
import csv
import json
import os
import webbrowser
from urllib.parse import urlencode
from datetime import datetime

# Конфигурация профилей приложений
PROFILES = {
    'personal_app': {
        'name': 'Personal App',
        'client_id': 'Dm4ruLMEr9MFsV72dN95',
        'client_secret': 'f73lNoAJLzuqwoGtVaMnByhQfSlwcyIN_m7wyOeT',
        'redirect_uri': 'http://127.0.0.1:8765/callback'
    },
    'poisk_kandidatov_polati': {
        'name': 'Поиск_Кандидатов_Полати',
        'client_id': 'pEm43bT2JX47aeb8OxNV',
        'client_secret': 'pURVGURY6Mt95xTPxrTHJ_SpzL7sBPNRfTt7qQkw',
        'redirect_uri': 'https://oauth.pstmn.io/v1/callback'
    }
}

# Выберите профиль по умолчанию (ключ из PROFILES). Меняйте при необходимости.
DEFAULT_PROFILE_KEY = 'poisk_kandidatov_polati'

CLIENT_ID = PROFILES[DEFAULT_PROFILE_KEY]['client_id']
CLIENT_SECRET = PROFILES[DEFAULT_PROFILE_KEY]['client_secret']
REDIRECT_URI = PROFILES[DEFAULT_PROFILE_KEY]['redirect_uri']

BASE_URL = "https://api.avito.ru"
CSV_PATH = r"C:\ManekiNeko\AVITO_API\output\already_bought_id.csv"
SAMPLE_SIZE = 500  # выборка из CSV для тестирования (увеличьте при необходимости)


def get_authorization_url(scopes):
    params = {
        'client_id': CLIENT_ID,
        'redirect_uri': REDIRECT_URI,
        'response_type': 'code',
        'scope': ' '.join(scopes)
    }
    return f"https://api.avito.ru/oauth/authorize?{urlencode(params)}"


def exchange_code_for_token(code):
    url = f"{BASE_URL}/token"
    data = {
        'grant_type': 'authorization_code',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code': code,
        'redirect_uri': REDIRECT_URI
    }
    resp = requests.post(url, data=data)
    return resp


def refresh_token(refresh_token):
    url = f"{BASE_URL}/token"
    data = {
        'grant_type': 'refresh_token',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'refresh_token': refresh_token
    }
    resp = requests.post(url, data=data)
    return resp


def read_ids(csv_path, limit=SAMPLE_SIZE):
    ids = []
    if not os.path.exists(csv_path):
        print(f"Файл {csv_path} не найден")
        return ids

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        content = f.read().strip()
        lines = content.split('\n')
        # Если есть заголовки
        if lines and ('id' in lines[0].lower() or 'resume' in lines[0].lower()):
            reader = csv.DictReader(lines)
            for row in reader:
                for k, v in row.items():
                    if k and 'id' in k.lower():
                        try:
                            ids.append(int(v.strip()) )
                        except:
                            pass
                        break
        else:
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                # Если строка может содержать запятые
                if ',' in line:
                    for part in line.split(','):
                        part = part.strip()
                        if part.isdigit():
                            ids.append(int(part))
                elif line.isdigit():
                    ids.append(int(line))

    print(f"Найдено {len(ids)} ID в CSV")
    return ids[:limit]


def get_resume(access_token, resume_id):
    headers = {'Authorization': f'Bearer {access_token}'}
    url = f"{BASE_URL}/job/v1/resumes/{resume_id}"
    r = requests.get(url, headers=headers)
    return r


def try_message_endpoints(access_token, resume_id):
    """Пробуем набор вариантов эндпоинтов для сообщений"""
    headers = {'Authorization': f'Bearer {access_token}'}
    endpoints = [
        f"/messenger/v1/resumes/{resume_id}/chats",
        f"/messenger/v2/resumes/{resume_id}/chats",
        f"/job/v1/resumes/{resume_id}/messages",
        f"/job/v1/resumes/{resume_id}/chat",
        f"/messenger/chats?resume_id={resume_id}",
        f"/messenger/v1/chats?resume_id={resume_id}",
        f"/messenger/v3/accounts/self/chats?resume_id={resume_id}",
        f"/messenger/v3/resumes/{resume_id}/chats",
    ]

    for ep in endpoints:
        url = f"{BASE_URL}{ep}"
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                try:
                    return {'endpoint': ep, 'data': r.json()}
                except:
                    return {'endpoint': ep, 'data': r.text}
            elif r.status_code in (401,403):
                return {'endpoint': ep, 'status': r.status_code, 'error': r.text}
        except Exception as e:
            continue
    return None


def main():
    scopes = [
        'messenger:read',
        'messenger:write',
        'job:cv',
        'job:applications',
        'user:read'
    ]

    print("1) Попытаемся автоматически получить authorization code через локальный redirect (http://127.0.0.1:8765/callback).")
    print("   Если ваш OAuth-приложение не содержит этот redirect URI — скрипт предложит вставить code вручную.")

    auth_url = get_authorization_url(scopes)
    print('\nОткрываю URL авторизации в браузере...')
    print(auth_url)
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    # Попробуем поднять локальный HTTP сервер и поймать редирект с code
    code = None
    try:
        from http.server import HTTPServer, BaseHTTPRequestHandler
        import threading

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                nonlocal code
                # Ожидаем путь /callback?code=...
                from urllib.parse import urlparse, parse_qs
                parsed = urlparse(self.path)
                qs = parse_qs(parsed.query)
                if 'code' in qs:
                    code = qs['code'][0]
                    # Ответ пользователю в браузере
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(b"<html><body><h2>Authorization code received. You can close this page.</h2></body></html>")
                else:
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(b"<html><body><h2>Waiting for authorization...</h2></body></html>")

        server = HTTPServer(('127.0.0.1', 8765), _Handler)

        def _serve():
            # Один запрос и остановка
            server.handle_request()

        t = threading.Thread(target=_serve, daemon=True)
        t.start()

        print('Ожидаю редирект с кодом (макс. 120 сек)...')
        t.join(timeout=120)
    except Exception as e:
        print('Не удалось поднять локальный сервер для catch redirect:', e)

    if not code:
        # Фоллбэк на ручной ввод
        print('\nАвтоматический редирект не сработал или redirect URI не зарегистрирован.')
        print('Если вы используете Postman redirect (https://oauth.pstmn.io/v1/callback), откройте URL вручную и скопируйте параметр code из адресной строки.')
        code = input('Вставьте authorization code из редиректа: ').strip()

    print('Обмениваем код на токен...')
    token_resp = exchange_code_for_token(code)
    try:
        token_resp_json = token_resp.json()
    except:
        print('Ошибка при получении токена:', token_resp.status_code, token_resp.text)
        return

    if 'access_token' not in token_resp_json:
        print('Не удалось получить access_token:', token_resp_json)
        return

    access_token = token_resp_json['access_token']
    refresh = token_resp_json.get('refresh_token')
    print('Токен получен. Начинаем выборку ID из CSV...')

    ids = read_ids(CSV_PATH, SAMPLE_SIZE)
    if not ids:
        print('Нет ID для обработки. Проверьте CSV.')
        return

    results = []
    for i, rid in enumerate(ids, start=1):
        print(f'[{i}/{len(ids)}] Проверка резюме {rid}...')
        r = get_resume(access_token, rid)
        if r.status_code == 200:
            try:
                resume_data = r.json()
            except:
                resume_data = {'raw': r.text}
            # Попробуем получить сообщения
            msg = try_message_endpoints(access_token, rid)
            results.append({'resume_id': rid, 'resume': resume_data, 'messages': msg})
        elif r.status_code == 404:
            results.append({'resume_id': rid, 'error': 'not_found', 'status': 404})
        else:
            try:
                err = r.json()
            except:
                err = r.text
            results.append({'resume_id': rid, 'error': err, 'status': r.status_code})

    # Сохраняем результаты
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_json = f"avito_personal_analysis_{ts}.json"
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f'Готово. Результаты сохранены в {out_json}')


if __name__ == '__main__':
    main()