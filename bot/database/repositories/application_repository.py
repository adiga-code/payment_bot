# bot/database/repositories/application_repository.py

from typing import Optional, List
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from datetime import datetime, date
from decimal import Decimal

from database.base_repository import BaseRepository
from database.models import Application


class ApplicationRepository(BaseRepository[Application]):
    """
    Репозиторий для работы с заявками
    """
    
    def __init__(self, session_maker):
        super().__init__(session_maker, Application)
    
    # ==================== ПОИСК ====================
    
    async def get_by_external_id(self, external_id: str) -> Optional[Application]:
        """Получить заявку по external_id"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(Application).where(Application.external_id == external_id)
            )
            return result.scalar_one_or_none()
    
    async def get_by_status(
        self,
        status: str,
        limit: int = 20,
        offset: int = 0
    ) -> List[Application]:
        """Получить заявки по статусу"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(Application)
                .where(Application.status == status)
                .order_by(Application.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())
    
    async def get_with_relations(self, app_id: int) -> Optional[Application]:
        """Получить заявку со всеми связями"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(Application)
                .options(
                    selectinload(Application.approvals),
                    selectinload(Application.company),
                    selectinload(Application.bank),
                    selectinload(Application.manager),
                    selectinload(Application.documents)
                )
                .where(Application.id == app_id)
            )
            return result.scalar_one_or_none()
    
    async def get_by_manager(
        self,
        manager_id: int,
        status: Optional[str] = None
    ) -> List[Application]:
        """Получить заявки менеджера"""
        async with self.session_maker() as session:
            query = select(Application).where(Application.manager_id == manager_id)
            
            if status:
                query = query.where(Application.status == status)
            
            query = query.order_by(Application.created_at.desc())
            
            result = await session.execute(query)
            return list(result.scalars().all())
    
    async def get_by_company(self, company_id: int) -> List[Application]:
        """Получить заявки компании"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(Application)
                .where(Application.company_id == company_id)
                .order_by(Application.created_at.desc())
            )
            return list(result.scalars().all())
    
    async def get_by_bank(self, bank_id: int) -> List[Application]:
        """Получить заявки банка"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(Application)
                .where(Application.bank_id == bank_id)
                .order_by(Application.created_at.desc())
            )
            return list(result.scalars().all())

    async def get_by_client(self, client_chat_id: int) -> List[Application]:
        """Получить заявки клиента"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(Application)
                .where(Application.client_chat_id == client_chat_id)
                .order_by(Application.created_at.desc())
            )
            return list(result.scalars().all())

    # ==================== ОБНОВЛЕНИЕ СТАТУСОВ ====================
    
    async def update_status(self, app_id: int, new_status: str) -> bool:
        """Обновить статус заявки"""
        return await self.update_by_id(
            app_id,
            status=new_status,
            updated_at=datetime.utcnow()
        )
    
    async def update_primary_check(
        self,
        app_id: int,
        status: str,
        result: dict,
        flags: dict
    ) -> bool:
        """Обновить результаты первичной проверки"""
        return await self.update_by_id(
            app_id,
            primary_check_status=status,
            primary_check_result=result,
            primary_check_flags=flags,
            primary_check_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
    
    async def assign_company(self, app_id: int, company_id: int) -> bool:
        """Назначить компанию"""
        return await self.update_by_id(
            app_id,
            company_id=company_id,
            updated_at=datetime.utcnow()
        )
    
    async def assign_bank(self, app_id: int, bank_id: int, bank_display_number: Optional[int] = None) -> bool:
        """Назначить банк"""
        update_fields = {
            'bank_id': bank_id,
            'sent_to_bank_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        if bank_display_number is not None:
            update_fields['bank_display_number'] = bank_display_number

        return await self.update_by_id(app_id, **update_fields)
    
    async def assign_manager(self, app_id: int, manager_id: int) -> bool:
        """Назначить менеджера"""
        return await self.update_by_id(
            app_id,
            manager_id=manager_id,
            updated_at=datetime.utcnow()
        )
    
    async def mark_approved(self, app_id: int) -> bool:
        """Отметить как одобренную"""
        return await self.update_by_id(
            app_id,
            status='approved',
            approved_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
    
    async def mark_invoice_generated(self, app_id: int) -> bool:
        """Отметить что счет сгенерирован"""
        return await self.update_by_id(
            app_id,
            status='invoice_generated',
            invoice_generated_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
    
    async def mark_paid(self, app_id: int) -> bool:
        """Отметить как оплаченную"""
        return await self.update_by_id(
            app_id,
            status='paid',
            paid_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
    
    # ==================== СТАТИСТИКА ====================
    
    async def get_daily_stats(self, target_date: date) -> List[dict]:
        """Статистика за день"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(
                    Application.status,
                    func.count().label('count'),
                    func.sum(Application.amount).label('total_amount')
                )
                .where(func.date(Application.created_at) == target_date)
                .group_by(Application.status)
            )
            
            return [
                {
                    'status': row.status,
                    'count': row.count,
                    'total_amount': float(row.total_amount) if row.total_amount else 0
                }
                for row in result.all()
            ]
    
    async def get_stats_by_company(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[dict]:
        """Статистика по компаниям"""
        async with self.session_maker() as session:
            query = select(
                Application.company_id,
                func.count().label('count'),
                func.sum(Application.amount).label('total_amount')
            ).group_by(Application.company_id)
            
            if start_date:
                query = query.where(func.date(Application.created_at) >= start_date)
            if end_date:
                query = query.where(func.date(Application.created_at) <= end_date)
            
            result = await session.execute(query)
            
            return [
                {
                    'company_id': row.company_id,
                    'count': row.count,
                    'total_amount': float(row.total_amount) if row.total_amount else 0
                }
                for row in result.all()
            ]
    
    async def get_conversion_rate(self, start_date: date, end_date: date) -> dict:
        """Конверсия заявок"""
        async with self.session_maker() as session:
            # Всего заявок
            total_result = await session.execute(
                select(func.count())
                .select_from(Application)
                .where(
                    func.date(Application.created_at) >= start_date,
                    func.date(Application.created_at) <= end_date
                )
            )
            total = total_result.scalar_one()
            
            # Оплаченных
            paid_result = await session.execute(
                select(func.count())
                .select_from(Application)
                .where(
                    func.date(Application.created_at) >= start_date,
                    func.date(Application.created_at) <= end_date,
                    Application.status == 'paid'
                )
            )
            paid = paid_result.scalar_one()
            
            # Отклоненных
            rejected_result = await session.execute(
                select(func.count())
                .select_from(Application)
                .where(
                    func.date(Application.created_at) >= start_date,
                    func.date(Application.created_at) <= end_date,
                    Application.status == 'rejected'
                )
            )
            rejected = rejected_result.scalar_one()
            
            return {
                'total': total,
                'paid': paid,
                'rejected': rejected,
                'conversion_rate': (paid / total * 100) if total > 0 else 0,
                'rejection_rate': (rejected / total * 100) if total > 0 else 0
            }

    async def get_stats_by_client(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[dict]:
        """Статистика по клиентам"""
        async with self.session_maker() as session:
            query = select(
                Application.client_chat_id,
                func.count().label('count'),
                func.sum(Application.amount).label('total_amount')
            ).group_by(Application.client_chat_id)

            if start_date:
                query = query.where(func.date(Application.created_at) >= start_date)
            if end_date:
                query = query.where(func.date(Application.created_at) <= end_date)

            result = await session.execute(query)

            return [
                {
                    'client_chat_id': row.client_chat_id,
                    'count': row.count,
                    'total_amount': float(row.total_amount) if row.total_amount else 0
                }
                for row in result.all()
            ]

    async def get_stats_by_bank(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[dict]:
        """Статистика по банкам"""
        async with self.session_maker() as session:
            query = select(
                Application.bank_id,
                func.count().label('count'),
                func.sum(Application.amount).label('total_amount')
            ).group_by(Application.bank_id)

            if start_date:
                query = query.where(func.date(Application.created_at) >= start_date)
            if end_date:
                query = query.where(func.date(Application.created_at) <= end_date)

            result = await session.execute(query)

            return [
                {
                    'bank_id': row.bank_id,
                    'count': row.count,
                    'total_amount': float(row.total_amount) if row.total_amount else 0
                }
                for row in result.all()
            ]

    async def get_detailed_stats(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> dict:
        """Детальная статистика за период"""
        async with self.session_maker() as session:
            # Базовый запрос с фильтрацией по датам
            base_query = select(Application)
            if start_date:
                base_query = base_query.where(func.date(Application.created_at) >= start_date)
            if end_date:
                base_query = base_query.where(func.date(Application.created_at) <= end_date)

            result = await session.execute(base_query)
            apps = result.scalars().all()

            # Подсчет общей статистики
            total_count = len(apps)
            total_amount = sum(app.amount for app in apps)

            # Группировка по статусам
            by_status = {}
            for app in apps:
                if app.status not in by_status:
                    by_status[app.status] = {'count': 0, 'amount': 0}
                by_status[app.status]['count'] += 1
                by_status[app.status]['amount'] += float(app.amount)

            # Группировка по компаниям
            by_company = {}
            for app in apps:
                if app.company_id:
                    if app.company_id not in by_company:
                        by_company[app.company_id] = {'count': 0, 'amount': 0}
                    by_company[app.company_id]['count'] += 1
                    by_company[app.company_id]['amount'] += float(app.amount)

            # Группировка по банкам
            by_bank = {}
            for app in apps:
                if app.bank_id:
                    if app.bank_id not in by_bank:
                        by_bank[app.bank_id] = {'count': 0, 'amount': 0}
                    by_bank[app.bank_id]['count'] += 1
                    by_bank[app.bank_id]['amount'] += float(app.amount)

            # Группировка по клиентам
            by_client = {}
            for app in apps:
                if app.client_chat_id:
                    if app.client_chat_id not in by_client:
                        by_client[app.client_chat_id] = {'count': 0, 'amount': 0}
                    by_client[app.client_chat_id]['count'] += 1
                    by_client[app.client_chat_id]['amount'] += float(app.amount)

            # Группировка по датам
            by_date = {}
            for app in apps:
                app_date = app.created_at.date()
                if app_date not in by_date:
                    by_date[app_date] = {'count': 0, 'amount': 0}
                by_date[app_date]['count'] += 1
                by_date[app_date]['amount'] += float(app.amount)

            return {
                'total_count': total_count,
                'total_amount': float(total_amount),
                'by_status': by_status,
                'by_company': by_company,
                'by_bank': by_bank,
                'by_client': by_client,
                'by_date': by_date
            }

    async def get_applications_by_period(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        status: Optional[str] = None
    ) -> List[Application]:
        """Получить заявки за период с опциональным фильтром по статусу"""
        async with self.session_maker() as session:
            query = select(Application)

            if start_date:
                query = query.where(func.date(Application.created_at) >= start_date)
            if end_date:
                query = query.where(func.date(Application.created_at) <= end_date)
            if status:
                query = query.where(Application.status == status)

            query = query.order_by(Application.created_at.desc())

            result = await session.execute(query)
            return list(result.scalars().all())

    async def get_pending_primary_check(self) -> List[Application]:
        """Получить заявки, ожидающие первичной проверки"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(Application)
                .where(Application.primary_check_status == 'pending')
                .order_by(Application.created_at.asc())
            )
            return list(result.scalars().all())

    async def clear_company(self, company_id: int) -> int:
        """Обнулить company_id у всех заявок компании (перед удалением)"""
        from sqlalchemy import update
        async with self.session_maker() as session:
            stmt = (
                update(Application)
                .where(Application.company_id == company_id)
                .values(company_id=None)
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    async def clear_bank(self, bank_id: int) -> int:
        """Обнулить bank_id у всех заявок банка (перед удалением)"""
        from sqlalchemy import update
        async with self.session_maker() as session:
            stmt = (
                update(Application)
                .where(Application.bank_id == bank_id)
                .values(bank_id=None)
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    # ==================== PAYMENT CONFIRMATION FLOW ====================

    async def mark_invoice_sent(self, app_id: int) -> bool:
        """Отметить что счёт отправлен клиенту"""
        return await self.update_by_id(
            app_id,
            status='invoice_sent',
            invoice_sent_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

    async def mark_client_confirmed(self, app_id: int) -> bool:
        """Отметить что клиент подтвердил оплату"""
        return await self.update_by_id(
            app_id,
            status='client_confirmed',
            client_confirmed_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

    async def mark_payment_received(self, app_id: int) -> bool:
        """Отметить что бухгалтер подтвердил получение средств"""
        return await self.update_by_id(
            app_id,
            status='payment_received',
            payment_received_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

    async def update_payout(
        self,
        app_id: int,
        payout_format: str,
        payout_date: datetime
    ) -> bool:
        """Установить формат и дату выдачи"""
        return await self.update_by_id(
            app_id,
            payout_format=payout_format,
            payout_date=payout_date,
            updated_at=datetime.utcnow()
        )

    async def cancel_application(self, app_id: int, reason: str) -> bool:
        """Отменить заявку с причиной"""
        return await self.update_by_id(
            app_id,
            status='cancelled',
            cancellation_reason=reason,
            updated_at=datetime.utcnow()
        )

    async def get_pending_client_payment(self) -> List[Application]:
        """Получить заявки, ожидающие подтверждения оплаты от клиента (invoice_sent)"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(Application)
                .where(Application.status == 'invoice_sent')
                .order_by(Application.invoice_sent_at.asc())
            )
            return list(result.scalars().all())

    async def get_pending_accountant_confirmation(self) -> List[Application]:
        """Получить заявки, ожидающие подтверждения от бухгалтера (client_confirmed)"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(Application)
                .where(Application.status == 'client_confirmed')
                .order_by(Application.client_confirmed_at.asc())
            )
            return list(result.scalars().all())