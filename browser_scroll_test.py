# browser_scroll_test.py
# -*- coding: utf-8 -*-
"""
Тестовый скрипт для отладки и оптимизации браузерной части загрузки Avito резюме.
Фокус на скорости и надежности скроллинга.
"""

from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright, Error as PwError
import time
import json

# Конфигурация
USER_DATA_DIR = Path("./avito_browser_profile").resolve()
TARGET_URL = "https://www.avito.ru/profile/paid-cvs"

# Быстрые константы без лишних ожиданий
MAX_TOTAL_SCROLL_SEC = 180  # Вернем к разумному лимиту
QUIET_MS = 1000             # Уменьшим ожидания
STABLE_GROWTH_ROUNDS = 15   # Компромисс между скоростью и полнотой
MAX_ACTIVE_BUTTON_ITERATIONS = 200  # Максимум итераций для активных кнопок
NAV_TIMEOUT = 30_000        # Быстрые таймауты

# Улучшенные селекторы для более точного обнаружения
CARD_SELECTOR = '[data-marker="cv-snippet"]'
MORE_BUTTON_PATTERNS = [
    'button:has-text("Показать ещё")',
    'button:has-text("ещё")', 
    'button:has-text("Загрузить ещё")',
    'a:has-text("Показать ещё")',
    '[data-marker*="load-more"]',
    '[data-marker*="show-more"]'
]

def log_with_time(msg):
    """Логирование с временной меткой"""
    print(f"🕐 [{datetime.now().strftime('%H:%M:%S')}] {msg}")

def detect_end_of_page(page):
    """Обнаруживает признаки конца страницы с приоритетом активных кнопок"""
    try:
        end_indicators = page.evaluate("""
            () => {
                // Ищем различные индикаторы конца страницы
                const indicators = {
                    footer_visible: false,
                    no_more_text: false,
                    pagination_end: false,
                    scroll_at_bottom: false,
                    empty_space: false,
                    active_load_buttons: 0  // ВАЖНО: счетчик активных кнопок
                };
                
                // 1. ПРИОРИТЕТ: Подсчет активных кнопок "Ещё"
                const moreButtons = document.querySelectorAll('button, a, [role="button"]');
                for (const btn of moreButtons) {
                    const text = btn.textContent.toLowerCase().trim();
                    if (text.includes('ещё') && btn.offsetParent !== null && 
                        !btn.disabled && !btn.getAttribute('aria-disabled')) {
                        indicators.active_load_buttons++;
                    }
                }
                
                // Если есть активные кнопки "Ещё" - НЕ конец страницы!
                if (indicators.active_load_buttons > 0) {
                    console.log(`[DETECT] Найдено ${indicators.active_load_buttons} активных кнопок "Ещё" - продолжаем`);
                    return indicators; // Возвращаем сразу, остальное не важно
                }
                
                // 2. Поиск футера или элементов конца (только если нет кнопок)
                const footerSelectors = [
                    'footer', '.footer', '[class*="footer"]',
                    '.pagination-end', '.no-results', '.end-of-list',
                    '[class*="nothing-found"]', '[class*="no-more"]',
                    'div:contains("больше резюме нет")', 
                    'div:contains("конец списка")',
                    'div:contains("все резюме загружены")'
                ];
                
                for (const selector of footerSelectors) {
                    try {
                        const elements = document.querySelectorAll(selector);
                        for (const el of elements) {
                            if (el.offsetParent !== null) { // элемент видимый
                                const rect = el.getBoundingClientRect();
                                if (rect.top < window.innerHeight) {
                                    indicators.footer_visible = true;
                                    break;
                                }
                            }
                        }
                        if (indicators.footer_visible) break;
                    } catch(e) {}
                }
                
                // 3. Поиск текста о том что больше нет результатов
                const bodyText = document.body.textContent.toLowerCase();
                const noMorePatterns = [
                    'больше резюме нет', 'конец списка', 'все резюме загружены',
                    'больше результатов нет', 'результаты закончились',
                    'показаны все резюме', 'загружены все резюме',
                    'no more results', 'end of list', 'nothing found'
                ];
                
                indicators.no_more_text = noMorePatterns.some(pattern => 
                    bodyText.includes(pattern)
                );
                
                // 4. Проверка позиции скролла
                const scrollTop = window.pageYOffset;
                const scrollHeight = document.documentElement.scrollHeight;
                const clientHeight = window.innerHeight;
                
                indicators.scroll_at_bottom = (scrollTop + clientHeight + 100) >= scrollHeight;
                
                // 5. Проверка большого пустого пространства в конце
                const lastElement = document.querySelector('[data-marker="cv-snippet"]:last-child');
                if (lastElement) {
                    const lastRect = lastElement.getBoundingClientRect();
                    const bottomSpace = scrollHeight - (lastRect.bottom + scrollTop);
                    indicators.empty_space = bottomSpace > window.innerHeight * 2; // больше 2 экранов пустоты
                }
                
                // 6. Проверка кнопок пагинации
                const paginationButtons = document.querySelectorAll(
                    'button:disabled, .pagination .disabled, [aria-disabled="true"]'
                );
                indicators.pagination_end = paginationButtons.length > 0;
                
                return indicators;
            }
        """)
        
        return end_indicators
    except Exception as e:
        log_with_time(f"⚠️ Ошибка определения конца страницы: {e}")
        return {"footer_visible": False, "no_more_text": False, "pagination_end": False, 
                "scroll_at_bottom": False, "empty_space": False, "active_load_buttons": 999}

