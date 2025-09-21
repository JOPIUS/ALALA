#!/usr/bin/env python3
"""
Отладочный скрипт для полной загрузки всех чатов Avito
Анализирует API ограничения и находит оптимальную стратегию загрузки
"""
import requests
import json
import time
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# API настройки
API_BASE = "https://api.avito.ru"
CLIENT_ID = "Dm4ruLMEr9MFsV72dN95"
CLIENT_SECRET = "f73lNoAJLzuqwoGtVaMnByhQfSlwcyIN_m7wyOeT"
TIMEOUT = 30

class AvitoChatsDebugger:
    def __init__(self):
        self.session = requests.Session()
        self.access_token = None
        self.user_id = None
        self.total_chats_found = 0
        self.all_chats = {}  # {chat_id: chat_data}
        
    def get_access_token(self) -> bool:
        """Получение access token"""
        print("🔑 Получаем access token...")
        
        try:
            response = self.session.post(
                f"{API_BASE}/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET
                },
                timeout=TIMEOUT
            )
            
            if response.status_code == 200:
                data = response.json()
                self.access_token = data["access_token"]
                print(f"✅ Токен получен: {self.access_token[:20]}...")
                return True
            else:
                print(f"❌ Ошибка получения токена: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Исключение при получении токена: {e}")
            return False
    
    def get_user_id(self) -> bool:
        """Получение user_id"""
        print("👤 Получаем user ID...")
        
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        # Пробуем разные endpoints для получения user_id
        endpoints = [
            "/core/v1/accounts/self",
            "/messenger/v1/accounts", 
            "/user/v1/self"
        ]
        
        for endpoint in endpoints:
            try:
                response = self.session.get(f"{API_BASE}{endpoint}", headers=headers, timeout=TIMEOUT)
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"✅ Ответ от {endpoint}: {json.dumps(data, ensure_ascii=False, indent=2)}")
                    
                    # Ищем user_id в разных форматах
                    user_id = (
                        data.get("id") or 
                        data.get("user_id") or 
                        data.get("account_id") or
                        (data.get("accounts", [{}])[0] if data.get("accounts") else {}).get("id")
                    )
                    
                    if user_id:
                        self.user_id = str(user_id)
                        print(f"✅ User ID найден: {self.user_id}")
                        return True
                        
                else:
                    print(f"⚠️ {endpoint}: {response.status_code}")
                    
            except Exception as e:
                print(f"⚠️ Ошибка {endpoint}: {e}")
        
        print("❌ Не удалось получить user_id")
        return False
    
    def analyze_chats_api(self) -> Dict:
        """Анализ API чатов - определение лимитов и параметров"""
        print("\n📊 Анализируем API чатов...")
        
        headers = {"Authorization": f"Bearer {self.access_token}"}
        analysis = {
            "v1_available": False,
            "v2_available": False, 
            "v1_total": 0,
            "v2_total": 0,
            "v1_max_offset": 0,
            "v2_max_offset": 0,
            "supported_params": [],
            "chat_types": [],
        }
        
        # Тестируем v1 API
        print("\n🔍 Тестируем messenger/v1...")
        try:
            v1_url = f"{API_BASE}/messenger/v1/accounts/{self.user_id}/chats"
            v1_response = self.session.get(v1_url, headers=headers, params={"limit": 1}, timeout=TIMEOUT)
            
            if v1_response.status_code == 200:
                analysis["v1_available"] = True
                v1_data = v1_response.json()
                analysis["v1_total"] = len(v1_data.get("chats", []))
                print(f"✅ v1 API доступен, образец: {len(v1_data.get('chats', []))} чатов")
                print(f"   Структура ответа: {list(v1_data.keys())}")
            else:
                print(f"❌ v1 API недоступен: {v1_response.status_code}")
                
        except Exception as e:
            print(f"❌ Ошибка v1 API: {e}")
        
        # Тестируем v2 API
        print("\n🔍 Тестируем messenger/v2...")
        try:
            v2_url = f"{API_BASE}/messenger/v2/accounts/{self.user_id}/chats"
            v2_response = self.session.get(v2_url, headers=headers, params={"limit": 1}, timeout=TIMEOUT)
            
            if v2_response.status_code == 200:
                analysis["v2_available"] = True
                v2_data = v2_response.json()
                analysis["v2_total"] = len(v2_data.get("chats", []))
                print(f"✅ v2 API доступен, образец: {len(v2_data.get('chats', []))} чатов")
                print(f"   Структура ответа: {list(v2_data.keys())}")
                
                # Проверяем поддержку дополнительной информации
                if "total" in v2_data:
                    print(f"🎯 Найдено поле 'total': {v2_data['total']}")
                if "has_more" in v2_data:
                    print(f"🎯 Найдено поле 'has_more': {v2_data['has_more']}")
                if "count" in v2_data:
                    print(f"🎯 Найдено поле 'count': {v2_data['count']}")
                    
            else:
                print(f"❌ v2 API недоступен: {v2_response.status_code}")
                
        except Exception as e:
            print(f"❌ Ошибка v2 API: {e}")
        
        return analysis
    
    def test_pagination_limits(self, api_version: str = "v2") -> Dict:
        """Тестирование лимитов пагинации"""
        print(f"\n🔬 Тестируем лимиты пагинации для {api_version}...")
        
        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"{API_BASE}/messenger/{api_version}/accounts/{self.user_id}/chats"
        
        limits_test = {
            "max_working_offset": 0,
            "max_working_limit": 0,
            "error_at_offset": None,
            "total_found": 0
        }
        
        # Тестируем максимальный лимит
        print("📏 Тестируем максимальный limit...")
        for test_limit in [50, 100, 200, 500]:
            try:
                response = self.session.get(url, headers=headers, params={"limit": test_limit, "offset": 0}, timeout=TIMEOUT)
                if response.status_code == 200:
                    data = response.json()
                    actual_count = len(data.get("chats", []))
                    limits_test["max_working_limit"] = test_limit
                    print(f"✅ limit={test_limit}: получено {actual_count} чатов")
                    if actual_count < test_limit:
                        print(f"   ⚠️ Получено меньше запрошенного - возможно это все доступные чаты")
                        break
                else:
                    print(f"❌ limit={test_limit}: ошибка {response.status_code}")
                    break
            except Exception as e:
                print(f"❌ limit={test_limit}: исключение {e}")
                break
        
        # Тестируем максимальный offset
        print("\n📐 Тестируем максимальный offset...")
        working_limit = min(limits_test["max_working_limit"], 100)
        
        for test_offset in [0, 500, 1000, 1500, 2000, 5000]:
            try:
                response = self.session.get(url, headers=headers, params={"limit": working_limit, "offset": test_offset}, timeout=TIMEOUT)
                if response.status_code == 200:
                    data = response.json()
                    actual_count = len(data.get("chats", []))
                    if actual_count > 0:
                        limits_test["max_working_offset"] = test_offset
                        print(f"✅ offset={test_offset}: получено {actual_count} чатов")
                    else:
                        print(f"⚠️ offset={test_offset}: пустой результат")
                        break
                else:
                    limits_test["error_at_offset"] = test_offset
                    print(f"❌ offset={test_offset}: ошибка {response.status_code}")
                    if test_offset == 1000:
                        print(f"   📋 Подтверждено ограничение Swagger: offset <= 1000")
                    break
            except Exception as e:
                print(f"❌ offset={test_offset}: исключение {e}")
                break
                
            time.sleep(0.2)  # Пауза между запросами
        
        return limits_test
    
    def test_advanced_parameters(self) -> Dict:
        """Тестирование дополнительных параметров API"""
        print("\n🧪 Тестируем дополнительные параметры...")
        
        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"{API_BASE}/messenger/v2/accounts/{self.user_id}/chats"
        
        params_test = {
            "unread_only": {"supported": False, "result_count": 0},
            "chat_types": {"supported": False, "types_tested": []},
            "item_ids": {"supported": False},
        }
        
        # Тестируем unread_only
        print("📨 Тестируем unread_only...")
        try:
            response = self.session.get(url, headers=headers, params={"limit": 50, "unread_only": True}, timeout=TIMEOUT)
            if response.status_code == 200:
                data = response.json()
                unread_count = len(data.get("chats", []))
                params_test["unread_only"]["supported"] = True
                params_test["unread_only"]["result_count"] = unread_count
                print(f"✅ unread_only=True: {unread_count} непрочитанных чатов")
            else:
                print(f"❌ unread_only не поддерживается: {response.status_code}")
        except Exception as e:
            print(f"❌ Ошибка unread_only: {e}")
        
        # Тестируем chat_types
        print("💬 Тестируем chat_types...")
        chat_types_to_test = ["u2i", "i2u", "public", "private"]
        
        for chat_type in chat_types_to_test:
            try:
                response = self.session.get(url, headers=headers, params={"limit": 10, "chat_types": chat_type}, timeout=TIMEOUT)
                if response.status_code == 200:
                    data = response.json()
                    type_count = len(data.get("chats", []))
                    params_test["chat_types"]["supported"] = True
                    params_test["chat_types"]["types_tested"].append({"type": chat_type, "count": type_count})
                    print(f"✅ chat_types={chat_type}: {type_count} чатов")
                else:
                    print(f"❌ chat_types={chat_type}: {response.status_code}")
            except Exception as e:
                print(f"❌ Ошибка chat_types={chat_type}: {e}")
                
            time.sleep(0.1)
        
        return params_test
    
    def estimate_total_chats(self) -> int:
        """Оценка общего количества чатов"""
        print("\n📊 Оцениваем общее количество чатов...")
        
        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"{API_BASE}/messenger/v2/accounts/{self.user_id}/chats"
        
        # Пробуем получить большой offset чтобы понять границы
        estimates = []
        
        for test_offset in [0, 500, 900, 999]:
            try:
                response = self.session.get(url, headers=headers, params={"limit": 100, "offset": test_offset}, timeout=TIMEOUT)
                if response.status_code == 200:
                    data = response.json()
                    count = len(data.get("chats", []))
                    if count > 0:
                        estimate = test_offset + count
                        estimates.append(estimate)
                        print(f"📍 offset={test_offset}: +{count} чатов, оценка минимум: {estimate}")
                    else:
                        print(f"📍 offset={test_offset}: конец данных")
                        break
                else:
                    print(f"📍 offset={test_offset}: ошибка {response.status_code}")
                    break
            except Exception as e:
                print(f"📍 offset={test_offset}: исключение {e}")
                break
                
            time.sleep(0.1)
        
        if estimates:
            estimated_total = max(estimates)
            print(f"🎯 Оценка общего количества чатов: ≥{estimated_total}")
            return estimated_total
        else:
            print("❌ Не удалось оценить количество чатов")
            return 0
    
    def load_all_chats_optimized(self) -> Dict[str, dict]:
        """Оптимизированная загрузка всех чатов с обходом ограничений"""
        print("\n🚀 Начинаем оптимизированную загрузку всех чатов...")
        
        headers = {"Authorization": f"Bearer {self.access_token}"}
        all_chats = {}
        
        strategies = [
            {"name": "Основная загрузка v2", "method": self._load_main_v2},
            {"name": "Непрочитанные отдельно", "method": self._load_unread_only},
            {"name": "Fallback v1", "method": self._load_v1_fallback},
            {"name": "По типам чатов", "method": self._load_by_chat_types},
        ]
        
        for strategy in strategies:
            print(f"\n🔄 Стратегия: {strategy['name']}")
            try:
                strategy_chats = strategy["method"](headers)
                
                # Объединяем результаты
                added_count = 0
                for chat_id, chat_data in strategy_chats.items():
                    if chat_id not in all_chats:
                        all_chats[chat_id] = chat_data
                        added_count += 1
                
                print(f"✅ {strategy['name']}: +{added_count} новых чатов (всего уникальных: {len(all_chats)})")
                
            except Exception as e:
                print(f"❌ Ошибка в стратегии '{strategy['name']}': {e}")
        
        print(f"\n🎉 Итого загружено уникальных чатов: {len(all_chats)}")
        return all_chats
    
    def _load_main_v2(self, headers: dict) -> Dict[str, dict]:
        """Основная загрузка через v2 API"""
        chats = {}
        url = f"{API_BASE}/messenger/v2/accounts/{self.user_id}/chats"
        
        offset = 0
        limit = 100
        max_offset = 1000
        
        while offset <= max_offset:
            try:
                response = self.session.get(url, headers=headers, params={"offset": offset, "limit": limit}, timeout=TIMEOUT)
                
                if response.status_code == 200:
                    data = response.json()
                    batch_chats = data.get("chats", [])
                    
                    if not batch_chats:
                        print(f"   📋 Нет больше чатов на offset={offset}")
                        break
                    
                    for chat in batch_chats:
                        if chat.get("id"):
                            chats[chat["id"]] = chat
                    
                    print(f"   📥 offset={offset}: +{len(batch_chats)} чатов")
                    
                    if len(batch_chats) < limit:
                        print(f"   📋 Получена неполная страница, завершаем")
                        break
                        
                    offset += limit
                else:
                    print(f"   ❌ Ошибка на offset={offset}: {response.status_code}")
                    break
                    
            except Exception as e:
                print(f"   ❌ Исключение на offset={offset}: {e}")
                break
                
            time.sleep(0.1)
        
        return chats
    
    def _load_unread_only(self, headers: dict) -> Dict[str, dict]:
        """Загрузка только непрочитанных чатов"""
        chats = {}
        url = f"{API_BASE}/messenger/v2/accounts/{self.user_id}/chats"
        
        try:
            response = self.session.get(url, headers=headers, params={"limit": 100, "unread_only": True}, timeout=TIMEOUT)
            
            if response.status_code == 200:
                data = response.json()
                batch_chats = data.get("chats", [])
                
                for chat in batch_chats:
                    if chat.get("id"):
                        chats[chat["id"]] = chat
                
                print(f"   📨 Непрочитанные: {len(batch_chats)} чатов")
            else:
                print(f"   ⚠️ unread_only не работает: {response.status_code}")
                
        except Exception as e:
            print(f"   ❌ Ошибка unread_only: {e}")
        
        return chats
    
    def _load_v1_fallback(self, headers: dict) -> Dict[str, dict]:
        """Fallback загрузка через v1 API"""
        chats = {}
        url = f"{API_BASE}/messenger/v1/accounts/{self.user_id}/chats"
        
        try:
            response = self.session.get(url, headers=headers, params={"limit": 100}, timeout=TIMEOUT)
            
            if response.status_code == 200:
                data = response.json()
                batch_chats = data.get("chats", [])
                
                for chat in batch_chats:
                    if chat.get("id"):
                        chats[chat["id"]] = chat
                
                print(f"   🔄 v1 API: {len(batch_chats)} чатов")
            else:
                print(f"   ⚠️ v1 API недоступен: {response.status_code}")
                
        except Exception as e:
            print(f"   ❌ Ошибка v1 API: {e}")
        
        return chats
    
    def _load_by_chat_types(self, headers: dict) -> Dict[str, dict]:
        """Загрузка по типам чатов"""
        chats = {}
        url = f"{API_BASE}/messenger/v2/accounts/{self.user_id}/chats"
        
        chat_types = ["u2i", "i2u"]
        
        for chat_type in chat_types:
            try:
                response = self.session.get(url, headers=headers, params={"limit": 100, "chat_types": chat_type}, timeout=TIMEOUT)
                
                if response.status_code == 200:
                    data = response.json()
                    batch_chats = data.get("chats", [])
                    
                    for chat in batch_chats:
                        if chat.get("id"):
                            chats[chat["id"]] = chat
                    
                    print(f"   💬 Тип {chat_type}: {len(batch_chats)} чатов")
                else:
                    print(f"   ⚠️ Тип {chat_type} не работает: {response.status_code}")
                    
            except Exception as e:
                print(f"   ❌ Ошибка типа {chat_type}: {e}")
                
            time.sleep(0.1)
        
        return chats
    
    def save_debug_results(self, analysis: dict, limits: dict, params: dict, all_chats: dict):
        """Сохранение результатов отладки"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        debug_data = {
            "timestamp": timestamp,
            "user_id": self.user_id,
            "api_analysis": analysis,
            "pagination_limits": limits,
            "parameters_test": params,
            "total_chats_loaded": len(all_chats),
            "chat_sample": list(all_chats.keys())[:10],  # Образец ID чатов
            "recommendations": self._generate_recommendations(analysis, limits, params, all_chats)
        }
        
        filename = f"avito_chats_debug_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(debug_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 Результаты отладки сохранены: {filename}")
        return filename
    
    def _generate_recommendations(self, analysis: dict, limits: dict, params: dict, all_chats: dict) -> List[str]:
        """Генерация рекомендаций для основного скрипта"""
        recommendations = []
        
        if limits.get("error_at_offset") == 1000:
            recommendations.append("✅ Подтверждено ограничение offset=1000, нужен обход")
        
        if params.get("unread_only", {}).get("supported"):
            recommendations.append("✅ Параметр unread_only работает, можно использовать для дополнительной загрузки")
        
        if analysis.get("v1_available"):
            recommendations.append("✅ v1 API доступен, можно использовать как fallback")
        
        if params.get("chat_types", {}).get("supported"):
            recommendations.append("✅ Параметр chat_types работает, можно загружать по типам")
        
        if len(all_chats) > 1000:
            recommendations.append(f"🎯 Удалось загрузить {len(all_chats)} чатов - больше лимита offset!")
        
        recommendations.append("🔧 Рекомендация: использовать комбинацию всех рабочих стратегий")
        
        return recommendations
    
    def run_full_debug(self):
        """Запуск полной отладки"""
        print("🐛 AVITO CHATS DEBUGGER - Полный анализ API чатов")
        print("=" * 60)
        
        # Шаг 1: Аутентификация
        if not self.get_access_token():
            return False
        
        if not self.get_user_id():
            return False
        
        # Шаг 2: Анализ API
        analysis = self.analyze_chats_api()
        
        # Шаг 3: Тестирование лимитов
        limits = self.test_pagination_limits()
        
        # Шаг 4: Тестирование параметров
        params = self.test_advanced_parameters()
        
        # Шаг 5: Оценка общего количества
        estimated_total = self.estimate_total_chats()
        
        # Шаг 6: Загрузка всех чатов
        all_chats = self.load_all_chats_optimized()
        
        # Шаг 7: Сохранение результатов
        debug_file = self.save_debug_results(analysis, limits, params, all_chats)
        
        # Финальный отчет
        print("\n" + "=" * 60)
        print("📊 ФИНАЛЬНЫЙ ОТЧЕТ")
        print("=" * 60)
        print(f"🎯 Оценка общего количества чатов: ≥{estimated_total}")
        print(f"📥 Фактически загружено: {len(all_chats)} чатов")
        print(f"📈 Эффективность: {len(all_chats)/max(estimated_total, 1)*100:.1f}%")
        print(f"💾 Подробный отчет: {debug_file}")
        
        if len(all_chats) > 1000:
            print("✅ УСПЕХ: Обход ограничения offset=1000 работает!")
        else:
            print("⚠️ ВНИМАНИЕ: Возможно, есть еще чаты за пределами лимитов")
        
        return True


def main():
    debugger = AvitoChatsDebugger()
    debugger.run_full_debug()


if __name__ == "__main__":
    main()