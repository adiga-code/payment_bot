# bot/database/repositories/setting_repository.py

from typing import Optional, Any
from sqlalchemy import select

from database.base_repository import BaseRepository
from database.models import Setting


class SettingRepository(BaseRepository[Setting]):
    """
    Репозиторий для работы с настройками
    """
    
    def __init__(self, session_maker):
        super().__init__(session_maker, Setting)
    
    async def get_value(self, key: str, default: Any = None) -> Any:
        """Получить значение настройки"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(Setting).where(Setting.key == key)
            )
            setting = result.scalar_one_or_none()
            
            return setting.value if setting else default
    
    async def set_value(
        self,
        key: str,
        value: Any,
        description: Optional[str] = None
    ) -> Setting:
        """Установить значение настройки"""
        async with self.session_maker() as session:
            # Проверяем существование
            result = await session.execute(
                select(Setting).where(Setting.key == key)
            )
            setting = result.scalar_one_or_none()
            
            if setting:
                # Обновляем
                setting.value = value
                if description:
                    setting.description = description
                await session.commit()
                await session.refresh(setting)
            else:
                # Создаем
                setting = Setting(
                    key=key,
                    value=value,
                    description=description
                )
                session.add(setting)
                await session.commit()
                await session.refresh(setting)
            
            return setting
    
    async def increment(self, key: str) -> int:
        """Инкрементировать числовое значение"""
        current = await self.get_value(key, 0)
        new_value = int(current) + 1
        await self.set_value(key, new_value)
        return new_value
    
    async def get_invoice_number(self) -> int:
        """Получить следующий номер счета"""
        return await self.increment('invoice_counter')
    
    async def get_contract_number(self) -> int:
        """Получить следующий номер договора"""
        return await self.increment('contract_counter')