def count_cards(page):
    """Подсчет карточек резюме"""
    try:
        return page.evaluate(f'() => document.querySelectorAll(\'{CARD_SELECTOR}\').length')
    except Exception:
        return 0

def wait_for_network_idle(page, timeout_ms=3000):
    """Ожидание завершения сетевых запросов"""
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
        return True
    except Exception:
        return False

def fast_scroll_to_load_all(page, target_count=None, max_time_sec=180):
    """
    БЫСТРЫЙ скроллинг для полной загрузки всех резюме v6
    
    Улучшения v6:
    - Автоматическая подгрузка при скролле (БЕЗ кнопок "Ещё")
    - Отслеживание высоты страницы как главного индикатора
    - Скролл вверх-вниз если загрузка застряла
    - Масштаб 60% для оптимизации
    """
    log_with_time(f"🚀 БЫСТРЫЙ скроллинг v6 - АВТОПОДГРУЗКА (цель: {target_count or 'ВСЕ'}, лимит: {max_time_sec}с)")
    
    start_time = time.time()
    deadline = start_time + max_time_sec
    
    last_count = 0
    last_height = 0
    no_height_change_rounds = 0
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
        
        # Логируем прогресс каждые 5 секунд или при изменениях
        if current_count > last_count or current_height > last_height or (current_time - last_log_time) > 5:
            if current_count > last_count or current_height > last_height:
                count_progress = current_count - last_count
                height_progress = current_height - last_height
                log_with_time(f"📈 +{count_progress} = {current_count} резюме, высота: {current_height}px (+{height_progress}) [итерация {iteration}]")
                last_count = current_count
                last_height = current_height
                no_height_change_rounds = 0
            else:
                log_with_time(f"⏳ {current_count} резюме, высота: {current_height}px [итерация {iteration}, стабильно: {no_height_change_rounds}]")
            last_log_time = current_time
            
            # Проверяем достижение цели
            if target_count and current_count >= target_count:
                log_with_time(f"🎯 ЦЕЛЬ ДОСТИГНУТА: {current_count} >= {target_count}")
                break
        
        # Основная логика: если высота не растет - застряли
        if current_height <= last_height:
            no_height_change_rounds += 1
        else:
            no_height_change_rounds = 0
        
        # Быстрая стратегия скроллинга
        try:
            # 1. Основной скролл вниз
            page.evaluate("window.scrollBy(0, 1500)")
            
            # 2. Каждые 3 итерации - скролл до конца для активации подгрузки
            if iteration % 3 == 0:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            
            # 3. Если высота долго не растет - делаем "встряску"
            if no_height_change_rounds > 0 and no_height_change_rounds % 5 == 0:
                log_with_time(f"� Встряска #{no_height_change_rounds // 5}: скролл вверх-вниз")
                # Скролл вверх
                page.evaluate("window.scrollBy(0, -800)")
                time.sleep(0.1)
                # Потом сразу вниз
                page.evaluate("window.scrollBy(0, 2000)")
                time.sleep(0.2)
            
            # 4. Каждые 10 итераций без роста высоты - экстремальные меры
            if no_height_change_rounds > 0 and no_height_change_rounds % 10 == 0:
                log_with_time(f"🚨 Экстремальная встряска #{no_height_change_rounds // 10}")
                # Прокручиваем в начало и обратно
                page.evaluate("window.scrollTo(0, 0)")
                time.sleep(0.3)
                page.keyboard.press("End")
                time.sleep(0.3)
                # Множественные скроллы для активации
                for shake in range(3):
                    page.evaluate("window.scrollBy(0, -1000)")
                    time.sleep(0.1)
                    page.evaluate("window.scrollBy(0, 2000)")
                    time.sleep(0.1)
            
            # 5. Минимальная пауза между итерациями
            time.sleep(0.05)
            
            # 6. Проверка сети только изредка
            if iteration % 50 == 0:
                wait_for_network_idle(page, timeout_ms=500)
                
        except Exception as e:
            if iteration % 100 == 0:
                log_with_time(f"⚠️ Ошибка в итерации {iteration}: {e}")
        
        # Условие выхода: очень долго нет роста высоты
        if no_height_change_rounds >= 30:  # 30 итераций без роста высоты
            log_with_time(f"� {no_height_change_rounds} итераций без роста высоты - финальная диагностика")
            
            # Финальная серия попыток
            log_with_time("🚀 Финальная серия попыток загрузки...")
            breakthrough = False
            for final_attempt in range(20):
                # Агрессивный скролл
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.keyboard.press("End")
                time.sleep(0.2)
                
                # Встряски для активации
                page.evaluate("window.scrollBy(0, -1500)")
                time.sleep(0.1)
                page.evaluate("window.scrollBy(0, 3000)")
                time.sleep(0.3)
                
                new_count = count_cards(page)
                new_height = page.evaluate("document.documentElement.scrollHeight")
                
                if new_count > current_count or new_height > current_height:
                    log_with_time(f"✅ Финальная попытка {final_attempt + 1}: +{new_count - current_count} резюме, +{new_height - current_height}px")
                    breakthrough = True
                    no_height_change_rounds = 0
                    break
                    
            if not breakthrough:
                log_with_time(f"🛑 Все {final_attempt + 1} финальных попыток исчерпаны")
                break
    
    final_count = count_cards(page)
    total_elapsed = time.time() - start_time
    
    # Финальная диагностика
    final_end_check = detect_end_of_page(page)
    
    # ДЕТАЛЬНАЯ диагностика состояния страницы
    page_diagnostics = page.evaluate("""
        () => {
            const diagnostics = {
                total_height: Math.max(document.body.scrollHeight, document.documentElement.scrollHeight),
                current_scroll: window.pageYOffset,
                viewport_height: window.innerHeight,
                cards_total: document.querySelectorAll('[data-marker="cv-snippet"]').length,
                
                // Поиск текста о завершении
                page_text_indicators: [],
                
                // Поиск кнопок загрузки
                load_buttons: [],
                
                // Поиск пагинации
                pagination_info: {},
                
                // Последние элементы на странице
                last_elements: []
            };
            
            // Анализ текста страницы
            const bodyText = document.body.textContent.toLowerCase();
            const endPatterns = [
                'больше резюме нет', 'конец списка', 'все резюме загружены',
                'больше результатов нет', 'результаты закончились', 'показаны все резюме',
                'nothing found', 'no more results', 'end of list', 'все результаты'
            ];
            
            endPatterns.forEach(pattern => {
                if (bodyText.includes(pattern)) {
                    diagnostics.page_text_indicators.push(pattern);
                }
            });
            
            // Поиск кнопок загрузки
            const buttonSelectors = [
                'button:contains("Показать")', 'button:contains("ещё")', 'button:contains("Загрузить")',
                '[data-marker*="load"]', '[data-marker*="more"]', '[data-marker*="show"]',
                '.load-more', '.show-more', '.pagination'
            ];
            
            document.querySelectorAll('button, a, [role="button"]').forEach(btn => {
                const text = btn.textContent.toLowerCase().trim();
                if (text.includes('ещё') || text.includes('показать') || text.includes('загруз') || 
                    text.includes('больше') || text.includes('далее')) {
                    diagnostics.load_buttons.push({
                        text: text,
                        visible: btn.offsetParent !== null,
                        enabled: !btn.disabled && !btn.getAttribute('aria-disabled'),
                        classes: btn.className
                    });
                }
            });
            
            // Анализ пагинации
            const paginationElements = document.querySelectorAll('.pagination, [class*="pagination"], .paging, [class*="paging"]');
            if (paginationElements.length > 0) {
                diagnostics.pagination_info = {
                    found: true,
                    count: paginationElements.length,
                    texts: Array.from(paginationElements).map(el => el.textContent.trim()).slice(0, 3)
                };
            }
            
            // Последние элементы на странице
            const allElements = Array.from(document.body.querySelectorAll('*'));
            const lastElements = allElements.slice(-10); // Последние 10 элементов
            diagnostics.last_elements = lastElements.map(el => ({
                tag: el.tagName,
                text: el.textContent.trim().substring(0, 100),
                classes: el.className,
                visible: el.offsetParent !== null
            }));
            
            return diagnostics;
        }
    """)
    
    log_with_time(f"🏁 БЫСТРЫЙ скроллинг v5 завершен!")
    log_with_time(f"📊 Результат: {final_count} резюме за {total_elapsed:.1f}с ({iteration} итераций)")
    log_with_time(f"⚡ Скорость: {final_count/total_elapsed:.1f} резюме/сек")
    log_with_time(f"🔍 Признаки конца страницы: {final_end_check}")
    
    # ДЕТАЛЬНАЯ диагностика
    log_with_time("🔬 ДЕТАЛЬНАЯ ДИАГНОСТИКА:")
    log_with_time(f"📏 Высота страницы: {page_diagnostics['total_height']}px")
    log_with_time(f"📍 Текущий скролл: {page_diagnostics['current_scroll']}px")
    log_with_time(f"👁️ Высота окна: {page_diagnostics['viewport_height']}px")
    
    if page_diagnostics['page_text_indicators']:
        log_with_time(f"✅ Найдены текстовые индикаторы конца: {page_diagnostics['page_text_indicators']}")
    else:
        log_with_time("❌ НЕ найдены текстовые индикаторы конца списка")
    
    if page_diagnostics['load_buttons']:
        log_with_time(f"🔘 Найдены кнопки загрузки ({len(page_diagnostics['load_buttons'])}):")
        for btn in page_diagnostics['load_buttons'][:3]:  # Показываем первые 3
            log_with_time(f"   - '{btn['text']}' (видимая: {btn['visible']}, активная: {btn['enabled']})")
    else:
        log_with_time("✅ Кнопки загрузки НЕ найдены (хороший знак)")
    
    if page_diagnostics['pagination_info'].get('found'):
        log_with_time(f"📄 Пагинация найдена: {page_diagnostics['pagination_info']}")
    
    log_with_time("🔍 Последние элементы на странице:")
    for i, elem in enumerate(page_diagnostics['last_elements'][-5:]):  # Последние 5
        if elem['text']:
            log_with_time(f"   {i+1}. {elem['tag']}: '{elem['text'][:50]}...'")
    
    # Рекомендации
    scroll_position = page_diagnostics['current_scroll'] + page_diagnostics['viewport_height']
    page_height = page_diagnostics['total_height']
    scroll_percentage = (scroll_position / page_height) * 100
    
    log_with_time(f"📊 Прокручено: {scroll_percentage:.1f}% страницы")
    
    if scroll_percentage < 95:
        log_with_time("⚠️ ВНИМАНИЕ: Возможно НЕ дошли до конца страницы!")
    elif page_diagnostics['load_buttons']:
        log_with_time("⚠️ ВНИМАНИЕ: Остались активные кнопки загрузки!")
    elif not page_diagnostics['page_text_indicators']:
        log_with_time("⚠️ ВНИМАНИЕ: Не найдены явные признаки конца списка!")
    else:
        log_with_time("✅ Похоже, что действительно достигнут конец списка резюме")
    
    return final_count

