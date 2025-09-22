# 🔧 Technical Implementation Details

## Архитектурные решения и техническая реализация

### 1. 🌐 Browser Automation Architecture

#### Playwright Configuration
```python
# Настройка персистентного контекста браузера
browser_context = playwright.chromium.launch_persistent_context(
    user_data_dir="./avito_browser_profile",
    headless=False,  # Визуальный режим для отладки
    viewport={"width": 1920, "height": 1080},
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
)
```

#### JavaScript Injection Patterns
```javascript
// Блокировка навигации по ссылкам чатов
function blockChatClicks() {
    const chatLinks = document.querySelectorAll('a[href*="/profile/messenger/channel/"]');
    chatLinks.forEach(link => {
        link.style.pointerEvents = 'none';
        link.style.opacity = '0.7';
        link.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            console.log('🚫 Навигация заблокирована:', link.href);
        });
    });
    return chatLinks.length;
}

// Мониторинг изменений URL
function setupURLMonitor(targetUrl) {
    const originalPushState = history.pushState;
    const originalReplaceState = history.replaceState;
    
    history.pushState = function(...args) {
        console.log('🔄 URL изменен (pushState):', args[2]);
        if (!window.location.href.includes(targetUrl)) {
            console.warn('⚠️ Обнаружен переход с целевой страницы!');
        }
        return originalPushState.apply(history, args);
    };
    
    history.replaceState = function(...args) {
        console.log('🔄 URL изменен (replaceState):', args[2]);
        return originalReplaceState.apply(history, args);
    };
}
```

#### Aggressive Scrolling Algorithm
```python
async def aggressive_scroll_with_bounce(page, duration_minutes=15):
    """
    Агрессивный скроллинг с имитацией человеческого поведения
    
    Особенности:
    - Рандомизированные шаги скроллинга (500-1000px)
    - Периодические откаты назад (300-700px)
    - Варьируемые задержки (1-3 секунды)
    - Мониторинг новых элементов
    """
    start_time = time.time()
    last_height = 0
    unique_chats = set()
    
    while time.time() - start_time < duration_minutes * 60:
        # Основной скроллинг
        scroll_step = 500 + random.randint(0, 500)  # 500-1000px
        await page.evaluate(f"window.scrollBy(0, {scroll_step})")
        
        # Рандомизированный откат (30% вероятность)
        if random.random() < 0.3:
            bounce_back = 300 + random.randint(0, 400)  # 300-700px
            await asyncio.sleep(0.2)
            await page.evaluate(f"window.scrollBy(0, -{bounce_back})")
        
        # Проверка новых чатов
        new_chats = await extract_unique_chat_links(page)
        unique_chats.update(new_chats)
        
        # Динамическая задержка
        delay = 1 + random.random() * 2  # 1-3 секунды
        await asyncio.sleep(delay)
        
        # Проверка достижения конца страницы
        current_height = await page.evaluate("document.body.scrollHeight")
        if current_height == last_height:
            console.log(f"🔄 Достигнут конец страницы. Найдено {len(unique_chats)} чатов")
            break
        last_height = current_height
    
    return list(unique_chats)
```

### 2. ⚡ Multi-threading API Architecture

#### ThreadPoolExecutor Configuration
```python
import concurrent.futures
from threading import Lock
import threading

class ThreadSafeAPIProcessor:
    def __init__(self, max_workers=20):
        self.max_workers = max_workers
        self.rate_limit_lock = Lock()
        self.last_request_time = threading.local()
        self.request_count = threading.local()
        
    def process_chats_parallel(self, chat_ids):
        """
        Многопоточная обработка чатов с rate limiting
        """
        results = []
        errors = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Создаем задачи
            future_to_chat = {
                executor.submit(self.process_single_chat, chat_id): chat_id 
                for chat_id in chat_ids
            }
            
            # Обрабатываем результаты
            for future in concurrent.futures.as_completed(future_to_chat):
                chat_id = future_to_chat[future]
                try:
                    result = future.result(timeout=30)
                    if result:
                        results.append(result)
                except Exception as exc:
                    error_info = {
                        'chat_id': chat_id,
                        'error': str(exc),
                        'timestamp': datetime.now().isoformat()
                    }
                    errors.append(error_info)
                    print(f"❌ Ошибка обработки {chat_id}: {exc}")
        
        return results, errors
```

#### Rate Limiting Implementation
```python
def respect_rate_limit(self):
    """
    Интеллектуальный rate limiting с адаптивными задержками
    """
    with self.rate_limit_lock:
        if not hasattr(self.last_request_time, 'value'):
            self.last_request_time.value = 0
            self.request_count.value = 0
        
        current_time = time.time()
        time_since_last = current_time - self.last_request_time.value
        
        # Базовая задержка между запросами
        min_delay = 0.1  # 100ms между запросами
        
        # Адаптивная задержка при высокой нагрузке
        if self.request_count.value > 100:  # После 100 запросов
            min_delay = 0.5  # Увеличиваем до 500ms
        elif self.request_count.value > 200:  # После 200 запросов
            min_delay = 1.0  # Увеличиваем до 1s
        
        if time_since_last < min_delay:
            sleep_time = min_delay - time_since_last
            time.sleep(sleep_time)
        
        self.last_request_time.value = time.time()
        self.request_count.value += 1
```

