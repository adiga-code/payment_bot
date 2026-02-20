# bot/handlers/manager.py

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from typing import Optional
from datetime import datetime
from services.honest_business_api import format_payer_check
from utils.business_days import get_payout_date, format_payout_date

from database import (
    ApplicationRepository,
    ApprovalRepository,
    UserRepository,
    CompanyRepository,
    BankRepository,
    CompanyBankRepository,
    LogRepository
)
from services.notification import NotificationService
from keyboards import ManagerKeyboards
from keyboards.bank_kb import BankKeyboards
from middleware import RoleRequiredMiddleware
from utils import format_application_number


class RejectReasonState(StatesGroup):
    """Состояние для ввода причины отклонения"""
    waiting_for_reason = State()


class ManagerHandlers:
    """Хендлеры для менеджера"""

    ALLOWED_ROLES = ['manager', 'supervisor', 'admin']

    def __init__(
            self,
            user_repo: UserRepository,
            application_repo: ApplicationRepository,
            approval_repo: ApprovalRepository,
            company_repo: CompanyRepository,
            bank_repo: BankRepository,
            company_bank_repo: CompanyBankRepository,
            log_repo: LogRepository,
            bot: Bot,
            notification_service: NotificationService = None
    ):
        self.router = Router()
        self.user_repo = user_repo
        self.application_repo = application_repo
        self.company_bank_repo = company_bank_repo
        self.approval_repo = approval_repo
        self.company_repo = company_repo
        self.bank_repo = bank_repo
        self.log_repo = log_repo
        self.bot = bot
        self.notification_service = notification_service
        self.kb = ManagerKeyboards()
        self.bank_kb = BankKeyboards()

        self._setup_middleware()
        self._setup_handlers()

    def _setup_middleware(self):
        """Настройка middleware для проверки роли"""
        self.router.message.middleware(
            RoleRequiredMiddleware(self.ALLOWED_ROLES, self.user_repo)
        )
        self.router.callback_query.middleware(
            RoleRequiredMiddleware(self.ALLOWED_ROLES, self.user_repo)
        )

    def _setup_handlers(self):
        """Регистрация обработчиков"""
        # Команды
        self.router.message(Command("manager"))(self.cmd_manager_menu)
        self.router.message(Command("applications"))(self.cmd_applications)

        # Callback handlers
        self.router.callback_query(F.data == "mgr:menu")(self.cb_menu)
        self.router.callback_query(F.data == "mgr:applications:new")(self.cb_new_applications)
        self.router.callback_query(F.data == "mgr:applications:my")(self.cb_my_applications)
        self.router.callback_query(F.data == "mgr:stats")(self.cb_stats)

        # Пагинация
        self.router.callback_query(F.data.startswith("mgr:page:"))(self.cb_page)

        # Действия с заявкой
        self.router.callback_query(F.data.startswith("mgr:app:"))(self.cb_view_application)
        self.router.callback_query(F.data.startswith("mgr:approve:"))(self.cb_approve)
        self.router.callback_query(F.data.startswith("mgr:reject:"))(self.cb_reject)
        self.router.callback_query(F.data.startswith("mgr:reject_reason:"))(self.cb_reject_reason)
        self.router.callback_query(F.data.startswith("mgr:escalate:"))(self.cb_escalate)

        # Выбор компании и банка
        self.router.callback_query(F.data.startswith("mgr:company:"))(self.cb_select_company)
        self.router.callback_query(F.data.startswith("mgr:bank:"))(self.cb_select_bank)

        # Выбор формата выдачи T+N
        self.router.callback_query(F.data.startswith("mgr:payout:"))(self.cb_select_payout)

        # Ввод причины отклонения (для "другая причина")
        self.router.message(RejectReasonState.waiting_for_reason)(self.process_reject_reason)

    # ==================== КОМАНДЫ ====================

    async def cmd_manager_menu(self, message: Message, db_user):
        """Команда /manager - главное меню"""
        # Получаем количество новых заявок
        new_apps = await self.application_repo.get_by_status('new')
        manager_review = await self.application_repo.get_by_status('manager_review')

        total_pending = len(new_apps) + len(manager_review)

        await message.answer(
            f"👔 <b>Панель менеджера</b>\n\n"
            f"👤 {db_user.first_name or db_user.username}\n"
            f"📥 Ожидают рассмотрения: <b>{total_pending}</b>\n",
            reply_markup=self.kb.main_menu(),
            parse_mode="HTML"
        )

    async def cmd_applications(self, message: Message, db_user):
        """Команда /applications - список новых заявок"""
        await self._show_new_applications(message, db_user)

    # ==================== CALLBACK HANDLERS ====================

    async def cb_menu(self, callback: CallbackQuery, db_user):
        """Возврат в главное меню"""
        new_apps = await self.application_repo.get_by_status('new')
        manager_review = await self.application_repo.get_by_status('manager_review')
        total_pending = len(new_apps) + len(manager_review)

        await callback.message.edit_text(
            f"👔 <b>Панель менеджера</b>\n\n"
            f"👤 {db_user.first_name or db_user.username}\n"
            f"📥 Ожидают рассмотрения: <b>{total_pending}</b>\n",
            reply_markup=self.kb.main_menu(),
            parse_mode="HTML"
        )
        await callback.answer()

    async def cb_new_applications(self, callback: CallbackQuery, db_user):
        """Список новых заявок"""
        await self._show_new_applications(callback, db_user)
        await callback.answer()

    async def cb_my_applications(self, callback: CallbackQuery, db_user):
        """Мои заявки (назначенные мне)"""
        applications = await self.application_repo.get_by_manager(db_user.id)

        if not applications:
            await callback.message.edit_text(
                "📋 У вас нет назначенных заявок.",
                reply_markup=self.kb.main_menu()
            )
        else:
            await callback.message.edit_text(
                f"📋 <b>Мои заявки</b> ({len(applications)})\n\n"
                "Выберите заявку для просмотра:",
                reply_markup=self.kb.applications_list(applications),
                parse_mode="HTML"
            )
        await callback.answer()

    async def cb_stats(self, callback: CallbackQuery, db_user):
        """Статистика"""
        from datetime import date
        today = date.today()

        daily_stats = await self.application_repo.get_daily_stats(today)

        total = sum(s['count'] for s in daily_stats)
        total_amount = sum(s['total_amount'] for s in daily_stats)

        stats_text = f"📊 <b>Статистика за {today.strftime('%d.%m.%Y')}</b>\n\n"
        stats_text += f"📋 Всего заявок: <b>{total}</b>\n"
        stats_text += f"💰 Общая сумма: <b>{total_amount:,.0f}₽</b>\n\n"

        if daily_stats:
            stats_text += "<b>По статусам:</b>\n"
            status_names = {
                'new': '🆕 Новые',
                'manager_review': '👀 На рассмотрении',
                'bank_review': '🏦 В банке',
                'approved': '✅ Одобрено',
                'rejected': '❌ Отклонено'
            }
            for stat in daily_stats:
                name = status_names.get(stat['status'], stat['status'])
                stats_text += f"  {name}: {stat['count']}\n"

        await callback.message.edit_text(
            stats_text,
            reply_markup=self.kb.main_menu(),
            parse_mode="HTML"
        )
        await callback.answer()

    async def cb_page(self, callback: CallbackQuery, db_user):
        """Пагинация списка заявок"""
        page = int(callback.data.split(":")[-1])
        applications = await self._get_pending_applications()

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

        # Формируем текст заявки
        text = self._format_application(app)

        # Определяем, можно ли одобрить
        can_approve = app.status in ['new', 'manager_review']

        await callback.message.edit_text(
            text,
            reply_markup=self.kb.application_actions(app_id, can_approve),
            parse_mode="HTML"
        )
        await callback.answer()

    async def cb_approve(self, callback: CallbackQuery, db_user):
        """Одобрение заявки - выбор компании"""
        app_id = int(callback.data.split(":")[-1])
        app = await self.application_repo.get_by_id(app_id)

        if not app:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        # Получаем все активные компании (без проверки лимитов)
        companies = await self.company_repo.get_all()
        available_companies = [c for c in companies if c.is_active]

        if not available_companies:
            await callback.answer(
                "Нет активных компаний!",
                show_alert=True
            )
            return

        await callback.message.edit_text(
            f"📋 <b>{format_application_number(app, for_client=True)}</b>\n"
            f"💰 Сумма: {app.amount:,.0f}₽\n\n"
            f"🏢 <b>Выберите компанию:</b>",
            reply_markup=self.kb.select_company(available_companies, app_id),
            parse_mode="HTML"
        )
        await callback.answer()

    async def cb_select_company(self, callback: CallbackQuery, db_user):
        """Выбор компании - переход к выбору банка"""
        parts = callback.data.split(":")
        app_id = int(parts[2])
        company_id = int(parts[3])

        app = await self.application_repo.get_by_id(app_id)
        if not app:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        # Сохраняем выбранную компанию
        await self.application_repo.assign_company(app_id, company_id)

        company = await self.company_repo.get_by_id(company_id)

        # Получаем все счета компании (CompanyBank)
        company_bank_accounts = await self.company_bank_repo.get_by_company(company_id)

        # Фильтруем по доступному лимиту (проверяем лимит счета, а не банка)
        available_accounts = [
            cb for cb in company_bank_accounts
            if (cb.daily_limit == 0 or (cb.daily_limit - cb.current_daily_used) >= app.amount)
        ]

        if not available_accounts:
            # Проверяем, есть ли вообще счета у компании
            if not company_bank_accounts:
                await callback.answer(
                    "У компании нет привязанных банковских счетов!",
                    show_alert=True
                )
            else:
                await callback.answer(
                    "Нет счетов с достаточным лимитом!",
                    show_alert=True
                )
            return

        # Получаем уникальные банки из доступных счетов
        bank_ids = list(set(cb.bank_id for cb in available_accounts))
        available_banks = []
        for bank_id in bank_ids:
            bank = await self.bank_repo.get_by_id(bank_id)
            if bank and bank.is_active and bank.is_available:
                available_banks.append(bank)

        await callback.message.edit_text(
            f"📋 <b>{format_application_number(app, for_client=True)}</b>\n"
            f"💰 Сумма: {app.amount:,.0f}₽\n"
            f"🏢 Компания: {company.name}\n\n"
            f"🏦 <b>Выберите банк:</b>",
            reply_markup=self.kb.select_bank(available_banks, app_id),
            parse_mode="HTML"
        )
        await callback.answer()

    async def cb_select_bank(self, callback: CallbackQuery, db_user):
        """Выбор банка - отправка в банк"""
        parts = callback.data.split(":")
        app_id = int(parts[2])
        bank_id = int(parts[3])

        app = await self.application_repo.get_with_relations(app_id)
        if not app:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        # Инкрементируем счетчик заявок для CompanyBank и проверяем лимиты
        bank_display_number = None
        if app.company_id:
            company_bank = await self.company_bank_repo.get_by_company_and_bank(
                app.company_id,
                bank_id
            )
            if company_bank:
                # Проверяем и обновляем лимиты счета
                limit_check = await self.company_bank_repo.check_and_update_limits(
                    company_bank.id,
                    float(app.amount)
                )

                if not limit_check['allowed']:
                    await callback.answer(
                        f"⚠️ Превышен лимит! Недостаточно средств на счете.",
                        show_alert=True
                    )
                    return

                bank_display_number = await self.company_bank_repo.increment_counter(company_bank.id)

        # Сохраняем банк и менеджера
        await self.application_repo.assign_bank(app_id, bank_id, bank_display_number)
        await self.application_repo.assign_manager(app_id, db_user.id)

        # Обновляем статус заявки
        await self.application_repo.update_status(app_id, 'bank_review')

        # Одобряем этап менеджера в workflow
        pending_approval = await self.approval_repo.get_pending(app_id)
        if pending_approval and pending_approval.role == 'manager':
            await self.approval_repo.approve(pending_approval.id, db_user.id)

        # Логируем
        await self.log_repo.create_log(
            action='manager_approved',
            application_id=app_id,
            user_id=db_user.id,
            details={'bank_id': bank_id}
        )

        bank = await self.bank_repo.get_by_id(bank_id)

        if bank and bank.chat_id:
            status_text = "⏳ Ожидаем ответа от банка..."
        else:
            status_text = "⚠️ Банк не привязан к групповому чату. Уведомление не отправлено."

        await callback.message.edit_text(
            f"✅ <b>Заявка одобрена!</b>\n\n"
            f"📋 {format_application_number(app, for_client=True)}\n"
            f"💰 {app.amount:,.0f}₽\n"
            f"🏦 Отправлена в: {bank.name}\n\n"
            f"{status_text}",
            reply_markup=self.kb.main_menu(),
            parse_mode="HTML"
        )
        await callback.answer("Заявка одобрена!")

        # Отправляем уведомление в групповой чат банка
        if bank and bank.chat_id:
            notification_text = (
                f"📥 <b>Новая заявка на оценку риска</b>\n\n"
                f"📋 {format_application_number(app, for_client=True)}\n"
                f"💰 Сумма: <b>{app.amount:,.0f}₽</b>\n"
                f"🏢 ИНН плательщика: <code>{app.payer_inn}</code>\n"
            )
            if app.payer_name:
                notification_text += f"📛 Плательщик: {app.payer_name}\n"
            notification_text += f"📝 Назначение: {app.purpose}\n"
            if app.primary_check_result:
                notification_text += f"\n{format_payer_check(app.primary_check_result)}\n"
            if app.company:
                notification_text += f"\n🏢 Компания: {app.company.name}\n"
            notification_text += (
                f"\n👔 Менеджер: {db_user.first_name or db_user.username}\n"
                f"\n<b>Оцените уровень риска:</b>"
            )
            try:
                await self.bot.send_message(
                    chat_id=bank.chat_id,
                    text=notification_text,
                    reply_markup=self.bank_kb.group_risk_assessment(app_id),
                    parse_mode="HTML"
                )
            except Exception:
                pass

    async def cb_reject(self, callback: CallbackQuery, db_user):
        """Отклонение заявки - выбор причины"""
        app_id = int(callback.data.split(":")[-1])

        await callback.message.edit_text(
            "❌ <b>Отклонение заявки</b>\n\n"
            "Выберите причину отклонения:",
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
            'invalid_data': 'Некорректные данные',
            'limit_exceeded': 'Превышен лимит',
            'counterparty_failed': 'Контрагент не прошёл проверку',
            'other': None
        }

        if reason_code == 'other':
            # Запрашиваем ввод причины
            await state.set_state(RejectReasonState.waiting_for_reason)
            await state.update_data(app_id=app_id)
            await callback.message.edit_text(
                "📝 Введите причину отклонения:"
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

        # Отклоняем заявку
        await self.application_repo.update_status(app_id, 'rejected')

        # Отклоняем в workflow
        pending_approval = await self.approval_repo.get_pending(app_id)
        if pending_approval:
            await self.approval_repo.reject(pending_approval.id, db_user.id, reason)

        # Логируем
        await self.log_repo.create_log(
            action='manager_rejected',
            application_id=app_id,
            user_id=db_user.id,
            details={'reason': reason}
        )

        await message.answer(
            f"❌ <b>{format_application_number(app, for_client=True)} отклонена</b>\n\n"
            f"📝 Причина: {reason}",
            reply_markup=self.kb.main_menu(),
            parse_mode="HTML"
        )

        if self.notification_service:
            await self.notification_service.notify_client_rejected(app, reason, "менеджер")

    async def cb_escalate(self, callback: CallbackQuery, db_user):
        """Эскалация к руководителю"""
        app_id = int(callback.data.split(":")[-1])
        app = await self.application_repo.get_by_id(app_id)

        if not app:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        # Создаём эскалацию
        await self.approval_repo.create_escalation(
            app_id=app_id,
            role='supervisor',
            reason='Эскалация от менеджера',
            sequence=0  # Срочный приоритет
        )

        # Обновляем статус
        await self.application_repo.update_status(app_id, 'supervisor_review')

        # Помечаем текущий этап как эскалированный
        pending_approval = await self.approval_repo.get_pending(app_id)
        if pending_approval:
            await self.approval_repo.escalate(pending_approval.id, db_user.id, 'Требуется решение руководителя')

        # Логируем
        await self.log_repo.create_log(
            action='manager_escalated',
            application_id=app_id,
            user_id=db_user.id
        )

        await callback.message.edit_text(
            f"🚨 <b>Заявка эскалирована</b>\n\n"
            f"📋 {format_application_number(app, for_client=True)}\n"
            f"💰 {app.amount:,.0f}₽\n\n"
            f"📤 Отправлена руководителю на рассмотрение.",
            reply_markup=self.kb.main_menu(),
            parse_mode="HTML"
        )
        await callback.answer("Заявка отправлена руководителю")

        if self.notification_service:
            await self.notification_service.notify_supervisors_escalation(app, "менеджер")

    async def cb_select_payout(self, callback: CallbackQuery, db_user):
        """Выбор формата выдачи T+N после подтверждения оплаты"""
        # Формат: mgr:payout:{days}:{app_id}
        parts = callback.data.split(":")
        payout_days = int(parts[2])
        app_id = int(parts[3])

        app = await self.application_repo.get_by_id(app_id)
        if not app:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        # Вычисляем дату выдачи
        payout_format = f"T+{payout_days}"
        payout_date = get_payout_date(payout_format, datetime.utcnow())

        # Обновляем заявку
        await self.application_repo.update_payout(
            app_id=app_id,
            payout_format=payout_format,
            payout_date=payout_date
        )
        await self.application_repo.update_status(app_id, 'scheduled_payout')

        # Логируем
        await self.log_repo.create_log(
            action='payout_scheduled',
            application_id=app_id,
            user_id=db_user.id,
            details={'payout_format': payout_format, 'payout_date': payout_date.isoformat()}
        )

        # Форматируем дату для отображения
        payout_date_str = format_payout_date(payout_date)

        await callback.message.edit_text(
            f"✅ <b>Дата выдачи назначена!</b>\n\n"
            f"📋 {format_application_number(app, for_client=True)}\n"
            f"💰 {app.amount:,.0f}₽\n"
            f"📅 Формат: {payout_format}\n"
            f"📆 Дата выдачи: {payout_date_str}",
            reply_markup=self.kb.main_menu(),
            parse_mode="HTML"
        )
        await callback.answer(f"Выдача назначена: {payout_date_str}")

        # Уведомляем клиента
        if self.notification_service:
            await self.notification_service.notify_client_payout_scheduled(app, payout_date_str)

    # ==================== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ====================

    async def _show_new_applications(self, event, db_user):
        """Показать новые заявки"""
        applications = await self._get_pending_applications()

        text = f"📥 <b>Новые заявки</b> ({len(applications)})\n\n"

        if not applications:
            text += "Нет заявок на рассмотрение."
            keyboard = self.kb.main_menu()
        else:
            text += "Выберите заявку для просмотра:"
            keyboard = self.kb.applications_list(applications)

        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        else:
            await event.answer(text, reply_markup=keyboard, parse_mode="HTML")

    async def _get_pending_applications(self):
        """Получить заявки, ожидающие рассмотрения"""
        new_apps = await self.application_repo.get_by_status('new')
        manager_review = await self.application_repo.get_by_status('manager_review')
        return new_apps + manager_review

    async def _reject_application(self, callback: CallbackQuery, app_id: int, reason: str, db_user):
        """Отклонить заявку"""
        app = await self.application_repo.get_by_id(app_id)

        # Обновляем статус
        await self.application_repo.update_status(app_id, 'rejected')

        # Отклоняем в workflow
        pending_approval = await self.approval_repo.get_pending(app_id)
        if pending_approval:
            await self.approval_repo.reject(pending_approval.id, db_user.id, reason)

        # Логируем
        await self.log_repo.create_log(
            action='manager_rejected',
            application_id=app_id,
            user_id=db_user.id,
            details={'reason': reason}
        )

        await callback.message.edit_text(
            f"❌ <b>{format_application_number(app, for_client=True)} отклонена</b>\n\n"
            f"📝 Причина: {reason}",
            reply_markup=self.kb.main_menu(),
            parse_mode="HTML"
        )
        await callback.answer("Заявка отклонена")

        if self.notification_service:
            await self.notification_service.notify_client_rejected(app, reason, "менеджер")

    def _format_application(self, app) -> str:
        """Форматирование заявки для отображения"""
        status_map = {
            'new': '🆕 Новая',
            'primary_check': '🔍 Проверка',
            'manager_review': '👀 На рассмотрении',
            'bank_review': '🏦 В банке',
            'min_risk_review': '⚠️ Минимальный риск',
            'awaiting_contract_details': '📝 Ожидание данных договора',
            'supervisor_review': '👔 У руководителя',
            'approved': '✅ Одобрена',
            'rejected': '❌ Отклонена',
            'invoice_generated': '📄 Счёт создан',
            'paid': '💰 Оплачено'
        }

        text = f"📋 <b>{format_application_number(app, for_client=True)}</b>\n\n"
        text += f"📊 Статус: {status_map.get(app.status, app.status)}\n"
        text += f"💰 Сумма: <b>{app.amount:,.0f}₽</b>\n"
        text += f"🏢 ИНН: {app.payer_inn}\n"

        if app.payer_name:
            text += f"📛 Плательщик: {app.payer_name}\n"

        text += f"📝 Назначение: {app.purpose}\n"
        text += f"📅 Создана: {app.created_at.strftime('%d.%m.%Y %H:%M')}\n"

        # Результаты проверки ЗЧБ
        if app.primary_check_result:
            text += f"\n{format_payer_check(app.primary_check_result)}\n"

        if app.company:
            text += f"\n🏢 Компания: {app.company.name}\n"

        if app.bank:
            text += f"🏦 Банк: {app.bank.name}\n"

        if app.manager:
            text += f"👤 Менеджер: {app.manager.first_name or app.manager.username}\n"

        # Информация о подписях
        if app.approvals:
            text += "\n<b>Подписи:</b>\n"
            for approval in sorted(app.approvals, key=lambda x: x.sequence):
                if approval.decision:
                    decision_emoji = {'approved': '✅', 'rejected': '❌', 'escalated': '🚨'}.get(approval.decision, '⏳')
                    text += f"  {decision_emoji} {approval.role}: {approval.decision}\n"
                else:
                    text += f"  ⏳ {approval.role}: ожидание\n"

        return text