def aggressive_scroll_to_load_all(page, target_count=None, max_time_sec=600):
    """
    АГРЕССИВНЫЙ скроллинг для ПОЛНОЙ загрузки всех резюме
    
    Новая стратегия v3:
    - НИКОГО РАННЕГО ЗАВЕРШЕНИЯ до достижения времени лимита
    - Принудительный скроллинг с множественными попытками
    - Постоянные попытки кликов кнопок
    - Детальное логирование каждого этапа
    """
    log_with_time(f"🚀 АГРЕССИВНЫЙ скроллинг v3 (цель: {target_count or 'ВСЕ'}, лимит: {max_time_sec}с)")
    
    start_time = time.time()
    deadline = start_time + max_time_sec
    
    last_count = 0
    no_change_count = 0
    iteration = 0
    
    log_with_time(f"📋 Стартовое количество резюме: {count_cards(page)}")
    
    while time.time() < deadline:
        iteration += 1
        current_count = count_cards(page)
        elapsed = time.time() - start_time
        
        if current_count > last_count:
            progress = current_count - last_count
            log_with_time(f"📈 Итерация {iteration}: +{progress} = {current_count} резюме [{elapsed:.1f}с]")
            last_count = current_count
            no_change_count = 0
            
            # Проверяем достижение цели ТОЛЬКО если она задана
            if target_count and current_count >= target_count:
                log_with_time(f"🎯 ЦЕЛЬ ДОСТИГНУТА: {current_count} >= {target_count}")
                # НО ПРОДОЛЖАЕМ еще немного для подстраховки
                extra_time = min(60, max_time_sec * 0.1)  # 10% от лимита или 60с
                log_with_time(f"⏰ Дополнительные {extra_time:.0f}с для подстраховки...")
                time.sleep(extra_time)
                break
        else:
            no_change_count += 1
            if iteration % 10 == 0:  # Логируем каждые 10 итераций без изменений
                log_with_time(f"⏳ Итерация {iteration}: без изменений ({no_change_count} подряд), резюме: {current_count}")
        
        # АГРЕССИВНАЯ стратегия: несколько типов скроллинга за раз
        try:
            # 1. Обычный скролл
            page.evaluate("window.scrollBy(0, 1000)")
            time.sleep(0.3)
            
            # 2. Скролл до конца страницы
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(0.5)
            
            # 3. Множественные попытки кликов кнопок
            for click_attempt in range(3):
                clicked = click_more_buttons(page)
                if clicked:
                    log_with_time(f"✅ Клик #{click_attempt + 1} успешен")
                    time.sleep(1.0)  # Ждем загрузки
                else:
                    time.sleep(0.2)
            
            # 4. Скролл вверх и снова вниз (иногда помогает)
            if iteration % 5 == 0:
                page.evaluate("window.scrollBy(0, -500)")
                time.sleep(0.2)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(0.5)
            
            # 5. Принудительная проверка высоты страницы
            if iteration % 10 == 0:
                page_height = page.evaluate("Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)")
                scroll_pos = page.evaluate("window.pageYOffset")
                log_with_time(f"� Высота страницы: {page_height}px, позиция: {scroll_pos}px")
            
            # 6. Ожидание сети только изредка чтобы не тормозить
            if iteration % 15 == 0:
                wait_for_network_idle(page, timeout_ms=1000)
                
        except Exception as e:
            log_with_time(f"⚠️ Ошибка в итерации {iteration}: {e}")
            time.sleep(0.5)
        
        # Проверяем, не зависла ли страница (долго без изменений)
        if no_change_count >= STABLE_GROWTH_ROUNDS:
            log_with_time(f"🔄 {no_change_count} итераций без изменений - пробуем экстремальные меры")
            
            # Экстремальные меры для "разблокировки" страницы
            try:
                # Нажимаем Page Down несколько раз
                for _ in range(5):
                    page.keyboard.press("PageDown")
                    time.sleep(0.3)
                
                # Принудительный рефреш элементов
                page.evaluate("""
                // Попробуем найти и кликнуть скрытые кнопки загрузки
                const buttons = document.querySelectorAll('button, a, [role="button"]');
                let clicked = false;
                for (const btn of buttons) {
                    const text = btn.textContent.toLowerCase();
                    if (text.includes('ещё') || text.includes('больше') || text.includes('показать') || 
                        text.includes('загруз') || text.includes('далее') || text.includes('продолжить')) {
                        try {
                            btn.click();
                            clicked = true;
                            console.log('Принудительно кликнул:', text);
                        } catch(e) {}
                    }
                }
                return clicked;
                """)
                
                time.sleep(2.0)  # Даем время на загрузку
                no_change_count = 0  # Сбрасываем счетчик
                
            except Exception as e:
                log_with_time(f"⚠️ Экстремальные меры не сработали: {e}")
    
    final_count = count_cards(page)
    total_elapsed = time.time() - start_time
    
    log_with_time(f"🏁 АГРЕССИВНЫЙ скроллинг завершен!")
    log_with_time(f"📊 Итого: {final_count} резюме за {total_elapsed:.1f}с ({iteration} итераций)")
    log_with_time(f"⚡ Скорость: {final_count/total_elapsed:.1f} резюме/сек")
    
    return final_count

