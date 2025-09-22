# browser_scroll_test_v8_final.py
# -*- coding: utf-8 -*-
"""
Финальная версия парсера Avito резюме v8
Фокус на качественном извлечении данных только из реальных карточек резюме
"""

from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright, Error as PwError
import time
import json

# Конфигурация
USER_DATA_DIR = Path("./avito_browser_profile").resolve()
TARGET_URL = "https://www.avito.ru/profile/paid-cvs"

# Настройки производительности
MAX_TOTAL_SCROLL_SEC = 300  # Увеличено для полной загрузки
QUIET_MS = 1000             
STABLE_GROWTH_ROUNDS = 20   # Увеличено для более терпеливого ожидания
NAV_TIMEOUT = 30_000        

# Точные селекторы только для карточек резюме
RESUME_CARD_SELECTORS = [
    '[class*="styles-module-root"]',  # Рабочий селектор из v7
    'article[data-marker="cv-snippet"]',  # Официальный маркер если есть
    'a[href*="/resume/"]:not([href*="/account/"]):not([href*="/step"])',  # Ссылки на резюме
    '[class*="cv-snippet"]',  # Альтернативные селекторы
    'article',   # Базовые статьи
]

# Специализированные селекторы для данных с fallback
RESUME_DATA_SELECTORS = {
    'name': [
        '[data-marker="cv-snippet-name"]',
        'h3[class*="title"]',
        'h3',
        '.text-text-LurtD.text-size-s-BxGpL.text-color-black-ohrjA',
        'a[href*="/resume/"] span',
        'a[href*="/resume/"]',
        '[class*="name"] span',
        '[class*="title"] span'
    ],
    'link': [
        'a[href*="/resume/"]:not([href*="/account/"]):not([href*="/step"])',
        'a[href*="/cv/"]'
    ],
    'salary': [
        '[data-marker="cv-snippet-salary"]',
        '.text-color-green-zxyRV',
        '[class*="salary"]',
        '[class*="price"]',
        'span:contains("₽")',
        'span:contains("руб")',
        '.text-text-LurtD:contains("₽")'
    ],
    'location': [
        '[data-marker="cv-snippet-location"]',
        '.text-color-blue-Ad9BB',
        '[class*="location"]',
        '.text-text-LurtD.text-size-s-BxGpL.text-color-blue-Ad9BB'
    ],
    'date': [
        '[data-marker="cv-snippet-date"]',
        '.text-size-xs-',
        '[class*="date"]',
        '.text-text-LurtD.text-size-xs-'
    ]
}

def log_with_time(msg):
    """Логирование с временной меткой"""
    print(f"🕐 [{datetime.now().strftime('%H:%M:%S')}] {msg}")

def find_best_resume_selector(page):
    """Находит лучший селектор для карточек резюме"""
    best_selector = None
    max_total_count = 0
    
    for selector in RESUME_CARD_SELECTORS:
        try:
            # Считаем общее количество элементов
            count = page.evaluate(f'() => document.querySelectorAll(\'{selector}\').length')
            if count > max_total_count:
                max_total_count = count
                best_selector = selector
                log_with_time(f"✅ Селектор '{selector}': {count} элементов")
        except Exception as e:
            log_with_time(f"❌ Ошибка тестирования селектора '{selector}': {e}")
    
    if best_selector:
        log_with_time(f"🎯 Лучший селектор: '{best_selector}' ({max_total_count} элементов)")
    else:
        log_with_time("❌ Не найден подходящий селектор")
    
    return best_selector

def count_valid_resumes(page, selector):
    """Подсчет элементов"""
    if not selector:
        return 0
    
    try:
        return page.evaluate(f'() => document.querySelectorAll(\'{selector}\').length')
    except:
        return 0

def wait_for_network_idle(page, timeout_ms=3000):
    """Ожидание завершения сетевых запросов"""
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
        return True
    except Exception:
        return False

