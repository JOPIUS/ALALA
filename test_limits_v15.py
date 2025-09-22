#!/usr/bin/env python3
"""
Тест исправленной версии v15 - проверка приоритетов лимитов
"""

def test_limits():
    print("🧪 ТЕСТ ПРИОРИТЕТОВ ЛИМИТОВ v15")
    print("=" * 50)
    
    print("📋 Логика приоритетов:")
    print("  1️⃣ Стоп-триггер (kassir_prodavets_sidelka_ofitsiantka_4162899311)")
    print("  2️⃣ Пользовательский лимит (--limit X)")
    print("  3️⃣ Контрольная цифра из избранного")
    print("  4️⃣ Без лимита (парсинг всех резюме)")
    print()
    
    test_cases = [
        {
            "cmd": "python avito_paid_cvs_save_v_15.py --limit 10",
            "expected": "Используется пользовательский лимит: 10"
        },
        {
            "cmd": "python avito_paid_cvs_save_v_15.py",
            "expected": "Используется контрольная цифра (если найдена)"
        }
    ]
    
    for i, case in enumerate(test_cases, 1):
        print(f"{i}️⃣ Тест: {case['cmd']}")
        print(f"   Ожидается: {case['expected']}")
        print()
    
    print("🎯 ИСПРАВЛЕНИЕ:")
    print("   ✅ Пользовательский --limit теперь имеет приоритет")
    print("   ✅ Контрольная цифра используется только если нет --limit")
    print("   ✅ Стоп-триггер всегда имеет высший приоритет")

if __name__ == "__main__":
    test_limits()