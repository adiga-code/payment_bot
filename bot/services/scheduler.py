# bot/services/scheduler.py

import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Optional

from database import CompanyRepository, BankRepository, ApplicationRepository

logger = logging.getLogger(__name__)


class SchedulerService:
    """Фоновые задачи: сброс лимитов и напоминания по расписанию"""

    def __init__(
        self,
        company_repo: CompanyRepository,
        bank_repo: BankRepository,
        application_repo: Optional[ApplicationRepository] = None,
        notification_service=None
    ):
        self.company_repo = company_repo
        self.bank_repo = bank_repo
        self.application_repo = application_repo
        self.notification_service = notification_service
        self._tasks: list[asyncio.Task] = []

    async def start(self):
        """Запустить все фоновые задачи"""
        self._tasks.append(asyncio.create_task(self._daily_reset_loop()))
        self._tasks.append(asyncio.create_task(self._weekly_reset_loop()))
        self._tasks.append(asyncio.create_task(self._monthly_reset_loop()))

        # Задачи для payment confirmation flow (если репозитории доступны)
        if self.application_repo and self.notification_service:
            # 18:00 MSK (15:00 UTC) - напоминание клиентам об оплате
            self._tasks.append(asyncio.create_task(self._client_payment_reminder_loop()))
            # 20:00 MSK (17:00 UTC) - напоминание бухгалтерам о проверке
            self._tasks.append(asyncio.create_task(self._accountant_reminder_loop()))
            # 21:00 MSK (18:00 UTC) - автоотмена неоплаченных заявок
            self._tasks.append(asyncio.create_task(self._auto_cancel_unpaid_loop()))
            logger.info("Scheduler started: limit resets + payment reminders")
        else:
            logger.info("Scheduler started: daily/weekly/monthly limit resets")

    async def stop(self):
        """Остановить все задачи"""
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        logger.info("Scheduler stopped")

    async def _seconds_until(self, target: time) -> float:
        """Секунд до указанного времени суток (UTC)"""
        now = datetime.utcnow()
        target_dt = datetime.combine(now.date(), target)
        if target_dt <= now:
            target_dt += timedelta(days=1)
        return (target_dt - now).total_seconds()

    async def _daily_reset_loop(self):
        """Сброс дневных лимитов каждый день в 00:00 UTC"""
        while True:
            try:
                sleep_sec = await self._seconds_until(time(0, 0))
                await asyncio.sleep(sleep_sec)

                companies = await self.company_repo.reset_daily_limits()
                banks = await self.bank_repo.reset_daily_limits()
                logger.info(f"Daily limits reset: {companies} companies, {banks} banks")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in daily reset: {e}")
                await asyncio.sleep(60)

    async def _weekly_reset_loop(self):
        """Сброс недельных лимитов каждый понедельник в 00:05 UTC"""
        while True:
            try:
                sleep_sec = await self._seconds_until(time(0, 5))
                await asyncio.sleep(sleep_sec)

                now = datetime.utcnow()
                if now.weekday() == 0:  # Понедельник
                    companies = await self.company_repo.reset_weekly_limits()
                    banks = await self.bank_repo.reset_weekly_limits()
                    logger.info(f"Weekly limits reset: {companies} companies, {banks} banks")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in weekly reset: {e}")
                await asyncio.sleep(60)

    async def _monthly_reset_loop(self):
        """Сброс месячных лимитов 1-го числа в 00:10 UTC"""
        while True:
            try:
                sleep_sec = await self._seconds_until(time(0, 10))
                await asyncio.sleep(sleep_sec)

                now = datetime.utcnow()
                if now.day == 1:
                    companies = await self.company_repo.reset_monthly_limits()
                    logger.info(f"Monthly limits reset: {companies} companies")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monthly reset: {e}")
                await asyncio.sleep(60)

    # ==================== PAYMENT CONFIRMATION TASKS ====================

    async def _client_payment_reminder_loop(self):
        """Напоминание клиентам об оплате в 18:00 MSK (15:00 UTC)"""
        while True:
            try:
                sleep_sec = await self._seconds_until(time(15, 0))
                await asyncio.sleep(sleep_sec)

                # Получаем заявки со статусом invoice_sent
                pending_apps = await self.application_repo.get_pending_client_payment()

                for app in pending_apps:
                    try:
                        await self.notification_service.notify_client_payment_reminder(app)
                    except Exception as e:
                        logger.error(f"Failed to send reminder for app {app.id}: {e}")

                if pending_apps:
                    logger.info(f"Client payment reminders sent: {len(pending_apps)}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in client reminder loop: {e}")
                await asyncio.sleep(60)

    async def _accountant_reminder_loop(self):
        """Напоминание бухгалтерам в 20:00 MSK (17:00 UTC)"""
        while True:
            try:
                sleep_sec = await self._seconds_until(time(17, 0))
                await asyncio.sleep(sleep_sec)

                # Получаем заявки со статусом client_confirmed
                pending_apps = await self.application_repo.get_pending_accountant_confirmation()

                if pending_apps:
                    try:
                        await self.notification_service.notify_accountant_daily_reminder(pending_apps)
                        logger.info(f"Accountant reminder sent: {len(pending_apps)} pending confirmations")
                    except Exception as e:
                        logger.error(f"Failed to send accountant reminder: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in accountant reminder loop: {e}")
                await asyncio.sleep(60)

    async def _auto_cancel_unpaid_loop(self):
        """Автоотмена неоплаченных заявок в 21:00 MSK (18:00 UTC)"""
        while True:
            try:
                sleep_sec = await self._seconds_until(time(18, 0))
                await asyncio.sleep(sleep_sec)

                # Получаем заявки со статусом invoice_sent (клиент не подтвердил)
                pending_apps = await self.application_repo.get_pending_client_payment()

                cancelled_count = 0
                for app in pending_apps:
                    try:
                        # Отменяем заявку
                        await self.application_repo.cancel_application(
                            app.id,
                            "Автоматическая отмена: клиент не подтвердил оплату до конца дня"
                        )
                        # Уведомляем менеджера
                        await self.notification_service.notify_manager_payment_failed(
                            app,
                            "Клиент не подтвердил оплату до конца дня"
                        )
                        cancelled_count += 1
                    except Exception as e:
                        logger.error(f"Failed to auto-cancel app {app.id}: {e}")

                if cancelled_count:
                    logger.info(f"Auto-cancelled unpaid applications: {cancelled_count}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in auto-cancel loop: {e}")
                await asyncio.sleep(60)
