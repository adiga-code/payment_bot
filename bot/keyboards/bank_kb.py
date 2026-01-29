# bot/keyboards/bank_kb.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


class BankKeyboards:
    """Клавиатуры для группового чата банка"""

    @staticmethod
    def group_risk_assessment(app_id: int) -> InlineKeyboardMarkup:
        """Оценка риска — кнопки для группового чата"""
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
    def rejection_reasons(app_id: int) -> InlineKeyboardMarkup:
        """Выбор причины отклонения"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="⛔ Высокий риск операции",
                callback_data=f"bank:reject:{app_id}:high_risk_op"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="🚫 Подозрительный контрагент",
                callback_data=f"bank:reject:{app_id}:suspicious"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="📋 Контрагент в чёрном списке",
                callback_data=f"bank:reject:{app_id}:blacklist"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="📄 Несоответствие документов",
                callback_data=f"bank:reject:{app_id}:docs_mismatch"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="🔙 Отмена",
                callback_data=f"bank:cancel_reject:{app_id}"
            )
        )
        return builder.as_markup()
