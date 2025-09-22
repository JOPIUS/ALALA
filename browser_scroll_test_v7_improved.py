# browser_scroll_test_v7_improved.py
# -*- coding: utf-8 -*-
"""
Улучшенный скрипт для парсинга Avito резюме v7
Фокус на точных селекторах и отладке HTML структуры
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
MAX_TOTAL_SCROLL_SEC = 180  
QUIET_MS = 1000             
STABLE_GROWTH_ROUNDS = 15   
NAV_TIMEOUT = 30_000        

# Улучшенные селекторы - множественные варианты для надежности
CARD_SELECTORS = [
    '[data-marker="cv-snippet"]',
    '.styles-module-root-_1qzTi',
    '[class*="cv-snippet"]',
    '[class*="resume-card"]',
    '.styles-module-root-RA_y4',
    '.styles-module-container-',
    'article',
    '[class*="styles-module-root"]'
]

# Селекторы для данных внутри карточек - множественные варианты
DATA_SELECTORS = {
    'name': [
        '[data-marker="cv-snippet-name"]',
        '.styles-module-title-',
        '[class*="title"]',
        'h3',
        '.text-text-LurtD.text-size-s-BxGpL',
        '.text-text-LurtD.text-size-s-BxGpL.text-color-black-ohrjA',
        '[class*="name"]',
        '[class*="title"]'
    ],
    'link': [
        'a[href*="/resume/"]',
        'a[href*="/cv/"]',
        '[data-marker="cv-snippet-link"]',
        '.styles-module-link-',
        'a'
    ],
    'salary': [
        '[data-marker="cv-snippet-salary"]',
        '.styles-module-salary-',
        '[class*="salary"]',
        '.text-text-LurtD.text-size-s-BxGpL.text-color-green-zxyRV',
        '[class*="price"]'
    ],
    'location': [
        '[data-marker="cv-snippet-location"]',
        '.styles-module-location-',
        '[class*="location"]',
        '.text-text-LurtD.text-size-s-BxGpL.text-color-blue-'
    ],
    'date': [
        '[data-marker="cv-snippet-date"]',
        '.styles-module-date-',
        '[class*="date"]',
        '.text-text-LurtD.text-size-xs-'
    ]
}

def log_with_time(msg):
    """Логирование с временной меткой"""
    print(f"🕐 [{datetime.now().strftime('%H:%M:%S')}] {msg}")

def analyze_page_structure(page):
    """Анализ структуры страницы для обнаружения правильных селекторов"""
    log_with_time("🔍 Анализируем HTML структуру страницы...")
    
    analysis_js = """
    () => {
        const analysis = {
            total_elements: document.querySelectorAll('*').length,
            possible_cards: [],
            data_attributes: new Set(),
            class_patterns: new Set()
        };
        
        // Ищем возможные карточки резюме
        const cardSelectors = [
            '[data-marker*="cv"]',
            '[data-marker*="resume"]',
            '[class*="cv"]',
            '[class*="resume"]',
            '[class*="snippet"]',
            '[class*="card"]',
            'article',
            '[class*="styles-module-root"]'
        ];
        
        cardSelectors.forEach(selector => {
            try {
                const elements = document.querySelectorAll(selector);
                if (elements.length > 0) {
                    analysis.possible_cards.push({
                        selector: selector,
                        count: elements.length,
                        first_element_html: elements[0].outerHTML.substring(0, 200) + '...'
                    });
                }
            } catch(e) {}
        });
        
        // Собираем data-marker атрибуты
        document.querySelectorAll('[data-marker]').forEach(el => {
            analysis.data_attributes.add(el.getAttribute('data-marker'));
        });
        
        // Собираем паттерны классов
        document.querySelectorAll('[class*="styles-module"]').forEach(el => {
            el.className.split(' ').forEach(cls => {
                if (cls.includes('styles-module')) {
                    analysis.class_patterns.add(cls);
                }
            });
        });
        
        // Ищем текстовые элементы, которые могут быть именами
        const textElements = Array.from(document.querySelectorAll('*')).filter(el => {
            const text = el.textContent?.trim();
            return text && text.length > 5 && text.length < 100 && 
                   !text.includes('₽') && !text.includes('руб') &&
                   !text.includes('город') && !text.includes('область');
        });
        
        return {
            ...analysis,
            data_attributes: Array.from(analysis.data_attributes),
            class_patterns: Array.from(analysis.class_patterns).slice(0, 20),
            sample_text_elements: textElements.slice(0, 10).map(el => ({
                tag: el.tagName,
                text: el.textContent?.trim(),
                classes: el.className
            }))
        };
    }
    """
    
    try:
        analysis = page.evaluate(analysis_js)
        log_with_time(f"📊 Найдено {analysis['total_elements']} элементов на странице")
        log_with_time(f"🎯 Возможные карточки:")
        
        for card in analysis['possible_cards']:
            log_with_time(f"   {card['selector']}: {card['count']} элементов")
        
        if analysis['data_attributes']:
            log_with_time(f"🏷️ data-marker атрибуты: {analysis['data_attributes'][:10]}")
        
        if analysis['class_patterns']:
            log_with_time(f"🎨 Паттерны классов: {analysis['class_patterns'][:10]}")
            
        return analysis
    except Exception as e:
        log_with_time(f"❌ Ошибка анализа: {e}")
        return {}

def find_best_selector(page, selectors_list, element_type="элемент"):
    """Находит лучший селектор из списка вариантов"""
    best_selector = None
    max_count = 0
    
    for selector in selectors_list:
        try:
            count = page.evaluate(f'() => document.querySelectorAll(\'{selector}\').length')
            if count > max_count:
                max_count = count
                best_selector = selector
        except:
            continue
    
    if best_selector:
        log_with_time(f"✅ Лучший селектор для {element_type}: '{best_selector}' ({max_count} элементов)")
    else:
        log_with_time(f"❌ Не найден рабочий селектор для {element_type}")
    
    return best_selector

def count_cards(page):
    """Подсчет карточек резюме с автоматическим выбором селектора"""
    best_selector = find_best_selector(page, CARD_SELECTORS, "карточек")
    if best_selector:
        try:
            return page.evaluate(f'() => document.querySelectorAll(\'{best_selector}\').length')
        except:
            pass
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
                    pagination_end: false,
                    scroll_at_bottom: false,
                    empty_space: false,
                    active_load_buttons: 0
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
                    'больше результатов нет', 'результаты закончились',
                    'показаны все резюме', 'загружены все резюме'
                ];
                
                const bodyText = document.body.textContent.toLowerCase();
                indicators.no_more_text = endTexts.some(text => bodyText.includes(text));
                
                // Проверка скролла
                const scrollTop = window.pageYOffset;
                const scrollHeight = document.documentElement.scrollHeight;
                const clientHeight = window.innerHeight;
                
                indicators.scroll_at_bottom = (scrollTop + clientHeight + 100) >= scrollHeight;
                
                return indicators;
            }
        """)
        
        return end_indicators
    except Exception as e:
        log_with_time(f"⚠️ Ошибка определения конца страницы: {e}")
        return {"active_load_buttons": 999, "no_more_text": False, "scroll_at_bottom": False}

