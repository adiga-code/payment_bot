# bot/handlers/admin.py

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from decimal import Decimal
from datetime import date, datetime

from database import (
    UserRepository,
    CompanyRepository,
    BankRepository,
    ApplicationRepository,
    LogRepository
)
from keyboards.admin_kb import AdminKeyboards
from middleware import RoleRequiredMiddleware
from services.honest_business_api import ZCBService, format_zcb_color


class AdminStates(StatesGroup):
    """FSM состояния для админ-панели"""
    # Пользователи
    waiting_user_forward = State()  # Ожидание пересланного сообщения для добавления
    waiting_user_role = State()  # Ожидание выбора роли для нового пользователя

    # Компании
    waiting_company_name = State()
    waiting_company_inn = State()
    waiting_company_ogrn = State()
    waiting_company_daily_limit = State()
    editing_company_name = State()
    editing_company_inn = State()
    editing_company_limit = State()
    editing_company_director_name = State()  # Редактирование ФИО директора
    waiting_company_bank_account = State()  # Ввод номера счёта при привязке банка
    editing_company_bank_account = State()  # Редактирование номера счёта
    waiting_company_signature = State()  # Ожидание загрузки подписи
    waiting_company_stamp = State()  # Ожидание загрузки печати

    # Банки
    waiting_bank_name = State()
    waiting_bank_bik = State()
    waiting_bank_corr_account = State()
    waiting_bank_daily_limit = State()
    waiting_group_code = State()  # Ожидание кода подтверждения группы
    editing_bank_name = State()
    editing_bank_priority = State()
    editing_bank_limit = State()


class AdminStatsDateState(StatesGroup):
    """Состояния для выбора даты статистики админа"""
    waiting_for_start_date = State()
    waiting_for_end_date = State()


