# bot/keyboards/admin_kb.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import List


class AdminKeyboards:
    """Клавиатуры для администратора"""

    @staticmethod
    def main_menu() -> InlineKeyboardMarkup:
        """Главное меню администратора"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="👥 Пользователи", callback_data="admin:users")
        )
        builder.row(
            InlineKeyboardButton(text="🏢 Компании", callback_data="admin:companies")
        )
        builder.row(
            InlineKeyboardButton(text="🏦 Банки", callback_data="admin:banks")
        )
        builder.row(
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")
        )
        return builder.as_markup()

    # ==================== ПОЛЬЗОВАТЕЛИ ====================

    @staticmethod
    def users_menu() -> InlineKeyboardMarkup:
        """Меню управления пользователями"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="📋 Все пользователи", callback_data="admin:users:list:all")
        )
        builder.row(
            InlineKeyboardButton(text="👔 Менеджеры", callback_data="admin:users:list:manager"),
            InlineKeyboardButton(text="👑 Супервайзеры", callback_data="admin:users:list:supervisor")
        )
        builder.row(
            InlineKeyboardButton(text="➕ Добавить пользователя", callback_data="admin:users:add")
        )
        builder.row(
            InlineKeyboardButton(text="🔙 Назад", callback_data="admin:menu")
        )
        return builder.as_markup()

    @staticmethod
    def users_list(users: list, role_filter: str = 'all', page: int = 0, per_page: int = 8) -> InlineKeyboardMarkup:
        """Список пользователей"""
        builder = InlineKeyboardBuilder()

        start = page * per_page
        end = start + per_page
        page_users = users[start:end]

        role_emoji = {
            'client': '👤',
            'manager': '👔',
            'bank': '🏦',
            'accountant': '📑',
            'supervisor': '👑',
            'admin': '⚙️'
        }

        for user in page_users:
            emoji = role_emoji.get(user.role, '👤')
            status = '✅' if user.is_active else '❌'
            name = user.first_name or user.username or str(user.telegram_id)
            builder.row(
                InlineKeyboardButton(
                    text=f"{emoji}{status} {name[:20]} ({user.role})",
                    callback_data=f"admin:user:{user.id}"
                )
            )

        # Пагинация
        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton(text="⬅️", callback_data=f"admin:users:page:{role_filter}:{page - 1}")
            )
        if end < len(users):
            nav_buttons.append(
                InlineKeyboardButton(text="➡️", callback_data=f"admin:users:page:{role_filter}:{page + 1}")
            )
        if nav_buttons:
            builder.row(*nav_buttons)

        builder.row(
            InlineKeyboardButton(text="🔙 Назад", callback_data="admin:users")
        )
        return builder.as_markup()

    @staticmethod
    def user_actions(user_id: int, is_active: bool) -> InlineKeyboardMarkup:
        """Действия с пользователем"""
        builder = InlineKeyboardBuilder()

        builder.row(
            InlineKeyboardButton(text="🔄 Изменить роль", callback_data=f"admin:user:role:{user_id}")
        )

        if is_active:
            builder.row(
                InlineKeyboardButton(text="🚫 Деактивировать", callback_data=f"admin:user:deactivate:{user_id}")
            )
        else:
            builder.row(
                InlineKeyboardButton(text="✅ Активировать", callback_data=f"admin:user:activate:{user_id}")
            )

        builder.row(
            InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"admin:user:delete:{user_id}")
        )
        builder.row(
            InlineKeyboardButton(text="🔙 К списку", callback_data="admin:users:list:all")
        )
        return builder.as_markup()

    @staticmethod
    def select_role(user_id: int) -> InlineKeyboardMarkup:
        """Выбор роли"""
        builder = InlineKeyboardBuilder()
        roles = [
            ('👤 Клиент', 'client'),
            ('👔 Менеджер', 'manager'),
            ('🏦 Сотрудник банка', 'bank'),
            ('📑 Бухгалтер', 'accountant'),
            ('👑 Супервайзер', 'supervisor'),
            ('⚙️ Админ', 'admin')
        ]
        for text, role in roles:
            builder.row(
                InlineKeyboardButton(text=text, callback_data=f"admin:user:setrole:{user_id}:{role}")
            )
        builder.row(
            InlineKeyboardButton(text="🔙 Отмена", callback_data=f"admin:user:{user_id}")
        )
        return builder.as_markup()

    @staticmethod
    def select_bank_for_user(user_id: int, banks: list) -> InlineKeyboardMarkup:
        """Выбор банка при назначении роли 'bank'"""
        builder = InlineKeyboardBuilder()

        for bank in banks:
            status = '✅' if bank.is_active else '❌'
            builder.row(
                InlineKeyboardButton(
                    text=f"{status} {bank.name[:25]}",
                    callback_data=f"admin:user:setbank:{user_id}:{bank.id}"
                )
            )

        builder.row(
            InlineKeyboardButton(
                text="⏭️ Пропустить (без банка)",
                callback_data=f"admin:user:setbank:{user_id}:skip"
            )
        )
        builder.row(
            InlineKeyboardButton(text="🔙 Отмена", callback_data=f"admin:user:role:{user_id}")
        )
        return builder.as_markup()

    @staticmethod
    def confirm_action(action: str, entity_type: str, entity_id: int) -> InlineKeyboardMarkup:
        """Универсальное подтверждение действия"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Да, подтверждаю",
                callback_data=f"admin:{entity_type}:confirm_{action}:{entity_id}"
            ),
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data=f"admin:{entity_type}:{entity_id}"
            )
        )
        return builder.as_markup()

    # ==================== КОМПАНИИ ====================

    @staticmethod
    def companies_menu() -> InlineKeyboardMarkup:
        """Меню управления компаниями"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="📋 Список компаний", callback_data="admin:companies:list")
        )
        builder.row(
            InlineKeyboardButton(text="➕ Добавить компанию", callback_data="admin:companies:add")
        )
        builder.row(
            InlineKeyboardButton(text="🔙 Назад", callback_data="admin:menu")
        )
        return builder.as_markup()

    @staticmethod
    def companies_list(companies: list, page: int = 0, per_page: int = 8) -> InlineKeyboardMarkup:
        """Список компаний"""
        builder = InlineKeyboardBuilder()

        start = page * per_page
        end = start + per_page
        page_companies = companies[start:end]

        for company in page_companies:
            status = '✅' if company.is_active else '❌'
            daily_left = company.daily_limit - company.current_daily_used
            builder.row(
                InlineKeyboardButton(
                    text=f"{status} {company.name[:20]} | {daily_left:,.0f}₽",
                    callback_data=f"admin:company:{company.id}"
                )
            )

        # Пагинация
        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton(text="⬅️", callback_data=f"admin:companies:page:{page - 1}")
            )
        if end < len(companies):
            nav_buttons.append(
                InlineKeyboardButton(text="➡️", callback_data=f"admin:companies:page:{page + 1}")
            )
        if nav_buttons:
            builder.row(*nav_buttons)

        builder.row(
            InlineKeyboardButton(text="🔙 Назад", callback_data="admin:companies")
        )
        return builder.as_markup()

    @staticmethod
    def company_actions(company_id: int, is_active: bool) -> InlineKeyboardMarkup:
        """Действия с компанией"""
        builder = InlineKeyboardBuilder()

        builder.row(
            InlineKeyboardButton(text="✏️ Изменить название", callback_data=f"admin:company:edit:name:{company_id}"),
            InlineKeyboardButton(text="🔢 Изменить ИНН", callback_data=f"admin:company:edit:inn:{company_id}")
        )
        builder.row(
            InlineKeyboardButton(text="💰 Лимиты", callback_data=f"admin:company:limits:{company_id}")
        )
        builder.row(
            InlineKeyboardButton(text="🏦 Банковские счета", callback_data=f"admin:company:banks:{company_id}")
        )
        builder.row(
            InlineKeyboardButton(text="🔄 Сбросить использование", callback_data=f"admin:company:reset:{company_id}")
        )

        if is_active:
            builder.row(
                InlineKeyboardButton(text="🚫 Деактивировать", callback_data=f"admin:company:deactivate:{company_id}")
            )
        else:
            builder.row(
                InlineKeyboardButton(text="✅ Активировать", callback_data=f"admin:company:activate:{company_id}")
            )

        builder.row(
            InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"admin:company:delete:{company_id}")
        )
        builder.row(
            InlineKeyboardButton(text="🔙 К списку", callback_data="admin:companies:list")
        )
        return builder.as_markup()

    @staticmethod
    def company_limits_menu(company_id: int) -> InlineKeyboardMarkup:
        """Меню изменения лимитов компании"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="📅 Дневной", callback_data=f"admin:company:limit:daily:{company_id}"),
            InlineKeyboardButton(text="📆 Недельный", callback_data=f"admin:company:limit:weekly:{company_id}")
        )
        builder.row(
            InlineKeyboardButton(text="🗓️ Месячный", callback_data=f"admin:company:limit:monthly:{company_id}")
        )
        builder.row(
            InlineKeyboardButton(text="🔙 Назад", callback_data=f"admin:company:{company_id}")
        )
        return builder.as_markup()

    @staticmethod
    def company_banks_list(company_id: int, company_banks: list) -> InlineKeyboardMarkup:
        """Список банковских счетов компании"""
        builder = InlineKeyboardBuilder()

        for cb in company_banks:
            bank_name = cb.bank.name if cb.bank else "—"
            account = cb.account_number or "—"
            preferred = "⭐ " if cb.is_preferred else ""
            builder.row(
                InlineKeyboardButton(
                    text=f"{preferred}{bank_name}: {account}",
                    callback_data=f"admin:company:bank:{cb.id}:{company_id}"
                )
            )

        builder.row(
            InlineKeyboardButton(text="➕ Добавить счёт", callback_data=f"admin:company:add_bank:{company_id}")
        )
        builder.row(
            InlineKeyboardButton(text="🔙 Назад", callback_data=f"admin:company:{company_id}")
        )
        return builder.as_markup()

    @staticmethod
    def select_bank_for_company(company_id: int, banks: list) -> InlineKeyboardMarkup:
        """Выбор банка для привязки к компании"""
        builder = InlineKeyboardBuilder()

        for bank in banks:
            builder.row(
                InlineKeyboardButton(
                    text=f"🏦 {bank.name}",
                    callback_data=f"admin:company:select_bank:{bank.id}:{company_id}"
                )
            )

        builder.row(
            InlineKeyboardButton(text="🔙 Назад", callback_data=f"admin:company:banks:{company_id}")
        )
        return builder.as_markup()

    @staticmethod
    def company_bank_actions(company_bank_id: int, company_id: int, is_preferred: bool) -> InlineKeyboardMarkup:
        """Действия со счётом компании"""
        builder = InlineKeyboardBuilder()

        builder.row(
            InlineKeyboardButton(text="✏️ Изменить номер счёта", callback_data=f"admin:company:edit_account:{company_bank_id}:{company_id}")
        )

        if is_preferred:
            builder.row(
                InlineKeyboardButton(text="⭐ Основной счёт", callback_data="noop")
            )
        else:
            builder.row(
                InlineKeyboardButton(text="☆ Сделать основным", callback_data=f"admin:company:set_preferred:{company_bank_id}:{company_id}")
            )

        builder.row(
            InlineKeyboardButton(text="🗑️ Отвязать счёт", callback_data=f"admin:company:unlink_bank:{company_bank_id}:{company_id}")
        )
        builder.row(
            InlineKeyboardButton(text="🔙 Назад", callback_data=f"admin:company:banks:{company_id}")
        )
        return builder.as_markup()

    # ==================== БАНКИ ====================

    @staticmethod
    def banks_menu() -> InlineKeyboardMarkup:
        """Меню управления банками"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="📋 Список банков", callback_data="admin:banks:list")
        )
        builder.row(
            InlineKeyboardButton(text="➕ Добавить банк", callback_data="admin:banks:add")
        )
        builder.row(
            InlineKeyboardButton(text="🔙 Назад", callback_data="admin:menu")
        )
        return builder.as_markup()

    @staticmethod
    def banks_list(banks: list, page: int = 0, per_page: int = 8) -> InlineKeyboardMarkup:
        """Список банков"""
        builder = InlineKeyboardBuilder()

        start = page * per_page
        end = start + per_page
        page_banks = banks[start:end]

        for bank in page_banks:
            status = '✅' if bank.is_active else '❌'
            avail = '🟢' if bank.is_available else '🔴'
            daily_left = bank.daily_limit - bank.current_daily_used
            builder.row(
                InlineKeyboardButton(
                    text=f"{status}{avail} {bank.name[:18]} | {daily_left:,.0f}₽",
                    callback_data=f"admin:bank:{bank.id}"
                )
            )

        # Пагинация
        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton(text="⬅️", callback_data=f"admin:banks:page:{page - 1}")
            )
        if end < len(banks):
            nav_buttons.append(
                InlineKeyboardButton(text="➡️", callback_data=f"admin:banks:page:{page + 1}")
            )
        if nav_buttons:
            builder.row(*nav_buttons)

        builder.row(
            InlineKeyboardButton(text="🔙 Назад", callback_data="admin:banks")
        )
        return builder.as_markup()

    @staticmethod
    def bank_actions(bank_id: int, is_active: bool, is_available: bool, has_chat: bool = False) -> InlineKeyboardMarkup:
        """Действия с банком"""
        builder = InlineKeyboardBuilder()

        builder.row(
            InlineKeyboardButton(text="✏️ Изменить название", callback_data=f"admin:bank:edit:name:{bank_id}")
        )
        builder.row(
            InlineKeyboardButton(text="💰 Лимиты", callback_data=f"admin:bank:limits:{bank_id}"),
            InlineKeyboardButton(text="⚡ Приоритет", callback_data=f"admin:bank:edit:priority:{bank_id}")
        )
        builder.row(
            InlineKeyboardButton(text="🔄 Сбросить использование", callback_data=f"admin:bank:reset:{bank_id}")
        )

        # Привязка/отвязка группы
        if has_chat:
            builder.row(
                InlineKeyboardButton(text="🔗 Отвязать группу", callback_data=f"admin:bank:unlink:{bank_id}")
            )
        else:
            builder.row(
                InlineKeyboardButton(text="💬 Привязать группу", callback_data=f"admin:bank:link:{bank_id}")
            )

        # Доступность
        if is_available:
            builder.row(
                InlineKeyboardButton(text="⏸️ Приостановить приём", callback_data=f"admin:bank:unavailable:{bank_id}")
            )
        else:
            builder.row(
                InlineKeyboardButton(text="▶️ Возобновить приём", callback_data=f"admin:bank:available:{bank_id}")
            )

        # Активность
        if is_active:
            builder.row(
                InlineKeyboardButton(text="🚫 Деактивировать", callback_data=f"admin:bank:deactivate:{bank_id}")
            )
        else:
            builder.row(
                InlineKeyboardButton(text="✅ Активировать", callback_data=f"admin:bank:activate:{bank_id}")
            )

        builder.row(
            InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"admin:bank:delete:{bank_id}")
        )
        builder.row(
            InlineKeyboardButton(text="🔙 К списку", callback_data="admin:banks:list")
        )
        return builder.as_markup()

    @staticmethod
    def bank_limits_menu(bank_id: int) -> InlineKeyboardMarkup:
        """Меню изменения лимитов банка"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="📅 Дневной", callback_data=f"admin:bank:limit:daily:{bank_id}"),
            InlineKeyboardButton(text="📆 Недельный", callback_data=f"admin:bank:limit:weekly:{bank_id}")
        )
        builder.row(
            InlineKeyboardButton(text="🔙 Назад", callback_data=f"admin:bank:{bank_id}")
        )
        return builder.as_markup()

    @staticmethod
    def link_group_button(bot_username: str) -> InlineKeyboardMarkup:
        """Кнопка для добавления бота в группу"""
        builder = InlineKeyboardBuilder()
        url = f"https://t.me/{bot_username}?startgroup=link&admin=post_messages+edit_messages"
        builder.row(
            InlineKeyboardButton(text="➕ Добавить бота в группу", url=url)
        )
        builder.row(
            InlineKeyboardButton(text="❌ Отмена", callback_data="admin:cancel")
        )
        return builder.as_markup()

    @staticmethod
    def cancel_input() -> InlineKeyboardMarkup:
        """Кнопка отмены ввода"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="❌ Отмена", callback_data="admin:cancel")
        )
        return builder.as_markup()

    @staticmethod
    def back_to_menu() -> InlineKeyboardMarkup:
        """Кнопка возврата в меню"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="🔙 В меню", callback_data="admin:menu")
        )
        return builder.as_markup()
