# bot/database/repositories/log_repository.py

from typing import Optional, List
from sqlalchemy import select
from datetime import datetime, date

from database.base_repository import BaseRepository
from database.models import Log


class LogRepository(BaseRepository[Log]):
    """
    Репозиторий для работы с логами
    """
    
    def __init__(self, session_maker):
        super().__init__(session_maker, Log)
    
    async def create_log(
        self,
        action: str,
        user_id: Optional[int] = None,
        application_id: Optional[int] = None,
        details: Optional[dict] = None
    ) -> Log:
        """Создать лог-запись"""
        return await self.create(
            action=action,
            user_id=user_id,
            application_id=application_id,
            details=details
        )
    
    async def get_by_user(
        self,
        user_id: int,
        limit: int = 50
    ) -> List[Log]:
        """Получить логи пользователя"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(Log)
                .where(Log.user_id == user_id)
                .order_by(Log.created_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())
    
    async def get_by_application(
        self,
        app_id: int
    ) -> List[Log]:
        """Получить логи заявки"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(Log)
                .where(Log.application_id == app_id)
                .order_by(Log.created_at.asc())
            )
            return list(result.scalars().all())
    
    async def get_by_date(
        self,
        target_date: date,
        action: Optional[str] = None
    ) -> List[Log]:
        """Получить логи за дату"""
        async with self.session_maker() as session:
            from sqlalchemy import func
            
            query = select(Log).where(
                func.date(Log.created_at) == target_date
            )
            
            if action:
                query = query.where(Log.action == action)
            
            result = await session.execute(query)
            return list(result.scalars().all())