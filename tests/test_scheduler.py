"""Тесты для SchedulerService"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'bot'))

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import time

from services.scheduler import SchedulerService


class TestSchedulerService:
    """Тесты планировщика сброса лимитов"""

    def test_init(self):
        company_repo = MagicMock()
        bank_repo = MagicMock()
        scheduler = SchedulerService(company_repo, bank_repo)
        assert scheduler.company_repo is company_repo
        assert scheduler.bank_repo is bank_repo
        assert scheduler._tasks == []

    @pytest.mark.asyncio
    async def test_start_creates_tasks(self):
        company_repo = MagicMock()
        bank_repo = MagicMock()
        scheduler = SchedulerService(company_repo, bank_repo)

        await scheduler.start()
        assert len(scheduler._tasks) == 3

        # Cleanup
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_tasks(self):
        company_repo = MagicMock()
        bank_repo = MagicMock()
        scheduler = SchedulerService(company_repo, bank_repo)

        await scheduler.start()
        assert len(scheduler._tasks) == 3

        await scheduler.stop()
        assert len(scheduler._tasks) == 0

    @pytest.mark.asyncio
    async def test_seconds_until_future(self):
        company_repo = MagicMock()
        bank_repo = MagicMock()
        scheduler = SchedulerService(company_repo, bank_repo)

        # Должно вернуть положительное число
        seconds = await scheduler._seconds_until(time(23, 59, 59))
        assert seconds >= 0
