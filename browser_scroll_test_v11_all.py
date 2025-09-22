# -*- coding: utf-8 -*-
"""
Тестовый скрипт: скроллер из v11 для загрузки всех купленных резюме на странице Avito.

Что делает:
- Открывает страницу `https://www.avito.ru/profile/paid-cvs`
- Использует робастный скроллер из v11 для догрузки ВСЕХ карточек
- Извлекает базовые данные из карточек (имя, город, даты, ссылки)
- Сохраняет результат в JSON `browser_test_v11_all_YYYYMMDD_HHMMSS.json`

Зависимости: playwright
  pip install playwright
  python -m playwright install chromium
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright, Error as PwError
import time, json, sys


# ========== Конфиг ==========
USER_DATA_DIR = Path("./avito_browser_profile").resolve()
TARGET_URL_DEFAULT = "https://www.avito.ru/profile/paid-cvs"

NAV_TIMEOUT = 60_000
MAX_TOTAL_SCROLL_SEC = 420
QUIET_MS = 2000
STABLE_GROWTH_ROUNDS = 5
MAX_WHEEL_STEPS = 480
WHEEL_DELAY_SEC = 0.20
WAIT_RESP_TIMEOUT_MS = 6000
NETWORK_IDLE_GRACE = 2


def log(msg: str) -> None:
    print(f"🕐 [{datetime.now().strftime('%H:%M:%S')}] {msg}")


# ========== JS/скроллер из v11 ==========
ROBUST_SCROLL_LIMIT_JS = rf"""
  async (need) => {{
    const deadline = Date.now() + {MAX_TOTAL_SCROLL_SEC} * 1000;
    const quietMs  = {QUIET_MS};
    document.documentElement.style.scrollBehavior = 'auto';
    const sleep = (ms) => new Promise(r => setTimeout(r, ms));
    const norm = s => (s||'').replace(/\s+/g,' ').trim();
    const listSelector = '[data-marker="cv-snippet"]';

    let lastMutation = Date.now();
    const mo = new MutationObserver(() => {{ lastMutation = Date.now(); }});
    mo.observe(document.body, {{childList:true, subtree:true}});

    async function clickMore() {{
      const reMore = /(показат[ьъ]\s*ещ[её]|показать больше|ещё|загрузить ещё)/i;
      const btns = Array.from(document.querySelectorAll('button,a')).filter(b => reMore.test(norm(b.textContent)));
      for (const b of btns) {{ if (!b.disabled && !b.getAttribute('aria-disabled')) {{ b.click(); await sleep(350); }} }}
    }}

    let lastCount = 0, stableRounds = 0;
    const cards = () => Array.from(document.querySelectorAll(listSelector));

    while (Date.now() < deadline) {{
      window.scrollTo(0, document.body.scrollHeight);
      await sleep(450);
      await clickMore();

      window.scrollBy(0, -200); await sleep(150);
      window.scrollTo(0, document.body.scrollHeight); await sleep(450);

      const curCount = cards().length;
      const quiet = (Date.now() - lastMutation) > quietMs;
      if (curCount <= lastCount && quiet) stableRounds++; else {{ stableRounds=0; lastCount=curCount; }}
      if (need && curCount >= need) break;
      if (stableRounds >= {STABLE_GROWTH_ROUNDS}) break;
    }}

    let before = cards().length;
    for (let i = 0; i < cards().length && Date.now() < deadline; i++) {{
      try {{ cards()[i].scrollIntoView({{block:'center'}}); }} catch(e) {{}}
      await sleep(140);
      await clickMore();
      window.scrollBy(0, 120); await sleep(80); window.scrollBy(0, -120);
      await sleep(120);
      const cur = cards().length;
      if (need && cur >= need) break;
      if (cur > before) {{ before = cur; i = Math.max(0, i-3); }}
    }}

    for (let k=0;k<10;k++) {{
      window.scrollTo(0, document.body.scrollHeight); await sleep(400); await clickMore();
      if (need && cards().length >= need) break;
    }}

    mo.disconnect();
    const total = cards().length;
    return need ? Math.min(total, need) : total;
  }}
"""

COUNT_CARDS_JS = '() => document.querySelectorAll(\'[data-marker="cv-snippet"]\').length'

EXTRACT_JS = r"""
  () => {
    const norm = s => (s||'').replace(/\s+/g,' ').trim();
    const q = (root, sel) => root.querySelector(sel);

    const getDateText = (card, preferSel, labelRx) => {
      for (const sel of preferSel) {
        const el = sel ? card.querySelector(sel) : null;
        const txt = norm(el?.textContent);
        if (txt) return txt;
      }
      const full = norm(card.textContent || '');
      const m = full.match(labelRx);
      return m ? norm(m[0]) : '';
    };

    const out = [], seen = new Set();
    const cards = Array.from(document.querySelectorAll('[data-marker="cv-snippet"]'));

    for (const card of cards) {
      const linkEl = card.querySelector('a[href]');
      const link = linkEl ? new URL(linkEl.getAttribute('href'), location.origin).href : '';
      const rid  = (link.match(/\/(\d+)(?:\?|$)/)||[])[1] || '';

      const purchasedRaw = getDateText(
        card,
        ['[data-marker="cv-snippet/date/item-bought"]', '[data-marker*="date"]'],
        /(Куплено\s+(?:сегодня|вчера|\d{1,2}\s+[А-Яа-яЁё\.]+(?:\s+\d{4})?\s+в\s+\d{1,2}:\d{2}))/i
      );
      const updatedRaw = getDateText(
        card,
        ['[data-marker="cv-snippet/date/item-changed"]', '[data-marker*="date"]'],
        /((?:Обновлено|Удалено)\s+(?:сегодня|вчера|\d{1,2}\s+[А-Яа-яЁё\.]+(?:\s+\d{4})?\s+в\s+\d{1,2}:\d{2}))/i
      );

      const fullText = norm(card.textContent || '');
      const jobSearchStatus = fullText.match(/(активно\s+ищ[аюеы]|ищ[аюеы]\s+работу|активен|готов\s+к\s+работе|рассматриваю\s+предложения)/i)?.[0] || '';
      const readyToStart    = fullText.match(/(готов\s+(?:выйти|приступить|начать)?\s*(?:завтра|сегодня|немедленно|сразу)|могу\s+приступить|начн[уы]|готов\s+(?:завтра|сегодня|сразу))/i)?.[0] || '';

      const rec = {
        candidate_name_web: norm(q(card, '[data-marker="cv-snippet/title"]').textContent),
        city_web:           norm(q(card, '[data-marker="cv-snippet/address"]').textContent),
        link: link, resume_id: rid,
        purchased_at_web: purchasedRaw,
        updated_at_web:   updatedRaw,
        photo_url_web:     q(card, 'img[src]')?.src || '',
        job_search_status_web: jobSearchStatus,
        ready_to_start_web: readyToStart
      };

      const key = rec.resume_id || rec.link || rec.candidate_name_web;
      if (key && !seen.has(key)) { seen.add(key); out.push(rec); }
    }
    return out;
  }