def detect_end_of_page(page):
    """Обнаруживает признаки конца страницы"""
    try:
        end_indicators = page.evaluate("""
            () => {
                const indicators = {
                    footer_visible: false,
                    no_more_text: false,
                    scroll_at_bottom: false,
                    active_load_buttons: 0,
                    no_new_content: false
                };
                
                // Подсчет активных кнопок загрузки
                const moreButtons = document.querySelectorAll('button, a, [role="button"]');
                for (const btn of moreButtons) {
                    const text = btn.textContent.toLowerCase().trim();
                    if (text.includes('ещё') && btn.offsetParent !== null && 
                        !btn.disabled && !btn.getAttribute('aria-disabled')) {
                        indicators.active_load_buttons++;
                    }
                }
                
                // Поиск индикаторов конца
                const endTexts = [
                    'больше резюме нет', 'конец списка', 'все резюме загружены',
                    'больше результатов нет', 'результаты закончились'
                ];
                
                const bodyText = document.body.textContent.toLowerCase();
                indicators.no_more_text = endTexts.some(text => bodyText.includes(text));
                
                // Проверка скролла
                const scrollTop = window.pageYOffset;
                const scrollHeight = document.documentElement.scrollHeight;
                const clientHeight = window.innerHeight;
                
                indicators.scroll_at_bottom = (scrollTop + clientHeight + 200) >= scrollHeight;
                
                return indicators;
            }
        """)
        
        return end_indicators
    except Exception as e:
        log_with_time(f"⚠️ Ошибка определения конца страницы: {e}")
        return {"active_load_buttons": 999, "no_more_text": False, "scroll_at_bottom": False}

def smart_scroll_with_resume_detection(page, target_count=None, max_time_sec=300):
    """
    Умный скроллинг с фокусом на реальные резюме
    """
    log_with_time(f"🚀 УМНЫЙ скроллинг v8 для резюме (цель: {target_count or 'ВСЕ'}, лимит: {max_time_sec}с)")
    
    start_time = time.time()
    deadline = start_time + max_time_sec
    
    # Находим лучший селектор
    best_selector = find_best_resume_selector(page)
    if not best_selector:
        log_with_time("❌ Не удалось найти селектор для резюме")
        return 0, None
    
    last_count = 0
    last_height = 0
    no_change_count = 0
    iteration = 0
    last_log_time = start_time
    
    initial_count = count_valid_resumes(page, best_selector)
    initial_height = page.evaluate("document.documentElement.scrollHeight")
    log_with_time(f"📋 Стартовое количество: {initial_count} элементов, высота: {initial_height}px")
    
    while time.time() < deadline:
        iteration += 1
        current_count = count_valid_resumes(page, best_selector)
        current_height = page.evaluate("document.documentElement.scrollHeight")
        current_time = time.time()
        
        # Логируем прогресс
        if current_count > last_count or current_height > last_height or (current_time - last_log_time) > 10:
            if current_count > last_count or current_height > last_height:
                count_progress = current_count - last_count
                height_progress = current_height - last_height
                log_with_time(f"📈 +{count_progress} = {current_count} элементов, высота: {current_height}px (+{height_progress}) [итерация {iteration}]")
                last_count = current_count
                last_height = current_height
                no_change_count = 0
            else:
                log_with_time(f"⏳ {current_count} элементов, высота: {current_height}px [итерация {iteration}, стабильно: {no_change_count}]")
                no_change_count += 1
            last_log_time = current_time
            
            # Проверяем достижение цели
            if target_count and current_count >= target_count:
                log_with_time(f"🎯 ЦЕЛЬ ДОСТИГНУТА: {current_count} >= {target_count}")
                break
        
        # Проверяем признаки конца страницы
        end_indicators = detect_end_of_page(page)
        if (end_indicators['no_more_text'] or 
            (end_indicators['scroll_at_bottom'] and end_indicators['active_load_buttons'] == 0 and no_change_count >= 10)):
            log_with_time("🏁 Достигнут конец страницы")
            break
        
        try:
            # Плавный скролл вниз
            page.evaluate("""
                window.scrollBy({
                    top: window.innerHeight * 0.9,
                    behavior: 'smooth'
                });
            """)
            
            time.sleep(0.5)  # Увеличенная пауза для загрузки
            
            # Дополнительные действия для стимуляции загрузки
            if iteration % 3 == 0:
                page.keyboard.press("PageDown")
                time.sleep(0.3)
            
            # Встряхивающий скролл при застое
            if no_change_count >= 5:
                log_with_time("💫 Встряска: скролл вверх-вниз + клик кнопок")
                page.evaluate("window.scrollBy(0, -800)")
                time.sleep(0.5)
                page.evaluate("window.scrollBy(0, 1600)")
                time.sleep(0.5)
                
                # Попытка кликнуть кнопки "Ещё"
                try:
                    clicked = page.evaluate("""
                        () => {
                            const buttons = document.querySelectorAll('button, a, [role="button"]');
                            let clicked = false;
                            for (const btn of buttons) {
                                const text = btn.textContent.toLowerCase();
                                if (text.includes('ещё') || text.includes('загруз') || text.includes('показать')) {
                                    try {
                                        btn.scrollIntoView();
                                        btn.click();
                                        clicked = true;
                                        break;
                                    } catch(e) {}
                                }
                            }
                            return clicked;
                        }
                    """)
                    
                    if clicked:
                        log_with_time("✅ Кликнул кнопку загрузки")
                        time.sleep(3.0)
                        no_change_count = 0
                except:
                    pass
            
            # Ожидание сети
            if iteration % 8 == 0:
                wait_for_network_idle(page, timeout_ms=2000)
                
        except Exception as e:
            log_with_time(f"⚠️ Ошибка в итерации {iteration}: {e}")
            time.sleep(1.0)
        
        # Защита от бесконечного зависания
        if no_change_count >= STABLE_GROWTH_ROUNDS:
            log_with_time(f"🛑 {no_change_count} итераций без изменений - возможно достигнут конец")
            break
    
    final_count = count_valid_resumes(page, best_selector)
    total_elapsed = time.time() - start_time
    
    log_with_time(f"🏁 УМНЫЙ скроллинг завершен!")
    log_with_time(f"📊 Итого: {final_count} элементов за {total_elapsed:.1f}с ({iteration} итераций)")
    log_with_time(f"⚡ Скорость: {final_count/total_elapsed:.1f} элементов/сек")
    
    return final_count, best_selector