### 3. 🔐 Authentication & Security

#### OAuth2 Client Credentials Flow
```python
class AvitoAuthenticator:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.token_expires_at = 0
        
    def get_access_token(self):
        """
        Получение access token с автоматическим обновлением
        """
        if self.access_token and time.time() < self.token_expires_at - 60:
            return self.access_token
        
        auth_url = "https://api.avito.ru/token"
        auth_data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        
        response = requests.post(auth_url, data=auth_data)
        response.raise_for_status()
        
        token_data = response.json()
        self.access_token = token_data["access_token"]
        self.token_expires_at = time.time() + token_data["expires_in"]
        
        return self.access_token
```

#### Request Authentication Wrapper
```python
def authenticated_request(self, method, url, **kwargs):
    """
    Обертка для HTTP запросов с автоматической аутентификацией
    """
    headers = kwargs.get('headers', {})
    headers['Authorization'] = f'Bearer {self.get_access_token()}'
    headers['Content-Type'] = 'application/json'
    kwargs['headers'] = headers
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.request(method, url, **kwargs)
            
            # Обработка ошибок аутентификации
            if response.status_code == 401:
                print("🔄 Токен истек, обновляем...")
                self.access_token = None  # Форсируем обновление
                headers['Authorization'] = f'Bearer {self.get_access_token()}'
                response = requests.request(method, url, **kwargs)
            
            response.raise_for_status()
            return response
            
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise
            print(f"⚠️ Попытка {attempt + 1} неудачна: {e}")
            time.sleep(2 ** attempt)  # Exponential backoff
```

### 4. 🎯 Chat ID Pattern Extraction

#### Complex Pattern Matching
```python
import base64
import re
from typing import Optional, Dict, Any

class ChatIDProcessor:
    
    # Паттерны для различных форматов chat_id
    PATTERNS = {
        'a2u': re.compile(r'^a2u-(\d+)-.*$'),
        'u2i': re.compile(r'^u2i-(.+)$'),
        'direct': re.compile(r'^\d+$')
    }
    
    @classmethod
    def extract_user_id(cls, chat_id: str) -> Optional[str]:
        """
        Универсальное извлечение user_id из различных форматов
        """
        if not chat_id:
            return None
            
        # Прямой числовой ID
        if cls.PATTERNS['direct'].match(chat_id):
            return chat_id
            
        # Формат a2u-USER_ID-ANOTHER_ID
        a2u_match = cls.PATTERNS['a2u'].match(chat_id)
        if a2u_match:
            return a2u_match.group(1)
            
        # Формат u2i-ENCODED_ID
        u2i_match = cls.PATTERNS['u2i'].match(chat_id)
        if u2i_match:
            return cls._decode_u2i_format(u2i_match.group(1))
            
        return None
    
    @classmethod
    def _decode_u2i_format(cls, encoded_part: str) -> Optional[str]:
        """
        Декодирование u2i формата
        """
        try:
            # Добавляем padding если необходимо
            padded = encoded_part + '=' * (4 - len(encoded_part) % 4)
            decoded_bytes = base64.b64decode(padded)
            decoded_str = decoded_bytes.decode('utf-8')
            
            # Ищем числовые паттерны в декодированной строке
            numbers = re.findall(r'\d+', decoded_str)
            if numbers:
                # Возвращаем самое длинное число (скорее всего user_id)
                return max(numbers, key=len)
                
        except Exception as e:
            print(f"⚠️ Ошибка декодирования u2i: {e}")
            
        return None
```

### 5. 📊 Data Processing & Export

#### Excel Export with Advanced Formatting
```python
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils.dataframe import dataframe_to_rows

class AdvancedExcelExporter:
    
    def create_formatted_excel(self, data, filename):
        """
        Создание Excel файла с продвинутым форматированием
        """
        wb = Workbook()
        
        # Основные данные
        ws_main = wb.active
        ws_main.title = "Results"
        self._write_main_data(ws_main, data['results'])
        
        # Сводка
        ws_summary = wb.create_sheet("Summary")
        self._write_summary(ws_summary, data['summary'])
        
        # Ошибки
        ws_errors = wb.create_sheet("Errors")
        self._write_errors(ws_errors, data['errors'])
        
        wb.save(filename)
        
    def _write_main_data(self, worksheet, results):
        """Запись основных данных с форматированием"""
        df = pd.DataFrame(results)
        
        # Добавляем заголовки
        headers = ['Chat ID', 'User ID', 'Resume Found', 'Resume URL', 'Status', 'Timestamp']
        for col, header in enumerate(headers, 1):
            cell = worksheet.cell(row=1, column=col, value=header)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
            cell.alignment = Alignment(horizontal="center")
        
        # Добавляем данные
        for row_idx, result in enumerate(results, 2):
            worksheet.cell(row=row_idx, column=1, value=result.get('chat_id'))
            worksheet.cell(row=row_idx, column=2, value=result.get('user_id'))
            
            # Цветовое кодирование для статуса поиска резюме
            resume_found = result.get('resume_found', False)
            status_cell = worksheet.cell(row=row_idx, column=3, value=resume_found)
            if resume_found:
                status_cell.fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
            else:
                status_cell.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
```

