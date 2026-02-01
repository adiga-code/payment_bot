# bot/services/notification.py

import logging
from aiogram import Bot

from database import UserRepository

logger = logging.getLogger(__name__)


class NotificationService:
    """Сервис уведомлений для участников workflow"""

    def __init__(self, bot: Bot, user_repo: UserRepository):
        self.bot = bot
        self.user_repo = user_repo

    async def _safe_send(self, chat_id: int, text: str, **kwargs) -> bool:
        """Безопасная отправка сообщения (без исключений)"""
        try:
            await self.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", **kwargs)
            return True
        except Exception as e:
            logger.error(f"Failed to send notification to {chat_id}: {e}")
            return False

    # ==================== УВЕДОМЛЕНИЯ КЛИЕНТУ ====================

    async def notify_client_rejected(self, app, reason: str, rejected_by: str):
        """Уведомить клиента об отклонении заявки"""
        text = (
            f"❌ <b>Заявка {app.external_id} отклонена</b>\n\n"
            f"💰 Сумма: {app.amount:,.0f}₽\n"
            f"📝 Причина: {reason}\n"
            f"👤 Этап: {rejected_by}"
        )
        await self._safe_send(app.client_chat_id, text)

    async def notify_client_approved(self, app):
        """Уведомить клиента об одобрении заявки"""
        text = (
            f"✅ <b>Заявка {app.external_id} одобрена!</b>\n\n"
            f"💰 Сумма: {app.amount:,.0f}₽\n"
            f"📋 Все этапы согласования пройдены.\n\n"
            f"📄 Документы будут отправлены в ближайшее время."
        )
        await self._safe_send(app.client_chat_id, text)

    async def notify_client_contract_details_needed(self, app):
        """Уведомить клиента о необходимости заполнить данные договора"""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="📝 Заполнить данные договора",
                callback_data=f"client:fill_contract:{app.id}"
            )]
        ])

        text = (
            f"🏦 <b>Заявка {app.external_id} одобрена банком!</b>\n\n"
            f"💰 Сумма: <b>{app.amount:,.0f}₽</b>\n\n"
            f"Для формирования счёта необходимо указать:\n"
            f"• Номер договора\n"
            f"• Дату договора\n"
            f"• Назначение платежа для счёта\n\n"
            f"Нажмите кнопку ниже:"
        )
        await self._safe_send(app.client_chat_id, text, reply_markup=kb)

    # ==================== УВЕДОМЛЕНИЯ МЕНЕДЖЕРУ ====================

    async def notify_manager_returned(self, app, reason: str = "Возвращено на доработку"):
        """Уведомить менеджера о возврате заявки"""
        if not app.manager_id:
            return
        manager = await self.user_repo.get_by_id(app.manager_id)
        if not manager:
            return
        text = (
            f"↩️ <b>Заявка возвращена на доработку</b>\n\n"
            f"📋 {app.external_id}\n"
            f"💰 {app.amount:,.0f}₽\n"
            f"📝 Причина: {reason}"
        )
        await self._safe_send(manager.telegram_id, text)

    async def notify_manager_final_decision(self, app, decision: str, reason: str = None):
        """Уведомить менеджера о финальном решении руководителя"""
        if not app.manager_id:
            return
        manager = await self.user_repo.get_by_id(app.manager_id)
        if not manager:
            return

        if decision == 'approved':
            text = (
                f"✅ <b>Заявка {app.external_id} одобрена руководителем</b>\n\n"
                f"💰 {app.amount:,.0f}₽\n"
                f"🎉 Все подписи собраны."
            )
        else:
            text = (
                f"❌ <b>Заявка {app.external_id} отклонена руководителем</b>\n\n"
                f"💰 {app.amount:,.0f}₽\n"
            )
            if reason:
                text += f"📝 Причина: {reason}"
        await self._safe_send(manager.telegram_id, text)

    # ==================== УВЕДОМЛЕНИЯ РУКОВОДИТЕЛЮ ====================

    async def notify_supervisors_new_application(self, app, risk_level: str = None):
        """Уведомить руководителей о новой заявке на рассмотрение"""
        supervisors = await self.user_repo.get_supervisors()

        risk_text = ""
        if risk_level == "min_risk":
            risk_text = "⚠️ Уровень: <b>Минимальный риск</b>\n"
        elif risk_level == "no_risk":
            risk_text = "✅ Уровень: <b>Без риска</b>\n"

        text = (
            f"📥 <b>Новая заявка на финальное согласование</b>\n\n"
            f"📋 {app.external_id}\n"
            f"💰 Сумма: <b>{app.amount:,.0f}₽</b>\n"
            f"{risk_text}"
        )

        if app.payer_name:
            text += f"📛 Плательщик: {app.payer_name}\n"

        text += f"\n🔔 Используйте /supervisor для просмотра."

        for sv in supervisors:
            await self._safe_send(sv.telegram_id, text)

    async def notify_supervisors_escalation(self, app, escalated_by: str = "менеджер"):
        """Уведомить руководителей об эскалации"""
        supervisors = await self.user_repo.get_supervisors()

        text = (
            f"🚨 <b>Эскалация заявки</b>\n\n"
            f"📋 {app.external_id}\n"
            f"💰 Сумма: <b>{app.amount:,.0f}₽</b>\n"
            f"📤 Эскалирована: {escalated_by}\n\n"
            f"🔔 Требуется ваше решение. Используйте /supervisor"
        )

        for sv in supervisors:
            await self._safe_send(sv.telegram_id, text)

    # ==================== УВЕДОМЛЕНИЯ БУХГАЛТЕРУ ====================

    async def notify_accountants_invoice_ready(self, app, invoice_number: str):
        """Уведомить бухгалтеров о новом счёте"""
        accountants = await self.user_repo.get_accountants()

        text = (
            f"📄 <b>Новый счёт на отправку</b>\n\n"
            f"📋 Заявка: {app.external_id}\n"
            f"🧾 Счёт: <b>{invoice_number}</b>\n"
            f"💰 Сумма: <b>{app.amount:,.0f}₽</b>\n"
        )

        if app.payer_name:
            text += f"📛 Плательщик: {app.payer_name}\n"

        text += f"\n🔔 Используйте /accountant для просмотра."

        for acc in accountants:
            await self._safe_send(acc.telegram_id, text)
