from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from services import LogicService
from database import UserRepository


class ApplicationForm(StatesGroup):
    waiting_for_amount = State()
    waiting_for_inn = State()
    waiting_for_purpose = State()


class ClientHandlers:
    def __init__(
            self,
            logic_service: LogicService,
            user_repo: UserRepository
            ):
        self.router = Router()
        self.logic_service = logic_service
        self.user_repo = user_repo
        self._setup_handlers()

    def _setup_handlers(self):
        self.router.message(Command("start"))(self.start_command)
        self.router.message(Command("zayavka"))(self.start_application)

        self.router.message.register(self.process_amount, ApplicationForm.waiting_for_amount)
        self.router.message.register(self.process_inn, ApplicationForm.waiting_for_inn)
        self.router.message.register(self.process_purpose, ApplicationForm.waiting_for_purpose)


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