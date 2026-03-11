from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class GristCacheManager:
    """Менеджер кеширования данных Grist в памяти"""

    # Основные кеши таблиц
    caches: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    index_caches: Dict[str, Dict[str, Dict[str, Any]]] = field(default_factory=dict)

    # Конфигурация таблиц для кеширования
    cached_tables = {
        "GRIST_access": {"indexed_by": "key"},  # проверки ключей доступа
        "EURMTL_secretaries": {"indexed_by": None},  # секретари
        "EURMTL_assets": {"indexed_by": "code"},  # активы
        "EURMTL_users": {"indexed_by": "account_id"},  # пользователи (основной индекс)
        "EURMTL_accounts": {"indexed_by": "id"},  # аккаунты
        "EURMTL_pools": {
            "indexed_by": "need_dropdown"
        },  # пулы (фильтрация по need_dropdown)
    }

    # Дополнительные индексы для таблиц
    additional_indexes = {
        "EURMTL_users": ["telegram_id"],  # дополнительный индекс для telegram_id
    }

    async def initialize_cache(self):
        """Инициализация кеша при запуске приложения"""
        logger.info("🔄 Начало инициализации кеша Grist...")

        for table_name in self.cached_tables:
            try:
                await self.load_table_to_cache(table_name)
                count = len(self.caches.get(table_name, []))
                logger.info(
                    f"✅ Таблица {table_name} загружена в кеш ({count} записей)"
                )
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки таблицы {table_name}: {e}")

        logger.info("🎉 Кеш Grist успешно инициализирован")

    async def load_table_to_cache(self, table_name: str):
        """Загрузка конкретной таблицы в кеш"""
        from other.grist_tools import grist_manager, MTLGrist

        table_config = getattr(MTLGrist, table_name)
        data = await grist_manager.load_table_data(table_config)

        if data:
            self.caches[table_name] = data

            # Создаем основной индекс если нужно
            config = self.cached_tables[table_name]
            if config.get("indexed_by"):
                index_field = config["indexed_by"]
                self.index_caches[table_name] = {
                    record[index_field]: record
                    for record in data
                    if index_field in record and record[index_field] is not None
                }

            # Создаем дополнительные индексы
            if table_name in self.additional_indexes:
                for field in self.additional_indexes[table_name]:
                    index_key = f"{table_name}_{field}"
                    self.index_caches[index_key] = {
                        record[field]: record
                        for record in data
                        if field in record and record[field] is not None
                    }

    async def update_cache_by_webhook(self, table_name: str):
        """Обновление кеша по вебхуку - полная перезагрузка таблицы"""
        logger.info(f"🔄 Обновление кеша для таблицы {table_name}")

        if table_name not in self.cached_tables:
            logger.warning(f"Таблица {table_name} не настроена для кеширования")
            return

        try:
            await self.load_table_to_cache(table_name)
            count = len(self.caches.get(table_name, []))
            logger.info(f"✅ Кеш таблицы {table_name} обновлен ({count} записей)")
        except Exception as e:
            logger.error(f"❌ Ошибка обновления кеша таблицы {table_name}: {e}")

    def get_table_data(self, table_name: str) -> List[Dict[str, Any]]:
        """Получение всех данных таблицы из кеша"""
        return self.caches.get(table_name, [])

    def find_by_index(
        self, table_name: str, key: str, field: str = None
    ) -> Optional[Dict[str, Any]]:
        """Поиск записи по индексу"""
        if field:
            # Ищем по дополнительному индексу
            index_key = f"{table_name}_{field}"
            index_cache = self.index_caches.get(index_key, {})
        else:
            # Ищем по основному индексу
            index_cache = self.index_caches.get(table_name, {})

        return index_cache.get(key)

    def find_by_filter(
        self, table_name: str, field: str, values: List[Any]
    ) -> List[Dict[str, Any]]:
        """Поиск записей по фильтру"""
        table_data = self.caches.get(table_name, [])
        return [record for record in table_data if record.get(field) in values]

    def find_one_by_filter(
        self, table_name: str, field: str, value: Any
    ) -> Optional[Dict[str, Any]]:
        """Поиск одной записи по фильтру"""
        table_data = self.caches.get(table_name, [])
        for record in table_data:
            if record.get(field) == value:
                return record
        return None


# Глобальный экземпляр
grist_cache = GristCacheManager()
