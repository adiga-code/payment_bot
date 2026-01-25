# bot/database/repositories/bank_repository.py

from typing import Optional, List
from sqlalchemy import select
from decimal import Decimal
from datetime import datetime

from database.base_repository import BaseRepository
from database.models import Bank, CompanyBank


class BankRepository(BaseRepository[Bank]):
    """
    Репозиторий для работы с банками
    """
    
    def __init__(self, session_maker):
        super().__init__(session_maker, Bank)
    
    async def get_by_chat_id(self, chat_id: int) -> Optional[Bank]:
        """Получить банк по chat_id"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(Bank).where(Bank.chat_id == chat_id)
            )
            return result.scalar_one_or_none()
    
    async def get_active(self) -> List[Bank]:
        """Получить все активные банки"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(Bank).where(
                    Bank.is_active == True,
                    Bank.is_available == True
                )
            )
            return list(result.scalars().all())
    
    async def get_for_company(self, company_id: int) -> List[Bank]:
        """Получить банки, работающие с компанией"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(Bank)
                .join(CompanyBank)
                .where(
                    CompanyBank.company_id == company_id,
                    Bank.is_active == True,
                    Bank.is_available == True
                )
            )
            return list(result.scalars().all())
    
    async def get_with_available_limit(
        self,
        amount: Decimal,
        period: str = 'daily'
    ) -> List[Bank]:
        """
        Получить банки с достаточным лимитом
        
        Args:
            amount: Требуемая сумма
            period: 'daily' или 'weekly'
        """
        async with self.session_maker() as session:
            if period == 'daily':
                query = select(Bank).where(
                    Bank.is_active == True,
                    Bank.is_available == True,
                    (Bank.daily_limit - Bank.current_daily_used) >= amount
                )
            else:  # weekly
                query = select(Bank).where(
                    Bank.is_active == True,
                    Bank.is_available == True,
                    (Bank.weekly_limit - Bank.current_weekly_used) >= amount
                )
            
            result = await session.execute(query)
            return list(result.scalars().all())
    
    async def update_usage(
        self,
        bank_id: int,
        amount: Decimal,
        increment: bool = True
    ) -> bool:
        """
        Обновить использование лимитов
        
        Args:
            bank_id: ID банка
            amount: Сумма
            increment: True - увеличить, False - уменьшить
        """
        bank = await self.get_by_id(bank_id)
        if not bank:
            return False
        
        if increment:
            new_daily = bank.current_daily_used + amount
            new_weekly = bank.current_weekly_used + amount
        else:
            new_daily = max(0, bank.current_daily_used - amount)
            new_weekly = max(0, bank.current_weekly_used - amount)
        
        return await self.update_by_id(
            bank_id,
            current_daily_used=new_daily,
            current_weekly_used=new_weekly,
            updated_at=datetime.utcnow()
        )
    
    async def reset_daily_limits(self) -> int:
        """Сбросить дневные лимиты всех банков"""
        async with self.session_maker() as session:
            from sqlalchemy import update
            
            stmt = (
                update(Bank)
                .where(Bank.is_active == True)
                .values(
                    current_daily_used=0,
                    updated_at=datetime.utcnow()
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount
    
    async def reset_weekly_limits(self) -> int:
        """Сбросить недельные лимиты всех банков"""
        async with self.session_maker() as session:
            from sqlalchemy import update
            
            stmt = (
                update(Bank)
                .where(Bank.is_active == True)
                .values(
                    current_weekly_used=0,
                    updated_at=datetime.utcnow()
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount
    
    async def set_available(self, bank_id: int, available: bool) -> bool:
        """Установить доступность банка"""
        return await self.update_by_id(bank_id, is_available=available)