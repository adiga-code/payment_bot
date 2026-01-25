# bot/database/repositories/approval_repository.py

from typing import Optional, List
from sqlalchemy import select, func
from datetime import datetime

from database.base_repository import BaseRepository
from database.models import Approval


class ApprovalRepository(BaseRepository[Approval]):
    """
    Репозиторий для работы с подписями (мультиподпись)
    """
    
    def __init__(self, session_maker):
        super().__init__(session_maker, Approval)
    
    # ==================== СОЗДАНИЕ WORKFLOW ====================
    
    async def create_workflow(self, app_id: int, steps: List[dict]) -> List[Approval]:
        """
        Создать workflow подписей
        
        Args:
            app_id: ID заявки
            steps: [
                {'role': 'manager', 'sequence': 1},
                {'role': 'bank', 'sequence': 2},
                {'role': 'supervisor', 'sequence': 3}
            ]
        """
        async with self.session_maker() as session:
            approvals = []
            
            for step in steps:
                approval = Approval(
                    application_id=app_id,
                    role=step['role'],
                    sequence=step['sequence'],
                    required=step.get('required', True)
                )
                session.add(approval)
                approvals.append(approval)
            
            await session.commit()
            
            # Refresh всех объектов
            for approval in approvals:
                await session.refresh(approval)
            
            return approvals
    
    async def create_escalation(
        self,
        app_id: int,
        role: str,
        reason: str,
        sequence: int = 999
    ) -> Approval:
        """Создать внеочередную подпись (эскалация)"""
        return await self.create(
            application_id=app_id,
            role=role,
            sequence=sequence,
            required=True,
            comment=f"Эскалация: {reason}"
        )
    
    # ==================== ПОИСК ====================
    
    async def get_by_application(self, app_id: int) -> List[Approval]:
        """Получить все подписи заявки"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(Approval)
                .where(Approval.application_id == app_id)
                .order_by(Approval.sequence.asc())
            )
            return list(result.scalars().all())
    
    async def get_pending(self, app_id: int) -> Optional[Approval]:
        """Получить следующий этап подписи (ожидающий)"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(Approval)
                .where(
                    Approval.application_id == app_id,
                    Approval.decision.is_(None)
                )
                .order_by(Approval.sequence.asc())
            )
            return result.scalars().first()
    
    async def get_by_role(self, app_id: int, role: str) -> Optional[Approval]:
        """Получить подпись по роли"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(Approval)
                .where(
                    Approval.application_id == app_id,
                    Approval.role == role
                )
                .order_by(Approval.sequence.asc())
            )
            return result.scalars().first()
    
    async def is_all_approved(self, app_id: int) -> bool:
        """Проверить: все ли подписи одобрены"""
        async with self.session_maker() as session:
            # Всего требуемых подписей
            total_result = await session.execute(
                select(func.count())
                .select_from(Approval)
                .where(
                    Approval.application_id == app_id,
                    Approval.required == True
                )
            )
            total = total_result.scalar_one()
            
            # Одобренных
            approved_result = await session.execute(
                select(func.count())
                .select_from(Approval)
                .where(
                    Approval.application_id == app_id,
                    Approval.required == True,
                    Approval.decision == 'approved'
                )
            )
            approved = approved_result.scalar_one()
            
            return total == approved and total > 0
    
    # ==================== ОБНОВЛЕНИЕ ====================
    
    async def approve(
        self,
        approval_id: int,
        user_id: int,
        comment: Optional[str] = None
    ) -> bool:
        """Подписать этап"""
        return await self.update_by_id(
            approval_id,
            decision='approved',
            user_id=user_id,
            comment=comment,
            decided_at=datetime.utcnow()
        )
    
    async def reject(
        self,
        approval_id: int,
        user_id: int,
        reason: str
    ) -> bool:
        """Отклонить этап"""
        return await self.update_by_id(
            approval_id,
            decision='rejected',
            user_id=user_id,
            comment=reason,
            decided_at=datetime.utcnow()
        )
    
    async def escalate(
        self,
        approval_id: int,
        user_id: int,
        reason: str
    ) -> bool:
        """Эскалировать"""
        return await self.update_by_id(
            approval_id,
            decision='escalated',
            user_id=user_id,
            comment=reason,
            decided_at=datetime.utcnow()
        )
    
    # ==================== СТАТИСТИКА ====================
    
    async def get_avg_approval_time_by_role(self, role: str) -> Optional[float]:
        """Среднее время подписи по роли (в минутах)"""
        async with self.session_maker() as session:
            result = await session.execute(
                select(
                    func.avg(
                        func.extract('epoch', Approval.decided_at - Approval.created_at) / 60
                    )
                )
                .where(
                    Approval.role == role,
                    Approval.decision == 'approved',
                    Approval.decided_at.isnot(None)
                )
            )
            return result.scalar_one_or_none()