def extract_premium_resume_data(page, card_selector):
    """Премиум извлечение данных только из валидных резюме"""
    log_with_time("📊 Премиум извлечение данных резюме...")
    
    if not card_selector:
        log_with_time("❌ Нет селектора карточек")
        return []
    
    # Находим лучшие селекторы для каждого типа данных
    best_data_selectors = {}
    for data_type, selectors in RESUME_DATA_SELECTORS.items():
        test_js = f"""
        () => {{
            // Тестируем на первых 5 валидных карточках резюме
            const cards = Array.from(document.querySelectorAll('{card_selector}')).filter(card => {{
                const resumeLink = card.href || card.querySelector('a[href*="/resume/"]')?.href;
                return resumeLink && resumeLink.includes('/resume/') && 
                       !resumeLink.includes('/account/') && !resumeLink.includes('/step');
            }}).slice(0, 5);
            
            if (cards.length === 0) return {{selector: null, count: 0}};
            
            let bestSelector = null;
            let maxCount = 0;
            
            {json.dumps(selectors)}.forEach(selector => {{
                try {{
                    let totalCount = 0;
                    cards.forEach(card => {{
                        const elements = card.querySelectorAll(selector);
                        if (elements.length > 0) {{
                            // Для ссылок проверяем валидность
                            if (selector.includes('href')) {{
                                const validLinks = Array.from(elements).filter(el => 
                                    el.href && el.href.includes('/resume/') && 
                                    !el.href.includes('/account/') && !el.href.includes('/step')
                                );
                                totalCount += validLinks.length;
                            }} else {{
                                // Для других данных проверяем наличие текста
                                const validElements = Array.from(elements).filter(el => 
                                    el.textContent && el.textContent.trim().length > 0
                                );
                                totalCount += validElements.length;
                            }}
                        }}
                    }});
                    
                    if (totalCount > maxCount) {{
                        maxCount = totalCount;
                        bestSelector = selector;
                    }}
                }} catch(e) {{}}
            }});
            
            return {{selector: bestSelector, count: maxCount}};
        }}
        """
        
        try:
            result = page.evaluate(test_js)
            if result['selector'] and result['count'] > 0:
                best_data_selectors[data_type] = result['selector']
                log_with_time(f"✅ Лучший селектор для {data_type}: '{result['selector']}' (найдено в {result['count']} случаях)")
            else:
                log_with_time(f"⚠️ Не найден селектор для {data_type}")
        except Exception as e:
            log_with_time(f"❌ Ошибка поиска селектора для {data_type}: {e}")
    
    # Извлекаем данные с найденными селекторами
    extract_js = f"""
    () => {{
        // Находим только валидные карточки резюме
        const allCards = document.querySelectorAll('{card_selector}');
        const validCards = Array.from(allCards).filter(card => {{
            const resumeLink = card.href || card.querySelector('a[href*="/resume/"]')?.href;
            return resumeLink && resumeLink.includes('/resume/') && 
                   !resumeLink.includes('/account/') && !resumeLink.includes('/step');
        }});
        
        const results = [];
        const selectors = {json.dumps(best_data_selectors)};
        
        validCards.forEach((card, index) => {{
            try {{
                const data = {{
                    index: index + 1,
                    name: '',
                    link: '',
                    resume_id: '',
                    salary: '',
                    location: '',
                    date: '',
                    visible: card.getBoundingClientRect().top < window.innerHeight * 2
                }};
                
                // Извлекаем каждый тип данных
                for (const [dataType, selector] of Object.entries(selectors)) {{
                    try {{
                        if (dataType === 'link') {{
                            const linkEl = card.href ? card : card.querySelector(selector);
                            if (linkEl) {{
                                const href = linkEl.href || linkEl.getAttribute('href') || '';
                                if (href.includes('/resume/') && !href.includes('/account/') && !href.includes('/step')) {{
                                    data.link = href;
                                    const match = href.match(/resume\\/([^?\\/]+)/);
                                    data.resume_id = match ? match[1] : '';
                                }}
                            }}
                        }} else {{
                            const el = card.querySelector(selector);
                            if (el && el.textContent) {{
                                const text = el.textContent.trim();
                                if (text.length > 0) {{
                                    data[dataType] = text;
                                }}
                            }}
                        }}
                    }} catch(e) {{
                        console.error(`Error extracting ${{dataType}}:`, e);
                    }}
                }}
                
                // Дополнительные эвристики если основные селекторы не сработали
                if (!data.name) {{
                    // Ищем имя в ссылке или заголовке
                    const nameEl = card.querySelector('h3, h4, h5, .title, [class*="title"], a[href*="/resume/"]');
                    if (nameEl) {{
                        const text = nameEl.textContent?.trim();
                        if (text && text.length > 2 && text.length < 200 && 
                            !text.includes('₽') && !text.includes('руб') &&
                            !text.match(/\\d{{2}}\\.\\d{{2}}\\.\\d{{4}}/)) {{
                            data.name = text;
                        }}
                    }}
                }}
                
                if (!data.link) {{
                    // Ищем любую валидную ссылку на резюме
                    const linkEl = card.querySelector('a[href*="/resume/"]');
                    if (linkEl && linkEl.href) {{
                        const href = linkEl.href;
                        if (!href.includes('/account/') && !href.includes('/step')) {{
                            data.link = href;
                            const match = href.match(/resume\\/([^?\\/]+)/);
                            data.resume_id = match ? match[1] : '';
                        }}
                    }}
                }}
                
                if (!data.salary) {{
                    // Ищем зарплату по содержимому
                    const salaryEl = Array.from(card.querySelectorAll('*')).find(el => 
                        el.textContent && (el.textContent.includes('₽') || el.textContent.includes('руб'))
                    );
                    if (salaryEl) {{
                        data.salary = salaryEl.textContent.trim();
                    }}
                }}
                
                // Проверяем валидность записи
                if (data.link || data.name) {{
                    results.push(data);
                }}
            }} catch (e) {{
                console.error('Error processing card:', e);
            }}
        }});
        
        return results;
    }}
    """
    
    try:
        data = page.evaluate(extract_js)
        valid_data = [item for item in data if item.get('link') and '/resume/' in item.get('link', '')]
        log_with_time(f"✅ Извлечено {len(data)} записей, {len(valid_data)} с валидными ссылками")
        
        # Статистика качества
        names_count = sum(1 for item in valid_data if item.get('name'))
        salary_count = sum(1 for item in valid_data if item.get('salary'))
        location_count = sum(1 for item in valid_data if item.get('location'))
        date_count = sum(1 for item in valid_data if item.get('date'))
        
        log_with_time(f"📈 Качество данных:")
        log_with_time(f"   Имена: {names_count}/{len(valid_data)} ({names_count/len(valid_data)*100:.1f}%)")
        log_with_time(f"   Зарплаты: {salary_count}/{len(valid_data)} ({salary_count/len(valid_data)*100:.1f}%)")
        log_with_time(f"   Локации: {location_count}/{len(valid_data)} ({location_count/len(valid_data)*100:.1f}%)")
        log_with_time(f"   Даты: {date_count}/{len(valid_data)} ({date_count/len(valid_data)*100:.1f}%)")
        
        # Показываем пример
        if valid_data:
            sample = valid_data[0]
            log_with_time(f"🔍 Пример: {sample.get('name', 'Нет имени')[:40]}... | {sample.get('link', '')[:60]}...")
        
        return valid_data
    except Exception as e:
        log_with_time(f"❌ Ошибка извлечения данных: {e}")
        return []