class AdminHandlers:
    """Хендлеры для администратора"""

    ALLOWED_ROLES = ['admin']

    def __init__(
            self,
            user_repo: UserRepository,
            company_repo: CompanyRepository,
            bank_repo: BankRepository,
            application_repo: ApplicationRepository,
            log_repo: LogRepository,
            pending_group_codes: dict = None,
            zcb_service: ZCBService = None
    ):
        self.router = Router()
        self.user_repo = user_repo
        self.company_repo = company_repo
        self.bank_repo = bank_repo
        self.application_repo = application_repo
        self.log_repo = log_repo
        self.kb = AdminKeyboards()
        self.pending_group_codes = pending_group_codes if pending_group_codes is not None else {}
        self.zcb_service = zcb_service

        self._setup_middleware()
        self._setup_handlers()

    def _setup_middleware(self):
        """Middleware для проверки роли admin"""
        self.router.message.middleware(
            RoleRequiredMiddleware(self.ALLOWED_ROLES, self.user_repo)
        )
        self.router.callback_query.middleware(
            RoleRequiredMiddleware(self.ALLOWED_ROLES, self.user_repo)
        )

    def _setup_handlers(self):
        """Регистрация обработчиков"""
        # Главная команда
        self.router.message(Command("admin"))(self.cmd_admin)

        # Callback: меню
        self.router.callback_query(F.data == "admin:menu")(self.cb_menu)
        self.router.callback_query(F.data == "admin:cancel")(self.cb_cancel)

        # ===== ПОЛЬЗОВАТЕЛИ =====
        self.router.callback_query(F.data == "admin:users")(self.cb_users_menu)
        self.router.callback_query(F.data.startswith("admin:users:list:"))(self.cb_users_list)
        self.router.callback_query(F.data.startswith("admin:users:page:"))(self.cb_users_page)
        self.router.callback_query(F.data == "admin:users:add")(self.cb_users_add)
        self.router.callback_query(F.data.startswith("admin:user:"))(self.cb_user_action)

        # FSM: добавление пользователя
        self.router.message(AdminStates.waiting_user_forward)(self.process_user_forward)

        # ===== КОМПАНИИ =====
        self.router.callback_query(F.data == "admin:companies")(self.cb_companies_menu)
        self.router.callback_query(F.data == "admin:companies:list")(self.cb_companies_list)
        self.router.callback_query(F.data.startswith("admin:companies:page:"))(self.cb_companies_page)
        self.router.callback_query(F.data == "admin:companies:add")(self.cb_companies_add)
        self.router.callback_query(F.data.startswith("admin:company:"))(self.cb_company_action)

        # FSM: компании
        self.router.message(AdminStates.waiting_company_name)(self.process_company_name)
        self.router.message(AdminStates.waiting_company_inn)(self.process_company_inn)
        self.router.message(AdminStates.waiting_company_ogrn)(self.process_company_ogrn)
        self.router.message(AdminStates.waiting_company_daily_limit)(self.process_company_daily_limit)
        self.router.message(AdminStates.editing_company_name)(self.process_edit_company_name)
        self.router.message(AdminStates.editing_company_inn)(self.process_edit_company_inn)
        self.router.message(AdminStates.editing_company_director_name)(self.process_edit_company_director_name)
        self.router.message(AdminStates.editing_company_limit)(self.process_edit_company_limit)
        self.router.message(AdminStates.waiting_company_bank_account)(self.process_company_bank_account)
        self.router.message(AdminStates.editing_company_bank_account)(self.process_edit_company_bank_account)
        self.router.message(AdminStates.waiting_company_signature)(self.process_company_signature)
        self.router.message(AdminStates.waiting_company_stamp)(self.process_company_stamp)

        # ===== БАНКИ =====
        self.router.callback_query(F.data == "admin:banks")(self.cb_banks_menu)
        self.router.callback_query(F.data == "admin:banks:list")(self.cb_banks_list)
        self.router.callback_query(F.data.startswith("admin:banks:page:"))(self.cb_banks_page)
        self.router.callback_query(F.data == "admin:banks:add")(self.cb_banks_add)
        self.router.callback_query(F.data.startswith("admin:bank:"))(self.cb_bank_action)

        # FSM: банки
        self.router.message(AdminStates.waiting_bank_name)(self.process_bank_name)
        self.router.message(AdminStates.waiting_bank_bik)(self.process_bank_bik)
        self.router.message(AdminStates.waiting_bank_corr_account)(self.process_bank_corr_account)
        self.router.message(AdminStates.waiting_bank_daily_limit)(self.process_bank_daily_limit)
        self.router.message(AdminStates.waiting_group_code)(self.process_group_code)
        self.router.message(AdminStates.editing_bank_name)(self.process_edit_bank_name)
        self.router.message(AdminStates.editing_bank_priority)(self.process_edit_bank_priority)
        self.router.message(AdminStates.editing_bank_limit)(self.process_edit_bank_limit)

        # Статистика
        self.router.callback_query(F.data == "admin:stats")(self.cb_stats)
        self.router.callback_query(F.data == "admin:stats:system")(self.cb_stats_system)
        self.router.callback_query(F.data == "admin:stats:today")(self.cb_stats_today)
        self.router.callback_query(F.data == "admin:stats:week")(self.cb_stats_week)
        self.router.callback_query(F.data == "admin:stats:month")(self.cb_stats_month)
        self.router.callback_query(F.data == "admin:stats:custom")(self.cb_stats_custom)
        self.router.callback_query(F.data.startswith("admin:stats:detail:"))(self.cb_stats_detail)
        self.router.callback_query(F.data == "admin:stats:payments")(self.cb_stats_payments)

        # FSM: Статистика
        self.router.message(AdminStatsDateState.waiting_for_start_date)(self.process_stats_start_date)
        self.router.message(AdminStatsDateState.waiting_for_end_date)(self.process_stats_end_date)

    # ==================== ГЛАВНОЕ МЕНЮ ====================

    async def cmd_admin(self, message: Message, state: FSMContext, db_user):
        """Команда /admin"""
        await state.clear()
        users_count = len(await self.user_repo.get_all())
        companies_count = len(await self.company_repo.get_all())
        banks_count = len(await self.bank_repo.get_all())

        await message.answer(
            f"⚙️ <b>Панель администратора</b>\n\n"
            f"👥 Пользователей: {users_count}\n"
            f"🏢 Компаний: {companies_count}\n"
            f"🏦 Банков: {banks_count}",
            reply_markup=self.kb.main_menu(),
            parse_mode="HTML"
        )

    async def cb_menu(self, callback: CallbackQuery, state: FSMContext, db_user):
        """Возврат в главное меню"""
        await state.clear()
        users_count = len(await self.user_repo.get_all())
        companies_count = len(await self.company_repo.get_all())
        banks_count = len(await self.bank_repo.get_all())

        await callback.message.edit_text(
            f"⚙️ <b>Панель администратора</b>\n\n"
            f"👥 Пользователей: {users_count}\n"
            f"🏢 Компаний: {companies_count}\n"
            f"🏦 Банков: {banks_count}",
            reply_markup=self.kb.main_menu(),
            parse_mode="HTML"
        )
        await callback.answer()

    async def cb_cancel(self, callback: CallbackQuery, state: FSMContext, db_user):
        """Отмена текущего действия"""
        await state.clear()
        await callback.message.edit_text(
            "❌ Действие отменено",
            reply_markup=self.kb.back_to_menu()
        )
        await callback.answer()

    # ==================== ПОЛЬЗОВАТЕЛИ ====================

    async def cb_users_menu(self, callback: CallbackQuery, db_user):
        """Меню пользователей"""
        await callback.message.edit_text(
            "👥 <b>Управление пользователями</b>\n\n"
            "Выберите действие:",
            reply_markup=self.kb.users_menu(),
            parse_mode="HTML"
        )
        await callback.answer()

    async def cb_users_list(self, callback: CallbackQuery, db_user):
        """Список пользователей"""
        role_filter = callback.data.split(":")[-1]

        if role_filter == 'all':
            users = await self.user_repo.get_all()
            title = "Все пользователи"
        else:
            users = await self.user_repo.get_by_role(role_filter, active_only=False)
            role_names = {
                'manager': 'Менеджеры',
                'supervisor': 'Супервайзеры',
                'admin': 'Администраторы',
                'client': 'Клиенты'
            }
            title = role_names.get(role_filter, role_filter)

        if not users:
            await callback.message.edit_text(
                f"👥 <b>{title}</b>\n\nСписок пуст.",
                reply_markup=self.kb.users_menu(),
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                f"👥 <b>{title}</b> ({len(users)})\n\n"
                "Выберите пользователя:",
                reply_markup=self.kb.users_list(users, role_filter),
                parse_mode="HTML"
            )
        await callback.answer()

    async def cb_users_page(self, callback: CallbackQuery, db_user):
        """Пагинация пользователей"""
        parts = callback.data.split(":")
        role_filter = parts[-2]
        page = int(parts[-1])

        if role_filter == 'all':
            users = await self.user_repo.get_all()
        else:
            users = await self.user_repo.get_by_role(role_filter, active_only=False)

        await callback.message.edit_reply_markup(
            reply_markup=self.kb.users_list(users, role_filter, page)
        )
        await callback.answer()

    async def cb_users_add(self, callback: CallbackQuery, state: FSMContext, db_user):
        """Добавление пользователя"""
        await state.set_state(AdminStates.waiting_user_forward)
        await callback.message.edit_text(
            "👤 <b>Добавление пользователя</b>\n\n"
            "📨 <b>Перешлите сообщение</b> от пользователя, которого хотите добавить.\n\n"
            "Или отправьте его <b>Telegram ID</b> числом.",
            reply_markup=self.kb.cancel_input(),
            parse_mode="HTML"
        )
        await callback.answer()

    async def process_user_forward(self, message: Message, state: FSMContext, db_user):
        """Обработка пересланного сообщения для добавления пользователя"""
        telegram_id = None
        username = None
        first_name = None

        # Проверяем, пересланное ли это сообщение
        if message.forward_from:
            telegram_id = message.forward_from.id
            username = message.forward_from.username
            first_name = message.forward_from.first_name
        elif message.text and message.text.isdigit():
            telegram_id = int(message.text)
        else:
            await message.answer(
                "❌ Не удалось определить пользователя.\n\n"
                "Перешлите сообщение от пользователя или отправьте его Telegram ID.",
                reply_markup=self.kb.cancel_input()
            )
            return

        # Проверяем, существует ли уже
        existing = await self.user_repo.get_by_telegram_id(telegram_id)
        if existing:
            await state.clear()
            await message.answer(
                f"⚠️ Пользователь уже существует!\n\n"
                f"👤 {existing.first_name or existing.username or telegram_id}\n"
                f"🎭 Роль: {existing.role}\n"
                f"{'✅ Активен' if existing.is_active else '❌ Неактивен'}",
                reply_markup=self.kb.user_actions(existing.id, existing.is_active),
                parse_mode="HTML"
            )
            return

        # Сохраняем данные и запрашиваем роль
        await state.update_data(
            new_user_telegram_id=telegram_id,
            new_user_username=username,
            new_user_first_name=first_name
        )
        await state.set_state(AdminStates.waiting_user_role)

        name_display = first_name or username or str(telegram_id)
        await message.answer(
            f"👤 <b>Новый пользователь</b>\n\n"
            f"ID: <code>{telegram_id}</code>\n"
            f"Имя: {name_display}\n\n"
            f"Выберите роль:",
            reply_markup=self.kb.select_role(0),  # 0 = новый пользователь
            parse_mode="HTML"
        )

    async def cb_user_action(self, callback: CallbackQuery, state: FSMContext, db_user):
        """Обработка действий с пользователем"""
        data = callback.data.replace("admin:user:", "")
        parts = data.split(":")

        action = parts[0]

        # Просмотр пользователя
        if action.isdigit():
            user_id = int(action)
            user = await self.user_repo.get_by_id(user_id)
            if not user:
                await callback.answer("Пользователь не найден", show_alert=True)
                return

            role_names = {
                'client': '👤 Клиент',
                'manager': '👔 Менеджер',
                'bank': '🏦 Сотрудник банка',
                'accountant': '📑 Бухгалтер',
                'supervisor': '👑 Супервайзер',
                'admin': '⚙️ Администратор'
            }

            text = (
                f"👤 <b>Пользователь</b>\n\n"
                f"🆔 ID: <code>{user.telegram_id}</code>\n"
                f"📛 Username: @{user.username or '—'}\n"
                f"👤 Имя: {user.first_name or '—'} {user.last_name or ''}\n"
                f"🎭 Роль: {role_names.get(user.role, user.role)}\n"
            )

            # Показываем привязку к банку для сотрудников банка
            if user.bank_id:
                bank = await self.bank_repo.get_by_id(user.bank_id)
                bank_name = bank.name if bank else "Не найден"
                text += f"🏦 Банк: {bank_name}\n"
            elif user.role == 'bank':
                text += f"🏦 Банк: <i>Не привязан</i>\n"

            text += (
                f"📊 Статус: {'✅ Активен' if user.is_active else '❌ Неактивен'}\n"
                f"📅 Создан: {user.created_at.strftime('%d.%m.%Y %H:%M')}"
            )

            await callback.message.edit_text(
                text,
                reply_markup=self.kb.user_actions(user.id, user.is_active),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        # Установка роли
        if action == "setrole":
            new_role = parts[-1]
            user_id = int(parts[-2])

            # Если выбрана роль 'bank', показываем выбор банка
            if new_role == 'bank':
                banks = await self.bank_repo.get_all()
                if not banks:
                    await callback.answer("Нет доступных банков. Сначала добавьте банк.", show_alert=True)
                    return

                await callback.message.edit_text(
                    "🏦 <b>Выберите банк</b>\n\n"
                    "К какому банку привязать сотрудника?",
                    reply_markup=self.kb.select_bank_for_user(user_id, banks),
                    parse_mode="HTML"
                )
                await callback.answer()
                return

            # Для остальных ролей — обычное поведение
            if user_id == 0:
                fsm_data = await state.get_data()
                telegram_id = fsm_data.get('new_user_telegram_id')
                username = fsm_data.get('new_user_username')
                first_name = fsm_data.get('new_user_first_name')

                if not telegram_id:
                    await callback.answer("Ошибка: данные потеряны", show_alert=True)
                    return

                user = await self.user_repo.create(
                    telegram_id=telegram_id,
                    username=username,
                    first_name=first_name,
                    role=new_role
                )
                await state.clear()

                await callback.message.edit_text(
                    f"✅ <b>Пользователь создан!</b>\n\n"
                    f"👤 {first_name or username or telegram_id}\n"
                    f"🎭 Роль: {new_role}",
                    reply_markup=self.kb.back_to_menu(),
                    parse_mode="HTML"
                )
            else:
                # При смене роли с 'bank' на другую — убираем bank_id
                await self.user_repo.update_role(user_id, new_role)
                await self.user_repo.update_bank(user_id, None)
                user = await self.user_repo.get_by_id(user_id)

                await callback.message.edit_text(
                    f"✅ Роль изменена на <b>{new_role}</b>",
                    reply_markup=self.kb.user_actions(user_id, user.is_active),
                    parse_mode="HTML"
                )
            await callback.answer("Роль обновлена!")
            return

        # Выбор банка для роли 'bank'
        if action == "setbank":
            user_id = int(parts[1])
            bank_choice = parts[2]

            bank_id = None if bank_choice == 'skip' else int(bank_choice)

            if user_id == 0:
                # Новый пользователь
                fsm_data = await state.get_data()
                telegram_id = fsm_data.get('new_user_telegram_id')
                username = fsm_data.get('new_user_username')
                first_name = fsm_data.get('new_user_first_name')

                if not telegram_id:
                    await callback.answer("Ошибка: данные потеряны", show_alert=True)
                    return

                user = await self.user_repo.create(
                    telegram_id=telegram_id,
                    username=username,
                    first_name=first_name,
                    role='bank',
                    bank_id=bank_id
                )
                await state.clear()

                bank_info = ""
                if bank_id:
                    bank = await self.bank_repo.get_by_id(bank_id)
                    bank_info = f"\n🏦 Банк: {bank.name}" if bank else ""

                await callback.message.edit_text(
                    f"✅ <b>Пользователь создан!</b>\n\n"
                    f"👤 {first_name or username or telegram_id}\n"
                    f"🎭 Роль: bank{bank_info}",
                    reply_markup=self.kb.back_to_menu(),
                    parse_mode="HTML"
                )
            else:
                # Существующий пользователь
                await self.user_repo.update_role(user_id, 'bank')
                await self.user_repo.update_bank(user_id, bank_id)
                user = await self.user_repo.get_by_id(user_id)

                bank_info = ""
                if bank_id:
                    bank = await self.bank_repo.get_by_id(bank_id)
                    bank_info = f"\n🏦 Банк: {bank.name}" if bank else ""

                await callback.message.edit_text(
                    f"✅ Роль изменена на <b>bank</b>{bank_info}",
                    reply_markup=self.kb.user_actions(user_id, user.is_active),
                    parse_mode="HTML"
                )

            await state.clear()
            await callback.answer("Роль обновлена!")
            return

        # Для остальных действий user_id - последний элемент
        user_id = int(parts[-1])

        # Изменение роли
        if action == "role":
            await callback.message.edit_text(
                "🔄 <b>Изменение роли</b>\n\nВыберите новую роль:",
                reply_markup=self.kb.select_role(user_id),
                parse_mode="HTML"
            )
            await callback.answer()

        # Деактивация
        elif action == "deactivate":
            await self.user_repo.deactivate(user_id)
            await callback.message.edit_text(
                "🚫 Пользователь деактивирован",
                reply_markup=self.kb.user_actions(user_id, False),
                parse_mode="HTML"
            )
            await callback.answer()

        # Активация
        elif action == "activate":
            await self.user_repo.activate(user_id)
            await callback.message.edit_text(
                "✅ Пользователь активирован",
                reply_markup=self.kb.user_actions(user_id, True),
                parse_mode="HTML"
            )
            await callback.answer()

        # Удаление
        elif action == "delete":
            user = await self.user_repo.get_by_id(user_id)
            await callback.message.edit_text(
                f"🗑️ <b>Удаление пользователя</b>\n\n"
                f"Вы уверены, что хотите удалить пользователя?\n"
                f"👤 {user.first_name or user.username or user.telegram_id}",
                reply_markup=self.kb.confirm_action("delete", "user", user_id),
                parse_mode="HTML"
            )
            await callback.answer()

        elif action == "confirm_delete":
            await self.user_repo.delete_by_id(user_id)
            await callback.message.edit_text(
                "✅ Пользователь удалён",
                reply_markup=self.kb.back_to_menu()
            )
            await callback.answer()

    # ==================== КОМПАНИИ ====================

    async def cb_companies_menu(self, callback: CallbackQuery, db_user):
        """Меню компаний"""
        await callback.message.edit_text(
            "🏢 <b>Управление компаниями</b>\n\n"
            "Выберите действие:",
            reply_markup=self.kb.companies_menu(),
            parse_mode="HTML"
        )
        await callback.answer()

    async def cb_companies_list(self, callback: CallbackQuery, db_user):
        """Список компаний"""
        companies = await self.company_repo.get_all()

        if not companies:
            await callback.message.edit_text(
                "🏢 <b>Компании</b>\n\nСписок пуст.",
                reply_markup=self.kb.companies_menu(),
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                f"🏢 <b>Компании</b> ({len(companies)})\n\n"
                "Выберите компанию:",
                reply_markup=self.kb.companies_list(companies),
                parse_mode="HTML"
            )
        await callback.answer()

    async def cb_companies_page(self, callback: CallbackQuery, db_user):
        """Пагинация компаний"""
        page = int(callback.data.split(":")[-1])
        companies = await self.company_repo.get_all()
        await callback.message.edit_reply_markup(
            reply_markup=self.kb.companies_list(companies, page)
        )
        await callback.answer()

    async def cb_companies_add(self, callback: CallbackQuery, state: FSMContext, db_user):
        """Добавление компании"""
        await state.set_state(AdminStates.waiting_company_name)
        await callback.message.edit_text(
            "🏢 <b>Добавление компании</b>\n\n"
            "Введите название компании:",
            reply_markup=self.kb.cancel_input(),
            parse_mode="HTML"
        )
        await callback.answer()

    async def process_company_name(self, message: Message, state: FSMContext, db_user):
        """Обработка названия компании"""
        name = message.text.strip()
        if len(name) < 3:
            await message.answer("❌ Название слишком короткое. Минимум 3 символа.")
            return

        await state.update_data(company_name=name)
        await state.set_state(AdminStates.waiting_company_inn)
        await message.answer(
            f"✅ Название: <b>{name}</b>\n\n"
            "Введите ИНН компании (10 или 12 цифр):",
            reply_markup=self.kb.cancel_input(),
            parse_mode="HTML"
        )

    async def process_company_inn(self, message: Message, state: FSMContext, db_user):
        """Обработка ИНН компании"""
        inn = message.text.strip()
        if not inn.isdigit() or len(inn) not in [10, 12]:
            await message.answer("❌ ИНН должен содержать 10 или 12 цифр.")
            return

        # Проверяем уникальность
        existing = await self.company_repo.get_by_inn(inn)
        if existing:
            await message.answer(
                f"❌ Компания с ИНН {inn} уже существует!\n"
                f"🏢 {existing.name}"
            )
            return

        await state.update_data(company_inn=inn)
        await state.set_state(AdminStates.waiting_company_ogrn)
        await message.answer(
            f"✅ ИНН: <b>{inn}</b>\n\n"
            "Введите ОГРН компании (13 или 15 цифр):",
            reply_markup=self.kb.cancel_input(),
            parse_mode="HTML"
        )

    async def process_company_ogrn(self, message: Message, state: FSMContext, db_user):
        """Обработка ОГРН компании"""
        ogrn = message.text.strip()
        if not ogrn.isdigit() or len(ogrn) not in [13, 15]:
            await message.answer("❌ ОГРН должен содержать 13 цифр (или 15 для ИП).")
            return

        await state.update_data(company_ogrn=ogrn)
        await state.set_state(AdminStates.waiting_company_daily_limit)
        await message.answer(
            f"✅ ОГРН: <b>{ogrn}</b>\n\n"
            "Введите дневной лимит (в рублях):\n"
            "<i>Например: 5000000</i>",
            reply_markup=self.kb.cancel_input(),
            parse_mode="HTML"
        )

    async def process_company_daily_limit(self, message: Message, state: FSMContext, db_user):
        """Обработка дневного лимита компании"""
        try:
            limit = Decimal(message.text.strip().replace(" ", "").replace(",", ""))
            if limit < 0:
                raise ValueError()
        except:
            await message.answer("❌ Введите корректное число.")
            return

        data = await state.get_data()
        await state.clear()

        ogrn = data.get('company_ogrn')

        # Создаём компанию
        company = await self.company_repo.create(
            name=data['company_name'],
            inn=data['company_inn'],
            ogrn=ogrn,
            daily_limit=limit,
            weekly_limit=limit * 5,
            monthly_limit=limit * 20
        )

        # Проверяем риск ЦБ РФ
        zcb_info = ""
        if ogrn and self.zcb_service:
            status_msg = await message.answer("🔍 Проверяю компанию (Риск ЦБ РФ)...")
            cbr_rating = await self.zcb_service.get_cbr_rating(ogrn)
            if cbr_rating:
                # Конвертируем ISO строку обратно в datetime для БД
                checked_at_str = cbr_rating.get('checked_at')
                checked_at = datetime.fromisoformat(checked_at_str) if checked_at_str else None

                await self.company_repo.update_by_id(
                    company.id,
                    cbr_risk_level=cbr_rating.get('level'),
                    cbr_risk_facts=cbr_rating.get('facts'),
                    cbr_checked_at=checked_at
                )
                from services.honest_business_api import get_cbr_risk_emoji, get_cbr_risk_name
                emoji = get_cbr_risk_emoji(cbr_rating.get('level'))
                risk_name = get_cbr_risk_name(cbr_rating.get('level'))
                zcb_info = (
                    f"\n\n<b>Риск ЦБ РФ:</b>\n"
                    f"{emoji} {risk_name}"
                )

                # Показываем краткую сводку по факторам
                facts = cbr_rating.get('facts', {})
                danger_count = len(facts.get('danger', []))
                warning_count = len(facts.get('warning', []))
                if danger_count > 0:
                    zcb_info += f"\n🔴 Критических факторов: {danger_count}"
                if warning_count > 0:
                    zcb_info += f"\n🟡 Предупреждений: {warning_count}"
            else:
                zcb_info = "\n\n⚠️ Не удалось получить риск ЦБ РФ"
            try:
                await status_msg.delete()
            except:
                pass

        await message.answer(
            f"✅ <b>Компания создана!</b>\n\n"
            f"🏢 {company.name}\n"
            f"🔢 ИНН: {company.inn}\n"
            f"🔢 ОГРН: {ogrn or '—'}\n"
            f"💰 Дневной лимит: {company.daily_limit:,.0f}₽{zcb_info}",
            reply_markup=self.kb.back_to_menu(),
            parse_mode="HTML"
        )

    async def cb_company_action(self, callback: CallbackQuery, state: FSMContext, db_user):
        """Обработка действий с компанией"""
        data = callback.data.replace("admin:company:", "")
        parts = data.split(":")

        action = parts[0]

        # Просмотр компании
        if action.isdigit():
            company_id = int(action)
            company = await self.company_repo.get_by_id(company_id)
            if not company:
                await callback.answer("Компания не найдена", show_alert=True)
                return

            daily_left = company.daily_limit - company.current_daily_used
            weekly_left = company.weekly_limit - company.current_weekly_used
            monthly_left = company.monthly_limit - company.current_monthly_used

            zcb_text = ""
            if company.cbr_risk_level:
                from services.honest_business_api import get_cbr_risk_emoji, get_cbr_risk_name
                emoji = get_cbr_risk_emoji(company.cbr_risk_level)
                risk_name = get_cbr_risk_name(company.cbr_risk_level)
                zcb_text = (
                    f"\n<b>Риск ЦБ РФ:</b>\n"
                    f"{emoji} {risk_name}\n"
                )
                if company.cbr_risk_facts:
                    danger_count = len(company.cbr_risk_facts.get('danger', []))
                    warning_count = len(company.cbr_risk_facts.get('warning', []))
                    if danger_count > 0:
                        zcb_text += f"🔴 Критических факторов: {danger_count}\n"
                    if warning_count > 0:
                        zcb_text += f"🟡 Предупреждений: {warning_count}\n"
                if company.cbr_checked_at:
                    zcb_text += f"🕐 Проверено: {company.cbr_checked_at.strftime('%d.%m.%Y %H:%M')}\n"
            elif company.ogrn:
                zcb_text = "\n🎨 Риск ЦБ РФ: ⚪ Не проверен\n"

            await callback.message.edit_text(
                f"🏢 <b>{company.name}</b>\n\n"
                f"🔢 ИНН: <code>{company.inn}</code>\n"
                f"🔢 ОГРН: <code>{company.ogrn or '—'}</code>\n"
                f"📊 Статус: {'✅ Активна' if company.is_active else '❌ Неактивна'}\n"
                f"{zcb_text}\n"
                f"<b>Лимиты:</b>\n"
                f"📅 Дневной: {company.current_daily_used:,.0f} / {company.daily_limit:,.0f}₽ (осталось {daily_left:,.0f}₽)\n"
                f"📆 Недельный: {company.current_weekly_used:,.0f} / {company.weekly_limit:,.0f}₽\n"
                f"🗓️ Месячный: {company.current_monthly_used:,.0f} / {company.monthly_limit:,.0f}₽",
                reply_markup=self.kb.company_actions(
                    company.id,
                    company.is_active,
                    has_signature=bool(company.signature_image_path),
                    has_stamp=bool(company.stamp_image_path)
                ),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        company_id = int(parts[-1])

        # Редактирование названия
        if action == "edit" and parts[1] == "name":
            await state.set_state(AdminStates.editing_company_name)
            await state.update_data(editing_company_id=company_id)
            await callback.message.edit_text(
                "✏️ Введите новое название компании:",
                reply_markup=self.kb.cancel_input()
            )
            await callback.answer()

        # Редактирование ИНН
        elif action == "edit" and parts[1] == "inn":
            await state.set_state(AdminStates.editing_company_inn)
            await state.update_data(editing_company_id=company_id)
            await callback.message.edit_text(
                "✏️ Введите новый ИНН:",
                reply_markup=self.kb.cancel_input()
            )
            await callback.answer()

        # Редактирование ФИО директора
        elif action == "edit" and parts[1] == "director":
            await state.set_state(AdminStates.editing_company_director_name)
            await state.update_data(editing_company_id=company_id)
            company = await self.company_repo.get_by_id(company_id)
            current_name = company.director_name or "не указано"
            await callback.message.edit_text(
                f"👤 <b>ФИО руководителя</b>\n\n"
                f"Текущее: {current_name}\n\n"
                f"Введите полное ФИО руководителя (минимум фамилия и имя):\n"
                f"Например: <i>Иванов Иван Петрович</i>\n\n"
                f"Бот автоматически преобразует в формат: <b>Иванов И.П.</b>",
                reply_markup=self.kb.cancel_input(),
                parse_mode="HTML"
            )
            await callback.answer()

        # Меню лимитов
        elif action == "limits":
            await callback.message.edit_text(
                "💰 <b>Изменение лимитов</b>\n\nВыберите тип лимита:",
                reply_markup=self.kb.company_limits_menu(company_id),
                parse_mode="HTML"
            )
            await callback.answer()

        # Банковские счета
        elif action == "banks":
            await self.cb_company_banks(callback, state, db_user)

        elif action == "add_bank":
            await self.cb_company_add_bank(callback, state, db_user)

        elif action == "select_bank":
            await self.cb_company_select_bank(callback, state, db_user)

        elif action == "bank":
            await self.cb_company_bank_view(callback, state, db_user)

        elif action == "edit_account":
            await self.cb_company_edit_account(callback, state, db_user)

        elif action == "set_preferred":
            await self.cb_company_set_preferred(callback, state, db_user)

        elif action == "unlink_bank":
            await self.cb_company_unlink_bank(callback, state, db_user)

        # Изменение конкретного лимита
        elif action == "limit":
            limit_type = parts[1]
            await state.set_state(AdminStates.editing_company_limit)
            await state.update_data(editing_company_id=company_id, limit_type=limit_type)

            limit_names = {'daily': 'дневной', 'weekly': 'недельный', 'monthly': 'месячный'}
            await callback.message.edit_text(
                f"💰 Введите новый {limit_names[limit_type]} лимит (в рублях):",
                reply_markup=self.kb.cancel_input()
            )
            await callback.answer()

        # Сброс использования
        elif action == "reset":
            await self.company_repo.update_by_id(
                company_id,
                current_daily_used=0,
                current_weekly_used=0,
                current_monthly_used=0
            )
            await callback.answer("✅ Использование сброшено!", show_alert=True)
            company = await self.company_repo.get_by_id(company_id)
            # Обновляем сообщение
            await self.cb_company_action(callback, state, db_user)

        # Деактивация
        elif action == "deactivate":
            await self.company_repo.update_by_id(company_id, is_active=False)
            await callback.answer("🚫 Компания деактивирована")
            company = await self.company_repo.get_by_id(company_id)
            await callback.message.edit_reply_markup(
                reply_markup=self.kb.company_actions(
                    company_id,
                    False,
                    has_signature=bool(company.signature_image_path),
                    has_stamp=bool(company.stamp_image_path)
                )
            )

        # Активация
        elif action == "activate":
            await self.company_repo.update_by_id(company_id, is_active=True)
            await callback.answer("✅ Компания активирована")
            company = await self.company_repo.get_by_id(company_id)
            await callback.message.edit_reply_markup(
                reply_markup=self.kb.company_actions(
                    company_id,
                    True,
                    has_signature=bool(company.signature_image_path),
                    has_stamp=bool(company.stamp_image_path)
                )
            )

        # Удаление
        elif action == "delete":
            company = await self.company_repo.get_by_id(company_id)
            await callback.message.edit_text(
                f"🗑️ <b>Удаление компании</b>\n\n"
                f"Вы уверены, что хотите удалить?\n"
                f"🏢 {company.name}",
                reply_markup=self.kb.confirm_action("delete", "company", company_id),
                parse_mode="HTML"
            )
            await callback.answer()

        elif action == "confirm_delete":
            # Обнуляем ссылки на компанию в заявках перед удалением
            await self.application_repo.clear_company(company_id)
            await self.company_repo.delete_by_id(company_id)
            await callback.message.edit_text(
                "✅ Компания удалена",
                reply_markup=self.kb.back_to_menu()
            )
            await callback.answer()

        # Загрузка подписи
        elif action == "upload_signature":
            await state.set_state(AdminStates.waiting_company_signature)
            await state.update_data(company_id=company_id)
            await callback.message.answer(
                "📤 <b>Загрузка подписи</b>\n\n"
                "Отправьте файл PNG с подписью (росчерк).\n\n"
                "⚠️ Требования:\n"
                "• Формат: PNG\n"
                "• Размер: до 5 МБ\n"
                "• Отправить как ДОКУМЕНТ (📎), не как фото!\n"
                "• Рекомендуемая ширина: 2 см",
                reply_markup=self.kb.back_to_menu(),
                parse_mode="HTML"
            )
            await callback.answer()

        # Загрузка печати
        elif action == "upload_stamp":
            await state.set_state(AdminStates.waiting_company_stamp)
            await state.update_data(company_id=company_id)
            await callback.message.answer(
                "📤 <b>Загрузка печати</b>\n\n"
                "Отправьте файл PNG с круглой печатью компании.\n\n"
                "⚠️ Требования:\n"
                "• Формат: PNG\n"
                "• Размер: до 5 МБ\n"
                "• Отправить как ДОКУМЕНТ (📎), не как фото!\n"
                "• Рекомендуемый диаметр: 4 см",
                reply_markup=self.kb.back_to_menu(),
                parse_mode="HTML"
            )
            await callback.answer()

        # Просмотр подписи
        elif action == "view_signature":
            company = await self.company_repo.get_by_id(company_id)
            if not company.signature_image_path:
                await callback.answer("❌ Подпись не загружена", show_alert=True)
                return

            try:
                from aiogram.types import FSInputFile
                photo = FSInputFile(company.signature_image_path)
                await callback.message.answer_photo(
                    photo=photo,
                    caption=f"🖼️ Подпись и печать\n🏢 {company.name}"
                )
                await callback.answer()
            except Exception as e:
                await callback.answer(f"❌ Ошибка загрузки: {e}", show_alert=True)

        # Удаление подписи
        elif action == "delete_signature":
            company = await self.company_repo.get_by_id(company_id)
            if company.signature_image_path:
                import os
                # Удаляем файл
                if os.path.exists(company.signature_image_path):
                    os.remove(company.signature_image_path)
                # Обнуляем путь в БД
                await self.company_repo.update_by_id(company_id, signature_image_path=None)
                await callback.answer("✅ Подпись удалена")
                # Обновляем клавиатуру
                company = await self.company_repo.get_by_id(company_id)
                await callback.message.edit_reply_markup(
                    reply_markup=self.kb.company_actions(
                        company_id,
                        company.is_active,
                        has_signature=False,
                        has_stamp=bool(company.stamp_image_path)
                    )
                )
            else:
                await callback.answer("❌ Подпись не загружена", show_alert=True)

        # Просмотр печати
        elif action == "view_stamp":
            company = await self.company_repo.get_by_id(company_id)
            if not company.stamp_image_path:
                await callback.answer("❌ Печать не загружена", show_alert=True)
                return

            try:
                from aiogram.types import FSInputFile
                photo = FSInputFile(company.stamp_image_path)
                await callback.message.answer_photo(
                    photo=photo,
                    caption=f"🖼️ Печать\n🏢 {company.name}"
                )
                await callback.answer()
            except Exception as e:
                await callback.answer(f"❌ Ошибка загрузки: {e}", show_alert=True)

        # Удаление печати
        elif action == "delete_stamp":
            company = await self.company_repo.get_by_id(company_id)
            if company.stamp_image_path:
                import os
                # Удаляем файл
                if os.path.exists(company.stamp_image_path):
                    os.remove(company.stamp_image_path)
                # Обнуляем путь в БД
                await self.company_repo.update_by_id(company_id, stamp_image_path=None)
                await callback.answer("✅ Печать удалена")
                # Обновляем клавиатуру
                company = await self.company_repo.get_by_id(company_id)
                await callback.message.edit_reply_markup(
                    reply_markup=self.kb.company_actions(
                        company_id,
                        company.is_active,
                        has_signature=bool(company.signature_image_path),
                        has_stamp=False
                    )
                )
            else:
                await callback.answer("❌ Печать не загружена", show_alert=True)

    async def process_edit_company_name(self, message: Message, state: FSMContext, db_user):
        """Редактирование названия компании"""
        data = await state.get_data()
        company_id = data['editing_company_id']
        new_name = message.text.strip()

        await self.company_repo.update_by_id(company_id, name=new_name)
        await state.clear()

        await message.answer(
            f"✅ Название изменено на: <b>{new_name}</b>",
            reply_markup=self.kb.back_to_menu(),
            parse_mode="HTML"
        )

    async def process_edit_company_inn(self, message: Message, state: FSMContext, db_user):
        """Редактирование ИНН компании"""
        inn = message.text.strip()
        if not inn.isdigit() or len(inn) not in [10, 12]:
            await message.answer("❌ ИНН должен содержать 10 или 12 цифр.")
            return

        data = await state.get_data()
        company_id = data['editing_company_id']

        await self.company_repo.update_by_id(company_id, inn=inn)
        await state.clear()

        await message.answer(
            f"✅ ИНН изменён на: <b>{inn}</b>",
            reply_markup=self.kb.back_to_menu(),
            parse_mode="HTML"
        )

    @staticmethod
    def format_full_name_to_initials(full_name: str) -> str:
        """
        Преобразует полное ФИО в формат 'Фамилия И.О.'
        Пример: 'Иванов Иван Петрович' -> 'Иванов И.П.'
        """
        parts = full_name.strip().split()
        if len(parts) < 2:
            return full_name  # Если меньше 2 частей, вернуть как есть

        surname = parts[0]
        name = parts[1]
        patronymic = parts[2] if len(parts) > 2 else None

        if patronymic:
            return f"{surname} {name[0].upper()}.{patronymic[0].upper()}."
        else:
            return f"{surname} {name[0].upper()}."

    async def process_edit_company_director_name(self, message: Message, state: FSMContext, db_user):
        """Редактирование ФИО директора компании"""
        full_name = message.text.strip()

        # Проверка: минимум 2 слова (фамилия + имя)
        parts = full_name.split()
        if len(parts) < 2:
            await message.answer(
                "❌ Введите минимум фамилию и имя.\n"
                "Например: <i>Иванов Иван</i> или <i>Иванов Иван Петрович</i>",
                parse_mode="HTML"
            )
            return

        # Преобразуем в формат "Фамилия И.О."
        formatted_name = self.format_full_name_to_initials(full_name)

        data = await state.get_data()
        company_id = data['editing_company_id']

        await self.company_repo.update_by_id(company_id, director_name=formatted_name)
        await state.clear()

        await message.answer(
            f"✅ <b>ФИО руководителя сохранено:</b>\n\n"
            f"Вы ввели: <i>{full_name}</i>\n"
            f"На счёте будет: <b>{formatted_name}</b>",
            reply_markup=self.kb.back_to_menu(),
            parse_mode="HTML"
        )

    async def process_edit_company_limit(self, message: Message, state: FSMContext, db_user):
        """Редактирование лимита компании"""
        try:
            limit = Decimal(message.text.strip().replace(" ", "").replace(",", ""))
            if limit < 0:
                raise ValueError()
        except:
            await message.answer("❌ Введите корректное число.")
            return

        data = await state.get_data()
        company_id = data['editing_company_id']
        limit_type = data['limit_type']

        field_map = {
            'daily': 'daily_limit',
            'weekly': 'weekly_limit',
            'monthly': 'monthly_limit'
        }

        await self.company_repo.update_by_id(company_id, **{field_map[limit_type]: limit})
        await state.clear()

        await message.answer(
            f"✅ Лимит изменён: <b>{limit:,.0f}₽</b>",
            reply_markup=self.kb.back_to_menu(),
            parse_mode="HTML"
        )

    async def process_company_signature(self, message: Message, state: FSMContext, db_user):
        """Обработка загруженной подписи"""
        import os
        from pathlib import Path

        # Проверяем что это документ
        if not message.document:
            await message.answer("❌ Пожалуйста, отправьте файл как документ (не как фото)")
            return

        document = message.document

        # Проверяем что это PNG
        if not document.file_name.lower().endswith('.png'):
            await message.answer("❌ Файл должен быть в формате PNG")
            return

        # Получаем company_id из состояния
        data = await state.get_data()
        company_id = data.get('company_id')

        if not company_id:
            await message.answer("❌ Ошибка: не найден ID компании")
            await state.clear()
            return

        # Проверяем размер (5 МБ = 5242880 байт)
        if document.file_size > 5242880:
            await message.answer("❌ Файл слишком большой. Максимум 5 МБ.")
            return

        try:
            # Создаем папку для подписей если не существует
            # Используем абсолютный путь относительно корня проекта (/app в Docker)
            import os
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))  # /app
            signatures_dir = Path(base_dir) / "documents" / "signatures"
            signatures_dir.mkdir(parents=True, exist_ok=True)

            # Формируем путь к файлу
            file_path = signatures_dir / f"company_{company_id}_signature.png"

            # Скачиваем файл
            file = await message.bot.get_file(document.file_id)
            await message.bot.download_file(file.file_path, file_path)

            # Сохраняем путь в БД
            await self.company_repo.update_by_id(
                company_id,
                signature_image_path=str(file_path)
            )

            await state.clear()

            await message.answer(
                "✅ <b>Подпись загружена!</b>\n\n"
                "Теперь она будет автоматически добавляться в счета.",
                reply_markup=self.kb.back_to_menu(),
                parse_mode="HTML"
            )

        except Exception as e:
            await message.answer(f"❌ Ошибка при загрузке: {e}")
            await state.clear()

    async def process_company_stamp(self, message: Message, state: FSMContext, db_user):
        """Обработка загруженной печати"""
        import os
        from pathlib import Path

        # Проверяем что это документ
        if not message.document:
            await message.answer("❌ Пожалуйста, отправьте файл как документ (не как фото)")
            return

        document = message.document

        # Проверяем что это PNG
        if not document.file_name.lower().endswith('.png'):
            await message.answer("❌ Файл должен быть в формате PNG")
            return

        # Получаем company_id из состояния
        data = await state.get_data()
        company_id = data.get('company_id')

        if not company_id:
            await message.answer("❌ Ошибка: не найден ID компании")
            await state.clear()
            return

        # Проверяем размер (5 МБ = 5242880 байт)
        if document.file_size > 5242880:
            await message.answer("❌ Файл слишком большой. Максимум 5 МБ.")
            return

        try:
            # Создаем папку для печатей если не существует
            # Используем абсолютный путь относительно корня проекта (/app в Docker)
            import os
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))  # /app
            stamps_dir = Path(base_dir) / "documents" / "stamps"
            stamps_dir.mkdir(parents=True, exist_ok=True)

            # Формируем путь к файлу
            file_path = stamps_dir / f"company_{company_id}_stamp.png"

            # Скачиваем файл
            file = await message.bot.get_file(document.file_id)
            await message.bot.download_file(file.file_path, file_path)

            # Сохраняем путь в БД
            await self.company_repo.update_by_id(
                company_id,
                stamp_image_path=str(file_path)
            )

            await state.clear()

            await message.answer(
                "✅ <b>Печать загружена!</b>\n\n"
                "Теперь она будет автоматически добавляться в счета.",
                reply_markup=self.kb.back_to_menu(),
                parse_mode="HTML"
            )

        except Exception as e:
            await message.answer(f"❌ Ошибка при загрузке: {e}")
            await state.clear()

    # ==================== БАНКОВСКИЕ СЧЕТА КОМПАНИИ ====================

    async def cb_company_banks(self, callback: CallbackQuery, state: FSMContext, db_user):
        """Список банковских счетов компании"""
        company_id = int(callback.data.split(":")[-1])
        company = await self.company_repo.get_by_id(company_id)

        if not company:
            await callback.answer("Компания не найдена", show_alert=True)
            return

        company_banks = await self.company_repo.get_company_banks(company_id)

        await callback.message.edit_text(
            f"🏢 <b>{company.name}</b>\n\n"
            f"🏦 <b>Банковские счета</b>\n\n"
            f"Всего счетов: {len(company_banks)}\n"
            f"⭐ = основной счёт",
            reply_markup=self.kb.company_banks_list(company_id, company_banks),
            parse_mode="HTML"
        )
        await callback.answer()

    async def cb_company_add_bank(self, callback: CallbackQuery, state: FSMContext, db_user):
        """Показать список банков для привязки"""
        company_id = int(callback.data.split(":")[-1])

        # Получить все банки
        all_banks = await self.bank_repo.get_all()

        # Получить ID уже привязанных банков
        linked_bank_ids = await self.company_repo.get_banks(company_id)

        # Отфильтровать только непривязанные банки
        available_banks = [b for b in all_banks if b.id not in linked_bank_ids]

        if not available_banks:
            await callback.answer("Все банки уже привязаны к компании!", show_alert=True)
            return

        await callback.message.edit_text(
            "🏦 <b>Выберите банк для привязки:</b>",
            reply_markup=self.kb.select_bank_for_company(company_id, available_banks),
            parse_mode="HTML"
        )
        await callback.answer()

    async def cb_company_select_bank(self, callback: CallbackQuery, state: FSMContext, db_user):
        """Банк выбран, запросить номер счёта"""
        parts = callback.data.split(":")
        bank_id = int(parts[-2])
        company_id = int(parts[-1])

        bank = await self.bank_repo.get_by_id(bank_id)

        await state.set_state(AdminStates.waiting_company_bank_account)
        await state.update_data(
            linking_company_id=company_id,
            linking_bank_id=bank_id,
            linking_bank_name=bank.name
        )

        await callback.message.edit_text(
            f"🏦 <b>{bank.name}</b>\n\n"
            f"Введите номер расчётного счёта (20 цифр):\n"
            f"<i>Например: 40702810500000012345</i>",
            reply_markup=self.kb.cancel_input(),
            parse_mode="HTML"
        )
        await callback.answer()

    async def process_company_bank_account(self, message: Message, state: FSMContext, db_user):
        """Обработка ввода номера счёта при привязке банка"""
        account = message.text.strip().replace(" ", "")

        if not account.isdigit() or len(account) != 20:
            await message.answer(
                "❌ Номер счёта должен содержать 20 цифр.",
                reply_markup=self.kb.cancel_input()
            )
            return

        data = await state.get_data()
        company_id = data['linking_company_id']
        bank_id = data['linking_bank_id']
        bank_name = data['linking_bank_name']

        await state.clear()

        # Проверить, есть ли уже счета у компании
        existing_banks = await self.company_repo.get_company_banks(company_id)
        is_first = len(existing_banks) == 0

        # Создать связь
        await self.company_repo.create_company_bank(
            company_id=company_id,
            bank_id=bank_id,
            account_number=account,
            is_preferred=is_first  # Первый счёт автоматически основной
        )

        await message.answer(
            f"✅ <b>Счёт добавлен!</b>\n\n"
            f"🏦 {bank_name}\n"
            f"💳 Счёт: <code>{account}</code>"
            + ("\n⭐ Установлен как основной" if is_first else ""),
            reply_markup=self.kb.back_to_menu(),
            parse_mode="HTML"
        )

    async def cb_company_bank_view(self, callback: CallbackQuery, state: FSMContext, db_user):
        """Просмотр конкретного счёта компании"""
        parts = callback.data.split(":")
        company_bank_id = int(parts[-2])
        company_id = int(parts[-1])

        company_bank = await self.company_repo.get_company_bank_by_id(company_bank_id)

        if not company_bank:
            await callback.answer("Счёт не найден", show_alert=True)
            return

        bank = company_bank.bank
        preferred_text = "⭐ Основной счёт" if company_bank.is_preferred else ""

        await callback.message.edit_text(
            f"🏦 <b>{bank.name}</b>\n\n"
            f"🔢 БИК: <code>{bank.bik or '—'}</code>\n"
            f"💳 Корр. счёт: <code>{bank.corr_account or '—'}</code>\n"
            f"💳 Р/счёт: <code>{company_bank.account_number or '—'}</code>\n"
            f"{preferred_text}",
            reply_markup=self.kb.company_bank_actions(company_bank_id, company_id, company_bank.is_preferred),
            parse_mode="HTML"
        )
        await callback.answer()

    async def cb_company_edit_account(self, callback: CallbackQuery, state: FSMContext, db_user):
        """Редактирование номера счёта"""
        parts = callback.data.split(":")
        company_bank_id = int(parts[-2])
        company_id = int(parts[-1])

        await state.set_state(AdminStates.editing_company_bank_account)
        await state.update_data(
            editing_company_bank_id=company_bank_id,
            editing_company_id=company_id
        )

        await callback.message.edit_text(
            "✏️ Введите новый номер счёта (20 цифр):",
            reply_markup=self.kb.cancel_input()
        )
        await callback.answer()

    async def process_edit_company_bank_account(self, message: Message, state: FSMContext, db_user):
        """Обработка нового номера счёта"""
        account = message.text.strip().replace(" ", "")

        if not account.isdigit() or len(account) != 20:
            await message.answer(
                "❌ Номер счёта должен содержать 20 цифр.",
                reply_markup=self.kb.cancel_input()
            )
            return

        data = await state.get_data()
        company_bank_id = data['editing_company_bank_id']

        await state.clear()

        await self.company_repo.update_company_bank(company_bank_id, account_number=account)

        await message.answer(
            f"✅ Номер счёта изменён: <code>{account}</code>",
            reply_markup=self.kb.back_to_menu(),
            parse_mode="HTML"
        )

    async def cb_company_set_preferred(self, callback: CallbackQuery, state: FSMContext, db_user):
        """Установить счёт как основной"""
        parts = callback.data.split(":")
        company_bank_id = int(parts[-2])
        company_id = int(parts[-1])

        await self.company_repo.set_preferred_bank(company_id, company_bank_id)

        await callback.answer("✅ Счёт установлен как основной", show_alert=True)

        # Обновить отображение
        company_bank = await self.company_repo.get_company_bank_by_id(company_bank_id)
        bank = company_bank.bank

        await callback.message.edit_text(
            f"🏦 <b>{bank.name}</b>\n\n"
            f"🔢 БИК: <code>{bank.bik or '—'}</code>\n"
            f"💳 Корр. счёт: <code>{bank.corr_account or '—'}</code>\n"
            f"💳 Р/счёт: <code>{company_bank.account_number or '—'}</code>\n"
            f"⭐ Основной счёт",
            reply_markup=self.kb.company_bank_actions(company_bank_id, company_id, True),
            parse_mode="HTML"
        )

    async def cb_company_unlink_bank(self, callback: CallbackQuery, state: FSMContext, db_user):
        """Отвязать банк от компании"""
        parts = callback.data.split(":")
        company_bank_id = int(parts[-2])
        company_id = int(parts[-1])

        await self.company_repo.delete_company_bank(company_bank_id)

        await callback.answer("✅ Счёт удалён", show_alert=True)

        # Вернуться к списку счетов
        company_banks = await self.company_repo.get_company_banks(company_id)
        company = await self.company_repo.get_by_id(company_id)

        await callback.message.edit_text(
            f"🏢 <b>{company.name}</b>\n\n"
            f"🏦 <b>Банковские счета</b>\n\n"
            f"Всего счетов: {len(company_banks)}\n"
            f"⭐ = основной счёт",
            reply_markup=self.kb.company_banks_list(company_id, company_banks),
            parse_mode="HTML"
        )

    # ==================== БАНКИ ====================

    async def cb_banks_menu(self, callback: CallbackQuery, db_user):
        """Меню банков"""
        await callback.message.edit_text(
            "🏦 <b>Управление банками</b>\n\n"
            "Выберите действие:",
            reply_markup=self.kb.banks_menu(),
            parse_mode="HTML"
        )
        await callback.answer()

    async def cb_banks_list(self, callback: CallbackQuery, db_user):
        """Список банков"""
        banks = await self.bank_repo.get_all()

        if not banks:
            await callback.message.edit_text(
                "🏦 <b>Банки</b>\n\nСписок пуст.",
                reply_markup=self.kb.banks_menu(),
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                f"🏦 <b>Банки</b> ({len(banks)})\n\n"
                "✅ = активен, 🟢 = принимает заявки\n"
                "Выберите банк:",
                reply_markup=self.kb.banks_list(banks),
                parse_mode="HTML"
            )
        await callback.answer()

    async def cb_banks_page(self, callback: CallbackQuery, db_user):
        """Пагинация банков"""
        page = int(callback.data.split(":")[-1])
        banks = await self.bank_repo.get_all()
        await callback.message.edit_reply_markup(
            reply_markup=self.kb.banks_list(banks, page)
        )
        await callback.answer()

    async def cb_banks_add(self, callback: CallbackQuery, state: FSMContext, db_user):
        """Добавление банка — начинаем с названия"""
        await state.set_state(AdminStates.waiting_bank_name)
        await callback.message.edit_text(
            "🏦 <b>Добавление банка</b>\n\n"
            "Введите название банка:",
            reply_markup=self.kb.cancel_input(),
            parse_mode="HTML"
        )
        await callback.answer()

    async def process_bank_name(self, message: Message, state: FSMContext, db_user):
        """Обработка названия банка"""
        name = message.text.strip()
        if len(name) < 2:
            await message.answer("❌ Название слишком короткое.")
            return

        await state.update_data(bank_name=name)
        await state.set_state(AdminStates.waiting_bank_bik)

        await message.answer(
            f"✅ Название: <b>{name}</b>\n\n"
            "Введите БИК банка (9 цифр):\n"
            "<i>Например: 044525225</i>",
            reply_markup=self.kb.cancel_input(),
            parse_mode="HTML"
        )

    async def process_bank_bik(self, message: Message, state: FSMContext, db_user):
        """Обработка БИК банка"""
        bik = message.text.strip().replace(" ", "")
        if not bik.isdigit() or len(bik) != 9:
            await message.answer("❌ БИК должен содержать 9 цифр.")
            return

        await state.update_data(bank_bik=bik)
        await state.set_state(AdminStates.waiting_bank_corr_account)

        await message.answer(
            f"✅ БИК: <b>{bik}</b>\n\n"
            "Введите корреспондентский счёт банка (20 цифр):\n"
            "<i>Например: 30101810400000000225</i>",
            reply_markup=self.kb.cancel_input(),
            parse_mode="HTML"
        )

    async def process_bank_corr_account(self, message: Message, state: FSMContext, db_user):
        """Обработка корр. счёта банка"""
        corr = message.text.strip().replace(" ", "")
        if not corr.isdigit() or len(corr) != 20:
            await message.answer("❌ Корр. счёт должен содержать 20 цифр.")
            return

        await state.update_data(bank_corr_account=corr)
        await state.set_state(AdminStates.waiting_bank_daily_limit)

        await message.answer(
            f"✅ Корр. счёт: <b>{corr}</b>\n\n"
            "Введите дневной лимит (в рублях):\n"
            "<i>Например: 10000000</i>",
            reply_markup=self.kb.cancel_input(),
            parse_mode="HTML"
        )

    async def process_bank_daily_limit(self, message: Message, state: FSMContext, db_user):
        """Обработка дневного лимита банка — создание банка без chat_id"""
        try:
            limit = Decimal(message.text.strip().replace(" ", "").replace(",", ""))
            if limit < 0:
                raise ValueError()
        except:
            await message.answer("❌ Введите корректное число.")
            return

        data = await state.get_data()
        await state.clear()

        # Создаём банк БЕЗ chat_id
        bank = await self.bank_repo.create(
            name=data['bank_name'],
            bik=data.get('bank_bik'),
            corr_account=data.get('bank_corr_account'),
            daily_limit=limit,
            weekly_limit=limit * 5
        )

        await message.answer(
            f"✅ <b>Банк создан!</b>\n\n"
            f"🏦 {bank.name}\n"
            f"🔢 БИК: {bank.bik or '—'}\n"
            f"💳 Корр. счёт: {bank.corr_account or '—'}\n"
            f"💰 Дневной лимит: {bank.daily_limit:,.0f}₽\n\n"
            f"💬 Группа не привязана.\n"
            f"Для привязки группы перейдите в настройки банка.",
            reply_markup=self.kb.bank_actions(bank.id, bank.is_active, bank.is_available, has_chat=False),
            parse_mode="HTML"
        )

    async def cb_bank_action(self, callback: CallbackQuery, state: FSMContext, db_user):
        """Обработка действий с банком"""
        data = callback.data.replace("admin:bank:", "")
        parts = data.split(":")

        action = parts[0]

        # Просмотр банка
        if action.isdigit():
            bank_id = int(action)
            bank = await self.bank_repo.get_by_id(bank_id)
            if not bank:
                await callback.answer("Банк не найден", show_alert=True)
                return

            daily_left = bank.daily_limit - bank.current_daily_used
            has_chat = bank.chat_id is not None

            chat_info = f"💬 Chat ID: <code>{bank.chat_id}</code>" if has_chat else "💬 Группа: <i>Не привязана</i>"

            # Подсчёт сотрудников
            employees = await self.user_repo.get_by_bank_id(bank_id)
            emp_count = len(employees)

            await callback.message.edit_text(
                f"🏦 <b>{bank.name}</b>\n\n"
                f"🔢 БИК: {bank.bik or '—'}\n"
                f"💳 Корр. счёт: {bank.corr_account or '—'}\n\n"
                f"{chat_info}\n"
                f"👥 Сотрудников: {emp_count}\n"
                f"⚡ Приоритет: {bank.priority}\n"
                f"📊 Статус: {'✅ Активен' if bank.is_active else '❌ Неактивен'}\n"
                f"🚦 Приём заявок: {'🟢 Открыт' if bank.is_available else '🔴 Закрыт'}\n\n"
                f"<b>Лимиты:</b>\n"
                f"📅 Дневной: {bank.current_daily_used:,.0f} / {bank.daily_limit:,.0f}₽ (осталось {daily_left:,.0f}₽)\n"
                f"📆 Недельный: {bank.current_weekly_used:,.0f} / {bank.weekly_limit:,.0f}₽",
                reply_markup=self.kb.bank_actions(bank.id, bank.is_active, bank.is_available, has_chat),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        bank_id = int(parts[-1])

        # Привязка группы
        if action == "link":
            bot_info = await callback.bot.get_me()
            bot_username = bot_info.username

            await state.set_state(AdminStates.waiting_group_code)
            await state.update_data(linking_bank_id=bank_id)

            await callback.message.edit_text(
                "💬 <b>Привязка группы</b>\n\n"
                "1. Нажмите кнопку ниже, чтобы добавить бота в группу банка\n"
                "2. Бот напишет в группу <b>код подтверждения</b>\n"
                "3. Скопируйте код и отправьте его сюда\n\n"
                "<i>Бот будет добавлен с правами администратора "
                "(отправка и редактирование сообщений)</i>",
                reply_markup=self.kb.link_group_button(bot_username),
                parse_mode="HTML"
            )
            await callback.answer()

        # Отвязка группы
        elif action == "unlink":
            await self.bank_repo.update_by_id(bank_id, chat_id=None)
            bank = await self.bank_repo.get_by_id(bank_id)
            await callback.answer("✅ Группа отвязана", show_alert=True)
            await callback.message.edit_reply_markup(
                reply_markup=self.kb.bank_actions(bank_id, bank.is_active, bank.is_available, has_chat=False)
            )

        # Редактирование названия
        elif action == "edit" and parts[1] == "name":
            await state.set_state(AdminStates.editing_bank_name)
            await state.update_data(editing_bank_id=bank_id)
            await callback.message.edit_text(
                "✏️ Введите новое название банка:",
                reply_markup=self.kb.cancel_input()
            )
            await callback.answer()

        # Редактирование приоритета
        elif action == "edit" and parts[1] == "priority":
            await state.set_state(AdminStates.editing_bank_priority)
            await state.update_data(editing_bank_id=bank_id)
            await callback.message.edit_text(
                "⚡ Введите приоритет (число, чем меньше - тем выше приоритет):\n"
                "<i>Например: 1, 10, 100</i>",
                reply_markup=self.kb.cancel_input(),
                parse_mode="HTML"
            )
            await callback.answer()

        # Меню лимитов
        elif action == "limits":
            await callback.message.edit_text(
                "💰 <b>Изменение лимитов</b>\n\nВыберите тип лимита:",
                reply_markup=self.kb.bank_limits_menu(bank_id),
                parse_mode="HTML"
            )
            await callback.answer()

        # Изменение конкретного лимита
        elif action == "limit":
            limit_type = parts[1]
            await state.set_state(AdminStates.editing_bank_limit)
            await state.update_data(editing_bank_id=bank_id, limit_type=limit_type)

            limit_names = {'daily': 'дневной', 'weekly': 'недельный'}
            await callback.message.edit_text(
                f"💰 Введите новый {limit_names[limit_type]} лимит (в рублях):",
                reply_markup=self.kb.cancel_input()
            )
            await callback.answer()

        # Сброс использования
        elif action == "reset":
            await self.bank_repo.update_by_id(
                bank_id,
                current_daily_used=0,
                current_weekly_used=0
            )
            await callback.answer("✅ Использование сброшено!", show_alert=True)

        # Приостановить/возобновить приём
        elif action == "unavailable":
            await self.bank_repo.update_by_id(bank_id, is_available=False)
            await callback.answer("⏸️ Приём заявок приостановлен")
            bank = await self.bank_repo.get_by_id(bank_id)
            await callback.message.edit_reply_markup(
                reply_markup=self.kb.bank_actions(bank_id, bank.is_active, False, has_chat=bank.chat_id is not None)
            )

        elif action == "available":
            await self.bank_repo.update_by_id(bank_id, is_available=True)
            await callback.answer("▶️ Приём заявок возобновлён")
            bank = await self.bank_repo.get_by_id(bank_id)
            await callback.message.edit_reply_markup(
                reply_markup=self.kb.bank_actions(bank_id, bank.is_active, True, has_chat=bank.chat_id is not None)
            )

        # Деактивация
        elif action == "deactivate":
            await self.bank_repo.update_by_id(bank_id, is_active=False)
            await callback.answer("🚫 Банк деактивирован")
            bank = await self.bank_repo.get_by_id(bank_id)
            await callback.message.edit_reply_markup(
                reply_markup=self.kb.bank_actions(bank_id, False, bank.is_available, has_chat=bank.chat_id is not None)
            )

        # Активация
        elif action == "activate":
            await self.bank_repo.update_by_id(bank_id, is_active=True)
            await callback.answer("✅ Банк активирован")
            bank = await self.bank_repo.get_by_id(bank_id)
            await callback.message.edit_reply_markup(
                reply_markup=self.kb.bank_actions(bank_id, True, bank.is_available, has_chat=bank.chat_id is not None)
            )

        # Удаление
        elif action == "delete":
            bank = await self.bank_repo.get_by_id(bank_id)
            await callback.message.edit_text(
                f"🗑️ <b>Удаление банка</b>\n\n"
                f"Вы уверены, что хотите удалить?\n"
                f"🏦 {bank.name}",
                reply_markup=self.kb.confirm_action("delete", "bank", bank_id),
                parse_mode="HTML"
            )
            await callback.answer()

        elif action == "confirm_delete":
            # Обнуляем ссылки на банк в заявках перед удалением
            await self.application_repo.clear_bank(bank_id)
            await self.bank_repo.delete_by_id(bank_id)
            await callback.message.edit_text(
                "✅ Банк удалён",
                reply_markup=self.kb.back_to_menu()
            )
            await callback.answer()

    async def process_group_code(self, message: Message, state: FSMContext, db_user):
        """Обработка кода подтверждения группы"""
        code = message.text.strip().upper()

        if code not in self.pending_group_codes:
            await message.answer(
                "❌ Неверный код.\n\n"
                "Убедитесь, что бот добавлен в группу и отправьте код, "
                "который он написал в чат группы.",
                reply_markup=self.kb.cancel_input()
            )
            return

        code_data = self.pending_group_codes.pop(code)
        chat_id = code_data['chat_id']
        chat_title = code_data.get('chat_title', '')

        fsm_data = await state.get_data()
        bank_id = fsm_data.get('linking_bank_id')

        if not bank_id:
            await state.clear()
            await message.answer(
                "❌ Ошибка: данные о банке потеряны. Попробуйте заново.",
                reply_markup=self.kb.back_to_menu()
            )
            return

        # Проверяем, не привязан ли этот chat_id к другому банку
        existing_bank = await self.bank_repo.get_by_chat_id(chat_id)
        if existing_bank and existing_bank.id != bank_id:
            await message.answer(
                f"❌ Эта группа уже привязана к банку <b>{existing_bank.name}</b>!\n"
                f"Сначала отвяжите группу от другого банка.",
                reply_markup=self.kb.back_to_menu(),
                parse_mode="HTML"
            )
            await state.clear()
            return

        # Привязываем группу к банку
        await self.bank_repo.update_by_id(bank_id, chat_id=chat_id)
        await state.clear()

        bank = await self.bank_repo.get_by_id(bank_id)
        title_info = f" ({chat_title})" if chat_title else ""

        await message.answer(
            f"✅ <b>Группа привязана!</b>\n\n"
            f"🏦 Банк: {bank.name}\n"
            f"💬 Группа: <code>{chat_id}</code>{title_info}",
            reply_markup=self.kb.bank_actions(bank.id, bank.is_active, bank.is_available, has_chat=True),
            parse_mode="HTML"
        )

    async def process_edit_bank_name(self, message: Message, state: FSMContext, db_user):
        """Редактирование названия банка"""
        data = await state.get_data()
        bank_id = data['editing_bank_id']
        new_name = message.text.strip()

        await self.bank_repo.update_by_id(bank_id, name=new_name)
        await state.clear()

        await message.answer(
            f"✅ Название изменено на: <b>{new_name}</b>",
            reply_markup=self.kb.back_to_menu(),
            parse_mode="HTML"
        )

    async def process_edit_bank_priority(self, message: Message, state: FSMContext, db_user):
        """Редактирование приоритета банка"""
        try:
            priority = int(message.text.strip())
        except:
            await message.answer("❌ Введите целое число.")
            return

        data = await state.get_data()
        bank_id = data['editing_bank_id']

        await self.bank_repo.update_by_id(bank_id, priority=priority)
        await state.clear()

        await message.answer(
            f"✅ Приоритет изменён на: <b>{priority}</b>",
            reply_markup=self.kb.back_to_menu(),
            parse_mode="HTML"
        )

    async def process_edit_bank_limit(self, message: Message, state: FSMContext, db_user):
        """Редактирование лимита банка"""
        try:
            limit = Decimal(message.text.strip().replace(" ", "").replace(",", ""))
            if limit < 0:
                raise ValueError()
        except:
            await message.answer("❌ Введите корректное число.")
            return

        data = await state.get_data()
        bank_id = data['editing_bank_id']
        limit_type = data['limit_type']

        field_map = {'daily': 'daily_limit', 'weekly': 'weekly_limit'}

        await self.bank_repo.update_by_id(bank_id, **{field_map[limit_type]: limit})
        await state.clear()

        await message.answer(
            f"✅ Лимит изменён: <b>{limit:,.0f}₽</b>",
            reply_markup=self.kb.back_to_menu(),
            parse_mode="HTML"
        )

    # ==================== СТАТИСТИКА ====================

    async def cb_stats(self, callback: CallbackQuery, db_user):
        """Меню выбора статистики"""
        text = "📊 <b>Статистика</b>\n\n" \
               "Выберите раздел:"

        await callback.message.edit_text(
            text,
            reply_markup=self.kb.stats_menu(),
            parse_mode="HTML"
        )
        await callback.answer()

    async def cb_stats_system(self, callback: CallbackQuery, db_user):
        """Статистика системы"""
        today = date.today()

        # Получаем данные
        users = await self.user_repo.get_all()
        companies = await self.company_repo.get_all()
        banks = await self.bank_repo.get_all()
        daily_stats = await self.application_repo.get_daily_stats(today)

        # Подсчёт по ролям
        roles_count = {}
        for user in users:
            roles_count[user.role] = roles_count.get(user.role, 0) + 1

        # Статистика заявок
        total_apps = sum(s['count'] for s in daily_stats)
        total_amount = sum(s['total_amount'] for s in daily_stats)

        text = f"📊 <b>Статистика системы</b>\n\n"
        text += f"<b>Пользователи ({len(users)}):</b>\n"

        role_names = {
            'client': '👤 Клиенты',
            'manager': '👔 Менеджеры',
            'bank': '🏦 Банк',
            'accountant': '📊 Бухгалтеры',
            'supervisor': '👑 Супервайзеры',
            'admin': '⚙️ Админы'
        }
        for role, name in role_names.items():
            count = roles_count.get(role, 0)
            if count > 0:
                text += f"  {name}: {count}\n"

        text += f"\n<b>Компании:</b> {len(companies)}\n"
        active_companies = len([c for c in companies if c.is_active])
        text += f"  ✅ Активных: {active_companies}\n"

        text += f"\n<b>Банки:</b> {len(banks)}\n"
        active_banks = len([b for b in banks if b.is_active and b.is_available])
        text += f"  🟢 Принимают заявки: {active_banks}\n"

        text += f"\n<b>Заявки за сегодня:</b>\n"
        text += f"  📋 Всего: {total_apps}\n"
        text += f"  💰 Сумма: {total_amount:,.0f}₽\n"

        await callback.message.edit_text(
            text,
            reply_markup=self.kb.back_to_stats_menu(),
            parse_mode="HTML"
        )
        await callback.answer()

    async def cb_stats_today(self, callback: CallbackQuery, db_user):
        """Детальная статистика за сегодня"""
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
        await state.set_state(AdminStatsDateState.waiting_for_start_date)
        await callback.answer()

    async def cb_stats_payments(self, callback: CallbackQuery, db_user):
        """Статистика по оплатам"""
        today = date.today()
        from datetime import timedelta
        week_ago = today - timedelta(days=7)

        # Получаем заявки за последние 7 дней
        apps = await self.application_repo.get_applications_by_period(week_ago, today)

        # Подсчет по статусам оплаты
        payment_stats = {
            'invoice_sent': {'count': 0, 'amount': 0},
            'client_confirmed': {'count': 0, 'amount': 0},
            'payment_received': {'count': 0, 'amount': 0},
            'paid': {'count': 0, 'amount': 0}
        }

        for app in apps:
            if app.status in payment_stats:
                payment_stats[app.status]['count'] += 1
                payment_stats[app.status]['amount'] += float(app.amount)

        text = f"💳 <b>Статистика по оплатам</b>\n"
        text += f"<i>За последние 7 дней</i>\n\n"

        text += f"📨 <b>Счет отправлен клиенту:</b>\n"
        text += f"  Заявок: {payment_stats['invoice_sent']['count']}\n"
        text += f"  Сумма: {payment_stats['invoice_sent']['amount']:,.0f}₽\n\n"

        text += f"✅ <b>Клиент подтвердил оплату:</b>\n"
        text += f"  Заявок: {payment_stats['client_confirmed']['count']}\n"
        text += f"  Сумма: {payment_stats['client_confirmed']['amount']:,.0f}₽\n\n"

        text += f"💰 <b>Бухгалтер подтвердил получение:</b>\n"
        text += f"  Заявок: {payment_stats['payment_received']['count']}\n"
        text += f"  Сумма: {payment_stats['payment_received']['amount']:,.0f}₽\n\n"

        text += f"💵 <b>Оплачено:</b>\n"
        text += f"  Заявок: {payment_stats['paid']['count']}\n"
        text += f"  Сумма: {payment_stats['paid']['amount']:,.0f}₽\n"

        await callback.message.edit_text(
            text,
            reply_markup=self.kb.back_to_stats_menu(),
            parse_mode="HTML"
        )
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
            await state.set_state(AdminStatsDateState.waiting_for_end_date)
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
            stats = await self._get_detailed_stats(start_date, end_date)
            text = self._format_stats_text(start_date, end_date, stats)

            await message.answer(
                text,
                reply_markup=self.kb.admin_stats_detail_menu(start_date, end_date),
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
            reply_markup=self.kb.admin_stats_detail_menu(start_date, end_date),
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

        text = f"📊 <b>Детальная статистика за {period}</b>\n\n"
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
                'invoice_sent': '📨 Счет отправлен',
                'client_confirmed': '✅ Клиент подтвердил',
                'payment_received': '💰 Оплата получена',
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
            text += "<b>По клиентам (топ-30):</b>\n"
            if stats['by_client']:
                sorted_clients = sorted(stats['by_client'].items(), key=lambda x: x[1]['count'], reverse=True)[:30]
                for client_id, data in sorted_clients:
                    user = await self.user_repo.get_by_telegram_id(client_id)
                    client_name = user.username or f"ID {client_id}" if user else f"ID {client_id}"
                    text += f"  👤 @{client_name}: {data['count']} ({data['amount']:,.0f}₽)\n"
                if len(stats['by_client']) > 30:
                    text += f"\n  ... и еще {len(stats['by_client']) - 30} клиентов\n"
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
            reply_markup=self.kb.back_to_stats_menu(),
            parse_mode="HTML"
        )
        await callback.answer()
