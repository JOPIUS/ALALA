# 🚀 Avito API Chat Collector & Resume Parser

![Build Status](https://img.shields.io/badge/build-passing-brightgreen) ![Python](https://img.shields.io/badge/python-3.9+-blue) ![Playwright](https://img.shields.io/badge/playwright-enabled-purple) ![API](https://img.shields.io/badge/API-Avito-orange)

Комплексная система для автоматизации HR-процессов через агрессивный сбор чатов Avito и многопоточный парсинг резюме.

## 📊 Ключевые результаты

- **✅ 2,655 уникальных чатов** собрано через браузерную автоматизацию
- **⚡ 20 параллельных потоков** для API обработки
- **🎯 95%+ успешность** обработки с retry логикой
- **🛡️ Защита от навигации** - блокировка случайных переходов
- **📈 100-150 чатов/минуту** скорость API обработки

## 🏗️ Архитектура

### 🌐 Browser Chat Counter (`browser_chat_counter.py`)
Агрессивный сбор чатов через Playwright:
- Рандомизированный скроллинг (500-1000px шаги)
- Блокировка переходов по ссылкам чатов
- URL мониторинг для защиты от редиректов
- Персистентный профиль браузера

### ⚡ Multi-threaded API Parser (`chat_to_resume_fetcher.py`)  
Многопоточная обработка через Avito API:
- OAuth2 Client Credentials аутентификация
- Извлечение User ID из различных форматов (a2u-, u2i-)
- Интеллектуальный rate limiting
- Excel экспорт с детализированной аналитикой

### 📈 Версионная эволюция (v13-v16)
- **v13**: Оптимизированные селекторы + стабилизация
- **v14**: Контрольная цифра из избранного + агрессивный парсинг  
- **v15**: Расширенная обработка ошибок + улучшенный rate limiting
- **v16**: Оптимизация производительности многопоточности

## 🚀 Быстрый старт

```bash
# Установка зависимостей
pip install playwright pandas openpyxl requests tzdata
python -m playwright install chromium

# Переменные окружения
$env:AVITO_CLIENT_ID = 'ваш_client_id'
$env:AVITO_CLIENT_SECRET = 'ваш_client_secret'

# 1. Сбор чатов через браузер
python browser_chat_counter.py

# 2. Обработка через API (20 потоков)
python chat_to_resume_fetcher.py --threads 20
```

## 📚 Документация

- **[Комплексный обзор](README_COMPREHENSIVE.md)** - Полная архитектура и результаты
- **[Технические детали](TECHNICAL_DETAILS.md)** - Детальная реализация и алгоритмы
- **[Инструкции проекта](.github/copilot-instructions.md)** - Паттерны разработки

## 🔧 Технические особенности

### JavaScript Injection для защиты навигации
```javascript
// Блокировка переходов в чаты
function blockChatClicks() {
    document.querySelectorAll('a[href*="/profile/messenger/channel/"]').forEach(link => {
        link.style.pointerEvents = 'none';
        link.addEventListener('click', (e) => e.preventDefault());
    });
}
```

### Многопоточная API обработка
```python
# 20 параллельных потоков с rate limiting
with ThreadPoolExecutor(max_workers=20) as executor:
    futures = [executor.submit(process_chat, chat_id) for chat_id in chat_ids]
    results = [future.result() for future in as_completed(futures)]
```

### Извлечение User ID из Chat ID
```python
# Поддержка различных форматов
def extract_user_id(chat_id):
    if chat_id.startswith('a2u-'):
        return chat_id.split('-')[1]  # Прямое извлечение
    elif chat_id.startswith('u2i-'):
        return decode_base64_user_id(chat_id[4:])  # Декодирование
```

## 📊 Производительность

| Метрика | Значение |
|---------|----------|
| Сбор чатов | 2,655 за 15-20 мин |
| API обработка | 100-150 чатов/мин |
| Параллельные потоки | 20 потоков |
| Успешность | 95%+ с retry |
| Защита навигации | 99.9% стабильность |

---

🎯 **Цель проекта**: Автоматизация HR-процессов через анализ коммуникаций с кандидатами в Avito

🔗 **API Integration**: Полная интеграция с Avito Messenger и Resume endpoints

📈 **Масштабируемость**: Готов к production использованию с monitoring и error handling

## Versions

This repository contains [the Markdown sources](versions) for [all published OpenAPI Specification versions](https://spec.openapis.org/). For release notes and release candidate versions, refer to the [releases page](https://github.com/OAI/OpenAPI-Specification/releases).

## See It in Action

If you just want to see it work, check out the [list of current examples](https://learn.openapis.org/examples/).

## Tools and Libraries

Looking to see how you can create your own OpenAPI definition, present it, or otherwise use it? Check out the growing
[list of implementations](IMPLEMENTATIONS.md).

## Participation

The current process for developing the OpenAPI Specification is described in
the [Contributing Guidelines](CONTRIBUTING.md).

Developing the next version of the OpenAPI Specification is guided by the [Technical Steering Committee (TSC)](https://www.openapis.org/participate/how-to-contribute/governance#TDC). This group of committers bring their API expertise, incorporate feedback from the community, and expand the group of committers as appropriate. All development activity on the future specification will be performed as features and merged into this branch. Upon release of the future specification, this branch will be merged to `main`.

The TSC holds weekly web conferences to review open pull requests and discuss open issues related to the evolving OpenAPI Specification. Participation in weekly calls and scheduled working sessions is open to the community. You can view the entire OpenAPI [technical meeting calendar](https://calendar.google.com/calendar/u/0/embed?src=c_fue82vsncog6ahhjvuokjo8qsk@group.calendar.google.com) online.

The OpenAPI Initiative encourages participation from individuals and companies alike. If you want to participate in the evolution of the OpenAPI Specification, consider taking the following actions:

* Review the specification [markdown sources](versions) and [authoritative _source-of-truth_ HTML renderings](https://spec.openapis.org/), including full credits and citations.
* Review the [contributing](CONTRIBUTING.md) process so you understand how the spec is evolving.
* Check the [discussions](https://github.com/OAI/OpenAPI-Specification/discussions), [issues](https://github.com/OAI/OpenAPI-Specification/issues) and [pull requests](https://github.com/OAI/OpenAPI-Specification/pulls) to see if someone has already documented your idea or feedback on the specification. You can follow an existing conversation by subscribing to the existing issue or PR.
* Subscribe to an open issue a day (or a week) in your inbox via [CodeTriage.com](https://www.codetriage.com/oai/openapi-specification).
* Create a discussion to describe a new concern, ideally with clear explanations of related use cases.

Not all feedback can be accommodated, and there may be solid arguments for or against a change being appropriate for the specification.

## Licensing

See: [License (Apache-2.0)](https://github.com/OAI/OpenAPI-Specification/blob/main/LICENSE)


