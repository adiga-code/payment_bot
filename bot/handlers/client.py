import re
from datetime import datetime

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from services import LogicService
from database import UserRepository, ApplicationRepository
from services.notification import NotificationService


class ApplicationForm(StatesGroup):
    waiting_for_amount = State()
    waiting_for_inn = State()
    waiting_for_purpose = State()


class ContractForm(StatesGroup):
    waiting_for_contract_number = State()
    waiting_for_contract_date = State()
    waiting_for_invoice_purpose = State()


class PaymentForm(StatesGroup):
    waiting_for_failure_reason = State()  # Ожидание причины неоплаты


class ClientHandlers:
    def __init__(
            self,
            logic_service: LogicService,
            user_repo: UserRepository,
            application_repo: ApplicationRepository = None,
            notification_service: NotificationService = None
            ):
        self.router = Router()
        self.logic_service = logic_service
        self.user_repo = user_repo
        self.application_repo = application_repo
        self.notification_service = notification_service
        self._setup_handlers()

    def _setup_handlers(self):
        self.router.message(Command("start"), F.chat.type == "private")(self.start_command)
        self.router.message(Command("zayavka"), F.chat.type == "private")(self.start_application)

        self.router.message.register(self.process_amount, ApplicationForm.waiting_for_amount)
        self.router.message.register(self.process_inn, ApplicationForm.waiting_for_inn)
        self.router.message.register(self.process_purpose, ApplicationForm.waiting_for_purpose)

        # Форма данных договора (после одобрения банком)
        self.router.callback_query(F.data.startswith("client:fill_contract:"))(self.cb_start_contract_form)
        self.router.message.register(self.process_contract_number, ContractForm.waiting_for_contract_number)
        self.router.message.register(self.process_contract_date, ContractForm.waiting_for_contract_date)
        self.router.message.register(self.process_invoice_purpose, ContractForm.waiting_for_invoice_purpose)

        # Подтверждение оплаты
        self.router.callback_query(F.data.startswith("client:paid:"))(self.cb_payment_confirmed)
        self.router.callback_query(F.data.startswith("client:not_paid:"))(self.cb_payment_failed)
        self.router.message.register(self.process_failure_reason, PaymentForm.waiting_for_failure_reason)

    # ==================== СОЗДАНИЕ ЗАЯВКИ ====================

    async def start_application(self, message: Message, state: FSMContext):
        """Начало создания заявки"""
        # Авторегистрация клиента (если ещё не зарегистрирован)
        await self.user_repo.get_or_create(
            telegram_id=message.from_user.id,
            role='client',
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name
        )

        await message.answer(
            "📋 Создание заявки\n\n"
            "Введите сумму платежа (в рублях):"
        )
        await state.set_state(ApplicationForm.waiting_for_amount)

    async def process_amount(self, message: Message, state: FSMContext):
        """Обработка введенной суммы платежа"""
        amount_text = message.text
        if not amount_text.isdigit() or int(amount_text) <= 0:
            await message.answer("❗ Пожалуйста, введите корректную сумму (положительное число).")
            return
        amount = int(amount_text)
        await state.update_data(amount=amount)
        await message.answer("Введите ИНН получателя:")
        await state.set_state(ApplicationForm.waiting_for_inn)

    async def process_inn(self, message: Message, state: FSMContext):
        """Обработка введенного ИНН"""
        inn = message.text
        if not inn.isdigit() or len(inn) not in [10, 12]:
            await message.answer("❗ Пожалуйста, введите корректный ИНН (10 или 12 цифр).")
            return
        await state.update_data(inn=inn)
        data = await state.get_data()
        await message.answer('Введите назначение платежа:')
        await state.set_state(ApplicationForm.waiting_for_purpose)

    async def process_purpose(self, message: Message, state: FSMContext):
        """Обработка введенного назначения платежа"""
        purpose = message.text
        await state.update_data(purpose=purpose)
        data = await state.get_data()

        amount = data['amount']
        inn = data['inn']

        # Создаём заявку и получаем объект с external_id
        app = await self.logic_service.create_new_application({
            'amount': amount,
            'inn': inn,
            'purpose': purpose,
            'chat_id': message.from_user.id
        })

        await message.answer(
            f"✅ Ваша заявка создана!\n\n"
            f"📋 Номер заявки: {app.external_id}\n"
            f"💰 Сумма: {amount:,} руб.\n"
            f"🏢 ИНН: {inn}\n"
            f"📝 Назначение: {purpose}\n\n"
            f"🔍 Заявка отправлена на проверку.\n"
            f"Вы получите уведомление о статусе."
        )
        await state.clear()

    async def start_command(self, message: Message):
        """Команда /start - приветствие и регистрация клиента"""
        # Авторегистрация клиента
        user, created = await self.user_repo.get_or_create(
            telegram_id=message.from_user.id,
            role='client',
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name
        )

        if created:
            await message.answer(
                "👋 Добро пожаловать в Payment Bot!\n\n"
                "Вы успешно зарегистрированы.\n\n"
                "📋 Для создания заявки используйте команду /zayavka"
            )
        else:
            await message.answer(
                "👋 С возвращением!\n\n"
                "📋 Для создания заявки используйте команду /zayavka"
            )

    # ==================== ФОРМА ДАННЫХ ДОГОВОРА ====================

    async def cb_start_contract_form(self, callback: CallbackQuery, state: FSMContext):
        """Начало заполнения данных договора"""
        app_id = int(callback.data.split(":")[-1])

        if not self.application_repo:
            await callback.answer("Сервис недоступен", show_alert=True)
            return

        app = await self.application_repo.get_by_id(app_id)
        if not app:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        if app.status != 'awaiting_contract_details':
            await callback.answer("Заявка не ожидает заполнения данных", show_alert=True)
            return

        await state.update_data(contract_app_id=app_id)
        await callback.message.answer(
            f"📝 <b>Заполнение данных договора</b>\n\n"
            f"📋 Заявка: {app.external_id}\n"
            f"💰 Сумма: {app.amount:,.0f}₽\n\n"
            f"Введите <b>номер договора</b>:",
            parse_mode="HTML"
        )
        await state.set_state(ContractForm.waiting_for_contract_number)
        await callback.answer()

    async def process_contract_number(self, message: Message, state: FSMContext):
        """Обработка номера договора"""
        contract_number = message.text.strip()
        if not contract_number:
            await message.answer("❗ Введите номер договора.")
            return

        await state.update_data(contract_number=contract_number)
        await message.answer(
            f"✅ Номер договора: <b>{contract_number}</b>\n\n"
            f"Введите <b>дату договора</b> (ДД.ММ.ГГГГ):",
            parse_mode="HTML"
        )
        await state.set_state(ContractForm.waiting_for_contract_date)

    async def process_contract_date(self, message: Message, state: FSMContext):
        """Обработка даты договора"""
        date_text = message.text.strip()

        # Проверяем формат
        if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', date_text):
            await message.answer("❗ Введите дату в формате ДД.ММ.ГГГГ (например: 19.01.2026)")
            return

        # Проверяем корректность даты
        try:
            datetime.strptime(date_text, '%d.%m.%Y')
        except ValueError:
            await message.answer("❗ Некорректная дата. Введите дату в формате ДД.ММ.ГГГГ")
            return

        await state.update_data(contract_date=date_text)
        await message.answer(
            f"✅ Дата договора: <b>{date_text}</b>\n\n"
            f"Введите <b>назначение платежа</b> для счёта\n"
            f"(например: сухие смеси, строительные материалы):",
            parse_mode="HTML"
        )
        await state.set_state(ContractForm.waiting_for_invoice_purpose)

    async def process_invoice_purpose(self, message: Message, state: FSMContext):
        """Обработка назначения и завершение формы"""
        invoice_purpose = message.text.strip()
        if not invoice_purpose:
            await message.answer("❗ Введите назначение платежа.")
            return

        data = await state.get_data()
        app_id = data['contract_app_id']
        contract_number = data['contract_number']
        contract_date = data['contract_date']

        # Сохраняем данные договора
        await self.application_repo.update_by_id(
            app_id,
            contract_number=contract_number,
            contract_date=contract_date,
            invoice_purpose=invoice_purpose
        )

        # Переводим на этап руководителя
        await self.application_repo.update_status(app_id, 'supervisor_review')

        app = await self.application_repo.get_by_id(app_id)

        await message.answer(
            f"✅ <b>Данные договора сохранены!</b>\n\n"
            f"📋 Заявка: {app.external_id}\n"
            f"📄 Договор: №{contract_number} от {contract_date}\n"
            f"📝 Назначение: {invoice_purpose}\n\n"
            f"🔍 Заявка отправлена на финальное согласование.",
            parse_mode="HTML"
        )

        await state.clear()

        # Уведомляем руководителей
        if self.notification_service:
            await self.notification_service.notify_supervisors_new_application(app)

    # ==================== ПОДТВЕРЖДЕНИЕ ОПЛАТЫ ====================

    async def cb_payment_confirmed(self, callback: CallbackQuery, state: FSMContext):
        """Клиент подтвердил оплату"""
        app_id = int(callback.data.split(":")[-1])

        if not self.application_repo:
            await callback.answer("Сервис недоступен", show_alert=True)
            return

        app = await self.application_repo.get_by_id(app_id)
        if not app:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        if app.status != 'invoice_sent':
            await callback.answer("Заявка уже обработана", show_alert=True)
            return

        # Обновляем статус
        await self.application_repo.update_status(app_id, 'client_confirmed')
        await self.application_repo.update_by_id(
            app_id,
            client_confirmed_at=datetime.utcnow()
        )

        await callback.message.edit_text(
            f"✅ <b>Спасибо! Оплата отмечена.</b>\n\n"
            f"📋 Заявка: {app.external_id}\n"
            f"💰 Сумма: {app.amount:,.0f}₽\n\n"
            f"⏳ Ожидайте подтверждения поступления средств.",
            parse_mode="HTML"
        )
        await callback.answer()

        # Уведомляем бухгалтера
        if self.notification_service:
            await self.notification_service.notify_accountant_payment_confirmed(app)

    async def cb_payment_failed(self, callback: CallbackQuery, state: FSMContext):
        """Клиент не смог оплатить"""
        app_id = int(callback.data.split(":")[-1])

        if not self.application_repo:
            await callback.answer("Сервис недоступен", show_alert=True)
            return

        app = await self.application_repo.get_by_id(app_id)
        if not app:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        if app.status != 'invoice_sent':
            await callback.answer("Заявка уже обработана", show_alert=True)
            return

        # Сохраняем app_id для следующего шага
        await state.update_data(failed_payment_app_id=app_id)
        await state.set_state(PaymentForm.waiting_for_failure_reason)

        await callback.message.edit_text(
            f"❌ <b>Не удалось оплатить</b>\n\n"
            f"📋 Заявка: {app.external_id}\n\n"
            f"Пожалуйста, укажите причину:",
            parse_mode="HTML"
        )
        await callback.answer()

    async def process_failure_reason(self, message: Message, state: FSMContext):
        """Обработка причины неоплаты"""
        reason = message.text.strip()
        if not reason:
            await message.answer("❗ Пожалуйста, укажите причину.")
            return

        data = await state.get_data()
        app_id = data.get('failed_payment_app_id')

        if not app_id or not self.application_repo:
            await message.answer("❗ Ошибка. Попробуйте ещё раз.")
            await state.clear()
            return

        app = await self.application_repo.get_by_id(app_id)
        if not app:
            await message.answer("❗ Заявка не найдена.")
            await state.clear()
            return

        # Аннулируем заявку
        await self.application_repo.update_status(app_id, 'cancelled')
        await self.application_repo.update_by_id(
            app_id,
            cancellation_reason=reason
        )

        await state.clear()

        await message.answer(
            f"❌ <b>Заявка аннулирована</b>\n\n"
            f"📋 Заявка: {app.external_id}\n"
            f"💰 Сумма: {app.amount:,.0f}₽\n"
            f"📝 Причина: {reason}\n\n"
            f"Для создания новой заявки используйте /zayavka",
            parse_mode="HTML"
        )

        # Уведомляем менеджера
        if self.notification_service:
            await self.notification_service.notify_manager_payment_failed(app, reason)
