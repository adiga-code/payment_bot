# bot/database/base_repository.py

from typing import TypeVar, Generic, Optional, List, Type, Any
from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

T = TypeVar('T')  # Тип ORM модели


class BaseRepository(Generic[T]):
    """
    Базовый репозиторий со стандартными CRUD операциями
    """
    
    def __init__(self, session_maker: async_sessionmaker, model_class: Type[T]):
        self.session_maker = session_maker
        self.model_class = model_class
    
    # ==================== CREATE ====================
    
    async def create(self, **kwargs) -> T:
        """Создать запись"""
        async with self.session_maker() as session:
            obj = self.model_class(**kwargs)
            session.add(obj)
            await session.commit()
            await session.refresh(obj)
            return obj
    
    async def create_many(self, items: List[dict]) -> List[T]:
        """Создать несколько записей"""
        async with self.session_maker() as session:
            objects = [self.model_class(**item) for item in items]
            session.add_all(objects)
            await session.commit()
            
            for obj in objects:
                await session.refresh(obj)
            
            return objects
    
    # ==================== READ ====================
    
    async def get_by_id(self, id: int) -> Optional[T]:
        """Получить по ID"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(self.model_class).where(self.model_class.id == id)
            )
            return result.scalar_one_or_none()
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[T]:
        """Получить все записи с пагинацией"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(self.model_class)
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())
    
    async def count(self) -> int:
        """Подсчитать общее количество записей"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(func.count()).select_from(self.model_class)
            )
            return result.scalar_one()
    
    async def exists(self, id: int) -> bool:
        """Проверить существование записи"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(func.count())
                .select_from(self.model_class)
                .where(self.model_class.id == id)
            )
            return result.scalar_one() > 0
    
    # ==================== UPDATE ====================
    
    async def update_by_id(self, id: int, **kwargs) -> bool:
        """Обновить запись по ID"""
        async with self.session_maker() as session:
            stmt = (
                update(self.model_class)
                .where(self.model_class.id == id)
                .values(**kwargs)
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0
    
    async def update_object(self, obj: T) -> T:
        """Обновить объект целиком"""
        async with self.session_maker() as session:
            obj = await session.merge(obj)
            await session.commit()
            await session.refresh(obj)
            return obj
    
    # ==================== DELETE ====================
    
    async def delete_by_id(self, id: int) -> bool:
        """Удалить по ID"""
        async with self.session_maker() as session:
            stmt = delete(self.model_class).where(self.model_class.id == id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0
    
    async def delete_object(self, obj: T) -> bool:
        """Удалить объект"""
        async with self.session_maker() as session:
            await session.delete(obj)
            await session.commit()
            return True