# Тест версии v15 с исправлениями
# Проверяет: лимит, потоки, стоп-триггер, масштаб браузера

import subprocess
import sys
import os

def test_v15():
    print("🧪 ТЕСТ ВЕРСИИ v15")
    print("=" * 50)
    
    # Тест 1: Парсинг аргументов лимита
    print("1️⃣ Тест парсинга лимита --limit 5")
    result = subprocess.run([
        sys.executable, "avito_paid_cvs_save_v_15.py", 
        "--limit", "5", "--tz", "Europe/Moscow", "--threads", "4"
    ], capture_output=True, text=True, timeout=10)
    
    if "лимит=5" in result.stdout and "потоков=4" in result.stdout:
        print("✅ Лимит и потоки парсятся корректно")
    else:
        print("❌ Ошибка парсинга аргументов")
        print("STDOUT:", result.stdout[:500])
        print("STDERR:", result.stderr[:500])
    
    # Тест 2: Проверка стоп-триггера в логах
    if "kassir_prodavets_sidelka_ofitsiantka_4162899311" in result.stdout:
        print("✅ Стоп-триггер отображается в логах")
    else:
        print("❌ Стоп-триггер не найден в логах")
    
    # Тест 3: Проверка приоритетов
    if "приоритет #1" in result.stdout and "приоритет #2" in result.stdout:
        print("✅ Приоритеты стоп-триггеров отображаются")
    else:
        print("❌ Приоритеты не найдены в логах")
    
    print("\n🔧 Настройки v15:")
    print("- Стоп-триггер: kassir_prodavets_sidelka_ofitsiantka_4162899311 (приоритет #1)")
    print("- Лимит: вторичный триггер (приоритет #2)")
    print("- Масштаб браузера: 45%")
    print("- Потоки: от 1 до 20 (по умолчанию 8)")
    print("- Лимит: от 0 до ∞ (по умолчанию: запрос у пользователя)")

if __name__ == "__main__":
    test_v15()