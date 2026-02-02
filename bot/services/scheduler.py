# bot/services/scheduler.py

import asyncio
import logging
from datetime import datetime, time, timedelta

from database import CompanyRepository, BankRepository

logger = logging.getLogger(__name__)


class SchedulerService:
    """Фоновые задачи: сброс лимитов по расписанию"""

    def __init__(self, company_repo: CompanyRepository, bank_repo: BankRepository):
        self.company_repo = company_repo
        self.bank_repo = bank_repo
        self._tasks: list[asyncio.Task] = []

    async def start(self):
        """Запустить все фоновые задачи"""
        self._tasks.append(asyncio.create_task(self._daily_reset_loop()))
        self._tasks.append(asyncio.create_task(self._weekly_reset_loop()))
        self._tasks.append(asyncio.create_task(self._monthly_reset_loop()))
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
