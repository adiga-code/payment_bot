# bot/keyboards/client_kb.py

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


class ClientKeyboard:
    """Клавиатуры для клиента"""

    @staticmethod
    def main_menu() -> ReplyKeyboardMarkup:
        """Главное меню клиента (Reply клавиатура)"""
        builder = ReplyKeyboardBuilder()
        builder.row(
            KeyboardButton(text="📝 Создать заявку")
        )
        builder.row(
            KeyboardButton(text="📋 Мои заявки"),
            KeyboardButton(text="📚 История заявок")
        )
        return builder.as_markup(resize_keyboard=True)

    @staticmethod
    def payment_confirmation(app_id: int) -> InlineKeyboardMarkup:
        """Кнопки подтверждения оплаты счёта"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Оплачено",
                callback_data=f"client:paid:{app_id}"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="❌ Не удалось оплатить",
                callback_data=f"client:not_paid:{app_id}"
            )
        )
        return builder.as_markup()

    @staticmethod
    def payment_reminder(app_id: int) -> InlineKeyboardMarkup:
        """Кнопки напоминания об оплате"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Оплачено",
                callback_data=f"client:paid:{app_id}"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="❌ Не удалось оплатить",
                callback_data=f"client:not_paid:{app_id}"
            )
        )
        return builder.as_markup()
