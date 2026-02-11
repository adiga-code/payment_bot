# bot/handlers/supervisor.py

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from datetime import date

from database import (
    ApplicationRepository,
    ApprovalRepository,
    UserRepository,
    CompanyRepository,
    BankRepository,
    LogRepository,
    DocumentRepository
)
from services.notification import NotificationService
from services.document import DocumentService
from keyboards.supervisor_kb import SupervisorKeyboards
from middleware import RoleRequiredMiddleware


class RejectReasonState(StatesGroup):
    """Состояние для ввода причины отклонения"""
    waiting_for_reason = State()


class SupervisorHandlers:
    """Хендлеры для руководителя (супервайзера)"""

    ALLOWED_ROLES = ['supervisor', 'admin']

    def __init__(
            self,
            user_repo: UserRepository,
            application_repo: ApplicationRepository,
            approval_repo: ApprovalRepository,
            company_repo: CompanyRepository,
            bank_repo: BankRepository,
            log_repo: LogRepository,
            document_repo: DocumentRepository,
            bot: Bot,
            notification_service: NotificationService = None,
            document_service: DocumentService = None
    ):
        self.router = Router()
        self.user_repo = user_repo
        self.application_repo = application_repo
        self.approval_repo = approval_repo
        self.company_repo = company_repo
        self.bank_repo = bank_repo
        self.log_repo = log_repo
        self.document_repo = document_repo
        self.bot = bot
        self.notification_service = notification_service
        self.document_service = document_service
        self.kb = SupervisorKeyboards()

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
        self.router.message(Command("supervisor"))(self.cmd_supervisor_menu)
        self.router.message(Command("sv"))(self.cmd_supervisor_menu)

        # Callback handlers
        self.router.callback_query(F.data == "sv:menu")(self.cb_menu)
        self.router.callback_query(F.data == "sv:pending")(self.cb_pending)
        self.router.callback_query(F.data == "sv:escalations")(self.cb_escalations)
        self.router.callback_query(F.data == "sv:min_risk")(self.cb_min_risk)
        self.router.callback_query(F.data == "sv:all")(self.cb_all_applications)
        self.router.callback_query(F.data.startswith("sv:page:"))(self.cb_page)
        self.router.callback_query(F.data.startswith("sv:app:"))(self.cb_view_application)
        self.router.callback_query(F.data.startswith("sv:approve:"))(self.cb_approve)
        self.router.callback_query(F.data.startswith("sv:reject:"))(self.cb_reject)
        self.router.callback_query(F.data.startswith("sv:reject_reason:"))(self.cb_reject_reason)
        self.router.callback_query(F.data.startswith("sv:return:"))(self.cb_return_to_manager)
        self.router.callback_query(F.data.startswith("sv:confirm_"))(self.cb_confirm)
        self.router.callback_query(F.data == "sv:stats")(self.cb_stats)

        # FSM
        self.router.message(RejectReasonState.waiting_for_reason)(self.process_reject_reason)

    # ==================== КОМАНДЫ ====================

    async def cmd_supervisor_menu(self, message: Message, db_user):
        """Команда /supervisor - главное меню"""
        pending = await self.application_repo.get_by_status('supervisor_review')
        escalations = await self._get_escalations()
        min_risk_apps = await self.application_repo.get_by_status('min_risk_review')

        await message.answer(
            f"👑 <b>Панель руководителя</b>\n\n"
            f"👤 {db_user.first_name or db_user.username}\n\n"
            f"🔴 Требуют решения: <b>{len(pending)}</b>\n"
            f"🚨 Эскалации: <b>{len(escalations)}</b>\n"
            f"⚠️ Минимальный риск: <b>{len(min_risk_apps)}</b>",
            reply_markup=self.kb.main_menu(),
            parse_mode="HTML"
        )

    # ==================== CALLBACK HANDLERS ====================

    async def cb_menu(self, callback: CallbackQuery, db_user):
        """Возврат в главное меню"""
        pending = await self.application_repo.get_by_status('supervisor_review')
        escalations = await self._get_escalations()
        min_risk_apps = await self.application_repo.get_by_status('min_risk_review')

        await callback.message.edit_text(
            f"👑 <b>Панель руководителя</b>\n\n"
            f"👤 {db_user.first_name or db_user.username}\n\n"
            f"🔴 Требуют решения: <b>{len(pending)}</b>\n"
            f"🚨 Эскалации: <b>{len(escalations)}</b>\n"
            f"⚠️ Минимальный риск: <b>{len(min_risk_apps)}</b>",
            reply_markup=self.kb.main_menu(),
            parse_mode="HTML"
        )
        await callback.answer()

    async def cb_pending(self, callback: CallbackQuery, db_user):
        """Заявки, требующие решения"""
        applications = await self.application_repo.get_by_status('supervisor_review')

        if not applications:
            await callback.message.edit_text(
                "🔴 <b>Требуют решения</b>\n\n"
                "Нет заявок на рассмотрение.",
                reply_markup=self.kb.back_to_menu(),
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                f"🔴 <b>Требуют решения</b> ({len(applications)})\n\n"
                "Выберите заявку:",
                reply_markup=self.kb.applications_list(applications, "pending"),
                parse_mode="HTML"
            )
        await callback.answer()

    async def cb_escalations(self, callback: CallbackQuery, db_user):
        """Эскалированные заявки"""
        applications = await self._get_escalations()

        if not applications:
            await callback.message.edit_text(
                "🚨 <b>Эскалации</b>\n\n"
                "Нет эскалированных заявок.",
                reply_markup=self.kb.back_to_menu(),
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                f"🚨 <b>Эскалации</b> ({len(applications)})\n\n"
                "Заявки, требующие особого внимания:",
                reply_markup=self.kb.applications_list(applications, "escalations"),
                parse_mode="HTML"
            )
        await callback.answer()

    async def cb_min_risk(self, callback: CallbackQuery, db_user):
        """Заявки с минимальным риском"""
        applications = await self.application_repo.get_by_status('min_risk_review')

        if not applications:
            await callback.message.edit_text(
                "⚠️ <b>Минимальный риск</b>\n\n"
                "Нет заявок с минимальным риском.",
                reply_markup=self.kb.back_to_menu(),
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                f"⚠️ <b>Минимальный риск</b> ({len(applications)})\n\n"
                "Заявки, требующие дополнительного одобрения:",
                reply_markup=self.kb.applications_list(applications, "min_risk"),
                parse_mode="HTML"
            )
        await callback.answer()

    async def cb_all_applications(self, callback: CallbackQuery, db_user):
        """Все заявки"""
        # Получаем заявки за последние дни
        applications = []
        for status in ['supervisor_review', 'approved', 'rejected', 'invoice_generated', 'paid']:
            apps = await self.application_repo.get_by_status(status)
            applications.extend(apps)

        # Сортируем по дате
        applications.sort(key=lambda x: x.created_at, reverse=True)

        if not applications:
            await callback.message.edit_text(
                "📋 <b>Все заявки</b>\n\n"
                "Список пуст.",
                reply_markup=self.kb.back_to_menu(),
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                f"📋 <b>Все заявки</b> ({len(applications)})\n\n"
                "Выберите заявку:",
                reply_markup=self.kb.applications_list(applications, "all"),
                parse_mode="HTML"
            )
        await callback.answer()

    async def cb_page(self, callback: CallbackQuery, db_user):
        """Пагинация"""
        parts = callback.data.split(":")
        list_type = parts[2]
        page = int(parts[3])

        if list_type == "pending":
            applications = await self.application_repo.get_by_status('supervisor_review')
        elif list_type == "escalations":
            applications = await self._get_escalations()
        else:
            applications = []
            for status in ['supervisor_review', 'approved', 'rejected', 'invoice_generated', 'paid']:
                apps = await self.application_repo.get_by_status(status)
                applications.extend(apps)
            applications.sort(key=lambda x: x.created_at, reverse=True)

        await callback.message.edit_reply_markup(
            reply_markup=self.kb.applications_list(applications, list_type, page)
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

        # Проверяем, есть ли эскалация
        is_escalation = any(
            a.decision == 'escalated' or (a.role == 'supervisor' and a.sequence == 0)
            for a in app.approvals
        )

        # Показываем кнопки в зависимости от статуса
        if app.status == 'supervisor_review':
            keyboard = self.kb.application_actions(app_id, is_escalation, back_to="pending")
        elif app.status == 'min_risk_review':
            keyboard = self.kb.application_actions(app_id, is_escalation=False, back_to="min_risk")
        else:
            keyboard = self.kb.back_to_menu()

        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await callback.answer()

    async def cb_approve(self, callback: CallbackQuery, db_user):
        """Одобрение заявки"""
        app_id = int(callback.data.split(":")[-1])
        app = await self.application_repo.get_with_relations(app_id)

        if not app:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        # Проверяем, это заявка с минимальным риском или обычная
        is_min_risk = app.status == 'min_risk_review'

        # Одобряем этап супервайзера
        pending_approval = await self.approval_repo.get_by_role(app_id, 'supervisor')
        if pending_approval and not pending_approval.decision:
            await self.approval_repo.approve(pending_approval.id, db_user.id)

        # Также одобряем эскалации если есть
        for approval in app.approvals:
            if approval.sequence == 0 and not approval.decision:
                await self.approval_repo.approve(approval.id, db_user.id, "Одобрено руководителем")

        # Если это заявка с минимальным риском - переводим в awaiting_contract_details
        # и отправляем уведомления клиенту
        if is_min_risk:
            await self.application_repo.update_status(app_id, 'awaiting_contract_details')

            await self.log_repo.create_log(
                action='supervisor_approved_min_risk',
                application_id=app_id,
                user_id=db_user.id
            )

            await callback.message.edit_text(
                f"✅ <b>Минимальный риск одобрен!</b>\n\n"
                f"📋 {app.external_id}\n"
                f"💰 {app.amount:,.0f}₽\n\n"
                f"📝 Клиенту отправлен запрос на данные договора.",
                reply_markup=self.kb.back_to_menu(),
                parse_mode="HTML"
            )
            await callback.answer("Минимальный риск одобрен!")

            if self.notification_service:
                # Отправляем клиенту уведомление об одобрении банком
                await self.notification_service.notify_client_approved_by_bank(app)
                # Запрашиваем данные договора
                await self.notification_service.notify_client_contract_details_needed(app)
            return

        # Проверяем, все ли подписи собраны
        all_approved = await self.approval_repo.is_all_approved(app_id)

        if all_approved:
            # Финальное одобрение
            await self.application_repo.mark_approved(app_id)

            # Логируем
            await self.log_repo.create_log(
                action='supervisor_final_approved',
                application_id=app_id,
                user_id=db_user.id
            )

            # Обновляем лимиты компании и банка
            if app.company_id:
                await self.company_repo.update_usage(app.company_id, app.amount, increment=True)
            if app.bank_id:
                await self.bank_repo.update_usage(app.bank_id, app.amount, increment=True)

            # Генерируем счёт
            invoice_number = None
            if self.document_service:
                file_path = await self.document_service.generate_invoice(app_id)
                if file_path:
                    # Получаем номер из БД
                    doc = await self.document_repo.get_latest_invoice(app_id)
                    if doc:
                        invoice_number = doc.number

            invoice_text = ""
            if invoice_number:
                invoice_text = f"🧾 Счёт: <b>{invoice_number}</b>\n"

            await callback.message.edit_text(
                f"✅ <b>Заявка одобрена!</b>\n\n"
                f"📋 {app.external_id}\n"
                f"💰 {app.amount:,.0f}₽\n\n"
                f"🎉 Все подписи собраны.\n"
                f"{invoice_text}"
                f"📄 Счёт отправлен бухгалтеру.",
                reply_markup=self.kb.back_to_menu(),
                parse_mode="HTML"
            )
            await callback.answer("Заявка одобрена!")

            if self.notification_service:
                await self.notification_service.notify_client_approved(app)
                await self.notification_service.notify_manager_final_decision(app, 'approved')
                if invoice_number:
                    await self.notification_service.notify_accountants_invoice_ready(app, invoice_number)
        else:
            # Просто одобряем свой этап
            await self.application_repo.update_status(app_id, 'approved')

            await self.log_repo.create_log(
                action='supervisor_approved',
                application_id=app_id,
                user_id=db_user.id
            )

            await callback.message.edit_text(
                f"✅ <b>Этап одобрен</b>\n\n"
                f"📋 {app.external_id}\n"
                f"💰 {app.amount:,.0f}₽\n\n"
                f"Ожидаются остальные подписи.",
                reply_markup=self.kb.back_to_menu(),
                parse_mode="HTML"
            )
            await callback.answer("Одобрено")

    async def cb_reject(self, callback: CallbackQuery, db_user):
        """Отклонение заявки - выбор причины"""
        app_id = int(callback.data.split(":")[-1])

        await callback.message.edit_text(
            "❌ <b>Отклонение заявки</b>\n\n"
            "Выберите причину:",
            reply_markup=self.kb.rejection_reasons(app_id),
            parse_mode="HTML"
        )
        await callback.answer()

    async def cb_reject_reason(self, callback: CallbackQuery, state: FSMContext, db_user):
        """Обработка причины отклонения"""
        parts = callback.data.split(":")
        app_id = int(parts[2])
        reason_code = parts[3]

        reasons_map = {
            'insufficient_info': 'Недостаточно информации о компании',
            'bad_reputation': 'Сомнительная деловая репутация',
            'policy_violation': 'Не соответствует политике банка',
            'gov_contracts_risk': 'Риски по госзакупкам',
            'other': None
        }

        if reason_code == 'other':
            await state.set_state(RejectReasonState.waiting_for_reason)
            await state.update_data(app_id=app_id)
            await callback.message.edit_text(
                "📝 Введите причину отклонения:",
                reply_markup=self.kb.back_to_menu()
            )
            await callback.answer()
            return

        reason = reasons_map.get(reason_code, reason_code)
        await self._reject_application(callback, app_id, reason, db_user)

    async def process_reject_reason(self, message: Message, state: FSMContext, db_user):
        """Обработка введённой причины отклонения"""
        data = await state.get_data()
        app_id = data.get('app_id')
        reason = message.text

        await state.clear()

        app = await self.application_repo.get_by_id(app_id)
        if not app:
            await message.answer("Заявка не найдена")
            return

        await self._do_reject(app, reason, db_user)

        await message.answer(
            f"❌ <b>Заявка {app.external_id} отклонена</b>\n\n"
            f"📝 Причина: {reason}",
            reply_markup=self.kb.back_to_menu(),
            parse_mode="HTML"
        )

    async def cb_return_to_manager(self, callback: CallbackQuery, db_user):
        """Вернуть заявку менеджеру"""
        app_id = int(callback.data.split(":")[-1])
        app = await self.application_repo.get_by_id(app_id)

        if not app:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        # Возвращаем на этап менеджера
        await self.application_repo.update_status(app_id, 'manager_review')

        # Логируем
        await self.log_repo.create_log(
            action='supervisor_returned',
            application_id=app_id,
            user_id=db_user.id,
            details={'reason': 'Возвращено на доработку'}
        )

        await callback.message.edit_text(
            f"↩️ <b>Заявка возвращена</b>\n\n"
            f"📋 {app.external_id}\n"
            f"💰 {app.amount:,.0f}₽\n\n"
            f"Заявка возвращена менеджеру на доработку.",
            reply_markup=self.kb.back_to_menu(),
            parse_mode="HTML"
        )
        await callback.answer("Возвращено менеджеру")

        if self.notification_service:
            await self.notification_service.notify_manager_returned(app)

    async def cb_confirm(self, callback: CallbackQuery, db_user):
        """Обработка подтверждения действий"""
        data = callback.data.replace("sv:confirm_", "")
        parts = data.split(":")
        action = parts[0]
        app_id = int(parts[1])

        # Обрабатываем подтверждённые действия
        if action == "approve":
            await self.cb_approve(callback, db_user)
        # Другие действия...

    async def cb_stats(self, callback: CallbackQuery, db_user):
        """Статистика"""
        today = date.today()
        daily_stats = await self.application_repo.get_daily_stats(today)

        total = sum(s['count'] for s in daily_stats)
        total_amount = sum(s['total_amount'] for s in daily_stats)

        # Подсчёт по статусам
        approved = next((s['count'] for s in daily_stats if s['status'] == 'approved'), 0)
        rejected = next((s['count'] for s in daily_stats if s['status'] == 'rejected'), 0)
        pending = next((s['count'] for s in daily_stats if s['status'] == 'supervisor_review'), 0)

        # Конверсия
        conversion = await self.application_repo.get_conversion_rate(today, today)

        text = f"📊 <b>Статистика за {today.strftime('%d.%m.%Y')}</b>\n\n"
        text += f"📋 Всего заявок: <b>{total}</b>\n"
        text += f"💰 Общая сумма: <b>{total_amount:,.0f}₽</b>\n\n"
        text += f"✅ Одобрено: {approved}\n"
        text += f"❌ Отклонено: {rejected}\n"
        text += f"⏳ На рассмотрении: {pending}\n\n"
        text += f"📈 Конверсия: {conversion['conversion_rate']:.1f}%"

        await callback.message.edit_text(
            text,
            reply_markup=self.kb.back_to_menu(),
            parse_mode="HTML"
        )
        await callback.answer()

    # ==================== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ====================

    async def _get_escalations(self):
        """Получить эскалированные заявки"""
        # Заявки с эскалациями (sequence=0 или decision='escalated')
        all_pending = await self.application_repo.get_by_status('supervisor_review')
        escalated = []

        for app in all_pending:
            app_with_rel = await self.application_repo.get_with_relations(app.id)
            for approval in app_with_rel.approvals:
                if approval.decision == 'escalated' or (approval.role == 'supervisor' and approval.sequence == 0):
                    escalated.append(app)
                    break

        return escalated

    async def _reject_application(self, callback: CallbackQuery, app_id: int, reason: str, db_user):
        """Отклонить заявку"""
        app = await self.application_repo.get_by_id(app_id)

        await self._do_reject(app, reason, db_user)

        await callback.message.edit_text(
            f"❌ <b>Заявка {app.external_id} отклонена</b>\n\n"
            f"📝 Причина: {reason}",
            reply_markup=self.kb.back_to_menu(),
            parse_mode="HTML"
        )
        await callback.answer("Заявка отклонена")

    async def _do_reject(self, app, reason: str, db_user):
        """Выполнить отклонение"""
        # Отклоняем все ожидающие подписи
        for approval in await self.approval_repo.get_by_application(app.id):
            if not approval.decision:
                await self.approval_repo.reject(approval.id, db_user.id, reason)

        # Обновляем статус
        await self.application_repo.update_status(app.id, 'rejected')

        # Логируем
        await self.log_repo.create_log(
            action='supervisor_rejected',
            application_id=app.id,
            user_id=db_user.id,
            details={'reason': reason}
        )

        # Уведомляем клиента об отклонении
        await self.notification_service.notify_client_rejected(
            app,
            reason=reason,
            rejected_by="Руководитель"
        )

        if self.notification_service:
            await self.notification_service.notify_client_rejected(app, reason, "руководитель")
            await self.notification_service.notify_manager_final_decision(app, 'rejected', reason)

    def _format_application(self, app) -> str:
        """Форматирование заявки"""
        status_map = {
            'new': '🆕 Новая',
            'primary_check': '🔍 Проверка',
            'manager_review': '👔 У менеджера',
            'bank_review': '🏦 В банке',
            'min_risk_review': '⚠️ Минимальный риск',
            'awaiting_contract_details': '📝 Ожидание данных договора',
            'supervisor_review': '👑 На одобрении',
            'approved': '✅ Одобрена',
            'rejected': '❌ Отклонена',
            'invoice_generated': '📄 Счёт создан',
            'paid': '💰 Оплачено'
        }

        text = f"📋 <b>Заявка {app.external_id}</b>\n\n"
        text += f"📊 Статус: {status_map.get(app.status, app.status)}\n"
        text += f"💰 Сумма: <b>{app.amount:,.0f}₽</b>\n"
        text += f"🏢 ИНН: <code>{app.payer_inn}</code>\n"

        if app.payer_name:
            text += f"📛 Плательщик: {app.payer_name}\n"

        text += f"📝 Назначение: {app.purpose}\n"
        text += f"📅 Создана: {app.created_at.strftime('%d.%m.%Y %H:%M')}\n"

        # Риск ЦБ РФ и госзакупки из primary_check
        if app.primary_check_result:
            from services.honest_business_api import format_cbr_rating, format_amount_short

            check_result = app.primary_check_result
            cbr_risk = check_result.get('cbr_risk')

            text += "\n"
            if cbr_risk:
                cbr_text = format_cbr_rating(cbr_risk)
                # Сокращенный формат для карточки
                lines = cbr_text.split('\n')
                text += lines[0] + "\n"  # Только заголовок с уровнем риска

            # Госзакупки
            zakupki = check_result.get('zakupki')
            if zakupki and zakupki.get('count', 0) > 0:
                count = zakupki['count']
                total_sum = zakupki.get('total_sum', 0)
                text += f"⚠️ <b>Госзакупки:</b> {count} контр. на {format_amount_short(total_sum)}\n"
            elif zakupki is not None:
                text += "✅ <b>Госзакупки:</b> проверка пройдена\n"

        if app.company:
            text += f"\n🏢 <b>Компания:</b> {app.company.name}\n"

        if app.bank:
            text += f"🏦 <b>Банк:</b> {app.bank.name}\n"

        if app.manager:
            text += f"👔 <b>Менеджер:</b> {app.manager.first_name or app.manager.username}\n"

        # История подписей
        if app.approvals:
            text += "\n<b>Подписи:</b>\n"
            for approval in sorted(app.approvals, key=lambda x: x.sequence):
                if approval.decision:
                    emoji = {'approved': '✅', 'rejected': '❌', 'escalated': '🚨'}.get(approval.decision, '⏳')
                    comment = f" ({approval.comment})" if approval.comment else ""
                    text += f"  {emoji} {approval.role}: {approval.decision}{comment}\n"
                else:
                    text += f"  ⏳ {approval.role}: ожидание\n"

        return text
