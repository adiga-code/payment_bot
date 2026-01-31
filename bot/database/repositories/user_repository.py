# bot/database/repositories/user_repository.py

from typing import Optional, List
from sqlalchemy import select

from database.base_repository import BaseRepository
from database.models import User


class UserRepository(BaseRepository[User]):
    """
    Репозиторий для работы с пользователями
    """
    
    def __init__(self, session_maker):
        super().__init__(session_maker, User)
    
    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        """Получить пользователя по Telegram ID"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            return result.scalar_one_or_none()
    
    async def get_or_create(
        self,
        telegram_id: int,
        role: str,
        **kwargs
    ) -> tuple[User, bool]:
        """
        Получить или создать пользователя
        
        Returns:
            (user, created) - пользователь и флаг создания
        """
        user = await self.get_by_telegram_id(telegram_id)
        
        if user:
            return user, False
        
        user = await self.create(
            telegram_id=telegram_id,
            role=role,
            **kwargs
        )
        return user, True
    
    async def get_by_role(self, role: str, active_only: bool = True) -> List[User]:
        """Получить всех пользователей с ролью"""
        async with self.session_maker() as session:
            query = select(User).where(User.role == role)
            
            if active_only:
                query = query.where(User.is_active == True)
            
            result = await session.execute(query)
            return list(result.scalars().all())
    
    async def get_managers(self) -> List[User]:
        """Получить всех активных менеджеров"""
        return await self.get_by_role('manager')
    
    async def get_supervisors(self) -> List[User]:
        """Получить всех активных руководителей"""
        return await self.get_by_role('supervisor')
    
    async def get_accountants(self) -> List[User]:
        """Получить всех активных бухгалтеров"""
        return await self.get_by_role('accountant')
    
    async def deactivate(self, user_id: int) -> bool:
        """Деактивировать пользователя"""
        return await self.update_by_id(user_id, is_active=False)
    
    async def activate(self, user_id: int) -> bool:
        """Активировать пользователя"""
        return await self.update_by_id(user_id, is_active=True)
    
    async def update_role(self, user_id: int, new_role: str) -> bool:
        """Обновить роль пользователя"""
        return await self.update_by_id(user_id, role=new_role)

    async def update_bank(self, user_id: int, bank_id: int | None) -> bool:
        """Привязать/отвязать пользователя от банка"""
        return await self.update_by_id(user_id, bank_id=bank_id)

    async def get_by_bank_id(self, bank_id: int) -> List[User]:
        """Получить всех сотрудников банка"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(User).where(
                    User.bank_id == bank_id,
                    User.role == 'bank',
                    User.is_active == True
                )
            )
            return list(result.scalars().all())