def smart_scroll_to_load_all(page, target_count=None, max_time_sec=180):
    """
    УМНЫЙ скроллинг с автоматическим обнаружением селекторов
    """
    log_with_time(f"🚀 УМНЫЙ скроллинг v7 (цель: {target_count or 'ВСЕ'}, лимит: {max_time_sec}с)")
    
    start_time = time.time()
    deadline = start_time + max_time_sec
    
    last_count = 0
    last_height = 0
    no_change_count = 0
    iteration = 0
    last_log_time = start_time
    
    initial_count = count_cards(page)
    initial_height = page.evaluate("document.documentElement.scrollHeight")
    log_with_time(f"📋 Стартовое количество: {initial_count} резюме, высота: {initial_height}px")
    
    while time.time() < deadline:
        iteration += 1
        current_count = count_cards(page)
        current_height = page.evaluate("document.documentElement.scrollHeight")
        current_time = time.time()
        
        # Логируем прогресс
        if current_count > last_count or current_height > last_height or (current_time - last_log_time) > 5:
            if current_count > last_count or current_height > last_height:
                count_progress = current_count - last_count
                height_progress = current_height - last_height
                log_with_time(f"📈 +{count_progress} = {current_count} резюме, высота: {current_height}px (+{height_progress}) [итерация {iteration}]")
                last_count = current_count
                last_height = current_height
                no_change_count = 0
            else:
                log_with_time(f"⏳ {current_count} резюме, высота: {current_height}px [итерация {iteration}, стабильно: {no_change_count}]")
                no_change_count += 1
            last_log_time = current_time
            
            # Проверяем достижение цели
            if target_count and current_count >= target_count:
                log_with_time(f"🎯 ЦЕЛЬ ДОСТИГНУТА: {current_count} >= {target_count}")
                break
        
        # Проверяем признаки конца страницы
        end_indicators = detect_end_of_page(page)
        if (end_indicators['no_more_text'] or 
            (end_indicators['scroll_at_bottom'] and end_indicators['active_load_buttons'] == 0)):
            log_with_time("🏁 Достигнут конец страницы")
            break
        
        try:
            # Плавный скролл вниз
            page.evaluate("""
                window.scrollBy({
                    top: window.innerHeight * 0.8,
                    behavior: 'smooth'
                });
            """)
            
            time.sleep(0.3)
            
            # Дополнительный скролл для надежности
            if iteration % 5 == 0:
                page.keyboard.press("PageDown")
                time.sleep(0.2)
            
            # Периодический "встряхивающий" скролл
            if no_change_count >= 3:
                log_with_time("💫 Встряска: скролл вверх-вниз")
                page.evaluate("window.scrollBy(0, -500)")
                time.sleep(0.3)
                page.evaluate("window.scrollBy(0, 1000)")
                time.sleep(0.5)
                no_change_count = 0
            
            # Ожидание сети
            if iteration % 10 == 0:
                wait_for_network_idle(page, timeout_ms=1000)
                
        except Exception as e:
            log_with_time(f"⚠️ Ошибка в итерации {iteration}: {e}")
            time.sleep(0.5)
        
        # Защита от зависания
        if no_change_count >= STABLE_GROWTH_ROUNDS:
            log_with_time(f"🔄 {no_change_count} итераций без изменений - экстремальные меры")
            
            try:
                # Принудительное нажатие кнопок
                clicked = page.evaluate("""
                    () => {
                        const buttons = document.querySelectorAll('button, a, [role="button"]');
                        let clicked = false;
                        for (const btn of buttons) {
                            const text = btn.textContent.toLowerCase();
                            if (text.includes('ещё') || text.includes('загруз') || text.includes('показать')) {
                                try {
                                    btn.click();
                                    clicked = true;
                                    console.log('Кликнул:', text);
                                    break;
                                } catch(e) {}
                            }
                        }
                        return clicked;
                    }
                """)
                
                if clicked:
                    log_with_time("✅ Кликнул кнопку загрузки")
                    time.sleep(2.0)
                
                no_change_count = 0
                
            except Exception as e:
                log_with_time(f"⚠️ Экстремальные меры не сработали: {e}")
    
    final_count = count_cards(page)
    total_elapsed = time.time() - start_time
    
    log_with_time(f"🏁 УМНЫЙ скроллинг завершен!")
    log_with_time(f"📊 Итого: {final_count} резюме за {total_elapsed:.1f}с ({iteration} итераций)")
    log_with_time(f"⚡ Скорость: {final_count/total_elapsed:.1f} резюме/сек")
    
    return final_count

