# bot/services/notification.py
"""
Сервис уведомлений для отправки заявок в групповые чаты и пользователям.
"""

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from datetime import datetime

from database import ApplicationRepository, BankRepository
from keyboards.bank_kb import BankKeyboards


class NotificationService:
    """Сервис отправки уведомлений"""

    def __init__(
            self,
            bot: Bot,
            application_repo: ApplicationRepository,
            bank_repo: BankRepository
    ):
        self.bot = bot
        self.application_repo = application_repo
        self.bank_repo = bank_repo
        self.bank_kb = BankKeyboards()

    async def send_to_bank_group(self, app_id: int) -> bool:
        """
        Отправить заявку в групповой чат банка.

        Returns:
            True если отправлено успешно, False если ошибка
        """
        app = await self.application_repo.get_with_relations(app_id)
        if not app or not app.bank_id:
            return False

        bank = await self.bank_repo.get_by_id(app.bank_id)
        if not bank or not bank.chat_id:
            return False

        # Формируем сообщение
        text = self._format_bank_notification(app)

        try:
            # Отправляем в групповой чат банка
            message = await self.bot.send_message(
                chat_id=bank.chat_id,
                text=text,
                reply_markup=self.bank_kb.risk_assessment(app_id),
                parse_mode="HTML"
            )

            # Сохраняем ID сообщения в заявке
            await self.application_repo.update_by_id(
                app_id,
                bank_message_id=message.message_id,
                sent_to_bank_at=datetime.utcnow()
            )

            return True

        except TelegramAPIError as e:
            # Логируем ошибку (бот не добавлен в группу или нет прав)
            print(f"Failed to send to bank group {bank.chat_id}: {e}")
            return False

    async def notify_supervisors(self, app_id: int, message: str) -> int:
        """
        Уведомить всех руководителей о заявке.

        Returns:
            Количество успешно отправленных уведомлений
        """
        # TODO: Реализовать уведомление руководителей
        pass

    async def notify_client(self, app_id: int, message: str) -> bool:
        """
        Уведомить клиента о статусе заявки.

        Returns:
            True если отправлено успешно
        """
        app = await self.application_repo.get_by_id(app_id)
        if not app or not app.client_chat_id:
            return False

        try:
            await self.bot.send_message(
                chat_id=app.client_chat_id,
                text=message,
                parse_mode="HTML"
            )
            return True
        except TelegramAPIError:
            return False

    async def notify_manager(self, app_id: int, message: str) -> bool:
        """
        Уведомить менеджера о заявке.

        Returns:
            True если отправлено успешно
        """
        app = await self.application_repo.get_with_relations(app_id)
        if not app or not app.manager:
            return False

        try:
            await self.bot.send_message(
                chat_id=app.manager.telegram_id,
                text=message,
                parse_mode="HTML"
            )
            return True
        except TelegramAPIError:
            return False

    def _format_bank_notification(self, app) -> str:
        """Форматирование заявки для банка"""
        text = f"🏦 <b>Новая заявка на проверку</b>\n\n"
        text += f"📋 Номер: <b>{app.external_id}</b>\n"
        text += f"💰 Сумма: <b>{app.amount:,.0f}₽</b>\n"
        text += f"🏢 ИНН плательщика: <code>{app.payer_inn}</code>\n"

        if app.payer_name:
            text += f"📛 Плательщик: {app.payer_name}\n"

        text += f"📝 Назначение: {app.purpose}\n"
        text += f"📅 Создана: {app.created_at.strftime('%d.%m.%Y %H:%M')}\n"

        if app.company:
            text += f"\n🏢 <b>Компания:</b> {app.company.name}\n"

        if app.manager:
            text += f"👔 <b>Менеджер:</b> {app.manager.first_name or app.manager.username}\n"

        text += "\n<b>Оцените уровень риска:</b>"
        return text