def extract_resume_data(page):
    """Извлечение данных резюме из страницы"""
    log_with_time("📊 Извлекаем данные резюме...")
    
    extract_js = f"""
    () => {{
        const cards = document.querySelectorAll('{CARD_SELECTOR}');
        const results = [];
        
        cards.forEach((card, index) => {{
            try {{
                const nameEl = card.querySelector('[data-marker="cv-snippet-name"]');
                const linkEl = card.querySelector('a[href*="/resume/"]');
                const salaryEl = card.querySelector('[data-marker="cv-snippet-salary"]');
                const locationEl = card.querySelector('[data-marker="cv-snippet-location"]');
                const dateEl = card.querySelector('[data-marker="cv-snippet-date"]');
                
                results.push({{
                    index: index + 1,
                    name: nameEl?.textContent?.trim() || '',
                    link: linkEl?.href || '',
                    resume_id: linkEl?.href?.match(/resume\\/([^?]+)/)?.[1] || '',
                    salary: salaryEl?.textContent?.trim() || '',
                    location: locationEl?.textContent?.trim() || '',
                    date: dateEl?.textContent?.trim() || '',
                    visible: card.getBoundingClientRect().top < window.innerHeight
                }});
            }} catch (e) {{
                console.error('Error processing card:', e);
            }}
        }});
        
        return results;
    }}
    """
    
    try:
        data = page.evaluate(extract_js)
        log_with_time(f"✅ Извлечено {len(data)} записей")
        return data
    except Exception as e:
        log_with_time(f"❌ Ошибка извлечения данных: {e}")
        return []

