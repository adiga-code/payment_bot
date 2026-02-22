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
from utils import format_application_number


class RejectReasonState(StatesGroup):
    """Состояние для ввода причины отклонения"""
    waiting_for_reason = State()


class StatsDateState(StatesGroup):
    """Состояния для выбора даты статистики"""
    waiting_for_start_date = State()
    waiting_for_end_date = State()


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
        self.router.callback_query(F.data == "sv:stats:today")(self.cb_stats_today)
        self.router.callback_query(F.data == "sv:stats:week")(self.cb_stats_week)
        self.router.callback_query(F.data == "sv:stats:month")(self.cb_stats_month)
        self.router.callback_query(F.data == "sv:stats:custom")(self.cb_stats_custom)
        self.router.callback_query(F.data.startswith("sv:stats:detail:"))(self.cb_stats_detail)

        # FSM
        self.router.message(RejectReasonState.waiting_for_reason)(self.process_reject_reason)
        self.router.message(StatsDateState.waiting_for_start_date)(self.process_stats_start_date)
        self.router.message(StatsDateState.waiting_for_end_date)(self.process_stats_end_date)

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
                f"📋 {format_application_number(app, for_client=True)}\n"
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
                missing = await self.document_service.validate_invoice_data(app_id)
                if missing:
                    if self.notification_service:
                        await self.notification_service.notify_accountants_missing_invoice_data(app, missing)
                else:
                    file_path = await self.document_service.generate_invoice(app_id)
                    if file_path:
                        doc = await self.document_repo.get_latest_invoice(app_id)
                        if doc:
                            invoice_number = doc.number

            if invoice_number:
                invoice_text = f"🧾 Счёт: <b>{invoice_number}</b>\n📄 Счёт отправлен бухгалтеру.\n"
            else:
                invoice_text = "⚠️ Бухгалтеру отправлен запрос на заполнение данных для счёта.\n"

            await callback.message.edit_text(
                f"✅ <b>Заявка одобрена!</b>\n\n"
                f"📋 {format_application_number(app, for_client=True)}\n"
                f"💰 {app.amount:,.0f}₽\n\n"
                f"🎉 Все подписи собраны.\n"
                f"{invoice_text}",
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
            # Проверяем, проходила ли заявка банк
            # Если нет - это эскалированная заявка, нужно отправить в банк
            has_bank_approval = any(a.role == 'bank' for a in app.approvals)

            if not has_bank_approval:
                # Эскалированная заявка - отправляем в банк
                await self.application_repo.update_status(app_id, 'bank_review')

                await self.log_repo.create_log(
                    action='supervisor_escalation_approved_to_bank',
                    application_id=app_id,
                    user_id=db_user.id
                )

                await callback.message.edit_text(
                    f"✅ <b>Эскалация одобрена!</b>\n\n"
                    f"📋 {format_application_number(app, for_client=True)}\n"
                    f"💰 {app.amount:,.0f}₽\n\n"
                    f"🏦 Заявка отправлена в банк на проверку рисков.",
                    reply_markup=self.kb.back_to_menu(),
                    parse_mode="HTML"
                )
                await callback.answer("Отправлено в банк")

                if self.notification_service:
                    await self.notification_service.notify_bank_new_application(app)
            else:
                # Обычная заявка - финальное одобрение
                await self.application_repo.update_status(app_id, 'approved')

                await self.log_repo.create_log(
                    action='supervisor_approved',
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
                    missing = await self.document_service.validate_invoice_data(app_id)
                    if missing:
                        if self.notification_service:
                            await self.notification_service.notify_accountants_missing_invoice_data(app, missing)
                    else:
                        file_path = await self.document_service.generate_invoice(app_id)
                        if file_path:
                            doc = await self.document_repo.get_latest_invoice(app_id)
                            if doc:
                                invoice_number = doc.number

                if invoice_number:
                    invoice_text = f"🧾 Счёт: <b>{invoice_number}</b>\n📄 Счёт отправлен бухгалтеру.\n"
                else:
                    invoice_text = "⚠️ Бухгалтеру отправлен запрос на заполнение данных для счёта.\n"

                await callback.message.edit_text(
                    f"✅ <b>Заявка одобрена!</b>\n\n"
                    f"📋 {format_application_number(app, for_client=True)}\n"
                    f"💰 {app.amount:,.0f}₽\n\n"
                    f"{invoice_text}",
                    reply_markup=self.kb.back_to_menu(),
                    parse_mode="HTML"
                )
                await callback.answer("Заявка одобрена!")

                if self.notification_service:
                    await self.notification_service.notify_client_approved(app)
                    await self.notification_service.notify_manager_final_decision(app, 'approved')
                    if invoice_number:
                        await self.notification_service.notify_accountants_invoice_ready(app, invoice_number)

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
            f"❌ <b>{format_application_number(app, for_client=True)} отклонена</b>\n\n"
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
            f"📋 {format_application_number(app, for_client=True)}\n"
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
        """Меню выбора периода для статистики"""
        text = "📊 <b>Статистика</b>\n\n" \
               "Выберите период для просмотра:"

        await callback.message.edit_text(
            text,
            reply_markup=self.kb.stats_menu(),
            parse_mode="HTML"
        )
        await callback.answer()

    async def cb_stats_today(self, callback: CallbackQuery, db_user):
        """Статистика за сегодня"""
        today = date.today()
        await self._show_detailed_stats(callback, today, today)

    async def cb_stats_week(self, callback: CallbackQuery, db_user):
        """Статистика за последние 7 дней"""
        today = date.today()
        from datetime import timedelta
        week_ago = today - timedelta(days=7)
        await self._show_detailed_stats(callback, week_ago, today)

    async def cb_stats_month(self, callback: CallbackQuery, db_user):
        """Статистика за последние 30 дней"""
        today = date.today()
        from datetime import timedelta
        month_ago = today - timedelta(days=30)
        await self._show_detailed_stats(callback, month_ago, today)

    async def cb_stats_custom(self, callback: CallbackQuery, db_user, state: FSMContext):
        """Ввод произвольного периода"""
        await callback.message.edit_text(
            "📅 <b>Выбор произвольного периода</b>\n\n"
            "Введите дату начала периода в формате ДД.ММ.ГГГГ\n"
            "Например: 01.01.2024",
            parse_mode="HTML"
        )
        await state.set_state(StatsDateState.waiting_for_start_date)
        await callback.answer()

    async def process_stats_start_date(self, message: Message, state: FSMContext, db_user):
        """Обработка даты начала"""
        from datetime import datetime
        try:
            start_date = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
            await state.update_data(start_date=start_date)
            await message.answer(
                f"✅ Дата начала: {start_date.strftime('%d.%m.%Y')}\n\n"
                f"Теперь введите дату окончания периода в формате ДД.ММ.ГГГГ\n"
                f"Например: {date.today().strftime('%d.%m.%Y')}",
                parse_mode="HTML"
            )
            await state.set_state(StatsDateState.waiting_for_end_date)
        except ValueError:
            await message.answer(
                "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ\n"
                "Например: 01.01.2024"
            )

    async def process_stats_end_date(self, message: Message, state: FSMContext, db_user):
        """Обработка даты окончания и показ статистики"""
        from datetime import datetime
        try:
            end_date = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
            data = await state.get_data()
            start_date = data['start_date']

            if end_date < start_date:
                await message.answer("❌ Дата окончания не может быть раньше даты начала!")
                return

            await state.clear()
            # Показываем статистику через callback эмуляцию
            stats = await self._get_detailed_stats(start_date, end_date)
            text = self._format_stats_text(start_date, end_date, stats)

            await message.answer(
                text,
                reply_markup=self.kb.stats_detail_menu(start_date, end_date),
                parse_mode="HTML"
            )
        except ValueError:
            await message.answer(
                "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ\n"
                "Например: 01.01.2024"
            )

    async def _show_detailed_stats(self, callback: CallbackQuery, start_date: date, end_date: date):
        """Показать детальную статистику за период"""
        stats = await self._get_detailed_stats(start_date, end_date)
        text = self._format_stats_text(start_date, end_date, stats)

        await callback.message.edit_text(
            text,
            reply_markup=self.kb.stats_detail_menu(start_date, end_date),
            parse_mode="HTML"
        )
        await callback.answer()

    async def _get_detailed_stats(self, start_date: date, end_date: date) -> dict:
        """Получить детальную статистику"""
        return await self.application_repo.get_detailed_stats(start_date, end_date)

    def _format_stats_text(self, start_date: date, end_date: date, stats: dict) -> str:
        """Форматировать текст статистики"""
        period = f"{start_date.strftime('%d.%m.%Y')}"
        if start_date != end_date:
            period += f" - {end_date.strftime('%d.%m.%Y')}"

        text = f"📊 <b>Статистика за {period}</b>\n\n"
        text += f"📋 Всего заявок: <b>{stats['total_count']}</b>\n"
        text += f"💰 Общая сумма: <b>{stats['total_amount']:,.0f}₽</b>\n\n"

        # Статистика по статусам
        if stats['by_status']:
            text += "<b>По статусам:</b>\n"
            status_names = {
                'new': '🆕 Новые',
                'manager_review': '👤 На проверке менеджера',
                'bank_review': '🏦 На проверке банка',
                'supervisor_review': '👔 На проверке супервайзера',
                'min_risk_review': '⚠️ Минимальный риск',
                'approved': '✅ Одобрено',
                'rejected': '❌ Отклонено',
                'cancelled': '🚫 Отменено',
                'paid': '💵 Оплачено'
            }
            for status, data in stats['by_status'].items():
                name = status_names.get(status, status)
                text += f"  {name}: {data['count']} ({data['amount']:,.0f}₽)\n"

        return text

    async def cb_stats_detail(self, callback: CallbackQuery, db_user):
        """Показать детализацию статистики"""
        parts = callback.data.split(":")
        detail_type = parts[3]  # by_company, by_bank, by_client, by_date

        # Получаем даты из callback data или используем сегодня
        try:
            start_date_str = parts[4] if len(parts) > 4 else date.today().isoformat()
            end_date_str = parts[5] if len(parts) > 5 else date.today().isoformat()
            from datetime import datetime
            start_date = datetime.fromisoformat(start_date_str).date()
            end_date = datetime.fromisoformat(end_date_str).date()
        except (IndexError, ValueError):
            start_date = end_date = date.today()

        stats = await self._get_detailed_stats(start_date, end_date)

        period = f"{start_date.strftime('%d.%m.%Y')}"
        if start_date != end_date:
            period += f" - {end_date.strftime('%d.%m.%Y')}"

        text = f"📊 <b>Детализация за {period}</b>\n\n"

        if detail_type == "by_company":
            text += "<b>По компаниям:</b>\n"
            if stats['by_company']:
                for company_id, data in sorted(stats['by_company'].items(), key=lambda x: x[1]['count'], reverse=True):
                    company = await self.company_repo.get_by_id(company_id)
                    company_name = company.name if company else f"ID {company_id}"
                    text += f"  🏢 {company_name}: {data['count']} ({data['amount']:,.0f}₽)\n"
            else:
                text += "  Нет данных\n"

        elif detail_type == "by_bank":
            text += "<b>По банкам:</b>\n"
            if stats['by_bank']:
                for bank_id, data in sorted(stats['by_bank'].items(), key=lambda x: x[1]['count'], reverse=True):
                    bank = await self.bank_repo.get_by_id(bank_id)
                    bank_name = bank.name if bank else f"ID {bank_id}"
                    text += f"  🏦 {bank_name}: {data['count']} ({data['amount']:,.0f}₽)\n"
            else:
                text += "  Нет данных\n"

        elif detail_type == "by_client":
            text += "<b>По клиентам:</b>\n"
            if stats['by_client']:
                # Показываем топ 20 клиентов
                sorted_clients = sorted(stats['by_client'].items(), key=lambda x: x[1]['count'], reverse=True)[:20]
                for client_id, data in sorted_clients:
                    user = await self.user_repo.get_by_telegram_id(client_id)
                    client_name = user.username or f"ID {client_id}" if user else f"ID {client_id}"
                    text += f"  👤 @{client_name}: {data['count']} ({data['amount']:,.0f}₽)\n"
                if len(stats['by_client']) > 20:
                    text += f"\n  ... и еще {len(stats['by_client']) - 20} клиентов\n"
            else:
                text += "  Нет данных\n"

        elif detail_type == "by_date":
            text += "<b>По датам:</b>\n"
            if stats['by_date']:
                for app_date, data in sorted(stats['by_date'].items()):
                    text += f"  📅 {app_date.strftime('%d.%m.%Y')}: {data['count']} ({data['amount']:,.0f}₽)\n"
            else:
                text += "  Нет данных\n"

        await callback.message.edit_text(
            text,
            reply_markup=self.kb.back_to_stats(),
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
            f"❌ <b>{format_application_number(app, for_client=True)} отклонена</b>\n\n"
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

        text = f"📋 <b>{format_application_number(app, for_client=True)}</b>\n\n"
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
