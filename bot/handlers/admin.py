# bot/handlers/admin.py

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from decimal import Decimal
from datetime import date

from database import (
    UserRepository,
    CompanyRepository,
    BankRepository,
    ApplicationRepository,
    LogRepository
)
from keyboards.admin_kb import AdminKeyboards
from middleware import RoleRequiredMiddleware


class AdminStates(StatesGroup):
    """FSM состояния для админ-панели"""
    # Пользователи
    waiting_user_forward = State()  # Ожидание пересланного сообщения для добавления
    waiting_user_role = State()  # Ожидание выбора роли для нового пользователя

    # Компании
    waiting_company_name = State()
    waiting_company_inn = State()
    waiting_company_daily_limit = State()
    editing_company_name = State()
    editing_company_inn = State()
    editing_company_limit = State()

    # Банки
    waiting_bank_forward = State()  # Ожидание пересланного сообщения из чата банка
    waiting_bank_name = State()
    waiting_bank_daily_limit = State()
    editing_bank_name = State()
    editing_bank_priority = State()
    editing_bank_limit = State()


class AdminHandlers:
    """Хендлеры для администратора"""

    ALLOWED_ROLES = ['admin']

    def __init__(
            self,
            user_repo: UserRepository,
            company_repo: CompanyRepository,
            bank_repo: BankRepository,
            application_repo: ApplicationRepository,
            log_repo: LogRepository
    ):
        self.router = Router()
        self.user_repo = user_repo
        self.company_repo = company_repo
        self.bank_repo = bank_repo
        self.application_repo = application_repo
        self.log_repo = log_repo
        self.kb = AdminKeyboards()

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
        self.router.callback_query(F.data.startswith("admin:user:") & ~F.data.contains("confirm"))(self.cb_user_action)

        # FSM: добавление пользователя
        self.router.message(AdminStates.waiting_user_forward)(self.process_user_forward)

        # ===== КОМПАНИИ =====
        self.router.callback_query(F.data == "admin:companies")(self.cb_companies_menu)
        self.router.callback_query(F.data == "admin:companies:list")(self.cb_companies_list)
        self.router.callback_query(F.data.startswith("admin:companies:page:"))(self.cb_companies_page)
        self.router.callback_query(F.data == "admin:companies:add")(self.cb_companies_add)
        self.router.callback_query(F.data.startswith("admin:company:") & ~F.data.contains("confirm"))(self.cb_company_action)

        # FSM: компании
        self.router.message(AdminStates.waiting_company_name)(self.process_company_name)
        self.router.message(AdminStates.waiting_company_inn)(self.process_company_inn)
        self.router.message(AdminStates.waiting_company_daily_limit)(self.process_company_daily_limit)
        self.router.message(AdminStates.editing_company_name)(self.process_edit_company_name)
        self.router.message(AdminStates.editing_company_inn)(self.process_edit_company_inn)
        self.router.message(AdminStates.editing_company_limit)(self.process_edit_company_limit)

        # ===== БАНКИ =====
        self.router.callback_query(F.data == "admin:banks")(self.cb_banks_menu)
        self.router.callback_query(F.data == "admin:banks:list")(self.cb_banks_list)
        self.router.callback_query(F.data.startswith("admin:banks:page:"))(self.cb_banks_page)
        self.router.callback_query(F.data == "admin:banks:add")(self.cb_banks_add)
        self.router.callback_query(F.data.startswith("admin:bank:") & ~F.data.contains("confirm"))(self.cb_bank_action)

        # FSM: банки
        self.router.message(AdminStates.waiting_bank_forward)(self.process_bank_forward)
        self.router.message(AdminStates.waiting_bank_name)(self.process_bank_name)
        self.router.message(AdminStates.waiting_bank_daily_limit)(self.process_bank_daily_limit)
        self.router.message(AdminStates.editing_bank_name)(self.process_edit_bank_name)
        self.router.message(AdminStates.editing_bank_priority)(self.process_edit_bank_priority)
        self.router.message(AdminStates.editing_bank_limit)(self.process_edit_bank_limit)

        # Статистика
        self.router.callback_query(F.data == "admin:stats")(self.cb_stats)

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
                f"📊 Статус: {'✅ Активен' if user.is_active else '❌ Неактивен'}\n"
            )

            # Для сотрудников банка показываем привязку
            if user.role == 'bank':
                if user.bank_id:
                    bank = await self.bank_repo.get_by_id(user.bank_id)
                    text += f"🏦 Банк: <b>{bank.name if bank else '—'}</b>\n"
                else:
                    text += f"🏦 Банк: <b>не привязан!</b>\n"

            text += f"📅 Создан: {user.created_at.strftime('%d.%m.%Y %H:%M')}"

            await callback.message.edit_text(
                text,
                reply_markup=self.kb.user_actions(
                    user.id,
                    user.is_active,
                    role=user.role,
                    has_bank=bool(user.bank_id)
                ),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        # Установка роли (обрабатываем отдельно, т.к. user_id не последний)
        if action == "setrole":
            new_role = parts[-1]
            user_id = int(parts[-2])

            # Если это новый пользователь (id=0)
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
                await self.user_repo.update_role(user_id, new_role)
                # При смене роли сбрасываем привязку к банку (если была)
                if new_role != 'bank':
                    await self.user_repo.assign_to_bank(user_id, None)
                user = await self.user_repo.get_by_id(user_id)

                await callback.message.edit_text(
                    f"✅ Роль изменена на <b>{new_role}</b>",
                    reply_markup=self.kb.user_actions(user_id, user.is_active, role=new_role, has_bank=bool(user.bank_id)),
                    parse_mode="HTML"
                )
            await callback.answer("Роль обновлена!")
            return

        # Привязка к банку (assignbank и setbank)
        if action == "assignbank":
            user_id = int(parts[-1])
            banks = await self.bank_repo.get_all()
            active_banks = [b for b in banks if b.is_active]

            if not active_banks:
                await callback.answer("Нет активных банков!", show_alert=True)
                return

            await callback.message.edit_text(
                "🏦 <b>Привязка к банку</b>\n\n"
                "Выберите банк для сотрудника:",
                reply_markup=self.kb.select_bank_for_user(user_id, active_banks),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        if action == "setbank":
            user_id = int(parts[-2])
            bank_id = int(parts[-1])

            if bank_id == 0:
                # Отвязка от банка
                await self.user_repo.assign_to_bank(user_id, None)
                await callback.message.edit_text(
                    "✅ Сотрудник отвязан от банка",
                    reply_markup=self.kb.back_to_menu(),
                    parse_mode="HTML"
                )
            else:
                # Привязка к банку
                bank = await self.bank_repo.get_by_id(bank_id)
                await self.user_repo.assign_to_bank(user_id, bank_id)
                await callback.message.edit_text(
                    f"✅ Сотрудник привязан к банку <b>{bank.name}</b>",
                    reply_markup=self.kb.back_to_menu(),
                    parse_mode="HTML"
                )
            await callback.answer("Банк обновлён!")
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
            user = await self.user_repo.get_by_id(user_id)
            await callback.message.edit_text(
                "🚫 Пользователь деактивирован",
                reply_markup=self.kb.user_actions(user_id, False, role=user.role, has_bank=bool(user.bank_id)),
                parse_mode="HTML"
            )
            await callback.answer()

        # Активация
        elif action == "activate":
            await self.user_repo.activate(user_id)
            user = await self.user_repo.get_by_id(user_id)
            await callback.message.edit_text(
                "✅ Пользователь активирован",
                reply_markup=self.kb.user_actions(user_id, True, role=user.role, has_bank=bool(user.bank_id)),
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
        await state.set_state(AdminStates.waiting_company_daily_limit)
        await message.answer(
            f"✅ ИНН: <b>{inn}</b>\n\n"
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

        # Создаём компанию
        company = await self.company_repo.create(
            name=data['company_name'],
            inn=data['company_inn'],
            daily_limit=limit,
            weekly_limit=limit * 5,
            monthly_limit=limit * 20
        )

        await message.answer(
            f"✅ <b>Компания создана!</b>\n\n"
            f"🏢 {company.name}\n"
            f"🔢 ИНН: {company.inn}\n"
            f"💰 Дневной лимит: {company.daily_limit:,.0f}₽",
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

            await callback.message.edit_text(
                f"🏢 <b>{company.name}</b>\n\n"
                f"🔢 ИНН: <code>{company.inn}</code>\n"
                f"📊 Статус: {'✅ Активна' if company.is_active else '❌ Неактивна'}\n\n"
                f"<b>Лимиты:</b>\n"
                f"📅 Дневной: {company.current_daily_used:,.0f} / {company.daily_limit:,.0f}₽ (осталось {daily_left:,.0f}₽)\n"
                f"📆 Недельный: {company.current_weekly_used:,.0f} / {company.weekly_limit:,.0f}₽\n"
                f"🗓️ Месячный: {company.current_monthly_used:,.0f} / {company.monthly_limit:,.0f}₽",
                reply_markup=self.kb.company_actions(company.id, company.is_active),
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

        # Меню лимитов
        elif action == "limits":
            await callback.message.edit_text(
                "💰 <b>Изменение лимитов</b>\n\nВыберите тип лимита:",
                reply_markup=self.kb.company_limits_menu(company_id),
                parse_mode="HTML"
            )
            await callback.answer()

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
                reply_markup=self.kb.company_actions(company_id, False)
            )

        # Активация
        elif action == "activate":
            await self.company_repo.update_by_id(company_id, is_active=True)
            await callback.answer("✅ Компания активирована")
            await callback.message.edit_reply_markup(
                reply_markup=self.kb.company_actions(company_id, True)
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
            await self.company_repo.delete_by_id(company_id)
            await callback.message.edit_text(
                "✅ Компания удалена",
                reply_markup=self.kb.back_to_menu()
            )
            await callback.answer()

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
        """Добавление банка"""
        await state.set_state(AdminStates.waiting_bank_forward)
        await callback.message.edit_text(
            "🏦 <b>Добавление банка</b>\n\n"
            "Введите <b>Chat ID</b> группы банка.\n\n"
            "<b>Как узнать Chat ID:</b>\n"
            "1️⃣ Добавьте бота @RawDataBot в группу банка\n"
            "2️⃣ Он покажет Chat ID (число вида <code>-100123456789</code>)\n"
            "3️⃣ Скопируйте и отправьте сюда\n\n"
            "<i>Или перешлите сообщение из канала/супергруппы</i>",
            reply_markup=self.kb.cancel_input(),
            parse_mode="HTML"
        )
        await callback.answer()

    async def process_bank_forward(self, message: Message, state: FSMContext, db_user):
        """Обработка пересланного сообщения для добавления банка"""
        chat_id = None
        chat_title = None

        # 1. Проверяем forward_from_chat (для каналов и супергрупп)
        if message.forward_from_chat:
            chat_id = message.forward_from_chat.id
            chat_title = message.forward_from_chat.title

        # 2. Проверяем forward_origin (новый API Telegram)
        elif hasattr(message, 'forward_origin') and message.forward_origin:
            origin = message.forward_origin
            if hasattr(origin, 'chat'):
                chat_id = origin.chat.id
                chat_title = getattr(origin.chat, 'title', None)

        # 3. Если отправили число напрямую (Chat ID)
        elif message.text:
            text = message.text.strip().replace(" ", "")
            try:
                chat_id = int(text)
            except ValueError:
                await message.answer(
                    "❌ Не удалось определить Chat ID.\n\n"
                    "Введите Chat ID числом (например: <code>-1001234567890</code>)\n\n"
                    "<b>Как узнать Chat ID:</b>\n"
                    "• Добавьте @RawDataBot в группу банка\n"
                    "• Или @getmyid_bot",
                    reply_markup=self.kb.cancel_input(),
                    parse_mode="HTML"
                )
                return

        if not chat_id:
            await message.answer(
                "❌ Не удалось определить Chat ID.\n\n"
                "Введите Chat ID числом или перешлите сообщение из <b>канала</b>.",
                reply_markup=self.kb.cancel_input(),
                parse_mode="HTML"
            )
            return

        # Проверяем, существует ли банк с таким chat_id
        existing = await self.bank_repo.get_by_chat_id(chat_id)
        if existing:
            await state.clear()
            await message.answer(
                f"⚠️ Банк с таким Chat ID уже существует!\n\n"
                f"🏦 {existing.name}",
                reply_markup=self.kb.bank_actions(existing.id, existing.is_active, existing.is_available),
                parse_mode="HTML"
            )
            return

        await state.update_data(bank_chat_id=chat_id, bank_suggested_name=chat_title)
        await state.set_state(AdminStates.waiting_bank_name)

        suggested = f"\n\n<i>Предложенное название: {chat_title}</i>" if chat_title else ""

        await message.answer(
            f"✅ Chat ID: <code>{chat_id}</code>{suggested}\n\n"
            "Введите название банка:",
            reply_markup=self.kb.cancel_input(),
            parse_mode="HTML"
        )

    async def process_bank_name(self, message: Message, state: FSMContext, db_user):
        """Обработка названия банка"""
        name = message.text.strip()
        if len(name) < 2:
            await message.answer("❌ Название слишком короткое.")
            return

        await state.update_data(bank_name=name)
        await state.set_state(AdminStates.waiting_bank_daily_limit)

        await message.answer(
            f"✅ Название: <b>{name}</b>\n\n"
            "Введите дневной лимит (в рублях):\n"
            "<i>Например: 10000000</i>",
            reply_markup=self.kb.cancel_input(),
            parse_mode="HTML"
        )

    async def process_bank_daily_limit(self, message: Message, state: FSMContext, db_user):
        """Обработка дневного лимита банка"""
        try:
            limit = Decimal(message.text.strip().replace(" ", "").replace(",", ""))
            if limit < 0:
                raise ValueError()
        except:
            await message.answer("❌ Введите корректное число.")
            return

        data = await state.get_data()
        await state.clear()

        # Создаём банк
        bank = await self.bank_repo.create(
            name=data['bank_name'],
            chat_id=data['bank_chat_id'],
            daily_limit=limit,
            weekly_limit=limit * 5
        )

        await message.answer(
            f"✅ <b>Банк добавлен!</b>\n\n"
            f"🏦 {bank.name}\n"
            f"💬 Chat ID: <code>{bank.chat_id}</code>\n"
            f"💰 Дневной лимит: {bank.daily_limit:,.0f}₽",
            reply_markup=self.kb.back_to_menu(),
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

            await callback.message.edit_text(
                f"🏦 <b>{bank.name}</b>\n\n"
                f"💬 Chat ID: <code>{bank.chat_id}</code>\n"
                f"⚡ Приоритет: {bank.priority}\n"
                f"📊 Статус: {'✅ Активен' if bank.is_active else '❌ Неактивен'}\n"
                f"🚦 Приём заявок: {'🟢 Открыт' if bank.is_available else '🔴 Закрыт'}\n\n"
                f"<b>Лимиты:</b>\n"
                f"📅 Дневной: {bank.current_daily_used:,.0f} / {bank.daily_limit:,.0f}₽ (осталось {daily_left:,.0f}₽)\n"
                f"📆 Недельный: {bank.current_weekly_used:,.0f} / {bank.weekly_limit:,.0f}₽",
                reply_markup=self.kb.bank_actions(bank.id, bank.is_active, bank.is_available),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        bank_id = int(parts[-1])

        # Редактирование названия
        if action == "edit" and parts[1] == "name":
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
                reply_markup=self.kb.bank_actions(bank_id, bank.is_active, False)
            )

        elif action == "available":
            await self.bank_repo.update_by_id(bank_id, is_available=True)
            await callback.answer("▶️ Приём заявок возобновлён")
            bank = await self.bank_repo.get_by_id(bank_id)
            await callback.message.edit_reply_markup(
                reply_markup=self.kb.bank_actions(bank_id, bank.is_active, True)
            )

        # Деактивация
        elif action == "deactivate":
            await self.bank_repo.update_by_id(bank_id, is_active=False)
            await callback.answer("🚫 Банк деактивирован")
            bank = await self.bank_repo.get_by_id(bank_id)
            await callback.message.edit_reply_markup(
                reply_markup=self.kb.bank_actions(bank_id, False, bank.is_available)
            )

        # Активация
        elif action == "activate":
            await self.bank_repo.update_by_id(bank_id, is_active=True)
            await callback.answer("✅ Банк активирован")
            bank = await self.bank_repo.get_by_id(bank_id)
            await callback.message.edit_reply_markup(
                reply_markup=self.kb.bank_actions(bank_id, True, bank.is_available)
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
            await self.bank_repo.delete_by_id(bank_id)
            await callback.message.edit_text(
                "✅ Банк удалён",
                reply_markup=self.kb.back_to_menu()
            )
            await callback.answer()

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
            reply_markup=self.kb.back_to_menu(),
            parse_mode="HTML"
        )
        await callback.answer()
