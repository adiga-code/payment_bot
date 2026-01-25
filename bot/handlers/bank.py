# bot/handlers/bank.py

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from datetime import date

from database import (
    ApplicationRepository,
    ApprovalRepository,
    UserRepository,
    BankRepository,
    LogRepository
)
from keyboards.bank_kb import BankKeyboards
from middleware import RoleRequiredMiddleware


class BankHandlers:
    """Хендлеры для сотрудника банка"""

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
        self.router.message.middleware(
            RoleRequiredMiddleware(self.ALLOWED_ROLES, self.user_repo)
        )
        self.router.callback_query.middleware(
            RoleRequiredMiddleware(self.ALLOWED_ROLES, self.user_repo)
        )

    def _setup_handlers(self):
        """Регистрация обработчиков"""
        # Команды
        self.router.message(Command("bank"))(self.cmd_bank_menu)

        # Callback handlers
        self.router.callback_query(F.data == "bank:menu")(self.cb_menu)
        self.router.callback_query(F.data == "bank:applications")(self.cb_applications)
        self.router.callback_query(F.data.startswith("bank:page:"))(self.cb_page)
        self.router.callback_query(F.data.startswith("bank:app:"))(self.cb_view_application)
        self.router.callback_query(F.data.startswith("bank:risk:"))(self.cb_risk_assessment)
        self.router.callback_query(F.data.startswith("bank:reject_confirm:"))(self.cb_reject_confirm)
        self.router.callback_query(F.data == "bank:stats")(self.cb_stats)

    # ==================== КОМАНДЫ ====================

    async def cmd_bank_menu(self, message: Message, db_user):
        """Команда /bank - главное меню"""
        # Получаем заявки для этого банка
        pending_count = await self._get_pending_count(db_user)

        await message.answer(
            f"🏦 <b>Панель банка</b>\n\n"
            f"👤 {db_user.first_name or db_user.username}\n"
            f"📥 Входящих заявок: <b>{pending_count}</b>",
            reply_markup=self.kb.main_menu(),
            parse_mode="HTML"
        )

    # ==================== CALLBACK HANDLERS ====================

    async def cb_menu(self, callback: CallbackQuery, db_user):
        """Возврат в главное меню"""
        pending_count = await self._get_pending_count(db_user)

        await callback.message.edit_text(
            f"🏦 <b>Панель банка</b>\n\n"
            f"👤 {db_user.first_name or db_user.username}\n"
            f"📥 Входящих заявок: <b>{pending_count}</b>",
            reply_markup=self.kb.main_menu(),
            parse_mode="HTML"
        )
        await callback.answer()

    async def cb_applications(self, callback: CallbackQuery, db_user):
        """Список входящих заявок"""
        applications = await self._get_bank_applications(db_user)

        if not applications:
            await callback.message.edit_text(
                "📥 <b>Входящие заявки</b>\n\n"
                "Нет заявок на рассмотрение.",
                reply_markup=self.kb.back_to_menu(),
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                f"📥 <b>Входящие заявки</b> ({len(applications)})\n\n"
                "Выберите заявку для оценки риска:",
                reply_markup=self.kb.applications_list(applications),
                parse_mode="HTML"
            )
        await callback.answer()

    async def cb_page(self, callback: CallbackQuery, db_user):
        """Пагинация"""
        page = int(callback.data.split(":")[-1])
        applications = await self._get_bank_applications(db_user)

        await callback.message.edit_reply_markup(
            reply_markup=self.kb.applications_list(applications, page)
        )
        await callback.answer()

    async def cb_view_application(self, callback: CallbackQuery, db_user):
        """Просмотр заявки"""
        app_id = int(callback.data.split(":")[-1])
        app = await self.application_repo.get_with_relations(app_id)

        if not app:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        text = self._format_application(app)

        await callback.message.edit_text(
            text,
            reply_markup=self.kb.risk_assessment(app_id),
            parse_mode="HTML"
        )
        await callback.answer()

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
            # Подтверждение отклонения
            await callback.message.edit_text(
                f"❌ <b>Высокий риск</b>\n\n"
                f"📋 {app.external_id}\n"
                f"💰 {app.amount:,.0f}₽\n\n"
                f"Заявка будет <b>отклонена</b>.\n"
                f"Подтвердите действие:",
                reply_markup=self.kb.confirm_high_risk(app_id),
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

        if risk_level == "min_risk":
            # Минимальный риск - создаём эскалацию к руководителю
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
                f"📤 Заявка отправлена руководителю на решение.",
                reply_markup=self.kb.back_to_menu(),
                parse_mode="HTML"
            )
            await callback.answer("Отправлено руководителю")

            # TODO: Уведомить руководителя
        else:
            # Без риска - отправляем к руководителю на финальное одобрение
            await self.application_repo.update_status(app_id, 'supervisor_review')

            await callback.message.edit_text(
                f"✅ <b>Без риска</b>\n\n"
                f"📋 {app.external_id}\n"
                f"💰 {app.amount:,.0f}₽\n\n"
                f"📤 Заявка отправлена руководителю на финальное одобрение.",
                reply_markup=self.kb.back_to_menu(),
                parse_mode="HTML"
            )
            await callback.answer("Отправлено руководителю")

            # TODO: Уведомить руководителя

    async def cb_reject_confirm(self, callback: CallbackQuery, db_user):
        """Подтверждение отклонения (высокий риск)"""
        app_id = int(callback.data.split(":")[-1])
        app = await self.application_repo.get_by_id(app_id)

        if not app:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        # Отклоняем этап банка
        pending_approval = await self.approval_repo.get_by_role(app_id, 'bank')
        if pending_approval:
            await self.approval_repo.reject(pending_approval.id, db_user.id, "Высокий риск")

        # Обновляем статус заявки
        await self.application_repo.update_status(app_id, 'rejected')

        # Логируем
        await self.log_repo.create_log(
            action='bank_rejected',
            application_id=app_id,
            user_id=db_user.id,
            details={'reason': 'high_risk'}
        )

        await callback.message.edit_text(
            f"❌ <b>Заявка отклонена</b>\n\n"
            f"📋 {app.external_id}\n"
            f"💰 {app.amount:,.0f}₽\n\n"
            f"📝 Причина: Высокий риск",
            reply_markup=self.kb.back_to_menu(),
            parse_mode="HTML"
        )
        await callback.answer("Заявка отклонена")

        # TODO: Уведомить клиента и менеджера

    async def cb_stats(self, callback: CallbackQuery, db_user):
        """Статистика банка"""
        today = date.today()

        # Получаем все заявки банка за сегодня
        all_apps = await self._get_bank_applications(db_user, include_processed=True)

        pending = len([a for a in all_apps if a.status == 'bank_review'])
        approved = len([a for a in all_apps if a.status in ['supervisor_review', 'approved', 'invoice_generated', 'paid']])
        rejected = len([a for a in all_apps if a.status == 'rejected'])

        total_amount = sum(a.amount for a in all_apps)

        await callback.message.edit_text(
            f"📊 <b>Статистика за {today.strftime('%d.%m.%Y')}</b>\n\n"
            f"📥 На рассмотрении: {pending}\n"
            f"✅ Одобрено: {approved}\n"
            f"❌ Отклонено: {rejected}\n\n"
            f"💰 Общая сумма: {total_amount:,.0f}₽",
            reply_markup=self.kb.back_to_menu(),
            parse_mode="HTML"
        )
        await callback.answer()

    # ==================== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ====================

    async def _get_pending_count(self, db_user) -> int:
        """Количество заявок на рассмотрении"""
        applications = await self._get_bank_applications(db_user)
        return len(applications)

    async def _get_bank_applications(self, db_user, include_processed: bool = False):
        """Получить заявки для банка"""
        # Получаем все заявки в статусе bank_review
        if include_processed:
            # Все заявки, которые прошли через банк
            all_apps = await self.application_repo.get_by_status('bank_review')
            supervisor_apps = await self.application_repo.get_by_status('supervisor_review')
            approved_apps = await self.application_repo.get_by_status('approved')
            rejected_apps = await self.application_repo.get_by_status('rejected')
            return all_apps + supervisor_apps + approved_apps + rejected_apps
        else:
            return await self.application_repo.get_by_status('bank_review')

    def _format_application(self, app) -> str:
        """Форматирование заявки"""
        text = f"📋 <b>Заявка {app.external_id}</b>\n\n"
        text += f"💰 Сумма: <b>{app.amount:,.0f}₽</b>\n"
        text += f"🏢 ИНН плательщика: <code>{app.payer_inn}</code>\n"

        if app.payer_name:
            text += f"📛 Плательщик: {app.payer_name}\n"

        text += f"📝 Назначение: {app.purpose}\n"
        text += f"📅 Создана: {app.created_at.strftime('%d.%m.%Y %H:%M')}\n"

        if app.company:
            text += f"\n🏢 <b>Компания:</b> {app.company.name}\n"
            text += f"   ИНН: {app.company.inn}\n"

        if app.manager:
            text += f"\n👔 <b>Менеджер:</b> {app.manager.first_name or app.manager.username}\n"

        # История подписей
        if app.approvals:
            text += "\n<b>История:</b>\n"
            for approval in sorted(app.approvals, key=lambda x: x.sequence):
                if approval.decision:
                    emoji = {'approved': '✅', 'rejected': '❌', 'escalated': '🚨'}.get(approval.decision, '⏳')
                    text += f"  {emoji} {approval.role}: {approval.decision}\n"

        text += "\n<b>Оцените уровень риска:</b>"
        return text
