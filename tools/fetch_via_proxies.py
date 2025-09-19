"""Simple fetcher that attempts to download a list of URLs using proxies from `proxies.ProxyManager`.

Notes:
- It will detect and skip `blob:` URLs because those are browser-internal object URLs and cannot be retrieved via HTTP.
- Useful for testing access to public docs behind network blocks by rotating through `proxies/proxy.txt`.

Usage:
  .venv\Scripts\python.exe tools/fetch_via_proxies.py urls.txt

Where `urls.txt` is a newline-separated list of URLs.
"""
from __future__ import annotations
import sys
import os
import time
from urllib.parse import urlparse

import requests

from proxies.proxy_manager import ProxyManager


def fetch(url: str, pm: ProxyManager, out_dir: str = 'downloads'):
    parsed = urlparse(url)
    if parsed.scheme == 'blob':
        print(f"SKIP blob URL: {url}")
        return None
    session = pm.get_session()
    for attempt in range(5):
        p = pm.next_proxy() if pm.has_proxies() else None
        if p:
            session.proxies = p
            print('Using proxy:', p)
        try:
            r = session.get(url, timeout=getattr(session, 'request_timeout', 15))
            r.raise_for_status()
            os.makedirs(out_dir, exist_ok=True)
            fname = os.path.join(out_dir, os.path.basename(parsed.path) or 'download')
            with open(fname, 'wb') as f:
                f.write(r.content)
            print('Saved', url, '->', fname)
            return fname
        except Exception as e:
            print('Attempt', attempt + 1, 'failed for', url, 'via', p, '->', e)
            time.sleep(1 + attempt)
    print('Failed to fetch', url)
    return None


def main():
    if len(sys.argv) < 2:
        print('Usage: fetch_via_proxies.py urls.txt')
        sys.exit(1)
    urls_file = sys.argv[1]
    if not os.path.exists(urls_file):
        print('File not found', urls_file)
        sys.exit(1)
    pm = ProxyManager()
    with open(urls_file, 'r', encoding='utf-8') as f:
        urls = [l.strip() for l in f if l.strip()]
    for u in urls:
        fetch(u, pm)

if __name__ == '__main__':
    main()
