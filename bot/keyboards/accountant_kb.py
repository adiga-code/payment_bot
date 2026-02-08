# bot/keyboards/accountant_kb.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


class AccountantKeyboards:
    """Клавиатуры для бухгалтера"""

    @staticmethod
    def main_menu() -> InlineKeyboardMarkup:
        """Главное меню бухгалтера"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="📄 Новые счета", callback_data="acc:pending")
        )
        builder.row(
            InlineKeyboardButton(text="📨 Отправленные", callback_data="acc:sent")
        )
        builder.row(
            InlineKeyboardButton(text="📊 Статистика", callback_data="acc:stats")
        )
        return builder.as_markup()

    @staticmethod
    def invoices_list(documents: list, list_type: str = "pending", page: int = 0, per_page: int = 5) -> InlineKeyboardMarkup:
        """Список счетов"""
        builder = InlineKeyboardBuilder()

        start = page * per_page
        end = start + per_page
        page_docs = documents[start:end]

        for doc_item in page_docs:
            app = doc_item['app']
            doc = doc_item['doc']
            builder.row(
                InlineKeyboardButton(
                    text=f"📄 {doc.number} | {app.amount:,.0f}₽",
                    callback_data=f"acc:doc:{doc.id}"
                )
            )

        # Пагинация
        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton(text="⬅️", callback_data=f"acc:page:{list_type}:{page - 1}")
            )
        if end < len(documents):
            nav_buttons.append(
                InlineKeyboardButton(text="➡️", callback_data=f"acc:page:{list_type}:{page + 1}")
            )
        if nav_buttons:
            builder.row(*nav_buttons)

        builder.row(
            InlineKeyboardButton(text="🔙 Назад", callback_data="acc:menu")
        )
        return builder.as_markup()

    @staticmethod
    def invoice_actions(doc_id: int, is_sent: bool = False) -> InlineKeyboardMarkup:
        """Действия со счётом"""
        builder = InlineKeyboardBuilder()

        if not is_sent:
            builder.row(
                InlineKeyboardButton(
                    text="📨 Отправить клиенту",
                    callback_data=f"acc:send:{doc_id}"
                )
            )
            builder.row(
                InlineKeyboardButton(
                    text="🔄 Перегенерировать",
                    callback_data=f"acc:regen:{doc_id}"
                )
            )

        builder.row(
            InlineKeyboardButton(text="🔙 К списку", callback_data="acc:pending")
        )
        return builder.as_markup()

    @staticmethod
    def confirm_send(doc_id: int) -> InlineKeyboardMarkup:
        """Подтверждение отправки клиенту"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Да, отправить",
                callback_data=f"acc:confirm_send:{doc_id}"
            ),
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data=f"acc:doc:{doc_id}"
            )
        )
        return builder.as_markup()

    @staticmethod
    def payment_confirmation(app_id: int) -> InlineKeyboardMarkup:
        """Кнопки подтверждения получения средств (для бухгалтера)"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Подтвердить получение",
                callback_data=f"acc:confirm_payment:{app_id}"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="❌ Средства не пришли",
                callback_data=f"acc:payment_not_received:{app_id}"
            )
        )
        return builder.as_markup()

    @staticmethod
    def pending_payments_list(applications: list, page: int = 0, per_page: int = 5) -> InlineKeyboardMarkup:
        """Список заявок, ожидающих подтверждения оплаты"""
        builder = InlineKeyboardBuilder()

        start = page * per_page
        end = start + per_page
        page_apps = applications[start:end]

        for app in page_apps:
            builder.row(
                InlineKeyboardButton(
                    text=f"💰 {app.external_id} | {app.amount:,.0f}₽",
                    callback_data=f"acc:check_payment:{app.id}"
                )
            )

        # Пагинация
        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton(text="⬅️", callback_data=f"acc:payments_page:{page - 1}")
            )
        if end < len(applications):
            nav_buttons.append(
                InlineKeyboardButton(text="➡️", callback_data=f"acc:payments_page:{page + 1}")
            )
        if nav_buttons:
            builder.row(*nav_buttons)

        builder.row(
            InlineKeyboardButton(text="🔙 В меню", callback_data="acc:menu")
        )
        return builder.as_markup()

    @staticmethod
    def back_to_menu() -> InlineKeyboardMarkup:
        """Кнопка возврата в меню"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="🔙 В меню", callback_data="acc:menu")
        )
        return builder.as_markup()
