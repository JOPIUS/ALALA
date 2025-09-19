"""Obtain a personal Avito access token using Authorization Code flow (loopback redirect).

This script requires the user to provide:
- personal `client_id` and `client_secret` (from a registered personal application)
- scopes (if required by Avito)

It opens the system browser to let the user authenticate and accept scopes. It then listens on localhost for
the redirect with the authorization code, exchanges the code for tokens, and saves them to `secrets/personal_token.json`.

Security note: keep `secrets/personal_token.json` safe; it contains a `refresh_token`.

Usage:
    .venv\\Scripts\\python.exe tools\\get_personal_token.py --client-id <ID> --client-secret <SECRET> --redirect-port 8765

After obtaining tokens, set environment variable `AVITO_PERSONAL_TOKEN` for other scripts.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import threading
import socket
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs, urlencode

import requests
import secrets

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Defaults for Avito — can be overridden via CLI args
# Swagger files reference https://avito.ru/oauth as authorization URL and https://api.avito.ru/token as token endpoint.
AUTH_HOSTS = ['https://avito.ru', 'https://accounts.avito.ru']
# Try the simple /oauth path first (matches Swagger), then /oauth/authorize
AUTH_PATHS = ['/oauth', '/oauth/authorize']
TOKEN_URL_DEFAULT = 'https://api.avito.ru/token'

SECRETS_PATH = os.path.join(os.getcwd(), 'secrets', 'personal_token.json')


class _CodeHandler(BaseHTTPRequestHandler):
    server_version = 'LocalCallback/1.0'

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        self.server.auth_code = qs.get('code', [None])[0]
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b'<html><body><h2>Authorization received. You may close this window.</h2></body></html>')

    def log_message(self, format, *args):
        # suppress default logging to stderr
        return


def _build_auth_urls(client_id: str, redirect_uri: str, scope: str | None = None,
                     auth_hosts: list | None = None, auth_paths: list | None = None,
                     extra_params: dict | None = None) -> list:
    """Build authorization URLs. Hosts/paths can be overridden for non-standard setups."""
    hosts = auth_hosts or AUTH_HOSTS
    paths = auth_paths or AUTH_PATHS
    params = {
        'response_type': 'code',
        'client_id': client_id,
        'redirect_uri': redirect_uri,
    }
    if scope:
        params['scope'] = scope
    if extra_params:
        for k, v in extra_params.items():
            if v is not None:
                params[k] = v
    q = urlencode(params, safe='')
    urls = []
    for host in hosts:
        for path in paths:
            urls.append(f"{host}{path}?{q}")
    return urls


def _parse_ports(s: str) -> list:
    """Parse a string like '8765,9876,8000-8005' into a list of ints."""
    parts = [p.strip() for p in s.split(',') if p.strip()]
    ports: list[int] = []
    for p in parts:
        if '-' in p:
            a, b = p.split('-', 1)
            try:
                a_i = int(a); b_i = int(b)
                ports.extend(list(range(a_i, b_i + 1)))
            except Exception:
                continue
        else:
            try:
                ports.append(int(p))
            except Exception:
                continue
    return ports


def _is_port_free(host: str, port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.close()
        return True
    except OSError:
        try:
            s.close()
        except Exception:
            pass
        return False


def obtain_code(client_id: str, redirect_uri: str, redirect_port: int | None = None,
                scope: str | None = None, auth_hosts: list | None = None, auth_paths: list | None = None,
                no_browser: bool = False) -> str | None:
    """Obtain authorization code.

    If `redirect_uri` is a loopback (http://127.0.0.1...), start a local HTTP server and capture the code.
    Otherwise open browser and prompt user to paste the final redirect URL (or just the code).
    """
    urls = _build_auth_urls(client_id, redirect_uri, scope, auth_hosts=auth_hosts, auth_paths=auth_paths)
    logger.info('Primary auth URL: %s', urls[0])
    if not no_browser:
        logger.info('Opening browser to the first auth URL. If it fails, try the others printed below.')
        webbrowser.open(urls[0])
    else:
        logger.info('No-browser mode: do not open a browser. Please open the primary or any alternative URL manually.')

    # print alternatives
    for u in urls[1:]:
        logger.info('Alternative auth URL: %s', u)

    # If redirect is loopback — run local server
    if redirect_uri.startswith('http://127.0.0.1') or redirect_uri.startswith('http://localhost'):
        host = '127.0.0.1' if '127.0.0.1' in redirect_uri else 'localhost'
        port = redirect_port or 8765
        try:
            server = HTTPServer((host, port), _CodeHandler)
        except OSError as exc:
            logger.warning('Cannot bind to %s:%d: %s', host, port, exc)
            return None
        logger.info('Listening on %s:%d for redirect; expecting redirect URI: %s', host, port, redirect_uri)
        server.auth_code = None

        def serve():
            server.handle_request()

        t = threading.Thread(target=serve, daemon=True)
        t.start()
        t.join(timeout=300)
        return server.auth_code

    # Otherwise prompt user to paste redirected URL or code
    print('\nЕсли вы были перенаправлены на ваш Redirect URL (внешний), пожалуйста, скопируйте весь URL из адресной строки и вставьте его сюда.')
    redirected = input('Paste full redirect URL (or just the `code` param): ').strip()
    if not redirected:
        return None
    # if user pasted only code
    if not redirected.lower().startswith('http'):
        return redirected
    parsed = urlparse(redirected)
    qs = parse_qs(parsed.query)
    return qs.get('code', [None])[0]


def exchange_code(client_id: str, client_secret: str, code: str, redirect_uri: str, token_url: str = TOKEN_URL_DEFAULT, debug: bool = False, debug_file: str | None = None) -> dict:
    """Exchange authorization code for tokens. Raises on HTTP errors.

    If debug is True, save full HTTP response (status, headers, body, json if parseable)
    into `debug_file` (or auto-generated path under `secrets/`).
    """
    url = token_url
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
        'client_id': client_id,
        'client_secret': client_secret,
    }
    r = None
    try:
        r = requests.post(url, data=data, timeout=15)
        # capture response details for debugging even before raise
        resp_info = {
            'url': url,
            'status_code': getattr(r, 'status_code', None),
            'headers': dict(getattr(r, 'headers', {})),
            'text': getattr(r, 'text', None),
        }
        try:
            resp_info['json'] = r.json()
        except Exception:
            resp_info['json'] = None

        if debug:
            # prepare debug path
            ts = __import__('time').strftime('%Y%m%d_%H%M%S')
            if not debug_file:
                debug_file = os.path.join(os.getcwd(), 'secrets', f'token_exchange_debug_{ts}.json')
            os.makedirs(os.path.dirname(debug_file), exist_ok=True)
            with open(debug_file, 'w', encoding='utf-8') as df:
                json.dump(resp_info, df, ensure_ascii=False, indent=2)
            logger.info('Wrote token exchange debug to %s', debug_file)

        r.raise_for_status()
        # attempt to parse JSON; fall back to raw text in error cases
        return r.json()
    except requests.HTTPError as exc:
        # provide the response body to aid debugging
        txt = getattr(r, 'text', '<no body>') if r is not None else '<no response>'
        logger.error('Token exchange failed: %s %s', exc, txt)
        raise
    except ValueError:
        logger.error('Token endpoint did not return JSON, raw response: %s', r.text if r is not None else '<no response>')
        raise


def save_tokens(tokens: dict):
    os.makedirs(os.path.dirname(SECRETS_PATH), exist_ok=True)
    with open(SECRETS_PATH, 'w', encoding='utf-8') as f:
        json.dump(tokens, f, ensure_ascii=False, indent=2)
    logger.info('Saved tokens to %s', SECRETS_PATH)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--client-id', required=True)
    p.add_argument('--client-secret', required=True)
    p.add_argument('--redirect-uri', required=True, help='The redirect URI registered in the Avito app (e.g. https://sdng.tech/avito/oauth_callback.php or http://127.0.0.1:8765/callback)')
    p.add_argument('--redirect-port', type=int, default=8765)
    p.add_argument('--scope', default=None)
    p.add_argument('--auth-host', action='append', help='Authorization host(s) to try (can be given multiple times).', default=None)
    p.add_argument('--auth-path', action='append', help='Authorization path(s) to try (can be given multiple times).', default=None)
    p.add_argument('--token-url', help='Token exchange URL (default: %s)' % TOKEN_URL_DEFAULT, default=TOKEN_URL_DEFAULT)
    p.add_argument('--no-browser', action='store_true', help='Do not open the system browser automatically; print URLs and prompt for pasted redirect URL.')
    p.add_argument('--try-ports', help='Comma-separated ports or ranges to try as loopback ports (e.g. "8765,9876,9000-9005").', default=None)
    p.add_argument('--try-hosts', help='Comma-separated alternative auth hosts to try (e.g. "https://auth.avito.ru,https://oauth.avito.ru").', default=None)
    p.add_argument('--try-paths', help='Comma-separated alternative auth paths to try (e.g. "/oauth,/oauth/authorize").', default=None)
    p.add_argument('--print-only', action='store_true', help='Just print an authorization URL (with state) and exit; do not start local server or exchange tokens.')
    p.add_argument('--open-url', action='store_true', help='Open generated authorization URL in system browser (only used with --print-only).')
    p.add_argument('--debug', action='store_true', help='Save full HTTP responses from token endpoint to a debug file under secrets/*.')
    p.add_argument('--debug-file', help='Path to debug JSON file to write token exchange details (default: secrets/token_exchange_debug_<ts>.json).', default=None)
    args = p.parse_args()
    # Build lists of alternatives
    alt_hosts = args.auth_host or []
    if args.try_hosts:
        alt_hosts.extend([h.strip() for h in args.try_hosts.split(',') if h.strip()])
    alt_paths = args.auth_path or []
    if args.try_paths:
        alt_paths.extend([p_.strip() for p_ in args.try_paths.split(',') if p_.strip()])

    ports = [args.redirect_port]
    if args.try_ports:
        parsed = _parse_ports(args.try_ports)
        ports = parsed + ports

    # Quick print-only mode: generate a fresh auth URL with a random state and exit
    if args.print_only:
        st = secrets.token_urlsafe(16)
        extra = {'state': st}
        urls = _build_auth_urls(args.client_id, args.redirect_uri, args.scope, auth_hosts=alt_hosts or None, auth_paths=alt_paths or None, extra_params=extra)
        print('Authorization URLs:')
        for u in urls:
            print(u)
        if args.open_url:
            webbrowser.open(urls[0])
        print('\nState value (save it to verify after redirect):', st)
        return

    code = None
    # Try combinations of ports/hosts/paths until auth code obtained
    for port in ports:
        for host_override in (alt_hosts or None,):
            for path_override in (alt_paths or None,):
                # construct redirect_uri with current port
                base_redirect = args.redirect_uri
                # replace port in redirect uri if present
                if '127.0.0.1' in base_redirect or 'localhost' in base_redirect:
                    # naive replacement of port
                    import re
                    base_redirect = re.sub(r':\d+', f':{port}', base_redirect)
                logger.info('Trying redirect %s with hosts=%s paths=%s', base_redirect, host_override, path_override)
                code = obtain_code(args.client_id, base_redirect, port, args.scope, auth_hosts=host_override or None, auth_paths=path_override or None, no_browser=args.no_browser)
                if code:
                    break
            if code:
                break
        if code:
            break
    if not code:
        logger.error('No authorization code obtained')
        return
    logger.info('Auth code obtained, exchanging...')
    tokens = exchange_code(args.client_id, args.client_secret, code, args.redirect_uri, token_url=args.token_url, debug=args.debug, debug_file=args.debug_file)
    save_tokens(tokens)
    logger.info('Done. Set AVITO_PERSONAL_TOKEN to the `access_token` or use `refresh_token` to refresh later.')


if __name__ == '__main__':
    main()