def test_browser_performance():
    """Основная функция тестирования v6 - автоподгрузка без кнопок"""
    log_with_time("🎭 Запуск тестирования браузерной части v6")
    
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    with sync_playwright() as p:
        # Запуск браузера с масштабом 60% и отключением картинок
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            viewport={"width": 1200, "height": 800},  # Уменьшенное окно
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-web-security",
                "--disable-features=VizDisplayCompositor",
                "--disable-ipc-flooding-protection",
                "--disable-renderer-backgrounding",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--blink-settings=imagesEnabled=false",  # Отключаем картинки
                "--disable-images",                       # Дополнительное отключение
                "--disable-plugins",
                "--disable-extensions",
                "--force-device-scale-factor=0.6",      # МАСШТАБ 60%
                "--window-size=1200,800"                 # Уменьшенное окно
            ],
        )
        
        context.set_default_timeout(NAV_TIMEOUT)
        context.set_default_navigation_timeout(NAV_TIMEOUT)
        page = context.new_page()
        
        # Дополнительно устанавливаем масштаб через JavaScript
        page.add_init_script("document.body.style.zoom = '0.6'")
        
        try:
            log_with_time("🌐 Переходим на страницу Avito...")
            page.goto(TARGET_URL, wait_until="domcontentloaded")
            
            input("\\n🔑 Войдите в Avito и нажмите Enter для продолжения...\\n")
            
            # Начальный подсчет
            initial_count = count_cards(page)
            log_with_time(f"📋 Начальное количество резюме: {initial_count}")
            
            # Тестируем разные лимиты - без кнопок, только автоподгрузка
            test_limits = [100, 500, None]  # None = все резюме
            
            for limit in test_limits:
                log_with_time(f"\\n{'='*60}")
                log_with_time(f"🧪 ТЕСТ v6: загрузка до {limit or 'всех'} резюме (автоподгрузка)")
                log_with_time(f"{'='*60}")
                
                start_time = time.time()
                
                # Сброс страницы
                page.reload(wait_until="domcontentloaded")
                time.sleep(2)
                
                # Быстрый скроллинг v6 без поиска кнопок
                final_count = fast_scroll_to_load_all(page, target_count=limit)
                
                # Извлечение данных
                data = extract_resume_data(page)
                
                elapsed = time.time() - start_time
                
                # Результаты теста
                log_with_time(f"⏱️ Время выполнения: {elapsed:.1f}с")
                log_with_time(f"📊 Загружено резюме: {final_count}")
                log_with_time(f"📊 Извлечено данных: {len(data)}")
                log_with_time(f"⚡ Скорость: {final_count/elapsed:.1f} резюме/сек")
                
                # Сохранение результатов теста
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"browser_test_{limit or 'all'}_{timestamp}.json"
                
                result = {
                    "test_params": {
                        "limit": limit,
                        "timestamp": timestamp,
                        "duration_seconds": elapsed
                    },
                    "performance": {
                        "cards_loaded": final_count,
                        "data_extracted": len(data),
                        "speed_per_second": final_count/elapsed
                    },
                    "data": data[:10]  # Первые 10 записей для примера
                }
                
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                
                log_with_time(f"💾 Результаты сохранены в {filename}")
                
                if limit is None:  # Для теста "все резюме" делаем только один прогон
                    break
                    
                input("\\n⏸️ Нажмите Enter для следующего теста...\\n")
        
        except Exception as e:
            log_with_time(f"❌ Ошибка: {e}")
        finally:
            log_with_time("🏁 Тестирование завершено")

if __name__ == "__main__":
    test_browser_performance()