"""


def robust_scroll(page, need_count: int | None = None) -> int:
    try:
        count1 = page.evaluate(ROBUST_SCROLL_LIMIT_JS, need_count)
    except Exception:
        count1 = 0

    last_h, still = 0, 0
    for _ in range(MAX_WHEEL_STEPS):
        try:
            page.mouse.wheel(0, 1600)
        except Exception:
            pass
        time.sleep(WHEEL_DELAY_SEC)
        try:
            h = page.evaluate("Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)")
        except Exception:
            h = last_h
        if h <= last_h:
            still += 1
            if still >= 6:
                break
        else:
            still = 0
            last_h = h
        if need_count is not None:
            try:
                cur = int(page.evaluate(COUNT_CARDS_JS))
                if cur >= int(need_count):
                    break
            except Exception:
                pass

    quiet = 0
    while quiet < NETWORK_IDLE_GRACE:
        try:
            page.wait_for_response(
                lambda r: ("avito.ru" in r.url) and r.status == 200 and (getattr(r.request, "resource_type", None) in ("xhr","fetch")),
                timeout=WAIT_RESP_TIMEOUT_MS
            )
            quiet = 0
        except Exception:
            quiet += 1

    try:
        count2 = int(page.evaluate(COUNT_CARDS_JS))
    except Exception:
        count2 = count1
    return min(count2, need_count) if need_count else max(count1, count2)


def parse_cli_args(argv: list[str]) -> tuple[str, int | None, bool]:
    """Возвращает (url, limit, headless)"""
    url = TARGET_URL_DEFAULT
    limit: int | None = None
    headless = False
    try:
        if "--url" in argv:
            url = argv[argv.index("--url") + 1]
        if "--limit" in argv:
            lv = int(argv[argv.index("--limit") + 1])
            limit = lv if lv > 0 else None
        if "--headless" in argv:
            headless = True
    except Exception:
        pass
    return url, limit, headless


def main() -> None:
    url, limit, headless = parse_cli_args(sys.argv)

    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    log(f"Стартуем тест v11-скроллера. URL={url}, лимит={limit or 'все'}, headless={headless}")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=headless,
            viewport=None,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context.set_default_timeout(NAV_TIMEOUT)
        context.set_default_navigation_timeout(NAV_TIMEOUT)
        page = context.new_page()

        try:
            page.goto("https://www.avito.ru/", wait_until="domcontentloaded")
        except PwError:
            pass

        input("\n🔑 Войдите в Avito (если требуется) и нажмите Enter здесь для продолжения...\n")

        # Переход на целевую страницу
        try:
            log("Открываем страницу купленных резюме...")
            page.goto(url, wait_until="domcontentloaded")
        except PwError:
            log("⚠️ Ошибка навигации — повтор")
            try:
                page.goto(url, wait_until="domcontentloaded")
            except PwError:
                log("⛔ Не удалось открыть страницу"); context.close(); return

        log("Запускаем робастный скролл v11…")
        t0 = time.time()
        total_cards = robust_scroll(page, need_count=limit)
        t1 = time.time()

        # Подтверждающий подсчёт
        try:
            counted = int(page.evaluate(COUNT_CARDS_JS))
        except Exception:
            counted = total_cards

        log(f"Скролл завершён: найдено {counted} карточек, время {t1 - t0:.1f}с")

        # Извлечение карточек
        try:
            records = page.evaluate(EXTRACT_JS) or []
        except Exception:
            records = []

        if limit is not None:
            records = records[:limit]

        # Сохранение
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_name = f"browser_test_v11_all_{ts}.json"
        out_path = Path(out_name)
        payload = {
            "test_params": {
                "version": "v11_scroll_only",
                "url": url,
                "timestamp": ts,
                "limit": limit,
                "headless": headless,
            },
            "performance": {
                "cards_loaded": counted,
                "duration_seconds": round(t1 - t0, 2),
                "speed_per_second": (counted / max(t1 - t0, 0.001)),
            },
            "sample_data": records[:10],
            "full_data": records,
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"💾 Результаты сохранены в {out_path.resolve()}")

        context.close()


if __name__ == "__main__":
    main()
