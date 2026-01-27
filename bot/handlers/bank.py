# bot/handlers/bank.py
"""
Хендлер для обработки заявок в групповых чатах банков.

Работает так:
1. Менеджер одобряет заявку и выбирает банк
2. Бот отправляет сообщение в групповой чат банка с кнопками
3. Сотрудники банка (привязанные к этому банку) могут нажимать кнопки
4. После нажатия кнопки сообщение обновляется (кнопки блокируются)
"""

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery
from datetime import datetime

from database import (
    ApplicationRepository,
    ApprovalRepository,
    UserRepository,
    BankRepository,
    LogRepository
)
from keyboards.bank_kb import BankKeyboards


class BankGroupHandlers:
    """Хендлеры для группового чата банка"""

    def __init__(
            self,
            user_repo: UserRepository,
            application_repo: ApplicationRepository,
            approval_repo: ApprovalRepository,
            bank_repo: BankRepository,
            log_repo: LogRepository,
            bot: Bot
    ):
        self.router = Router()
        self.user_repo = user_repo
        self.application_repo = application_repo
        self.approval_repo = approval_repo
        self.bank_repo = bank_repo
        self.log_repo = log_repo
        self.bot = bot
        self.kb = BankKeyboards()

        self._setup_handlers()

    def _setup_handlers(self):
        """Регистрация обработчиков"""
        # Callback handlers для группового чата (без middleware!)
        self.router.callback_query(F.data.startswith("bankgrp:"))(self.handle_bank_callback)

    async def handle_bank_callback(self, callback: CallbackQuery):
        """Обработка всех callback из группового чата банка"""
        # Разбираем callback data
        parts = callback.data.split(":")
        action = parts[1] if len(parts) > 1 else None

        # Пустое действие (заглушка)
        if action == "noop":
            await callback.answer("Заявка уже обработана", show_alert=False)
            return

        # Получаем банк по chat_id
        chat_id = callback.message.chat.id
        bank = await self.bank_repo.get_by_chat_id(chat_id)

        if not bank:
            await callback.answer("Этот чат не привязан к банку", show_alert=True)
            return

        # Проверяем что пользователь - сотрудник этого банка
        telegram_id = callback.from_user.id
        is_employee = await self.user_repo.is_bank_employee(telegram_id, bank.id)

        if not is_employee:
            await callback.answer(
                "У вас нет прав для обработки заявок этого банка",
                show_alert=True
            )
            return

        # Получаем пользователя
        db_user = await self.user_repo.get_by_telegram_id(telegram_id)

        # Обрабатываем действия
        if action == "risk":
            await self._handle_risk_assessment(callback, parts, db_user, bank)
        elif action == "reject_confirm":
            await self._handle_reject_confirm(callback, parts, db_user, bank)
        elif action == "back":
            await self._handle_back(callback, parts)

    async def _handle_risk_assessment(self, callback: CallbackQuery, parts: list, db_user, bank):
        """Оценка риска"""
        app_id = int(parts[2])
        risk_level = parts[3]

        app = await self.application_repo.get_with_relations(app_id)
        if not app:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        # Проверяем что заявка ещё на этапе bank_review
        if app.status != 'bank_review':
            await callback.answer("Заявка уже обработана", show_alert=True)
            return

        # Высокий риск - показываем подтверждение
        if risk_level == "high_risk":
            await callback.message.edit_text(
                f"❌ <b>Высокий риск</b>\n\n"
                f"📋 Заявка: {app.external_id}\n"
                f"💰 Сумма: {app.amount:,.0f}₽\n"
                f"🏢 ИНН: {app.payer_inn}\n\n"
                f"Заявка будет <b>отклонена</b>.\n"
                f"Подтвердите действие:",
                reply_markup=self.kb.confirm_high_risk(app_id),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        # Одобряем этап банка
        pending_approval = await self.approval_repo.get_by_role(app_id, 'bank')
        if pending_approval and not pending_approval.decision:
            comment = "Без риска" if risk_level == "no_risk" else "Минимальный риск"
            await self.approval_repo.approve(pending_approval.id, db_user.id, comment)

        # Логируем
        await self.log_repo.create_log(
            action='bank_approved',
            application_id=app_id,
            user_id=db_user.id,
            details={'risk_level': risk_level, 'bank_id': bank.id}
        )

        # Обновляем время ответа банка
        await self.application_repo.update_by_id(app_id, bank_response_at=datetime.utcnow())

        if risk_level == "min_risk":
            # Минимальный риск - эскалация к руководителю
            await self.approval_repo.create_escalation(
                app_id=app_id,
                role='supervisor',
                reason='Минимальный риск - требуется решение руководителя',
                sequence=0
            )

        # Отправляем к руководителю
        await self.application_repo.update_status(app_id, 'supervisor_review')

        # Обновляем сообщение в чате банка
        user_name = db_user.first_name or db_user.username or str(db_user.telegram_id)
        status_text = "✅ Без риска" if risk_level == "no_risk" else "⚠️ Минимальный риск"

        await callback.message.edit_text(
            f"📋 <b>Заявка {app.external_id}</b>\n\n"
            f"💰 Сумма: {app.amount:,.0f}₽\n"
            f"🏢 ИНН плательщика: {app.payer_inn}\n"
            f"📝 Назначение: {app.purpose}\n\n"
            f"<b>{status_text}</b>\n"
            f"👤 Обработал: {user_name}\n"
            f"📤 Отправлено руководителю",
            reply_markup=self.kb.processed(risk_level, user_name),
            parse_mode="HTML"
        )
        await callback.answer(f"Заявка отправлена руководителю ({status_text})")

        # TODO: Уведомить руководителя

    async def _handle_reject_confirm(self, callback: CallbackQuery, parts: list, db_user, bank):
        """Подтверждение отклонения (высокий риск)"""
        app_id = int(parts[2])
        app = await self.application_repo.get_by_id(app_id)

        if not app:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        if app.status != 'bank_review':
            await callback.answer("Заявка уже обработана", show_alert=True)
            return

        # Отклоняем этап банка
        pending_approval = await self.approval_repo.get_by_role(app_id, 'bank')
        if pending_approval:
            await self.approval_repo.reject(pending_approval.id, db_user.id, "Высокий риск")

        # Обновляем статус заявки
        await self.application_repo.update_status(app_id, 'rejected')
        await self.application_repo.update_by_id(app_id, bank_response_at=datetime.utcnow())

        # Логируем
        await self.log_repo.create_log(
            action='bank_rejected',
            application_id=app_id,
            user_id=db_user.id,
            details={'reason': 'high_risk', 'bank_id': bank.id}
        )

        # Обновляем сообщение
        user_name = db_user.first_name or db_user.username or str(db_user.telegram_id)

        await callback.message.edit_text(
            f"📋 <b>Заявка {app.external_id}</b>\n\n"
            f"💰 Сумма: {app.amount:,.0f}₽\n"
            f"🏢 ИНН плательщика: {app.payer_inn}\n\n"
            f"<b>❌ ОТКЛОНЕНО</b>\n"
            f"📝 Причина: Высокий риск\n"
            f"👤 Отклонил: {user_name}",
            reply_markup=self.kb.processed("high_risk", user_name),
            parse_mode="HTML"
        )
        await callback.answer("Заявка отклонена")

        # TODO: Уведомить клиента и менеджера

    async def _handle_back(self, callback: CallbackQuery, parts: list):
        """Возврат к оценке риска"""
        app_id = int(parts[2])
        app = await self.application_repo.get_with_relations(app_id)

        if not app:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        if app.status != 'bank_review':
            await callback.answer("Заявка уже обработана", show_alert=True)
            return

        # Возвращаем исходное сообщение с кнопками
        text = self._format_application(app)
        await callback.message.edit_text(
            text,
            reply_markup=self.kb.risk_assessment(app_id),
            parse_mode="HTML"
        )
        await callback.answer()

    def _format_application(self, app) -> str:
        """Форматирование заявки для сообщения в группе"""
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


# Для обратной совместимости
BankHandlers = BankGroupHandlers
