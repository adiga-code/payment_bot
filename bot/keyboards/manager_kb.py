# bot/keyboards/manager_kb.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import List, Optional


class ManagerKeyboards:
    """Клавиатуры для менеджера"""

    @staticmethod
    def main_menu() -> InlineKeyboardMarkup:
        """Главное меню менеджера"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="📥 Новые заявки",
                callback_data="mgr:applications:new"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="📋 Мои заявки",
                callback_data="mgr:applications:my"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="📊 Статистика",
                callback_data="mgr:stats"
            )
        )
        return builder.as_markup()

    @staticmethod
    def applications_list(applications: list, page: int = 0, per_page: int = 5) -> InlineKeyboardMarkup:
        """Список заявок с пагинацией"""
        builder = InlineKeyboardBuilder()

        # Заявки на текущей странице
        start = page * per_page
        end = start + per_page
        page_apps = applications[start:end]

        for app in page_apps:
            status_emoji = {
                'new': '🆕',
                'primary_check': '🔍',
                'manager_review': '👀',
                'bank_review': '🏦',
                'supervisor_review': '👔',
                'approved': '✅',
                'rejected': '❌'
            }.get(app.status, '📋')

            # Название компании или ИНН (обрезаем до 35 символов если длинное)
            company_name = app.payer_name or f"ИНН {app.payer_inn}"
            if len(company_name) > 35:
                company_name = company_name[:32] + "..."

            builder.row(
                InlineKeyboardButton(
                    text=f"{status_emoji} {company_name} | {app.amount:,.0f}₽",
                    callback_data=f"mgr:app:{app.id}"
                )
            )

        # Пагинация
        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton(text="⬅️", callback_data=f"mgr:page:{page - 1}")
            )
        if end < len(applications):
            nav_buttons.append(
                InlineKeyboardButton(text="➡️", callback_data=f"mgr:page:{page + 1}")
            )
        if nav_buttons:
            builder.row(*nav_buttons)

        # Кнопка назад
        builder.row(
            InlineKeyboardButton(text="🔙 Назад", callback_data="mgr:menu")
        )

        return builder.as_markup()

    @staticmethod
    def application_actions(app_id: int, can_approve: bool = True) -> InlineKeyboardMarkup:
        """Действия с заявкой"""
        builder = InlineKeyboardBuilder()

        if can_approve:
            builder.row(
                InlineKeyboardButton(
                    text="✅ Одобрить",
                    callback_data=f"mgr:approve:{app_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"mgr:reject:{app_id}"
                )
            )
            builder.row(
                InlineKeyboardButton(
                    text="🚨 Эскалировать",
                    callback_data=f"mgr:escalate:{app_id}"
                )
            )

        builder.row(
            InlineKeyboardButton(text="🔙 К списку", callback_data="mgr:applications:new")
        )

        return builder.as_markup()

    @staticmethod
    def select_company(companies: list, app_id: int) -> InlineKeyboardMarkup:
        """Выбор компании для заявки"""
        builder = InlineKeyboardBuilder()

        for company in companies:
            # Показываем остаток лимита
            daily_left = company.daily_limit - company.current_daily_used
            builder.row(
                InlineKeyboardButton(
                    text=f"🏢 {company.name} | Лимит: {daily_left:,.0f}₽",
                    callback_data=f"mgr:company:{app_id}:{company.id}"
                )
            )

        builder.row(
            InlineKeyboardButton(text="🔙 Отмена", callback_data=f"mgr:app:{app_id}")
        )

        return builder.as_markup()

    @staticmethod
    def select_bank(banks: list, app_id: int) -> InlineKeyboardMarkup:
        """Выбор банка для заявки"""
        builder = InlineKeyboardBuilder()

        for bank in banks:
            daily_left = bank.daily_limit - bank.current_daily_used
            availability = "✅" if bank.is_available else "⏸️"
            builder.row(
                InlineKeyboardButton(
                    text=f"{availability} {bank.name} | {daily_left:,.0f}₽",
                    callback_data=f"mgr:bank:{app_id}:{bank.id}"
                )
            )

        builder.row(
            InlineKeyboardButton(text="🔙 Отмена", callback_data=f"mgr:app:{app_id}")
        )

        return builder.as_markup()

    @staticmethod
    def confirm_reject(app_id: int) -> InlineKeyboardMarkup:
        """Подтверждение отклонения"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Да, отклонить",
                callback_data=f"mgr:reject_confirm:{app_id}"
            ),
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data=f"mgr:app:{app_id}"
            )
        )
        return builder.as_markup()

    @staticmethod
    def rejection_reasons(app_id: int) -> InlineKeyboardMarkup:
        """Причины отклонения"""
        builder = InlineKeyboardBuilder()

        reasons = [
            ("Некорректные данные", "invalid_data"),
            ("Превышен лимит", "limit_exceeded"),
            ("Контрагент не прошёл проверку", "counterparty_failed"),
            ("Другая причина", "other")
        ]

        for text, reason in reasons:
            builder.row(
                InlineKeyboardButton(
                    text=text,
                    callback_data=f"mgr:reject_reason:{app_id}:{reason}"
                )
            )

        builder.row(
            InlineKeyboardButton(text="🔙 Отмена", callback_data=f"mgr:app:{app_id}")
        )

        return builder.as_markup()

    @staticmethod
    def payout_format(app_id: int) -> InlineKeyboardMarkup:
        """Выбор формата выдачи T+N"""
        builder = InlineKeyboardBuilder()

        builder.row(
            InlineKeyboardButton(text="T+1", callback_data=f"mgr:payout:1:{app_id}"),
            InlineKeyboardButton(text="T+2", callback_data=f"mgr:payout:2:{app_id}")
        )
        builder.row(
            InlineKeyboardButton(text="T+3", callback_data=f"mgr:payout:3:{app_id}"),
            InlineKeyboardButton(text="T+4", callback_data=f"mgr:payout:4:{app_id}")
        )
        builder.row(
            InlineKeyboardButton(text="T+5", callback_data=f"mgr:payout:5:{app_id}")
        )

        return builder.as_markup()