def test_browser_performance_v8():
    """Финальное тестирование v8 - только качественные резюме"""
    log_with_time("🎭 Запуск финального тестирования v8")
    
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            viewport={"width": 1200, "height": 800},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-web-security",
                "--blink-settings=imagesEnabled=false",
                "--disable-images",
                "--force-device-scale-factor=0.7",
                "--window-size=1200,800"
            ],
        )
        
        context.set_default_timeout(NAV_TIMEOUT)
        page = context.new_page()
        page.add_init_script("document.body.style.zoom = '0.7'")
        
        try:
            log_with_time("🌐 Переходим на страницу Avito...")
            page.goto(TARGET_URL, wait_until="domcontentloaded")
            
            input("\n🔑 Войдите в Avito и нажмите Enter для продолжения...\n")
            
            # Финальный тест - загрузка всех резюме
            log_with_time(f"\n{'='*60}")
            log_with_time(f"🧪 ФИНАЛЬНЫЙ ТЕСТ v8: все резюме с максимальным качеством")
            log_with_time(f"{'='*60}")
            
            start_time = time.time()
            
            # Умный скроллинг
            result = smart_scroll_with_resume_detection(page, target_count=None)
            if isinstance(result, tuple):
                final_count, card_selector = result
            else:
                final_count = result
                card_selector = None
            
            # Премиум извлечение данных
            data = extract_premium_resume_data(page, card_selector)
            
            elapsed = time.time() - start_time
            
            # Финальные результаты
            log_with_time(f"⏱️ Общее время выполнения: {elapsed:.1f}с")
            log_with_time(f"📊 Загружено резюме: {final_count}")
            log_with_time(f"📊 Извлечено качественных данных: {len(data)}")
            log_with_time(f"⚡ Общая скорость: {final_count/elapsed:.1f} резюме/сек")
            log_with_time(f"🎯 Успешность извлечения: {len(data)/final_count*100:.1f}%")
            
            # Сохранение результатов
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"browser_test_v8_final_{timestamp}.json"
            
            result = {
                "test_params": {
                    "version": "v8_final",
                    "timestamp": timestamp,
                    "duration_seconds": elapsed,
                    "selector_used": card_selector
                },
                "performance": {
                    "cards_loaded": final_count,
                    "data_extracted": len(data),
                    "extraction_success_rate": len(data)/final_count*100 if final_count > 0 else 0,
                    "speed_per_second": final_count/elapsed,
                    "data_quality": {
                        "valid_names": sum(1 for item in data if item.get('name')),
                        "valid_links": sum(1 for item in data if item.get('link') and '/resume/' in item.get('link', '')),
                        "valid_salaries": sum(1 for item in data if item.get('salary')),
                        "valid_locations": sum(1 for item in data if item.get('location')),
                        "valid_dates": sum(1 for item in data if item.get('date'))
                    }
                },
                "sample_data": data[:10],  # Первые 10 записей для анализа
                "full_data": data  # Все данные
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            log_with_time(f"💾 Результаты сохранены в {filename}")
            
        except Exception as e:
            log_with_time(f"❌ Ошибка: {e}")
        finally:
            log_with_time("🏁 Финальное тестирование завершено")

if __name__ == "__main__":
    test_browser_performance_v8()