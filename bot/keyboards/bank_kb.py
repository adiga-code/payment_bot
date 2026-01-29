# bot/keyboards/bank_kb.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


class BankKeyboards:
    """Клавиатуры для сотрудника банка"""

    @staticmethod
    def main_menu() -> InlineKeyboardMarkup:
        """Главное меню банка"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="📥 Входящие заявки", callback_data="bank:applications")
        )
        builder.row(
            InlineKeyboardButton(text="📊 Статистика", callback_data="bank:stats")
        )
        return builder.as_markup()

    @staticmethod
    def applications_list(applications: list, page: int = 0, per_page: int = 5) -> InlineKeyboardMarkup:
        """Список заявок"""
        builder = InlineKeyboardBuilder()

        start = page * per_page
        end = start + per_page
        page_apps = applications[start:end]

        for app in page_apps:
            builder.row(
                InlineKeyboardButton(
                    text=f"📋 {app.external_id} | {app.amount:,.0f}₽",
                    callback_data=f"bank:app:{app.id}"
                )
            )

        # Пагинация
        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton(text="⬅️", callback_data=f"bank:page:{page - 1}")
            )
        if end < len(applications):
            nav_buttons.append(
                InlineKeyboardButton(text="➡️", callback_data=f"bank:page:{page + 1}")
            )
        if nav_buttons:
            builder.row(*nav_buttons)

        builder.row(
            InlineKeyboardButton(text="🔙 Назад", callback_data="bank:menu")
        )
        return builder.as_markup()

    @staticmethod
    def risk_assessment(app_id: int) -> InlineKeyboardMarkup:
        """Оценка риска заявки"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Без риска",
                callback_data=f"bank:risk:{app_id}:no_risk"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="⚠️ Минимальный риск",
                callback_data=f"bank:risk:{app_id}:min_risk"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="❌ Высокий риск",
                callback_data=f"bank:risk:{app_id}:high_risk"
            )
        )
        builder.row(
            InlineKeyboardButton(text="🔙 К списку", callback_data="bank:applications")
        )
        return builder.as_markup()

    @staticmethod
    def confirm_high_risk(app_id: int) -> InlineKeyboardMarkup:
        """Подтверждение высокого риска (отклонение)"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Да, отклонить",
                callback_data=f"bank:reject_confirm:{app_id}"
            ),
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data=f"bank:app:{app_id}"
            )
        )
        return builder.as_markup()

    @staticmethod
    def group_risk_assessment(app_id: int) -> InlineKeyboardMarkup:
        """Оценка риска — клавиатура для группового чата банка"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Без риска",
                callback_data=f"bank:risk:{app_id}:no_risk"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="⚠️ Минимальный риск",
                callback_data=f"bank:risk:{app_id}:min_risk"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="❌ Высокий риск",
                callback_data=f"bank:risk:{app_id}:high_risk"
            )
        )
        return builder.as_markup()

    @staticmethod
    def back_to_menu() -> InlineKeyboardMarkup:
        """Кнопка возврата в меню"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="🔙 В меню", callback_data="bank:menu")
        )
        return builder.as_markup()