### 6. 🔄 Error Handling & Resilience

#### Comprehensive Error Recovery
```python
class ResilientAPIProcessor:
    
    def __init__(self):
        self.error_counts = defaultdict(int)
        self.circuit_breaker_threshold = 10
        self.circuit_breaker_timeout = 300  # 5 минут
        self.circuit_breaker_state = {}
        
    def circuit_breaker(self, endpoint):
        """
        Circuit breaker pattern для защиты от каскадных сбоев
        """
        current_time = time.time()
        breaker_key = f"breaker_{endpoint}"
        
        if breaker_key in self.circuit_breaker_state:
            breaker_info = self.circuit_breaker_state[breaker_key]
            if current_time < breaker_info['open_until']:
                raise Exception(f"Circuit breaker открыт для {endpoint}")
        
        # Проверяем количество ошибок
        if self.error_counts[endpoint] >= self.circuit_breaker_threshold:
            self.circuit_breaker_state[breaker_key] = {
                'open_until': current_time + self.circuit_breaker_timeout
            }
            raise Exception(f"Circuit breaker активирован для {endpoint}")
    
    def handle_api_error(self, error, endpoint, chat_id):
        """
        Централизованная обработка ошибок API
        """
        self.error_counts[endpoint] += 1
        
        error_info = {
            'endpoint': endpoint,
            'chat_id': chat_id,
            'error_type': type(error).__name__,
            'error_message': str(error),
            'timestamp': datetime.now().isoformat(),
            'retry_recommended': self._should_retry(error)
        }
        
        # Логирование с контекстом
        if hasattr(error, 'response') and error.response:
            error_info['status_code'] = error.response.status_code
            error_info['response_headers'] = dict(error.response.headers)
        
        return error_info
    
    def _should_retry(self, error) -> bool:
        """
        Определение необходимости повторной попытки
        """
        if hasattr(error, 'response'):
            status_code = error.response.status_code
            # Retry для временных ошибок
            return status_code in [429, 500, 502, 503, 504]
        return False
```

### 7. 📈 Performance Monitoring

#### Real-time Metrics Collection
```python
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Dict, List

@dataclass
class PerformanceMetrics:
    requests_per_second: float
    average_response_time: float
    error_rate: float
    active_threads: int
    memory_usage: float

class PerformanceMonitor:
    
    def __init__(self, window_size=100):
        self.window_size = window_size
        self.response_times = deque(maxlen=window_size)
        self.request_timestamps = deque(maxlen=window_size)
        self.error_count = 0
        self.total_requests = 0
        
    def record_request(self, response_time: float, success: bool = True):
        """Запись метрик выполнения запроса"""
        current_time = time.time()
        
        self.response_times.append(response_time)
        self.request_timestamps.append(current_time)
        self.total_requests += 1
        
        if not success:
            self.error_count += 1
    
    def get_current_metrics(self) -> PerformanceMetrics:
        """Получение текущих метрик производительности"""
        current_time = time.time()
        
        # Вычисляем RPS за последнюю минуту
        recent_requests = [t for t in self.request_timestamps if current_time - t <= 60]
        rps = len(recent_requests) / 60.0
        
        # Среднее время ответа
        avg_response_time = sum(self.response_times) / len(self.response_times) if self.response_times else 0
        
        # Процент ошибок
        error_rate = (self.error_count / self.total_requests * 100) if self.total_requests > 0 else 0
        
        return PerformanceMetrics(
            requests_per_second=rps,
            average_response_time=avg_response_time,
            error_rate=error_rate,
            active_threads=threading.active_count(),
            memory_usage=self._get_memory_usage()
        )
    
    def _get_memory_usage(self) -> float:
        """Получение использования памяти в MB"""
        import psutil
        process = psutil.Process()
        return process.memory_info().rss / 1024 / 1024
```

---

## 🛠️ Development Guidelines

### Code Style & Standards
- **PEP 8** compliance для Python кода
- **Type hints** для всех публичных методов
- **Docstrings** в Google стиле
- **Error handling** с детализированным логированием

### Testing Strategy
- **Unit tests** для критических компонентов
- **Integration tests** для API взаимодействий
- **Performance tests** для многопоточных операций
- **Browser automation tests** для UI компонентов

### Deployment Considerations
- **Environment variables** для конфигурации
- **Docker containerization** для изоляции
- **Health checks** для мониторинга
- **Graceful shutdown** для корректного завершения

---

**Версия документации**: 1.0  
**Дата создания**: 22 сентября 2025  
**Авторы**: Development Team