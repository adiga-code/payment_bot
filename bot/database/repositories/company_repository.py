# bot/database/repositories/company_repository.py

from typing import Optional, List
from sqlalchemy import select
from decimal import Decimal
from datetime import datetime

from database.base_repository import BaseRepository
from database.models import Company, CompanyBank


class CompanyRepository(BaseRepository[Company]):
    """
    Репозиторий для работы с компаниями
    """
    
    def __init__(self, session_maker):
        super().__init__(session_maker, Company)
    
    async def get_by_inn(self, inn: str) -> Optional[Company]:
        """Получить компанию по ИНН"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(Company).where(Company.inn == inn)
            )
            return result.scalar_one_or_none()
    
    async def get_active(self) -> List[Company]:
        """Получить все активные компании"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(Company).where(Company.is_active == True)
            )
            return list(result.scalars().all())
    
    async def get_with_available_limit(
        self,
        amount: Decimal,
        period: str = 'daily'
    ) -> List[Company]:
        """
        Получить компании с достаточным лимитом
        
        Args:
            amount: Требуемая сумма
            period: 'daily', 'weekly', 'monthly'
        """
        async with self.session_maker() as session:
            if period == 'daily':
                query = select(Company).where(
                    Company.is_active == True,
                    (Company.daily_limit - Company.current_daily_used) >= amount
                )
            elif period == 'weekly':
                query = select(Company).where(
                    Company.is_active == True,
                    (Company.weekly_limit - Company.current_weekly_used) >= amount
                )
            else:  # monthly
                query = select(Company).where(
                    Company.is_active == True,
                    (Company.monthly_limit - Company.current_monthly_used) >= amount
                )
            
            result = await session.execute(query)
            return list(result.scalars().all())
    
    async def update_usage(
        self,
        company_id: int,
        amount: Decimal,
        increment: bool = True
    ) -> bool:
        """
        Обновить использование лимитов
        
        Args:
            company_id: ID компании
            amount: Сумма
            increment: True - увеличить, False - уменьшить
        """
        company = await self.get_by_id(company_id)
        if not company:
            return False
        
        if increment:
            new_daily = company.current_daily_used + amount
            new_weekly = company.current_weekly_used + amount
            new_monthly = company.current_monthly_used + amount
        else:
            new_daily = max(0, company.current_daily_used - amount)
            new_weekly = max(0, company.current_weekly_used - amount)
            new_monthly = max(0, company.current_monthly_used - amount)
        
        return await self.update_by_id(
            company_id,
            current_daily_used=new_daily,
            current_weekly_used=new_weekly,
            current_monthly_used=new_monthly,
            updated_at=datetime.utcnow()
        )
    
    async def reset_daily_limits(self) -> int:
        """Сбросить дневные лимиты всех компаний"""
        async with self.session_maker() as session:
            from sqlalchemy import update
            
            stmt = (
                update(Company)
                .where(Company.is_active == True)
                .values(
                    current_daily_used=0,
                    updated_at=datetime.utcnow()
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount
    
    async def reset_weekly_limits(self) -> int:
        """Сбросить недельные лимиты всех компаний"""
        async with self.session_maker() as session:
            from sqlalchemy import update
            
            stmt = (
                update(Company)
                .where(Company.is_active == True)
                .values(
                    current_weekly_used=0,
                    updated_at=datetime.utcnow()
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount
    
    async def reset_monthly_limits(self) -> int:
        """Сбросить месячные лимиты всех компаний"""
        async with self.session_maker() as session:
            from sqlalchemy import update
            
            stmt = (
                update(Company)
                .where(Company.is_active == True)
                .values(
                    current_monthly_used=0,
                    updated_at=datetime.utcnow()
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount
    
    async def get_banks(self, company_id: int) -> List[int]:
        """Получить список ID банков, работающих с компанией"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(CompanyBank.bank_id)
                .where(CompanyBank.company_id == company_id)
            )
            return [row[0] for row in result.all()]
    
    async def get_preferred_bank(self, company_id: int) -> Optional[int]:
        """Получить предпочтительный банк компании"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(CompanyBank.bank_id)
                .where(
                    CompanyBank.company_id == company_id,
                    CompanyBank.is_preferred == True
                )
            )
            bank_id = result.scalar_one_or_none()
            return bank_id

    # ==================== COMPANY-BANK RELATIONSHIPS ====================

    async def get_company_banks(self, company_id: int) -> List[CompanyBank]:
        """Получить все связи компании с банками (с загруженными банками)"""
        from sqlalchemy.orm import selectinload
        async with self.session_maker() as session:
            result = await session.execute(
                select(CompanyBank)
                .options(selectinload(CompanyBank.bank))
                .where(CompanyBank.company_id == company_id)
            )
            return list(result.scalars().all())

    async def get_company_bank_by_id(self, company_bank_id: int) -> Optional[CompanyBank]:
        """Получить связь компании с банком по ID"""
        from sqlalchemy.orm import selectinload
        async with self.session_maker() as session:
            result = await session.execute(
                select(CompanyBank)
                .options(selectinload(CompanyBank.bank))
                .where(CompanyBank.id == company_bank_id)
            )
            return result.scalar_one_or_none()

    async def create_company_bank(
        self,
        company_id: int,
        bank_id: int,
        account_number: str = None,
        is_preferred: bool = False
    ) -> CompanyBank:
        """Создать связь компании с банком"""
        async with self.session_maker() as session:
            company_bank = CompanyBank(
                company_id=company_id,
                bank_id=bank_id,
                account_number=account_number,
                is_preferred=is_preferred
            )
            session.add(company_bank)
            await session.commit()
            await session.refresh(company_bank)
            return company_bank

    async def update_company_bank(self, company_bank_id: int, **kwargs) -> bool:
        """Обновить связь компании с банком"""
        from sqlalchemy import update
        async with self.session_maker() as session:
            stmt = (
                update(CompanyBank)
                .where(CompanyBank.id == company_bank_id)
                .values(**kwargs)
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def delete_company_bank(self, company_bank_id: int) -> bool:
        """Удалить связь компании с банком"""
        from sqlalchemy import delete
        async with self.session_maker() as session:
            stmt = delete(CompanyBank).where(CompanyBank.id == company_bank_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def set_preferred_bank(self, company_id: int, company_bank_id: int) -> bool:
        """Установить банк как предпочтительный для компании"""
        from sqlalchemy import update
        async with self.session_maker() as session:
            # Сначала сбросить все is_preferred для компании
            await session.execute(
                update(CompanyBank)
                .where(CompanyBank.company_id == company_id)
                .values(is_preferred=False)
            )
            # Установить новый предпочтительный
            await session.execute(
                update(CompanyBank)
                .where(CompanyBank.id == company_bank_id)
                .values(is_preferred=True)
            )
            await session.commit()
            return True

    async def get_company_bank_for_invoice(
        self,
        company_id: int,
        bank_id: int
    ) -> Optional[CompanyBank]:
        """Получить связь компании с банком для генерации счёта"""
        from sqlalchemy.orm import selectinload
        async with self.session_maker() as session:
            result = await session.execute(
                select(CompanyBank)
                .options(selectinload(CompanyBank.bank))
                .where(
                    CompanyBank.company_id == company_id,
                    CompanyBank.bank_id == bank_id
                )
            )
            return result.scalar_one_or_none()