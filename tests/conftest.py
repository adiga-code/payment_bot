"""Общие фикстуры для тестов"""

import sys
import os
from unittest.mock import MagicMock

# Заглушки для тяжёлых зависимостей, которые не нужны для юнит-тестов
_STUB_MODULES = [
    'sqlalchemy',
    'sqlalchemy.ext',
    'sqlalchemy.ext.asyncio',
    'sqlalchemy.orm',
    'sqlalchemy.future',
    'aiogram',
    'aiogram.types',
    'aiogram.filters',
    'aiogram.fsm',
    'aiogram.fsm.context',
    'aiogram.fsm.state',
    'aiogram.fsm.storage',
    'aiogram.fsm.storage.memory',
    'aiogram.dispatcher',
    'aiohttp',
    # Мокируем весь модуль database, чтобы не тянуть ORM-зависимости
    'database',
]
for _mod in _STUB_MODULES:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# Добавляем bot/ в sys.path для импортов
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'bot'))