def extract_resume_data_smart(page):
    """Умное извлечение данных с автоматическим подбором селекторов"""
    log_with_time("📊 Умное извлечение данных резюме...")
    
    # Сначала находим лучший селектор для карточек
    best_card_selector = find_best_selector(page, CARD_SELECTORS, "карточек")
    if not best_card_selector:
        log_with_time("❌ Не удалось найти селектор для карточек")
        return []
    
    # Находим лучшие селекторы для каждого типа данных
    best_data_selectors = {}
    for data_type, selectors in DATA_SELECTORS.items():
        # Тестируем селекторы в контексте первой карточки
        test_js = f"""
        () => {{
            const firstCard = document.querySelector('{best_card_selector}');
            if (!firstCard) return 0;
            
            let maxCount = 0;
            let bestSelector = null;
            
            {json.dumps(selectors)}.forEach(selector => {{
                try {{
                    const elements = firstCard.querySelectorAll(selector);
                    if (elements.length > maxCount) {{
                        maxCount = elements.length;
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
                log_with_time(f"✅ Лучший селектор для {data_type}: '{result['selector']}'")
            else:
                log_with_time(f"⚠️ Не найден селектор для {data_type}")
        except Exception as e:
            log_with_time(f"❌ Ошибка поиска селектора для {data_type}: {e}")
    
    # Извлекаем данные с найденными селекторами
    extract_js = f"""
    () => {{
        const cards = document.querySelectorAll('{best_card_selector}');
        const results = [];
        const selectors = {json.dumps(best_data_selectors)};
        
        cards.forEach((card, index) => {{
            try {{
                const data = {{
                    index: index + 1,
                    name: '',
                    link: '',
                    resume_id: '',
                    salary: '',
                    location: '',
                    date: '',
                    visible: card.getBoundingClientRect().top < window.innerHeight
                }};
                
                // Извлекаем каждый тип данных
                for (const [dataType, selector] of Object.entries(selectors)) {{
                    try {{
                        if (dataType === 'link') {{
                            const linkEl = card.querySelector(selector);
                            if (linkEl) {{
                                data.link = linkEl.href || linkEl.getAttribute('href') || '';
                                const match = data.link.match(/resume\\/([^?\\/]+)/);
                                data.resume_id = match ? match[1] : '';
                            }}
                        }} else {{
                            const el = card.querySelector(selector);
                            if (el) {{
                                data[dataType] = el.textContent?.trim() || '';
                            }}
                        }}
                    }} catch(e) {{
                        console.error(`Error extracting ${{dataType}}:`, e);
                    }}
                }}
                
                // Если данные пустые, пробуем альтернативные методы
                if (!data.name) {{
                    // Ищем любой текстовый элемент, который может быть именем
                    const textElements = card.querySelectorAll('h1, h2, h3, h4, h5, h6, a, span, div');
                    for (const el of textElements) {{
                        const text = el.textContent?.trim();
                        if (text && text.length > 5 && text.length < 100 && 
                            !text.includes('₽') && !text.includes('руб') &&
                            !text.match(/\\d{{2}}\\.\\d{{2}}\\.\\d{{4}}/)) {{
                            data.name = text;
                            break;
                        }}
                    }}
                }}
                
                if (!data.link) {{
                    // Ищем любую ссылку
                    const linkEl = card.querySelector('a[href]');
                    if (linkEl) {{
                        data.link = linkEl.href;
                        const match = data.link.match(/resume\\/([^?\\/]+)/);
                        data.resume_id = match ? match[1] : '';
                    }}
                }}
                
                results.push(data);
            }} catch (e) {{
                console.error('Error processing card:', e);
                results.push({{
                    index: index + 1,
                    name: '',
                    link: '',
                    resume_id: '',
                    salary: '',
                    location: '',
                    date: '',
                    visible: false,
                    error: e.message
                }});
            }}
        }});
        
        return results;
    }}
    """
    
    try:
        data = page.evaluate(extract_js)
        valid_data = [item for item in data if item.get('name') or item.get('link')]
        log_with_time(f"✅ Извлечено {len(data)} записей, {len(valid_data)} с данными")
        
        # Показываем пример найденных данных
        if valid_data:
            sample = valid_data[0]
            log_with_time(f"🔍 Пример: {sample.get('name', 'Нет имени')[:30]}... | {sample.get('link', 'Нет ссылки')[:50]}...")
        
        return data
    except Exception as e:
        log_with_time(f"❌ Ошибка извлечения данных: {e}")
        return []

def test_browser_performance_v7():
    """Основная функция тестирования v7 - умное извлечение"""
    log_with_time("🎭 Запуск умного тестирования браузерной части v7")
    
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
                "--force-device-scale-factor=0.6",
                "--window-size=1200,800"
            ],
        )
        
        context.set_default_timeout(NAV_TIMEOUT)
        page = context.new_page()
        page.add_init_script("document.body.style.zoom = '0.6'")
        
        try:
            log_with_time("🌐 Переходим на страницу Avito...")
            page.goto(TARGET_URL, wait_until="domcontentloaded")
            
            input("\n🔑 Войдите в Avito и нажмите Enter для продолжения...\n")
            
            # Анализируем структуру страницы
            analyze_page_structure(page)
            
            # Начальный подсчет
            initial_count = count_cards(page)
            log_with_time(f"📋 Начальное количество резюме: {initial_count}")
            
            # Тест полной загрузки
            log_with_time(f"\n{'='*60}")
            log_with_time(f"🧪 ТЕСТ v7: умная загрузка всех резюме")
            log_with_time(f"{'='*60}")
            
            start_time = time.time()
            
            # Умный скроллинг
            final_count = smart_scroll_to_load_all(page, target_count=None)
            
            # Извлечение данных
            data = extract_resume_data_smart(page)
            
            elapsed = time.time() - start_time
            
            # Результаты теста
            log_with_time(f"⏱️ Время выполнения: {elapsed:.1f}с")
            log_with_time(f"📊 Загружено резюме: {final_count}")
            log_with_time(f"📊 Извлечено данных: {len(data)}")
            log_with_time(f"⚡ Скорость: {final_count/elapsed:.1f} резюме/сек")
            
            # Анализ качества данных
            valid_names = sum(1 for item in data if item.get('name'))
            valid_links = sum(1 for item in data if item.get('link'))
            
            log_with_time(f"📈 Качество данных:")
            log_with_time(f"   Имена: {valid_names}/{len(data)} ({valid_names/len(data)*100:.1f}%)")
            log_with_time(f"   Ссылки: {valid_links}/{len(data)} ({valid_links/len(data)*100:.1f}%)")
            
            # Сохранение результатов
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"browser_test_v7_smart_{timestamp}.json"
            
            result = {
                "test_params": {
                    "version": "v7_smart",
                    "timestamp": timestamp,
                    "duration_seconds": elapsed
                },
                "performance": {
                    "cards_loaded": final_count,
                    "data_extracted": len(data),
                    "speed_per_second": final_count/elapsed,
                    "data_quality": {
                        "valid_names": valid_names,
                        "valid_links": valid_links,
                        "name_percentage": valid_names/len(data)*100 if data else 0,
                        "link_percentage": valid_links/len(data)*100 if data else 0
                    }
                },
                "sample_data": data[:10],  # Первые 10 записей
                "full_data": data  # Все данные
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            log_with_time(f"💾 Результаты сохранены в {filename}")
            
        except Exception as e:
            log_with_time(f"❌ Ошибка: {e}")
        finally:
            log_with_time("🏁 Умное тестирование завершено")

if __name__ == "__main__":
    test_browser_performance_v7()