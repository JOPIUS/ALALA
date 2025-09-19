"""
Simple Proxy Manager
- Reads proxies from `proxies/proxy.txt` in workspace (one per line)
- Supports formats:
  - host:port
  - http://user:pass@host:port
  - socks5://host:port
- Exposes ProxyManager class with:
  - get_session(): returns a configured requests.Session that uses a rotating proxy via a custom request adapter
  - next_proxy(): returns next proxy dict for requests

Graceful fallback when proxy file missing: returns Session without proxies.
"""
from __future__ import annotations
import os
import random
import threading
from typing import List, Optional, Dict
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

PROXY_FILE = os.path.join(os.path.dirname(__file__), "proxy.txt")


class ProxyManager:
    def __init__(self, proxy_file: Optional[str] = None, shuffle: bool = True):
        self.proxy_file = proxy_file or PROXY_FILE
        self._lock = threading.Lock()
        self.proxies: List[str] = []
        self.index = 0
        self._load_proxies()
        if shuffle:
            random.shuffle(self.proxies)

    def _load_proxies(self):
        try:
            with open(self.proxy_file, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f.readlines()]
        except FileNotFoundError:
            # No proxy file inside workspace; leave proxies empty
            self.proxies = []
            return
        cleaned = []
        for l in lines:
            if not l or l.startswith("#"):
                continue
            # skip CSV-like header lines that contain words like IP or PORT
            first_segment = l.split(":")[0]
            if any(c.isalpha() for c in first_segment):
                # header or invalid host, skip
                continue
            cleaned.append(l)
        self.proxies = cleaned

    def has_proxies(self) -> bool:
        return len(self.proxies) > 0

    def next_proxy(self) -> Optional[Dict[str, str]]:
        """Return a proxies dict suitable for requests or None if no proxies configured."""
        if not self.proxies:
            return None
        with self._lock:
            proxy = self.proxies[self.index]
            self.index = (self.index + 1) % len(self.proxies)
        # Build requests proxies mapping for both http and https
        # Accept formats:
        #  - host:port
        #  - http://user:pass@host:port
        #  - host:port:user:pass  -> convert to http://user:pass@host:port
        parts = proxy.split(":")
        if proxy.startswith(("http://", "https://", "socks5://")):
            proxy_url = proxy
        elif len(parts) == 4:
            # host:port:user:pass -> swap to http://user:pass@host:port
            host, port, user, pwd = parts
            proxy_url = f"http://{user}:{pwd}@{host}:{port}"
        else:
            proxy_url = f"http://{proxy}"
        return {"http": proxy_url, "https": proxy_url}

    def get_session(self, timeout: int = 15, retries: int = 2, backoff_factor: float = 0.3) -> requests.Session:
        """Return a requests.Session that can be used for calls. The caller should set proxy per-request using session.proxies = pm.next_proxy()"""
        session = requests.Session()
        retry = Retry(
            total=retries,
            read=retries,
            connect=retries,
            backoff_factor=backoff_factor,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("HEAD", "GET", "PUT", "POST", "DELETE", "OPTIONS"),
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update({
            "User-Agent": "avito-resume-downloader/1.0",
            "Accept": "application/json",
        })
        session.request_timeout = timeout  # convenience attribute
        return session


if __name__ == "__main__":
    pm = ProxyManager()
    print("Proxies loaded:", len(pm.proxies))
    for _ in range(min(5, len(pm.proxies))):
        print(pm.next_proxy())
