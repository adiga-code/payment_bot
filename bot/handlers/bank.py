# bot/handlers/bank.py

from datetime import datetime, date

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, func

from database import (
    ApplicationRepository,
    ApprovalRepository,
    UserRepository,
    BankRepository,
    LogRepository
)
from database.models import Application
from services.notification import NotificationService
from keyboards.bank_kb import BankKeyboards
from middleware import RoleRequiredMiddleware
from utils import format_application_number


REJECTION_REASONS = {
    'high_risk_op': 'Высокий риск операции',
    'suspicious': 'Подозрительный контрагент',
    'blacklist': 'Контрагент в чёрном списке',
    'docs_mismatch': 'Несоответствие документов',
}


class BankStates(StatesGroup):
    """FSM состояния для банка"""
    waiting_for_risk_comment = State()  # Ожидание комментария к минимальному риску


class BankHandlers:
    """Хендлеры для сотрудника банка (работа через групповой чат + личный кабинет)"""

    ALLOWED_ROLES = ['bank', 'supervisor', 'admin']

    def __init__(
            self,
            user_repo: UserRepository,
            application_repo: ApplicationRepository,
            approval_repo: ApprovalRepository,
            bank_repo: BankRepository,
            log_repo: LogRepository,
            bot: Bot,
            notification_service: NotificationService = None
    ):
        self.router = Router()
        self.user_repo = user_repo
        self.application_repo = application_repo
        self.approval_repo = approval_repo
        self.bank_repo = bank_repo
        self.log_repo = log_repo
        self.bot = bot
        self.notification_service = notification_service
        self.kb = BankKeyboards()

        self._setup_middleware()
        self._setup_handlers()

    def _setup_middleware(self):
        """Middleware для проверки роли"""
        role_middleware = RoleRequiredMiddleware(self.ALLOWED_ROLES, self.user_repo)
        self.router.message.middleware(role_middleware)
        self.router.callback_query.middleware(role_middleware)

    def _setup_handlers(self):
        """Регистрация обработчиков"""
        # Панель банка (личный чат)
        self.router.message(Command("bank"), F.chat.type == "private")(self.cmd_bank)
        self.router.callback_query(F.data == "bankpanel:menu")(self.cb_bank_menu)
        self.router.callback_query(F.data == "bankpanel:stats")(self.cb_bank_stats)
        self.router.callback_query(F.data == "bankpanel:limits")(self.cb_bank_limits)

        # Оценка рисков (групповой чат)
        self.router.callback_query(F.data.startswith("bank:risk:"))(self.cb_risk_assessment)
        self.router.callback_query(F.data.startswith("bank:reject:"))(self.cb_reject_reason)
        self.router.callback_query(F.data.startswith("bank:cancel_reject:"))(self.cb_cancel_reject)

        # FSM обработчики
        self.router.message(BankStates.waiting_for_risk_comment)(self.process_risk_comment)

    # ==================== ПАНЕЛЬ БАНКА ====================

    async def cmd_bank(self, message: Message, db_user):
        """Команда /bank — панель сотрудника банка"""
        bank = await self._get_user_bank(db_user)
        if not bank:
            await message.answer("❌ Вы не привязаны к банку.")
            return

        text = await self._build_bank_summary(bank)
        await message.answer(text, reply_markup=self.kb.panel_menu(), parse_mode="HTML")

    async def cb_bank_menu(self, callback: CallbackQuery, db_user):
        """Возврат в главное меню панели"""
        bank = await self._get_user_bank(db_user)
        if not bank:
            await callback.answer("Банк не найден", show_alert=True)
            return

        text = await self._build_bank_summary(bank)
        await callback.message.edit_text(text, reply_markup=self.kb.panel_menu(), parse_mode="HTML")
        await callback.answer()

    async def cb_bank_stats(self, callback: CallbackQuery, db_user):
        """Статистика банка"""
        bank = await self._get_user_bank(db_user)
        if not bank:
            await callback.answer("Банк не найден", show_alert=True)
            return

        today = date.today()
        stats = await self._get_bank_stats(bank.id, today)

        text = (
            f"📊 <b>Статистика «{bank.name}»</b>\n\n"
            f"<b>Сегодня ({today.strftime('%d.%m.%Y')}):</b>\n"
            f"  📥 Заявок на рассмотрении: <b>{stats['pending']}</b>\n"
            f"  ✅ Одобрено: <b>{stats['approved']}</b>\n"
            f"  ❌ Отклонено: <b>{stats['rejected']}</b>\n"
            f"  💰 Сумма одобренных: <b>{stats['approved_sum']:,.0f}₽</b>\n\n"
            f"<b>Всего заявок в банке:</b> {stats['total']}"
        )
        await callback.message.edit_text(
            text, reply_markup=self.kb.back_to_panel(), parse_mode="HTML"
        )
        await callback.answer()

    async def cb_bank_limits(self, callback: CallbackQuery, db_user):
        """Лимиты банка"""
        bank = await self._get_user_bank(db_user)
        if not bank:
            await callback.answer("Банк не найден", show_alert=True)
            return

        daily_remain = bank.daily_limit - bank.current_daily_used
        weekly_remain = bank.weekly_limit - bank.current_weekly_used
        daily_pct = (bank.current_daily_used / bank.daily_limit * 100) if bank.daily_limit else 0
        weekly_pct = (bank.current_weekly_used / bank.weekly_limit * 100) if bank.weekly_limit else 0

        text = (
            f"📈 <b>Лимиты «{bank.name}»</b>\n\n"
            f"<b>Дневной лимит:</b>\n"
            f"  Лимит: {bank.daily_limit:,.0f}₽\n"
            f"  Использовано: {bank.current_daily_used:,.0f}₽ ({daily_pct:.0f}%)\n"
            f"  Остаток: <b>{daily_remain:,.0f}₽</b>\n\n"
            f"<b>Недельный лимит:</b>\n"
            f"  Лимит: {bank.weekly_limit:,.0f}₽\n"
            f"  Использовано: {bank.current_weekly_used:,.0f}₽ ({weekly_pct:.0f}%)\n"
            f"  Остаток: <b>{weekly_remain:,.0f}₽</b>\n\n"
            f"📌 Приоритет: {bank.priority}\n"
            f"{'✅ Принимает заявки' if bank.is_available else '⛔ Приём приостановлен'}"
        )
        await callback.message.edit_text(
            text, reply_markup=self.kb.back_to_panel(), parse_mode="HTML"
        )
        await callback.answer()

    # ==================== HELPERS ====================

    async def _get_user_bank(self, db_user):
        """Получить банк пользователя"""
        if db_user.bank_id:
            return await self.bank_repo.get_by_id(db_user.bank_id)
        # Для supervisor/admin — показать первый активный банк
        if db_user.role in ('supervisor', 'admin'):
            banks = await self.bank_repo.get_active()
            return banks[0] if banks else None
        return None

    async def _build_bank_summary(self, bank) -> str:
        """Сводка банка для главного меню"""
        today = date.today()
        stats = await self._get_bank_stats(bank.id, today)
        daily_remain = bank.daily_limit - bank.current_daily_used

        return (
            f"🏦 <b>Панель банка «{bank.name}»</b>\n\n"
            f"📥 Заявок на рассмотрении: <b>{stats['pending']}</b>\n"
            f"💰 Дневной остаток: <b>{daily_remain:,.0f}₽</b> "
            f"из {bank.daily_limit:,.0f}₽\n"
            f"{'✅ Принимает заявки' if bank.is_available else '⛔ Приём приостановлен'}"
        )

    async def _get_bank_stats(self, bank_id: int, target_date: date) -> dict:
        """Получить статистику банка за день"""
        async with self.application_repo.session_maker() as session:
            # Заявки на рассмотрении
            pending_result = await session.execute(
                select(func.count()).select_from(Application).where(
                    Application.bank_id == bank_id,
                    Application.status == 'bank_review'
                )
            )
            pending = pending_result.scalar_one()

            # Одобрено сегодня
            approved_result = await session.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(Application.amount), 0)
                ).select_from(Application).where(
                    Application.bank_id == bank_id,
                    Application.status.in_(['approved', 'supervisor_review',
                                            'awaiting_contract_details',
                                            'invoice_generated', 'paid']),
                    func.date(Application.sent_to_bank_at) == target_date
                )
            )
            approved_row = approved_result.one()
            approved = approved_row[0]
            approved_sum = float(approved_row[1])

            # Отклонено сегодня
            rejected_result = await session.execute(
                select(func.count()).select_from(Application).where(
                    Application.bank_id == bank_id,
                    Application.status == 'rejected',
                    func.date(Application.updated_at) == target_date
                )
            )
            rejected = rejected_result.scalar_one()

            # Всего заявок банка
            total_result = await session.execute(
                select(func.count()).select_from(Application).where(
                    Application.bank_id == bank_id
                )
            )
            total = total_result.scalar_one()

        return {
            'pending': pending,
            'approved': approved,
            'approved_sum': approved_sum,
            'rejected': rejected,
            'total': total,
        }

    async def _validate_bank_access(self, callback: CallbackQuery, db_user) -> bool:
        """Проверяет, что сотрудник банка имеет доступ к группе."""
        if db_user.role in ('supervisor', 'admin'):
            return True

        bank = await self.bank_repo.get_by_chat_id(callback.message.chat.id)
        if not bank:
            await callback.answer("Банк для этой группы не найден", show_alert=True)
            return False

        if db_user.bank_id != bank.id:
            await callback.answer("У вас нет доступа к заявкам этого банка", show_alert=True)
            return False

        return True

    # ==================== CALLBACK HANDLERS (групповой чат) ====================

    async def cb_risk_assessment(self, callback: CallbackQuery, state: FSMContext, db_user):
        """Оценка риска"""
        if not await self._validate_bank_access(callback, db_user):
            return

        parts = callback.data.split(":")
        app_id = int(parts[2])
        risk_level = parts[3]

        app = await self.application_repo.get_with_relations(app_id)
        if not app:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        if risk_level == "high_risk":
            await callback.message.edit_text(
                f"❌ <b>Отклонение заявки</b>\n\n"
                f"📋 {format_application_number(app, for_client=False)}\n"
                f"💰 {app.amount:,.0f}₽\n\n"
                f"Выберите причину отклонения:",
                reply_markup=self.kb.rejection_reasons(app_id),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        # Если минимальный риск - запрашиваем комментарий
        if risk_level == "min_risk":
            await state.set_state(BankStates.waiting_for_risk_comment)
            await state.update_data(app_id=app_id, risk_level=risk_level, employee_id=db_user.id)
            await callback.message.edit_text(
                f"⚠️ <b>Минимальный риск</b>\n\n"
                f"📋 {format_application_number(app, for_client=False)}\n"
                f"💰 {app.amount:,.0f}₽\n\n"
                f"Опишите минимальный риск (комментарий будет отправлен супервайзеру):",
                parse_mode="HTML"
            )
            await callback.answer()
            return

        # Только для "Без риска" (min_risk обрабатывается через FSM выше)
        # Одобряем этап банка
        pending_approval = await self.approval_repo.get_by_role(app_id, 'bank')
        if pending_approval and not pending_approval.decision:
            await self.approval_repo.approve(pending_approval.id, db_user.id, "Без риска")

        # Логируем
        await self.log_repo.create_log(
            action='bank_approved',
            application_id=app_id,
            user_id=db_user.id,
            details={'risk_level': risk_level}
        )

        employee_name = db_user.first_name or db_user.username

        # Без риска - ожидаем данные договора от клиента
        await self.application_repo.update_status(app_id, 'awaiting_contract_details')

        await callback.message.edit_text(
            f"✅ <b>Без риска</b>\n\n"
            f"📋 {format_application_number(app, for_client=False)}\n"
            f"💰 {app.amount:,.0f}₽\n\n"
            f"👤 Оценил: {employee_name}\n"
            f"📝 Клиенту отправлен запрос на данные договора.",
            parse_mode="HTML"
        )
        await callback.answer("Одобрено банком")

        if self.notification_service:
            await self.notification_service.notify_client_contract_details_needed(app)

    async def cb_reject_reason(self, callback: CallbackQuery, db_user):
        """Отклонение заявки с выбранной причиной"""
        if not await self._validate_bank_access(callback, db_user):
            return

        parts = callback.data.split(":")
        app_id = int(parts[2])
        reason_code = parts[3]

        app = await self.application_repo.get_by_id(app_id)
        if not app:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        reason = REJECTION_REASONS.get(reason_code, reason_code)

        pending_approval = await self.approval_repo.get_by_role(app_id, 'bank')
        if pending_approval:
            await self.approval_repo.reject(pending_approval.id, db_user.id, reason)

        await self.application_repo.update_status(app_id, 'rejected')

        await self.log_repo.create_log(
            action='bank_rejected',
            application_id=app_id,
            user_id=db_user.id,
            details={'reason': reason_code}
        )

        employee_name = db_user.first_name or db_user.username

        await callback.message.edit_text(
            f"❌ <b>Заявка отклонена</b>\n\n"
            f"📋 {format_application_number(app, for_client=False)}\n"
            f"💰 {app.amount:,.0f}₽\n\n"
            f"👤 Отклонил: {employee_name}\n"
            f"📝 Причина: {reason}",
            parse_mode="HTML"
        )
        await callback.answer("Заявка отклонена")

        if self.notification_service:
            await self.notification_service.notify_client_rejected(app, reason, "банк")
            await self.notification_service.notify_manager_final_decision(app, 'rejected', reason)

    async def cb_cancel_reject(self, callback: CallbackQuery, db_user):
        """Отмена отклонения — возврат к кнопкам оценки риска"""
        if not await self._validate_bank_access(callback, db_user):
            return

        app_id = int(callback.data.split(":")[-1])
        app = await self.application_repo.get_with_relations(app_id)

        if not app:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        notification_text = (
            f"📥 <b>Заявка на оценку риска</b>\n\n"
            f"📋 {format_application_number(app, for_client=False)}\n"
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

    async def process_risk_comment(self, message: Message, state: FSMContext, db_user):
        """Обработка комментария к минимальному риску"""
        comment = message.text.strip()
        
        if not comment:
            await message.answer("❗ Введите описание риска")
            return
        
        data = await state.get_data()
        app_id = data['app_id']
        risk_level = data['risk_level']
        employee_id = data['employee_id']
        
        await state.clear()
        
        app = await self.application_repo.get_with_relations(app_id)
        if not app:
            await message.answer("❗ Заявка не найдена")
            return
        
        # Одобряем этап банка с комментарием
        pending_approval = await self.approval_repo.get_by_role(app_id, 'bank')
        if pending_approval and not pending_approval.decision:
            await self.approval_repo.approve(pending_approval.id, employee_id, f"Минимальный риск: {comment}")
        
        # Логируем
        await self.log_repo.create_log(
            action='bank_approved',
            application_id=app_id,
            user_id=employee_id,
            details={'risk_level': risk_level, 'comment': comment}
        )
        
        # Эскалация к руководителю
        await self.approval_repo.create_escalation(
            app_id=app_id,
            role='supervisor',
            reason=f'Минимальный риск: {comment}',
            sequence=0
        )
        
        # Переводим в статус min_risk_review
        await self.application_repo.update_status(app_id, 'min_risk_review')
        
        employee_name = db_user.first_name or db_user.username
        
        await message.answer(
            f"⚠️ <b>Минимальный риск</b>\n\n"
            f"📋 {format_application_number(app, for_client=False)}\n"
            f"💰 {app.amount:,.0f}₽\n\n"
            f"📝 Комментарий: {comment}\n"
            f"👤 Оценил: {employee_name}\n\n"
            f"✅ Отправлено на проверку супервайзеру.",
            parse_mode="HTML"
        )
        
        if self.notification_service:
            await self.notification_service.notify_supervisors_escalation(app, f"банк (минимальный риск: {comment})")
