# bot/keyboards/supervisor_kb.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


class SupervisorKeyboards:
    """Клавиатуры для руководителя (супервайзера)"""

    @staticmethod
    def main_menu() -> InlineKeyboardMarkup:
        """Главное меню руководителя"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="🔴 Требуют решения", callback_data="sv:pending")
        )
        builder.row(
            InlineKeyboardButton(text="🚨 Эскалации", callback_data="sv:escalations")
        )
        builder.row(
            InlineKeyboardButton(text="⚠️ Минимальный риск", callback_data="sv:min_risk")
        )
        builder.row(
            InlineKeyboardButton(text="📋 Все заявки", callback_data="sv:all")
        )
        builder.row(
            InlineKeyboardButton(text="📊 Статистика", callback_data="sv:stats")
        )
        return builder.as_markup()

    @staticmethod
    def applications_list(applications: list, list_type: str = "pending", page: int = 0, per_page: int = 5) -> InlineKeyboardMarkup:
        """Список заявок"""
        builder = InlineKeyboardBuilder()

        start = page * per_page
        end = start + per_page
        page_apps = applications[start:end]

        for app in page_apps:
            status_emoji = {
                'supervisor_review': '🔴',
                'approved': '✅',
                'rejected': '❌',
                'bank_review': '🏦'
            }.get(app.status, '📋')

            builder.row(
                InlineKeyboardButton(
                    text=f"{status_emoji} {app.external_id} | {app.amount:,.0f}₽",
                    callback_data=f"sv:app:{app.id}"
                )
            )

        # Пагинация
        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton(text="⬅️", callback_data=f"sv:page:{list_type}:{page - 1}")
            )
        if end < len(applications):
            nav_buttons.append(
                InlineKeyboardButton(text="➡️", callback_data=f"sv:page:{list_type}:{page + 1}")
            )
        if nav_buttons:
            builder.row(*nav_buttons)

        builder.row(
            InlineKeyboardButton(text="🔙 Назад", callback_data="sv:menu")
        )
        return builder.as_markup()

    @staticmethod
    def application_actions(app_id: int, is_escalation: bool = False) -> InlineKeyboardMarkup:
        """Действия с заявкой"""
        builder = InlineKeyboardBuilder()

        builder.row(
            InlineKeyboardButton(
                text="✅ Одобрить",
                callback_data=f"sv:approve:{app_id}"
            ),
            InlineKeyboardButton(
                text="❌ Отклонить",
                callback_data=f"sv:reject:{app_id}"
            )
        )

        if is_escalation:
            builder.row(
                InlineKeyboardButton(
                    text="↩️ Вернуть менеджеру",
                    callback_data=f"sv:return:{app_id}"
                )
            )

        builder.row(
            InlineKeyboardButton(text="🔙 К списку", callback_data="sv:pending")
        )
        return builder.as_markup()

    @staticmethod
    def rejection_reasons(app_id: int) -> InlineKeyboardMarkup:
        """Причины отклонения"""
        builder = InlineKeyboardBuilder()

        reasons = [
            ("Высокий риск", "high_risk"),
            ("Недостаточно данных", "insufficient_data"),
            ("Превышение лимитов", "limit_exceeded"),
            ("Другая причина", "other")
        ]

        for text, reason in reasons:
            builder.row(
                InlineKeyboardButton(
                    text=text,
                    callback_data=f"sv:reject_reason:{app_id}:{reason}"
                )
            )

        builder.row(
            InlineKeyboardButton(text="🔙 Отмена", callback_data=f"sv:app:{app_id}")
        )
        return builder.as_markup()

    @staticmethod
    def confirm_action(action: str, app_id: int) -> InlineKeyboardMarkup:
        """Подтверждение действия"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Подтвердить",
                callback_data=f"sv:confirm_{action}:{app_id}"
            ),
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data=f"sv:app:{app_id}"
            )
        )
        return builder.as_markup()

    @staticmethod
    def back_to_menu() -> InlineKeyboardMarkup:
        """Кнопка возврата в меню"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="🔙 В меню", callback_data="sv:menu")
        )
        return builder.as_markup()
