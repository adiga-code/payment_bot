# bot/database/repositories/company_bank_repository.py

from typing import Optional, List
from sqlalchemy import select
from datetime import datetime, date
from decimal import Decimal
import pytz

from database.base_repository import BaseRepository
from database.models import CompanyBank


class CompanyBankRepository(BaseRepository[CompanyBank]):
    """
    Репозиторий для работы со счетами компаний в банках
    """

    def __init__(self, session_maker):
        super().__init__(session_maker, CompanyBank)

    async def get_by_company_and_bank(
        self,
        company_id: int,
        bank_id: int
    ) -> Optional[CompanyBank]:
        """Получить счет компании в банке"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(CompanyBank).where(
                    CompanyBank.company_id == company_id,
                    CompanyBank.bank_id == bank_id
                )
            )
            return result.scalar_one_or_none()

    async def get_by_company(self, company_id: int) -> List[CompanyBank]:
        """Получить все счета компании"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(CompanyBank).where(CompanyBank.company_id == company_id)
            )
            return list(result.scalars().all())

    async def get_by_bank(self, bank_id: int) -> List[CompanyBank]:
        """Получить все счета в банке"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(CompanyBank).where(CompanyBank.bank_id == bank_id)
            )
            return list(result.scalars().all())

    async def get_preferred_for_company(self, company_id: int) -> Optional[CompanyBank]:
        """Получить предпочитаемый счет компании"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(CompanyBank).where(
                    CompanyBank.company_id == company_id,
                    CompanyBank.is_preferred == True
                )
            )
            return result.scalar_one_or_none()

    async def set_preferred(self, company_bank_id: int) -> bool:
        """Установить счет как предпочитаемый (сбрасывая другие)"""
        async with self.session_maker() as session:
            # Получаем счет
            cb = await self.get_by_id(company_bank_id)
            if not cb:
                return False

            # Сбрасываем все предпочтения для этой компании
            from sqlalchemy import update
            await session.execute(
                update(CompanyBank)
                .where(CompanyBank.company_id == cb.company_id)
                .values(is_preferred=False)
            )

            # Устанавливаем новое предпочтение
            await session.execute(
                update(CompanyBank)
                .where(CompanyBank.id == company_bank_id)
                .values(is_preferred=True)
            )

            await session.commit()
            return True

    async def increment_counter(self, company_bank_id: int) -> int:
        """
        Увеличить счетчик заявок для счета компании в банке.
        Сбрасывает счетчик если это новый день (00:00 MSK).
        Возвращает новое значение счетчика.
        """
        moscow_tz = pytz.timezone('Europe/Moscow')
        now_msk = datetime.now(moscow_tz)
        today_msk = now_msk.date()

        async with self.session_maker() as session:
            # Получаем счет
            result = await session.execute(
                select(CompanyBank).where(CompanyBank.id == company_bank_id)
            )
            cb = result.scalar_one_or_none()

            if not cb:
                raise ValueError(f"CompanyBank with id {company_bank_id} not found")

            # Проверяем, нужно ли сбросить счетчик
            if cb.counter_date is None or cb.counter_date.date() < today_msk:
                # Новый день - сбрасываем счетчик
                cb.daily_application_counter = 1
                cb.counter_date = now_msk.replace(tzinfo=None)  # Убираем timezone для сохранения в БД
            else:
                # Тот же день - инкрементируем
                cb.daily_application_counter += 1

            await session.commit()
            await session.refresh(cb)

            return cb.daily_application_counter

    async def reset_daily_counter(self, company_bank_id: int) -> bool:
        """Сбросить дневной счетчик заявок"""
        moscow_tz = pytz.timezone('Europe/Moscow')
        now_msk = datetime.now(moscow_tz)

        return await self.update_by_id(
            company_bank_id,
            daily_application_counter=0,
            counter_date=now_msk.replace(tzinfo=None)  # Убираем timezone для сохранения в БД
        )

    async def reset_all_daily_counters(self) -> int:
        """Сбросить все дневные счетчики (для запланированной задачи в 00:00)"""
        moscow_tz = pytz.timezone('Europe/Moscow')
        now_msk = datetime.now(moscow_tz)

        from sqlalchemy import update
        async with self.session_maker() as session:
            stmt = (
                update(CompanyBank)
                .values(
                    daily_application_counter=0,
                    counter_date=now_msk.replace(tzinfo=None)  # Убираем timezone для сохранения в БД
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    async def check_and_update_limits(
        self,
        company_bank_id: int,
        amount: float
    ) -> dict:
        """
        Проверить лимиты счета и обновить использованные суммы.
        Возвращает dict с информацией о лимитах.
        """
        async with self.session_maker() as session:
            result = await session.execute(
                select(CompanyBank).where(CompanyBank.id == company_bank_id)
            )
            cb = result.scalar_one_or_none()

            if not cb:
                raise ValueError(f"CompanyBank with id {company_bank_id} not found")

            # Конвертируем amount в Decimal для совместимости с полями БД
            amount_decimal = Decimal(str(amount))

            # Проверяем лимиты
            daily_available = cb.daily_limit - cb.current_daily_used
            weekly_available = cb.weekly_limit - cb.current_weekly_used
            monthly_available = cb.monthly_limit - cb.current_monthly_used

            # Проверяем, не превышен ли хотя бы один лимит
            limit_exceeded = False
            exceeded_limits = []

            if cb.daily_limit > 0 and amount_decimal > daily_available:
                limit_exceeded = True
                exceeded_limits.append('daily')

            if cb.weekly_limit > 0 and amount_decimal > weekly_available:
                limit_exceeded = True
                exceeded_limits.append('weekly')

            if cb.monthly_limit > 0 and amount_decimal > monthly_available:
                limit_exceeded = True
                exceeded_limits.append('monthly')

            # Обновляем использованные суммы если не превышен
            if not limit_exceeded:
                cb.current_daily_used += amount_decimal
                cb.current_weekly_used += amount_decimal
                cb.current_monthly_used += amount_decimal
                await session.commit()

            return {
                'allowed': not limit_exceeded,
                'exceeded_limits': exceeded_limits,
                'daily_available': float(daily_available),
                'weekly_available': float(weekly_available),
                'monthly_available': float(monthly_available),
                'daily_limit': float(cb.daily_limit),
                'weekly_limit': float(cb.weekly_limit),
                'monthly_limit': float(cb.monthly_limit)
            }
