# bot/database/repositories/document_repository.py

from typing import Optional, List
from sqlalchemy import select

from database.base_repository import BaseRepository
from database.models import Document


class DocumentRepository(BaseRepository[Document]):
    """
    Репозиторий для работы с документами
    """
    
    def __init__(self, session_maker):
        super().__init__(session_maker, Document)
    
    async def get_by_application(
        self,
        app_id: int,
        doc_type: Optional[str] = None
    ) -> List[Document]:
        """Получить документы заявки"""
        async with self.session_maker() as session:
            query = select(Document).where(Document.application_id == app_id)
            
            if doc_type:
                query = query.where(Document.type == doc_type)
            
            query = query.order_by(Document.generated_at.desc())
            
            result = await session.execute(query)
            return list(result.scalars().all())
    
    async def get_latest_invoice(self, app_id: int) -> Optional[Document]:
        """Получить последний счет"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(Document)
                .where(
                    Document.application_id == app_id,
                    Document.type == 'invoice',
                    Document.is_active == True
                )
                .order_by(Document.generated_at.desc())
            )
            return result.scalars().first()
    
    async def deactivate_old(self, app_id: int, doc_type: str) -> int:
        """Деактивировать старые документы типа"""
        async with self.session_maker() as session:
            from sqlalchemy import update
            
            stmt = (
                update(Document)
                .where(
                    Document.application_id == app_id,
                    Document.type == doc_type
                )
                .values(is_active=False)
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount