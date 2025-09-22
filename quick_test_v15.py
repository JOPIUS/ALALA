#!/usr/bin/env python3
"""
Быстрый тест v15 - Проверка ключевых настроек
"""

def test_quick():
    print("🧪 БЫСТРЫЙ ТЕСТ v15")
    print("=" * 40)
    
    # Команда для тестирования
    cmd = "python avito_paid_cvs_save_v_15.py --limit 10 --threads 6 --tz Europe/Moscow"
    
    print(f"📋 Команда: {cmd}")
    print()
    print("✅ Ожидаемые результаты:")
    print("  🔧 Настройки: лимит=10, потоков=6, часовой_пояс=Europe/Moscow")
    print("  🛑 Стоп-триггер (приоритет #1): kassir_prodavets_sidelka_ofitsiantka_4162899311")
    print("  🎯 Лимит (приоритет #2): 10")
    print("  📊 Масштаб браузера: 45%")
    print()
    print("🔥 ПРИОРИТЕТЫ ОСТАНОВКИ:")
    print("  1️⃣ Стоп-триггер (найдена целевая ссылка)")
    print("  2️⃣ Лимит (достигнуто указанное количество)")
    print("  3️⃣ Нет прогресса (20 попыток подряд)")
    print()
    print("🎮 Для запуска:")
    print(f"  {cmd}")

if __name__ == "__main__":
    test_quick()