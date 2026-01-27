# bot/keyboards/bank_kb.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


class BankKeyboards:
    """Клавиатуры для банка (групповой чат)"""

    @staticmethod
    def risk_assessment(app_id: int) -> InlineKeyboardMarkup:
        """Кнопки оценки риска для заявки в групповом чате"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Без риска",
                callback_data=f"bankgrp:risk:{app_id}:no_risk"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="⚠️ Минимальный риск",
                callback_data=f"bankgrp:risk:{app_id}:min_risk"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="❌ Высокий риск",
                callback_data=f"bankgrp:risk:{app_id}:high_risk"
            )
        )
        return builder.as_markup()

    @staticmethod
    def confirm_high_risk(app_id: int) -> InlineKeyboardMarkup:
        """Подтверждение отклонения при высоком риске"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="❌ Да, отклонить",
                callback_data=f"bankgrp:reject_confirm:{app_id}"
            ),
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data=f"bankgrp:back:{app_id}"
            )
        )
        return builder.as_markup()

    @staticmethod
    def processed(decision: str, user_name: str) -> InlineKeyboardMarkup:
        """Показывает что заявка обработана (кнопка-заглушка)"""
        builder = InlineKeyboardBuilder()
        emoji = {"no_risk": "✅", "min_risk": "⚠️", "high_risk": "❌"}.get(decision, "✅")
        text_map = {
            "no_risk": "Без риска",
            "min_risk": "Минимальный риск",
            "high_risk": "Отклонено (высокий риск)"
        }
        builder.row(
            InlineKeyboardButton(
                text=f"{emoji} {text_map.get(decision, 'Обработано')} — {user_name}",
                callback_data="bankgrp:noop"
            )
        )
        return builder.as_markup()
