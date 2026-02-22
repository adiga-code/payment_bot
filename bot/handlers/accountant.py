# bot/handlers/accountant.py

import os
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from datetime import datetime

from database import (
    ApplicationRepository,
    UserRepository,
    DocumentRepository,
    LogRepository,
    BankRepository,
    CompanyBankRepository,
)
from services.notification import NotificationService
from services.document import DocumentService
from keyboards.accountant_kb import AccountantKeyboards
from middleware import RoleRequiredMiddleware
from utils import format_application_number


class AccountantStates(StatesGroup):
    """FSM состояния для бухгалтера"""
    waiting_for_purpose = State()       # Ожидание ввода назначения платежа
    filling_invoice_field = State()     # Поочерёдный ввод недостающих данных для счёта


class AccountantHandlers:
    """Хендлеры для бухгалтера"""

    ALLOWED_ROLES = ['accountant', 'supervisor', 'admin']

    def __init__(
            self,
            user_repo: UserRepository,
            application_repo: ApplicationRepository,
            document_repo: DocumentRepository,
            log_repo: LogRepository,
            bot: Bot,
            notification_service: NotificationService = None,
            document_service: DocumentService = None,
            bank_repo: BankRepository = None,
            company_bank_repo: CompanyBankRepository = None,
    ):
        self.router = Router()
        self.user_repo = user_repo
        self.application_repo = application_repo
        self.document_repo = document_repo
        self.log_repo = log_repo
        self.bot = bot
        self.notification_service = notification_service
        self.document_service = document_service
        self.bank_repo = bank_repo
        self.company_bank_repo = company_bank_repo
        self.kb = AccountantKeyboards()

        self._setup_middleware()
        self._setup_handlers()

    def _setup_middleware(self):
        """Настройка middleware для проверки роли"""
        role_middleware = RoleRequiredMiddleware(self.ALLOWED_ROLES, self.user_repo)
        self.router.message.middleware(role_middleware)
        self.router.callback_query.middleware(role_middleware)

    def _setup_handlers(self):
        """Регистрация хендлеров"""
        self.router.message(Command("accountant"))(self.cmd_accountant)

        self.router.callback_query(F.data == "acc:menu")(self.cb_menu)
        self.router.callback_query(F.data == "acc:pending")(self.cb_pending_invoices)
        self.router.callback_query(F.data == "acc:sent")(self.cb_sent_invoices)
        self.router.callback_query(F.data == "acc:stats")(self.cb_stats)
        self.router.callback_query(F.data == "acc:set_purpose")(self.cb_set_purpose)
        self.router.callback_query(F.data.startswith("acc:page:"))(self.cb_page)
        self.router.callback_query(F.data.startswith("acc:doc:"))(self.cb_view_invoice)
        self.router.callback_query(F.data.startswith("acc:send:"))(self.cb_send_to_client)
        self.router.callback_query(F.data.startswith("acc:confirm_send:"))(self.cb_confirm_send)
        self.router.callback_query(F.data.startswith("acc:regen:"))(self.cb_regenerate)
        self.router.callback_query(F.data.startswith("acc:fill:"))(self.cb_fill_invoice_data)

        # FSM обработчики
        self.router.message(AccountantStates.waiting_for_purpose)(self.process_purpose)
        self.router.message(AccountantStates.filling_invoice_field)(self.process_invoice_field)

        # Подтверждение получения средств
        self.router.callback_query(F.data.startswith("acc:confirm_payment:"))(self.cb_confirm_payment)
        self.router.callback_query(F.data.startswith("acc:payment_not_received:"))(self.cb_payment_not_received)

    # ==================== КОМАНДЫ ====================

    async def cmd_accountant(self, message: Message, db_user):
        """Команда /accountant — главное меню бухгалтера"""
        pending_count = len(await self._get_pending_invoices())
        await message.answer(
            f"📑 <b>Панель бухгалтера</b>\n\n"
            f"📄 Счетов на отправку: <b>{pending_count}</b>",
            reply_markup=self.kb.main_menu(),
            parse_mode="HTML"
        )

    # ==================== CALLBACKS ====================

    async def cb_menu(self, callback: CallbackQuery, db_user):
        """Возврат в главное меню"""
        pending_count = len(await self._get_pending_invoices())
        await self._safe_edit(
            callback,
            f"📑 <b>Панель бухгалтера</b>\n\n"
            f"📄 Счетов на отправку: <b>{pending_count}</b>",
            reply_markup=self.kb.main_menu(),
        )
        await callback.answer()

    async def cb_pending_invoices(self, callback: CallbackQuery, db_user):
        """Список неотправленных счетов"""
        invoices = await self._get_pending_invoices()

        if not invoices:
            await self._safe_edit(
                callback,
                "📄 Нет счетов, ожидающих отправки.",
                reply_markup=self.kb.back_to_menu(),
            )
            await callback.answer()
            return

        await self._safe_edit(
            callback,
            f"📄 <b>Счета на отправку ({len(invoices)})</b>",
            reply_markup=self.kb.invoices_list(invoices, list_type="pending"),
        )
        await callback.answer()

    async def cb_sent_invoices(self, callback: CallbackQuery, db_user):
        """Список отправленных счетов"""
        invoices = await self._get_sent_invoices()

        if not invoices:
            await self._safe_edit(
                callback,
                "📨 Нет отправленных счетов.",
                reply_markup=self.kb.back_to_menu(),
            )
            await callback.answer()
            return

        await self._safe_edit(
            callback,
            f"📨 <b>Отправленные счета ({len(invoices)})</b>",
            reply_markup=self.kb.invoices_list(invoices, list_type="sent"),
        )
        await callback.answer()

    async def cb_page(self, callback: CallbackQuery, db_user):
        """Пагинация списка счетов"""
        parts = callback.data.split(":")
        list_type = parts[2]
        page = int(parts[3])

        if list_type == "pending":
            invoices = await self._get_pending_invoices()
            title = "Счета на отправку"
        else:
            invoices = await self._get_sent_invoices()
            title = "Отправленные счета"

        await self._safe_edit(
            callback,
            f"📄 <b>{title} ({len(invoices)})</b>",
            reply_markup=self.kb.invoices_list(invoices, list_type=list_type, page=page),
        )
        await callback.answer()

    async def cb_view_invoice(self, callback: CallbackQuery, db_user):
        """Просмотр деталей счёта"""
        doc_id = int(callback.data.split(":")[-1])
        doc = await self.document_repo.get_by_id(doc_id)

        if not doc:
            await callback.answer("Документ не найден", show_alert=True)
            return

        app = await self.application_repo.get_with_relations(doc.application_id)
        if not app:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        is_sent = doc.sent_to_client_at is not None

        company_name = app.company.name if app.company else "—"
        bank_name = app.bank.name if app.bank else "—"
        sent_status = (
            f"✅ Отправлен {doc.sent_to_client_at.strftime('%d.%m.%Y %H:%M')}"
            if is_sent else "⏳ Не отправлен клиенту"
        )

        text = (
            f"📄 <b>Счёт {doc.number}</b>\n\n"
            f"📋 {format_application_number(app, for_client=True)}\n"
            f"💰 Сумма: <b>{app.amount:,.0f}₽</b>\n"
            f"🏢 Компания: {company_name}\n"
            f"🏦 Банк: {bank_name}\n"
            f"📛 Плательщик: {app.payer_name or '—'}\n"
            f"📝 Назначение: {app.purpose}\n\n"
            f"📌 Статус: {sent_status}"
        )

        # Отправляем файл документа + текст с кнопками
        if doc.file_path and os.path.exists(doc.file_path):
            # Удаляем старое сообщение и отправляем новое с файлом
            await callback.message.delete()
            file = FSInputFile(doc.file_path)
            await self.bot.send_document(
                chat_id=callback.message.chat.id,
                document=file,
                caption=text,
                reply_markup=self.kb.invoice_actions(doc_id, is_sent=is_sent),
                parse_mode="HTML"
            )
        else:
            await self._safe_edit(
                callback,
                text + "\n\n⚠️ Файл счёта не найден на сервере.",
                reply_markup=self.kb.invoice_actions(doc_id, is_sent=is_sent),
            )

        await callback.answer()

    async def cb_send_to_client(self, callback: CallbackQuery, db_user):
        """Запрос подтверждения отправки клиенту"""
        doc_id = int(callback.data.split(":")[-1])
        doc = await self.document_repo.get_by_id(doc_id)

        if not doc:
            await callback.answer("Документ не найден", show_alert=True)
            return

        await self.bot.send_message(
            chat_id=callback.message.chat.id,
            text=(
                f"📨 <b>Отправить счёт {doc.number} клиенту?</b>\n\n"
                f"Счёт будет отправлен в чат клиента."
            ),
            reply_markup=self.kb.confirm_send(doc_id),
            parse_mode="HTML"
        )
        await callback.answer()

    async def cb_confirm_send(self, callback: CallbackQuery, db_user):
        """Подтверждённая отправка счёта клиенту"""
        doc_id = int(callback.data.split(":")[-1])
        doc = await self.document_repo.get_by_id(doc_id)

        if not doc:
            await callback.answer("Документ не найден", show_alert=True)
            return

        if doc.sent_to_client_at:
            await callback.answer("Счёт уже был отправлен ранее", show_alert=True)
            return

        app = await self.application_repo.get_with_relations(doc.application_id)
        if not app:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        # Отправляем файл клиенту
        sent = False
        if doc.file_path and os.path.exists(doc.file_path):
            try:
                file = FSInputFile(doc.file_path)
                await self.bot.send_document(
                    chat_id=app.client_chat_id,
                    document=file,
                    caption=(
                        f"📄 <b>Счёт на оплату {doc.number}</b>\n\n"
                        f"💰 Сумма: <b>{app.amount:,.0f}₽</b>\n"
                        f"📋 {format_application_number(app, for_client=True)}"
                    ),
                    parse_mode="HTML"
                )
                sent = True
            except Exception as e:
                await self._safe_edit(
                    callback,
                    f"❌ Ошибка отправки клиенту: {e}",
                    reply_markup=self.kb.back_to_menu(),
                )
                await callback.answer()
                return

        if not sent:
            await self._safe_edit(
                callback,
                "❌ Файл счёта не найден на сервере.",
                reply_markup=self.kb.back_to_menu(),
            )
            await callback.answer()
            return

        # Обновляем статус документа
        await self.document_repo.update_by_id(
            doc_id,
            sent_to_client_at=datetime.utcnow()
        )

        # Обновляем статус заявки на 'invoice_sent'
        await self.application_repo.update_status(app.id, 'invoice_sent')
        await self.application_repo.update_by_id(
            app.id,
            invoice_sent_at=datetime.utcnow()
        )

        # Отправляем клиенту уведомление с кнопками подтверждения оплаты
        if self.notification_service:
            await self.notification_service.notify_client_invoice_sent(app)

        # Лог
        await self.log_repo.create_log(
            action='invoice_sent_to_client',
            application_id=app.id,
            user_id=db_user.id,
            details={'document_id': doc_id, 'invoice_number': doc.number}
        )

        await self._safe_edit(
            callback,
            f"✅ <b>Счёт {doc.number} отправлен клиенту!</b>\n\n"
            f"📋 {format_application_number(app, for_client=True)}\n"
            f"💰 Сумма: {app.amount:,.0f}₽\n\n"
            f"⏳ Ожидаем подтверждения оплаты от клиента.",
            reply_markup=self.kb.back_to_menu(),
        )
        await callback.answer("Отправлено!")

    async def cb_regenerate(self, callback: CallbackQuery, db_user):
        """Перегенерация счёта"""
        doc_id = int(callback.data.split(":")[-1])
        doc = await self.document_repo.get_by_id(doc_id)

        if not doc:
            await callback.answer("Документ не найден", show_alert=True)
            return

        if doc.sent_to_client_at:
            await callback.answer("Нельзя перегенерировать отправленный счёт", show_alert=True)
            return

        if not self.document_service:
            await callback.answer("Сервис документов недоступен", show_alert=True)
            return

        app_id = doc.application_id

        # Проверяем обязательные поля перед генерацией
        missing = await self.document_service.validate_invoice_data(app_id)
        if missing:
            fields_text = "\n".join(f"  • {f['label']}" for f in missing)
            await self._safe_edit(
                callback,
                f"⚠️ <b>Не хватает данных для счёта</b>\n\n"
                f"❌ Не заполнены обязательные поля:\n{fields_text}",
                reply_markup=self.kb.fill_invoice_data(app_id),
            )
            await callback.answer()
            return

        # Генерируем новый счёт (старый деактивируется внутри generate_invoice)
        file_path = await self.document_service.generate_invoice(app_id)

        if not file_path:
            await callback.answer("Ошибка генерации счёта", show_alert=True)
            return

        # Получаем новый документ
        new_doc = await self.document_repo.get_latest_invoice(app_id)
        if not new_doc:
            await callback.answer("Ошибка: документ не найден", show_alert=True)
            return

        # Лог
        await self.log_repo.create_log(
            action='invoice_regenerated',
            application_id=app_id,
            user_id=db_user.id,
            details={'old_doc_id': doc_id, 'new_doc_id': new_doc.id, 'invoice_number': new_doc.number}
        )

        app = await self.application_repo.get_with_relations(app_id)
        company_name = app.company.name if app and app.company else "—"
        bank_name = app.bank.name if app and app.bank else "—"

        text = (
            f"🔄 <b>Счёт перегенерирован</b>\n\n"
            f"📄 Новый: <b>{new_doc.number}</b>\n"
            f"📋 {format_application_number(app, for_client=True)}\n"
            f"💰 Сумма: <b>{app.amount:,.0f}₽</b>\n"
            f"🏢 Компания: {company_name}\n"
            f"🏦 Банк: {bank_name}\n\n"
            f"📌 Статус: ⏳ Не отправлен клиенту"
        )

        # Отправляем новый файл
        try:
            await callback.message.delete()
        except Exception:
            pass

        file = FSInputFile(file_path)
        await self.bot.send_document(
            chat_id=callback.message.chat.id,
            document=file,
            caption=text,
            reply_markup=self.kb.invoice_actions(new_doc.id, is_sent=False),
            parse_mode="HTML"
        )
        await callback.answer("Счёт перегенерирован")

    async def cb_stats(self, callback: CallbackQuery, db_user):
        """Статистика бухгалтера"""
        pending = await self._get_pending_invoices()
        sent = await self._get_sent_invoices()

        await self._safe_edit(
            callback,
            f"📊 <b>Статистика</b>\n\n"
            f"📄 Ожидают отправки: <b>{len(pending)}</b>\n"
            f"📨 Отправлено: <b>{len(sent)}</b>",
            reply_markup=self.kb.back_to_menu(),
        )
        await callback.answer()

    # ==================== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ====================

    async def _safe_edit(
        self,
        callback: CallbackQuery,
        text: str,
        reply_markup=None,
        parse_mode: str = "HTML",
    ) -> None:
        """
        Редактирует текстовое сообщение или заменяет медиа-сообщение новым текстом.
        edit_text() не работает на сообщениях с файлами (только caption), поэтому
        в таком случае удаляем старое сообщение и отправляем новое.
        """
        if callback.message.text is not None:
            await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            try:
                await callback.message.delete()
            except Exception:
                pass
            await self.bot.send_message(
                chat_id=callback.message.chat.id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )



    async def _get_pending_invoices(self) -> list:
        """Получить счета, не отправленные клиенту"""
        from sqlalchemy import select
        from database.models import Document, Application

        async with self.document_repo.session_maker() as session:
            result = await session.execute(
                select(Document, Application)
                .join(Application, Document.application_id == Application.id)
                .where(
                    Document.type == 'invoice',
                    Document.is_active == True,
                    Document.sent_to_client_at.is_(None),
                )
                .order_by(Document.generated_at.desc())
            )
            rows = result.all()
            return [{'doc': row[0], 'app': row[1]} for row in rows]

    async def _get_sent_invoices(self) -> list:
        """Получить отправленные счета"""
        from sqlalchemy import select
        from database.models import Document, Application

        async with self.document_repo.session_maker() as session:
            result = await session.execute(
                select(Document, Application)
                .join(Application, Document.application_id == Application.id)
                .where(
                    Document.type == 'invoice',
                    Document.is_active == True,
                    Document.sent_to_client_at.is_not(None),
                )
                .order_by(Document.sent_to_client_at.desc())
                .limit(20)
            )
            rows = result.all()
            return [{'doc': row[0], 'app': row[1]} for row in rows]

    # ==================== ПОДТВЕРЖДЕНИЕ ПОЛУЧЕНИЯ СРЕДСТВ ====================

    async def cb_confirm_payment(self, callback: CallbackQuery, db_user):
        """Бухгалтер подтверждает получение средств"""
        app_id = int(callback.data.split(":")[-1])

        app = await self.application_repo.get_with_relations(app_id)
        if not app:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        if app.status != 'client_confirmed':
            await callback.answer("Заявка уже обработана", show_alert=True)
            return

        # Обновляем статус
        await self.application_repo.update_status(app_id, 'payment_received')
        await self.application_repo.update_by_id(
            app_id,
            payment_received_at=datetime.utcnow()
        )

        # Лог
        await self.log_repo.create_log(
            action='payment_confirmed_by_accountant',
            application_id=app_id,
            user_id=db_user.id
        )

        await self._safe_edit(
            callback,
            f"✅ <b>Получение средств подтверждено!</b>\n\n"
            f"📋 {format_application_number(app, for_client=True)}\n"
            f"💰 Сумма: {app.amount:,.0f}₽\n\n"
            f"📤 Менеджер уведомлён для выбора формата выдачи.",
        )
        await callback.answer("Подтверждено!")

        # Уведомляем менеджера для выбора T+N
        if self.notification_service:
            await self.notification_service.notify_manager_payout_selection(app)

    async def cb_payment_not_received(self, callback: CallbackQuery, db_user):
        """Бухгалтер отмечает, что средства не поступили"""
        app_id = int(callback.data.split(":")[-1])

        app = await self.application_repo.get_with_relations(app_id)
        if not app:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        if app.status != 'client_confirmed':
            await callback.answer("Заявка уже обработана", show_alert=True)
            return

        # Аннулируем заявку
        await self.application_repo.update_status(app_id, 'cancelled')
        await self.application_repo.update_by_id(
            app_id,
            cancellation_reason="Средства не поступили на счёт"
        )

        # Лог
        await self.log_repo.create_log(
            action='payment_not_received',
            application_id=app_id,
            user_id=db_user.id
        )

        await self._safe_edit(
            callback,
            f"❌ <b>Средства не поступили</b>\n\n"
            f"📋 {format_application_number(app, for_client=True)}\n"
            f"💰 Сумма: {app.amount:,.0f}₽\n\n"
            f"⚠️ Заявка аннулирована. Клиент уведомлён.",
        )
        await callback.answer()

        # Уведомляем клиента
        if self.notification_service:
            await self.notification_service.notify_client_payment_not_received(app)

    async def cb_set_purpose(self, callback: CallbackQuery, state: FSMContext, db_user):
        """Настройка назначения платежа по умолчанию"""
        # Получаем текущее назначение
        current_purpose = db_user.default_invoice_purpose or "не установлено"
        
        await self._safe_edit(
            callback,
            f"⚙️ <b>Настройка назначения платежа</b>\n\n"
            f"Текущее значение:\n"
            f"<i>{current_purpose}</i>\n\n"
            f"Введите новое назначение платежа, которое будет использоваться для всех счетов:\n"
            f"Например: <i>за строительные материалы</i>",
        )
        await state.set_state(AccountantStates.waiting_for_purpose)
        await callback.answer()

    async def process_purpose(self, message: Message, state: FSMContext, db_user):
        """Обработка введенного назначения платежа"""
        purpose = message.text.strip()

        if not purpose:
            await message.answer("❗ Введите назначение платежа")
            return

        # Сохраняем назначение
        await self.user_repo.update_by_id(db_user.id, default_invoice_purpose=purpose)
        await state.clear()

        await message.answer(
            f"✅ <b>Назначение платежа сохранено!</b>\n\n"
            f"Новое значение:\n"
            f"<i>{purpose}</i>\n\n"
            f"Это назначение будет использоваться для всех новых счетов.",
            parse_mode="HTML"
        )

    # ==================== FSM: ЗАПОЛНЕНИЕ ДАННЫХ ДЛЯ СЧЁТА ====================

    async def cb_fill_invoice_data(self, callback: CallbackQuery, state: FSMContext, db_user):
        """Начало FSM-диалога заполнения недостающих полей для счёта"""
        app_id = int(callback.data.split(":")[-1])

        if not self.document_service:
            await callback.answer("Сервис документов недоступен", show_alert=True)
            return

        missing = await self.document_service.validate_invoice_data(app_id)

        if not missing:
            # Все поля заполнены — генерируем сразу
            await self._safe_edit(callback, "⏳ Генерирую счёт...")
            file_path = await self.document_service.generate_invoice(app_id)
            if not file_path:
                await self._safe_edit(
                    callback,
                    "❌ Ошибка генерации счёта.",
                    reply_markup=self.kb.back_to_menu(),
                )
                await callback.answer()
                return
            new_doc = await self.document_repo.get_latest_invoice(app_id)
            app = await self.application_repo.get_with_relations(app_id)
            text = (
                f"🧾 <b>Счёт сгенерирован: {new_doc.number}</b>\n\n"
                f"📋 {format_application_number(app, for_client=True)}\n"
                f"💰 Сумма: <b>{app.amount:,.0f}₽</b>"
            )
            try:
                await callback.message.delete()
            except Exception:
                pass
            file = FSInputFile(file_path)
            await self.bot.send_document(
                chat_id=callback.message.chat.id,
                document=file,
                caption=text,
                reply_markup=self.kb.invoice_actions(new_doc.id, is_sent=False),
                parse_mode="HTML",
            )
            await callback.answer("Счёт сгенерирован!")
            return

        # Сохраняем список недостающих полей в FSM и запрашиваем первое
        await state.set_state(AccountantStates.filling_invoice_field)
        await state.update_data(app_id=app_id, fields=missing, current=0)

        field = missing[0]
        await self._safe_edit(
            callback,
            f"✏️ <b>Заполнение данных для счёта</b> (1/{len(missing)})\n\n"
            f"Введите <b>{field['label']}</b>:",
        )
        await callback.answer()

    async def process_invoice_field(self, message: Message, state: FSMContext, db_user):
        """Обработка введённого значения поля и переход к следующему"""
        data = await state.get_data()
        fields = data['fields']
        current = data['current']
        app_id = data['app_id']
        field = fields[current]

        value = message.text.strip()
        if not value:
            await message.answer("❗ Значение не может быть пустым. Введите ещё раз:")
            return

        saved = await self._save_invoice_field(field, value)
        if not saved:
            await message.answer("❌ Ошибка сохранения. Попробуйте ещё раз:")
            return

        next_idx = current + 1
        if next_idx < len(fields):
            await state.update_data(current=next_idx)
            next_field = fields[next_idx]
            await message.answer(
                f"✅ Сохранено!\n\n"
                f"✏️ <b>Поле {next_idx + 1}/{len(fields)}</b>\n\n"
                f"Введите <b>{next_field['label']}</b>:",
                parse_mode="HTML",
            )
        else:
            # Все поля заполнены — генерируем счёт
            await state.clear()
            await message.answer("✅ Все данные заполнены! Генерирую счёт...", parse_mode="HTML")
            file_path = await self.document_service.generate_invoice(app_id)
            if not file_path:
                await message.answer(
                    "❌ Ошибка генерации счёта. Попробуйте «Переформировать» из меню."
                )
                return
            new_doc = await self.document_repo.get_latest_invoice(app_id)
            app = await self.application_repo.get_with_relations(app_id)
            text = (
                f"🧾 <b>Счёт сгенерирован: {new_doc.number}</b>\n\n"
                f"📋 {format_application_number(app, for_client=True)}\n"
                f"💰 Сумма: <b>{app.amount:,.0f}₽</b>"
            )
            file = FSInputFile(file_path)
            await self.bot.send_document(
                chat_id=message.chat.id,
                document=file,
                caption=text,
                reply_markup=self.kb.invoice_actions(new_doc.id, is_sent=False),
                parse_mode="HTML",
            )

    async def _save_invoice_field(self, field: dict, value: str) -> bool:
        """Сохраняет значение поля в нужную модель БД"""
        import logging as _logging
        logger = _logging.getLogger(__name__)

        model = field['model']
        model_id = field['model_id']
        attr = field['attr']

        try:
            if model == 'bank' and self.bank_repo:
                await self.bank_repo.update_by_id(model_id, **{attr: value})
                return True

            elif model == 'company':
                company_repo = getattr(self.document_service, 'company_repo', None)
                if company_repo:
                    await company_repo.update_by_id(model_id, **{attr: value})
                    return True

            elif model == 'company_bank':
                if model_id and self.company_bank_repo:
                    await self.company_bank_repo.update_by_id(model_id, **{attr: value})
                    return True
                elif not model_id:
                    # Запись CompanyBank ещё не существует — создаём
                    company_id = field.get('company_id')
                    bank_id = field.get('bank_id')
                    company_repo = getattr(self.document_service, 'company_repo', None)
                    if company_repo and company_id and bank_id:
                        await company_repo.create_company_bank(company_id, bank_id, value, False)
                        return True

        except Exception as e:
            logger.error(f"Error saving invoice field {field}: {e}")

        return False
