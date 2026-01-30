# bot/handlers/bank.py

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery

from database import (
    ApplicationRepository,
    ApprovalRepository,
    UserRepository,
    BankRepository,
    LogRepository
)
from keyboards.bank_kb import BankKeyboards
from middleware import RoleRequiredMiddleware


REJECTION_REASONS = {
    'high_risk_op': 'Высокий риск операции',
    'suspicious': 'Подозрительный контрагент',
    'blacklist': 'Контрагент в чёрном списке',
    'docs_mismatch': 'Несоответствие документов',
}


class BankHandlers:
    """Хендлеры для сотрудника банка (работа через групповой чат)"""

    ALLOWED_ROLES = ['bank', 'supervisor', 'admin']

    def __init__(
            self,
            user_repo: UserRepository,
            application_repo: ApplicationRepository,
            approval_repo: ApprovalRepository,
            bank_repo: BankRepository,
            log_repo: LogRepository,
            bot: Bot
    ):
        self.router = Router()
        self.user_repo = user_repo
        self.application_repo = application_repo
        self.approval_repo = approval_repo
        self.bank_repo = bank_repo
        self.log_repo = log_repo
        self.bot = bot
        self.kb = BankKeyboards()

        self._setup_middleware()
        self._setup_handlers()

    def _setup_middleware(self):
        """Middleware для проверки роли"""
        self.router.callback_query.middleware(
            RoleRequiredMiddleware(self.ALLOWED_ROLES, self.user_repo)
        )

    def _setup_handlers(self):
        """Регистрация обработчиков"""
        self.router.callback_query(F.data.startswith("bank:risk:"))(self.cb_risk_assessment)
        self.router.callback_query(F.data.startswith("bank:reject:"))(self.cb_reject_reason)
        self.router.callback_query(F.data.startswith("bank:cancel_reject:"))(self.cb_cancel_reject)

    # ==================== CALLBACK HANDLERS ====================

    async def cb_risk_assessment(self, callback: CallbackQuery, db_user):
        """Оценка риска"""
        parts = callback.data.split(":")
        app_id = int(parts[2])
        risk_level = parts[3]

        app = await self.application_repo.get_with_relations(app_id)
        if not app:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        if risk_level == "high_risk":
            # Показываем выбор причины отклонения
            await callback.message.edit_text(
                f"❌ <b>Отклонение заявки</b>\n\n"
                f"📋 {app.external_id}\n"
                f"💰 {app.amount:,.0f}₽\n\n"
                f"Выберите причину отклонения:",
                reply_markup=self.kb.rejection_reasons(app_id),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        # Одобряем этап банка
        pending_approval = await self.approval_repo.get_by_role(app_id, 'bank')
        if pending_approval and not pending_approval.decision:
            comment = "Без риска" if risk_level == "no_risk" else "Минимальный риск"
            await self.approval_repo.approve(pending_approval.id, db_user.id, comment)

        # Логируем
        await self.log_repo.create_log(
            action='bank_approved',
            application_id=app_id,
            user_id=db_user.id,
            details={'risk_level': risk_level}
        )

        employee_name = db_user.first_name or db_user.username

        if risk_level == "min_risk":
            # Минимальный риск - эскалация к руководителю
            await self.approval_repo.create_escalation(
                app_id=app_id,
                role='supervisor',
                reason='Минимальный риск - требуется решение руководителя',
                sequence=0
            )
            await self.application_repo.update_status(app_id, 'supervisor_review')

            await callback.message.edit_text(
                f"⚠️ <b>Минимальный риск</b>\n\n"
                f"📋 {app.external_id}\n"
                f"💰 {app.amount:,.0f}₽\n\n"
                f"👤 Оценил: {employee_name}\n"
                f"📤 Заявка отправлена руководителю на решение.",
                parse_mode="HTML"
            )
            await callback.answer("Отправлено руководителю")

            # TODO: Уведомить руководителя
        else:
            # Без риска - на финальное одобрение
            await self.application_repo.update_status(app_id, 'supervisor_review')

            await callback.message.edit_text(
                f"✅ <b>Без риска</b>\n\n"
                f"📋 {app.external_id}\n"
                f"💰 {app.amount:,.0f}₽\n\n"
                f"👤 Оценил: {employee_name}\n"
                f"📤 Заявка отправлена руководителю на финальное одобрение.",
                parse_mode="HTML"
            )
            await callback.answer("Отправлено руководителю")

            # TODO: Уведомить руководителя

    async def cb_reject_reason(self, callback: CallbackQuery, db_user):
        """Отклонение заявки с выбранной причиной"""
        parts = callback.data.split(":")
        app_id = int(parts[2])
        reason_code = parts[3]

        app = await self.application_repo.get_by_id(app_id)
        if not app:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        reason = REJECTION_REASONS.get(reason_code, reason_code)

        # Отклоняем этап банка
        pending_approval = await self.approval_repo.get_by_role(app_id, 'bank')
        if pending_approval:
            await self.approval_repo.reject(pending_approval.id, db_user.id, reason)

        # Обновляем статус заявки
        await self.application_repo.update_status(app_id, 'rejected')

        # Логируем
        await self.log_repo.create_log(
            action='bank_rejected',
            application_id=app_id,
            user_id=db_user.id,
            details={'reason': reason_code}
        )

        employee_name = db_user.first_name or db_user.username

        await callback.message.edit_text(
            f"❌ <b>Заявка отклонена</b>\n\n"
            f"📋 {app.external_id}\n"
            f"💰 {app.amount:,.0f}₽\n\n"
            f"👤 Отклонил: {employee_name}\n"
            f"📝 Причина: {reason}",
            parse_mode="HTML"
        )
        await callback.answer("Заявка отклонена")

        # TODO: Уведомить клиента и менеджера

    async def cb_cancel_reject(self, callback: CallbackQuery, db_user):
        """Отмена отклонения — возврат к кнопкам оценки риска"""
        app_id = int(callback.data.split(":")[-1])
        app = await self.application_repo.get_with_relations(app_id)

        if not app:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        # Возвращаем исходное уведомление с кнопками
        notification_text = (
            f"📥 <b>Заявка на оценку риска</b>\n\n"
            f"📋 {app.external_id}\n"
            f"💰 Сумма: <b>{app.amount:,.0f}₽</b>\n"
            f"🏢 ИНН плательщика: <code>{app.payer_inn}</code>\n"
        )
        if app.payer_name:
            notification_text += f"📛 Плательщик: {app.payer_name}\n"
        notification_text += f"📝 Назначение: {app.purpose}\n"
        if app.company:
            notification_text += f"🏢 Компания: {app.company.name}\n"
        if app.manager:
            notification_text += f"\n👔 Менеджер: {app.manager.first_name or app.manager.username}\n"
        notification_text += "\n<b>Оцените уровень риска:</b>"

        await callback.message.edit_text(
            notification_text,
            reply_markup=self.kb.group_risk_assessment(app_id),
            parse_mode="HTML"
        )
        await callback.answer()
