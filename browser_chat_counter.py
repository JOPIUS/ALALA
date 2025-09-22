# -*- coding: utf-8 -*-
"""
Скрипт для подсчета уникальных чатов на странице Avito Messenger.

Что делает:
- Открывает страницу `https://www.avito.ru/profile/messenger`
- Дает время пользователю для авторизации в браузере
- Агрессивно скроллит вниз до загрузки всех чатов
- Извлекает уникальные ссылки чатов и считает их количество
- Выводит статистику с прогрессом в терминале и сохраняет результат в JSON

Зависимости: playwright
  pip install playwright
  python -m playwright install chromium

Использование:
  python browser_chat_counter.py              # Обычный режим с браузером (рекомендуется)
  python browser_chat_counter.py --headless   # Headless режим (требует готовой авторизации)
  python browser_chat_counter.py --timeout 600 # Установить таймаут скроллинга

ВАЖНО: 
- При первом запуске ОБЯЗАТЕЛЬНО используйте режим без --headless
- Убедитесь что вы авторизованы в Avito
- Скрипт сам подождет пока вы войдете в аккаунт
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright, Error as PwError
import time, json, sys, re


# ========== Конфиг ==========
USER_DATA_DIR = Path("./avito_browser_profile").resolve()
TARGET_URL = "https://www.avito.ru/profile/messenger"

NAV_TIMEOUT = 60_000
MAX_TOTAL_SCROLL_SEC = 600  # 10 минут максимум
QUIET_MS = 3000  # 3 секунды тишины
STABLE_GROWTH_ROUNDS = 5
SCROLL_DELAY_SEC = 0.5
WAIT_RESP_TIMEOUT_MS = 8000


def log(msg: str) -> None:
    print(f"💬 [{datetime.now().strftime('%H:%M:%S')}] {msg}")


def log_progress(current: int, total: int, prefix: str = "Прогресс") -> None:
    """Выводит прогресс-бар в терминал"""
    if total == 0:
        percent = 0
    else:
        percent = min(100, (current / total) * 100)
    
    bar_length = 30
    filled_length = int(bar_length * percent // 100)
    bar = '█' * filled_length + '-' * (bar_length - filled_length)
    
    print(f"\r🔄 {prefix}: |{bar}| {percent:.1f}% ({current}/{total})", end='', flush=True)


# ========== JS для агрессивного скроллинга чатов ==========
AGGRESSIVE_CHAT_SCROLL_JS = rf"""
  async () => {{
    const deadline = Date.now() + {MAX_TOTAL_SCROLL_SEC} * 1000;
    const quietMs = {QUIET_MS};
    document.documentElement.style.scrollBehavior = 'auto';
    const sleep = (ms) => new Promise(r => setTimeout(r, ms));
    
    // Расширенный список селекторов для чатов
    const chatSelectors = [
      '[data-marker="messenger/chat-item"]',
      '[data-marker="messenger-chat-item"]', 
      '[data-marker="messenger-chat"]',
      '[data-marker*="chat"]',
      '[data-marker*="channel"]',
      '.messenger-chat-item',
      '.chat-item',
      '.chat-list-item',
      '[class*="chat"]',
      '[class*="Chat"]',
      '[class*="messenger"]',
      '[class*="channel"]',
      'a[href*="/profile/messenger/chat/"]',
      'a[href*="/messenger/chat/"]',
      'a[href*="/profile/messenger/channel/"]',
      'a[href*="/messenger/channel/"]',
      'a[href*="/m/"]',
      '[data-testid*="chat"]',
      '[data-testid*="channel"]',
      '.styles-module-root',
      '.styles-module-item'
    ];
    
    let lastMutation = Date.now();
    const mo = new MutationObserver(() => {{ lastMutation = Date.now(); }});
    mo.observe(document.body, {{childList: true, subtree: true}});
    
    // БЛОКИРУЕМ ВСЕ КЛИКИ ПО ССЫЛКАМ ЧАТОВ
    function blockChatClicks() {{
      const chatLinks = document.querySelectorAll('a[href*="/messenger/"], a[href*="/channel/"]');
      chatLinks.forEach(link => {{
        link.addEventListener('click', (e) => {{
          e.preventDefault();
          e.stopPropagation();
          console.log('🚫 Заблокирован клик по ссылке чата:', link.href);
        }}, true);
        
        // Также блокируем через CSS
        link.style.pointerEvents = 'none';
      }});
    }}
    
    // Функция для поиска кнопок "Показать еще" или загрузки
    async function clickLoadMore() {{
      const loadMorePatterns = [
        /(показат[ьъ]\s*ещ[её]|показать больше|ещё|загрузить ещё|load more)/i,
        /(загруз[ки]|loading)/i
      ];
      
      const buttons = Array.from(document.querySelectorAll('button, a, div[role="button"]'));
      for (const btn of buttons) {{
        const text = (btn.textContent || '').trim();
        // НЕ КЛИКАЕМ по ссылкам чатов!
        const href = btn.getAttribute('href') || '';
        if (href.includes('/messenger/') || href.includes('/channel/')) {{
          continue; // Пропускаем ссылки чатов
        }}
        
        if (loadMorePatterns.some(pattern => pattern.test(text))) {{
          if (!btn.disabled && !btn.getAttribute('aria-disabled')) {{
            try {{
              btn.click();
              await sleep(500);
              console.log('✅ Clicked load more button:', text);
            }} catch(e) {{
              console.log('❌ Error clicking button:', e);
            }}
          }}
        }}
      }}
    }}
    
    // Функция для подсчета уникальных чатов
    function getUniqueChats() {{
      const chatLinks = new Set();
      const allElements = document.querySelectorAll('*');
      
      console.log(`Scanning ${{allElements.length}} elements for chat patterns...`);
      
      // Поиск по ссылкам
      const allLinks = document.querySelectorAll('a[href]');
      console.log(`Found ${{allLinks.length}} links total`);
      
      for (const link of allLinks) {{
        const href = link.getAttribute('href');
        if (href) {{
          // Более широкий поиск паттернов чатов
          const chatPatterns = [
            /\/messenger\/chat\/([^\/\?#]+)/,
            /\/profile\/messenger\/chat\/([^\/\?#]+)/,
            /\/messenger\/channel\/([^\/\?#]+)/,
            /\/profile\/messenger\/channel\/([^\/\?#]+)/,
            /\/m\/([^\/\?#]+)/,
            /\/chat\/([^\/\?#]+)/,
            /\/channel\/([^\/\?#]+)/,
            /chat[_-]?id[=:]([^&\?#]+)/i,
            /channel[_-]?id[=:]([^&\?#]+)/i
          ];
          
          for (const pattern of chatPatterns) {{
            const match = href.match(pattern);
            if (match) {{
              chatLinks.add(match[1]);
              console.log(`Found chat via URL: ${{href}} -> ID: ${{match[1]}}`);
              break;
            }}
          }}
        }}
      }}
      
      // Поиск по селекторам
      for (const selector of chatSelectors) {{
        try {{
          const elements = document.querySelectorAll(selector);
          console.log(`Selector "${{selector}}" found ${{elements.length}} elements`);
          
          for (const el of elements) {{
            // Ищем ссылку внутри элемента или сам элемент
            const linkEl = el.tagName === 'A' ? el : el.querySelector('a[href]');
            if (linkEl) {{
              const href = linkEl.getAttribute('href');
              if (href) {{
                const chatPatterns = [
                  /\/messenger\/chat\/([^\/\?#]+)/,
                  /\/profile\/messenger\/chat\/([^\/\?#]+)/,
                  /\/messenger\/channel\/([^\/\?#]+)/,
                  /\/profile\/messenger\/channel\/([^\/\?#]+)/,
                  /\/m\/([^\/\?#]+)/,
                  /\/chat\/([^\/\?#]+)/,
                  /\/channel\/([^\/\?#]+)/
                ];
                
                for (const pattern of chatPatterns) {{
                  const match = href.match(pattern);
                  if (match) {{
                    chatLinks.add(match[1]);
                    console.log(`Found chat via selector: ${{selector}} -> ${{href}} -> ID: ${{match[1]}}`);
                    break;
                  }}
                }}
              }}
            }}
            
            // Проверяем data-атрибуты
            const dataAttrs = ['data-chat-id', 'data-id', 'data-item-id', 'data-conversation-id'];
            for (const attr of dataAttrs) {{
              const dataId = el.getAttribute(attr);
              if (dataId && dataId.length > 5) {{
                chatLinks.add(dataId);
                console.log(`Found chat via data attribute ${{attr}}: ${{dataId}}`);
              }}
            }}
          }}
        }} catch(e) {{
          console.log(`Error with selector "${{selector}}": ${{e.message}}`);
        }}
      }}
      
      console.log(`Total unique chat IDs found: ${{chatLinks.size}}`);
      return Array.from(chatLinks);
    }}
    
    let lastCount = 0;
    let stableRounds = 0;
    let scrollAttempts = 0;
    const maxScrollAttempts = 1000;
    
    console.log('Starting aggressive chat scrolling...');
    
    while (Date.now() < deadline && scrollAttempts < maxScrollAttempts) {{
      // ПРОВЕРЯЕМ ЧТО МЫ НЕ УШЛИ СО СТРАНИЦЫ МЕССЕНДЖЕРА
      if (!location.href.includes('/profile/messenger')) {{
        console.log('🚨 ВНИМАНИЕ: Ушли со страницы мессенджера! URL:', location.href);
        console.log('⚠️ Возможно кликнули по ссылке чата. Останавливаем скроллинг.');
        break;
      }}
      
      // БЛОКИРУЕМ КЛИКИ ПО ССЫЛКАМ ЧАТОВ ПЕРЕД КАЖДОЙ ИТЕРАЦИЕЙ
      blockChatClicks();
      
      // АГРЕССИВНЫЙ СКРОЛЛИНГ С РАНДОМИЗАЦИЕЙ (БЕЗ КЛИКОВ!)
      
      // 1. Базовый скролл до низа
      window.scrollTo(0, document.body.scrollHeight);
      await sleep(200 + Math.random() * 200); // 200-400ms
      
      // 2. Рандомизированный отскок назад
      const randomBounce = 300 + Math.random() * 700; // 300-1000px
      window.scrollBy(0, -randomBounce);
      await sleep(100 + Math.random() * 100); // 100-200ms
      
      // 3. Агрессивный возврат к низу
      window.scrollTo(0, document.body.scrollHeight);
      await sleep(150 + Math.random() * 150); // 150-300ms
      
      // 4. Дополнительные рандомные движения для загрузки (ТОЛЬКО СКРОЛЛ!)
      for (let i = 0; i < 3; i++) {{
        const randomJump = Math.random() * window.innerHeight;
        window.scrollBy(0, randomJump);
        await sleep(50 + Math.random() * 50);
        window.scrollBy(0, -randomJump/2);
        await sleep(50 + Math.random() * 50);
      }}
      
      // 5. Финальный скролл к низу
      window.scrollTo(0, document.body.scrollHeight);
      await sleep(200);
      
      // 6. ОСТОРОЖНО кликаем кнопки загрузки (НЕ ссылки чатов!)
      await clickLoadMore();
      await sleep(300);
      
      // 7. Пробуем прокрутить в контейнере чатов, если он есть
      const chatContainers = [
        '.messenger-chat-list', 
        '.chat-list', 
        '[class*="chat"][class*="list"]',
        '[class*="messenger"][class*="list"]',
        '[class*="channel"][class*="list"]'
      ];
      
      for (const containerSelector of chatContainers) {{
        const chatContainer = document.querySelector(containerSelector);
        if (chatContainer) {{
          // Агрессивный скролл внутри контейнера (ТОЛЬКО СКРОЛЛ!)
          chatContainer.scrollTop = chatContainer.scrollHeight;
          await sleep(150);
          
          // Рандомный отскок в контейнере
          const containerBounce = Math.random() * chatContainer.scrollHeight * 0.3;
          chatContainer.scrollTop = chatContainer.scrollHeight - containerBounce;
          await sleep(100);
          chatContainer.scrollTop = chatContainer.scrollHeight;
          await sleep(150);
          break;
        }}
      }}
      
      // 8. Дополнительные хаотичные движения (ТОЛЬКО СКРОЛЛ!)
      if (scrollAttempts % 10 === 0) {{
        console.log(`💥 Агрессивная прокрутка #${{scrollAttempts + 1}}: хаотичные движения для загрузки`);
        for (let chaos = 0; chaos < 5; chaos++) {{
          window.scrollBy(0, (Math.random() - 0.5) * 1000);
          await sleep(80);
        }}
        window.scrollTo(0, document.body.scrollHeight);
        await sleep(200);
        
        // Дополнительная блокировка кликов после хаотичных движений
        blockChatClicks();
      }}
      
      const currentChats = getUniqueChats();
      const currentCount = currentChats.length;
      
      // Создаем прогресс-бар для вывода в консоль Python
      const progress = Math.min(scrollAttempts / maxScrollAttempts * 100, 100);
      const elapsedTime = (Date.now() - (deadline - {MAX_TOTAL_SCROLL_SEC} * 1000)) / 1000;
      
      console.log(`🔄 Попытка ${{scrollAttempts + 1}}/${{maxScrollAttempts}} | Найдено: ${{currentCount}} чатов | Время: ${{elapsedTime.toFixed(1)}}с | Прогресс: ${{progress.toFixed(1)}}%`);
      
      const quiet = (Date.now() - lastMutation) > quietMs;
      if (currentCount <= lastCount && quiet) {{
        stableRounds++;
        console.log(`⏸️ Стабильный раунд ${{stableRounds}}/5 (новые чаты не загружаются)`);
      }} else {{
        stableRounds = 0;
        lastCount = currentCount;
        console.log(`📈 Новые чаты обнаружены! Общее количество: ${{currentCount}}`);
      }}
      
      // Если долго нет изменений, заканчиваем
      if (stableRounds >= 5) {{
        console.log('⏹️ Новые чаты не загружались 5 раундов подряд, завершаем...');
        break;
      }}
      
      scrollAttempts++;
      
      // Каждые 50 попыток показываем дополнительную статистику
      if (scrollAttempts % 50 === 0) {{
        console.log(`📊 Промежуточная статистика: ${{currentCount}} уникальных чатов за ${{scrollAttempts}} попыток`);
      }}
    }}
    
    // Финальный подсчет
    const finalChats = getUniqueChats();
    
    console.log(`✅ Скроллинг завершен! Итого найдено: ${{finalChats.length}} уникальных чатов`);
    console.log(`📊 Статистика: ${{scrollAttempts}} попыток скроллинга за ${{((Date.now() - (deadline - {MAX_TOTAL_SCROLL_SEC} * 1000)) / 1000).toFixed(1)}} секунд`);
    
    mo.disconnect();
    
    return {{
      total_chats: finalChats.length,
      chat_ids: finalChats,
      scroll_attempts: scrollAttempts,
      duration_ms: Date.now() - (deadline - {MAX_TOTAL_SCROLL_SEC} * 1000)
    }};
  }}
"""

# JS для финального извлечения данных о чатах
EXTRACT_CHAT_DATA_JS = r"""
  () => {
    const chatLinks = new Set();
    const chatData = [];
    
    // Ищем все ссылки на чаты и каналы
    const allLinks = document.querySelectorAll('a[href]');
    for (const link of allLinks) {
      const href = link.getAttribute('href');
      if (href && (
        href.includes('/messenger/chat/') || 
        href.includes('/profile/messenger/chat/') ||
        href.includes('/messenger/channel/') || 
        href.includes('/profile/messenger/channel/')
      )) {
        const chatIdMatch = href.match(/(?:chat|channel)\/([^\/\?#]+)/);
        if (chatIdMatch) {
          const chatId = chatIdMatch[1];
          if (!chatLinks.has(chatId)) {
            chatLinks.add(chatId);
            
            // Пытаемся извлечь дополнительную информацию о чате
            const chatElement = link.closest('[data-marker*="chat"], [data-marker*="channel"], .chat-item, .messenger-chat-item');
            const chatInfo = {
              chat_id: chatId,
              href: href,
              title: '',
              last_message: '',
              timestamp: '',
              unread: false,
              type: href.includes('/channel/') ? 'channel' : 'chat'
            };
            
            if (chatElement) {
              // Извлекаем название/имя
              const titleEl = chatElement.querySelector('[class*="title"], [class*="name"], h3, h4');
              if (titleEl) {
                chatInfo.title = (titleEl.textContent || '').trim();
              }
              
              // Последнее сообщение
              const messageEl = chatElement.querySelector('[class*="message"], [class*="text"]');
              if (messageEl) {
                chatInfo.last_message = (messageEl.textContent || '').trim();
              }
              
              // Время
              const timeEl = chatElement.querySelector('[class*="time"], [class*="date"]');
              if (timeEl) {
                chatInfo.timestamp = (timeEl.textContent || '').trim();
              }
              
              // Непрочитанные
              const unreadEl = chatElement.querySelector('[class*="unread"], [class*="badge"]');
              chatInfo.unread = !!unreadEl;
            }
            
            chatData.push(chatInfo);
          }
        }
      }
    }
    
    return {
      total_unique_chats: chatLinks.size,
      chat_data: chatData
    };
  }
"""


def parse_cli_args(argv: list[str]) -> tuple[bool, int]:
    """Возвращает (headless, timeout)"""
    headless = False  # По умолчанию НЕ headless для удобства авторизации
    timeout = MAX_TOTAL_SCROLL_SEC
    
    try:
        if "--headless" in argv:
            headless = True
            log("⚠️ Включен headless режим - убедитесь что авторизация уже настроена")
        if "--timeout" in argv:
            timeout = int(argv[argv.index("--timeout") + 1])
    except Exception:
        pass
    
    return headless, timeout


def main() -> None:
    headless, scroll_timeout = parse_cli_args(sys.argv)
    
    # Обновляем таймаут в JS коде
    global MAX_TOTAL_SCROLL_SEC
    MAX_TOTAL_SCROLL_SEC = scroll_timeout
    
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    log(f"Запуск подсчета чатов на Avito Messenger")
    log(f"Параметры: headless={headless}, timeout={scroll_timeout}s")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=headless,
            viewport={"width": 1200, "height": 800},
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context.set_default_timeout(NAV_TIMEOUT)
        context.set_default_navigation_timeout(NAV_TIMEOUT)
        page = context.new_page()

        try:
            log("Переход на главную страницу Avito...")
            page.goto("https://www.avito.ru/", wait_until="domcontentloaded")
            time.sleep(2)
        except PwError as e:
            log(f"⚠️ Ошибка загрузки главной страницы: {e}")

        log("🔑 Убедитесь что вы авторизованы в Avito в открывшемся браузере")
        log("   Если нужно - войдите в свой аккаунт")
        log("   После авторизации нажмите Enter чтобы продолжить...")
        
        input("\n[ENTER для продолжения] ")

        # Проверяем авторизацию
        log("🔍 Проверяем авторизацию...")
        try:
            # Ищем признаки авторизации
            auth_selectors = [
                '[data-marker="header/avatar"]',
                '[data-marker="header/username"]', 
                '.header-username',
                '.user-name',
                'a[href*="/profile"]',
                '.header-avatar'
            ]
            
            is_authorized = False
            for selector in auth_selectors:
                try:
                    element = page.wait_for_selector(selector, timeout=3000)
                    if element:
                        is_authorized = True
                        log(f"✅ Найден элемент авторизации: {selector}")
                        break
                except:
                    continue
            
            if not is_authorized:
                log("⚠️ Не найдены признаки авторизации, но продолжаем...")
                
        except Exception as e:
            log(f"⚠️ Ошибка проверки авторизации: {e}")

        log("📱 Переходим на страницу мессенджера...")
        try:
            page.goto(TARGET_URL, wait_until="domcontentloaded")
            time.sleep(5)  # Даем больше времени на загрузку
            
            # Проверяем что мы на правильной странице
            current_url = page.url
            log(f"📍 Текущий URL: {current_url}")
            
            if "messenger" not in current_url.lower():
                log("⚠️ Возможно произошло перенаправление")
                log("   Проверьте что вы авторизованы и имеете доступ к мессенджеру")
                
                user_input = input("\n🤔 Продолжить работу? (y/n): ").strip().lower()
                if user_input != 'y':
                    log("❌ Операция отменена пользователем")
                    context.close()
                    return
            
        except PwError:
            log("⚠️ Ошибка навигации на страницу мессенджера — повтор")
            try:
                page.goto(TARGET_URL, wait_until="domcontentloaded")
                time.sleep(5)
            except PwError:
                log("⛔ Не удалось открыть страницу мессенджера")
                context.close()
                return

        log("🔄 Запускаем агрессивный скроллинг для загрузки всех чатов...")
        
        # Дополнительная проверка перед скроллингом
        log("🔍 Проверяем наличие элементов чатов на странице...")
        try:
            # Ждем загрузки элементов страницы
            page.wait_for_load_state("networkidle", timeout=10000)
            
            # Проверяем наличие хотя бы одного элемента чата
            chat_check_selectors = [
                '[data-marker*="messenger"]',
                '[data-marker*="chat"]',
                '[data-marker*="channel"]', 
                '.messenger-chat',
                '.chat-item',
                'a[href*="/messenger/chat/"]',
                'a[href*="/messenger/channel/"]',
                'a[href*="/profile/messenger/channel/"]',
                '[class*="chat"]'
            ]
            
            found_chats = False
            for selector in chat_check_selectors:
                try:
                    elements = page.query_selector_all(selector)
                    if elements:
                        log(f"✅ Найдено {len(elements)} элементов по селектору: {selector}")
                        found_chats = True
                        break
                except:
                    continue
            
            if not found_chats:
                log("⚠️ Не найдено элементов чатов на странице")
                log("   Возможно требуется ручное вмешательство")
                
                user_choice = input("\n🤔 Продолжить поиск чатов? (y/n): ").strip().lower()
                if user_choice != 'y':
                    log("❌ Поиск отменен пользователем")
                    context.close()
                    return
            else:
                log("✅ Элементы чатов найдены, начинаем скроллинг")
                
        except Exception as e:
            log(f"⚠️ Ошибка при проверке элементов: {e}")
        
        t0 = time.time()
        
        try:
            # Обновляем JS код с новым таймаутом
            scroll_js = AGGRESSIVE_CHAT_SCROLL_JS.replace(
                f"{600} * 1000", f"{scroll_timeout} * 1000"
            )
            
            log("⏰ Запуск скроллинга...")
            
            # Запускаем скроллинг с отслеживанием консольных сообщений
            console_messages = []
            
            def on_console(msg):
                message_text = msg.text
                console_messages.append(message_text)
                # Выводим сообщения из браузера в терминал с форматированием
                if '🔄 Попытка' in message_text:
                    # Извлекаем данные для прогресс-бара
                    try:
                        parts = message_text.split('|')
                        if len(parts) >= 4:
                            attempt_part = parts[0].strip()
                            chats_part = parts[1].strip()
                            time_part = parts[2].strip()
                            progress_part = parts[3].strip()
                            
                            # Извлекаем числа
                            attempt_match = re.search(r'(\d+)/(\d+)', attempt_part)
                            chats_match = re.search(r'(\d+)', chats_part)
                            
                            if attempt_match and chats_match:
                                current_attempt = int(attempt_match.group(1))
                                total_attempts = int(attempt_match.group(2))
                                chat_count = int(chats_match.group(1))
                                
                                # Выводим красивый прогресс-бар
                                print(f"\r", end='')  # Очищаем строку
                                log_progress(current_attempt, total_attempts, f"Скроллинг (найдено {chat_count} чатов)")
                                print(f" | {time_part} | {progress_part}")
                    except:
                        print(f"  📊 {message_text}")
                        
                elif any(marker in message_text for marker in ['', '⏸️', '⏹️', '📊']):
                    print(f"\n  {message_text}")
                elif "Scrolling completed" in message_text:
                    print(f"\n  ✅ {message_text}")
                elif "Found chat via" in message_text and len(console_messages) % 10 == 0:
                    # Показываем только каждый 10й найденный чат чтобы не засорять вывод
                    print(f"  🔍 {message_text}")
            
            page.on("console", on_console)
            
            scroll_result = page.evaluate(scroll_js)
            t1 = time.time()
            
            log(f"✅ Скроллинг завершен за {t1 - t0:.1f}с")
            log(f"📊 Найдено {scroll_result['total_chats']} уникальных чатов")
            log(f"🔄 Выполнено {scroll_result['scroll_attempts']} попыток скроллинга")
            
        except Exception as e:
            log(f"❌ Ошибка при скроллинге: {e}")
            context.close()
            return

        # Извлекаем финальные данные
        try:
            log("📝 Извлекаем детальную информацию о чатах...")
            chat_data = page.evaluate(EXTRACT_CHAT_DATA_JS)
            
            log(f"✅ Собрано данных о {chat_data['total_unique_chats']} чатах")
            
        except Exception as e:
            log(f"⚠️ Ошибка при извлечении данных: {e}")
            chat_data = {"total_unique_chats": 0, "chat_data": []}

        # Сохранение результатов
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_name = f"avito_chat_count_{ts}.json"
        out_path = Path(out_name)
        
        result = {
            "timestamp": ts,
            "url": TARGET_URL,
            "parameters": {
                "headless": headless,
                "timeout_seconds": scroll_timeout,
            },
            "performance": {
                "scroll_duration_seconds": round(t1 - t0, 2),
                "scroll_attempts": scroll_result.get('scroll_attempts', 0),
            },
            "statistics": {
                "total_unique_chats": chat_data['total_unique_chats'],
                "chat_ids_count": len(scroll_result.get('chat_ids', [])),
            },
            "chat_data": chat_data['chat_data'][:10],  # Первые 10 для примера
            "all_chat_ids": scroll_result.get('chat_ids', []),
        }
        
        out_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), 
            encoding="utf-8"
        )
        
        log(f"💾 Результаты сохранены в {out_path.resolve()}")
        log(f"🎯 ИТОГО УНИКАЛЬНЫХ ЧАТОВ: {chat_data['total_unique_chats']}")

        context.close()


if __name__ == "__main__":
    main()