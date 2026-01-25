from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from services import LogicService

class ApplicationForm(StatesGroup):
    waiting_for_amount = State()
    waiting_for_inn = State()
    waiting_for_purpose = State()

class ClientHandlers:
    def __init__(
            self, 
            logic_service: LogicService
            ):
        self.router = Router()
        self._setup_handlers()
        self.logic_service = logic_service

    def _setup_handlers(self):
        self.router.message(Command("start"))(self.start_command)
        self.router.message(Command("zayavka"))(self.start_application)

        self.router.message.register(self.process_amount, ApplicationForm.waiting_for_amount)
        self.router.message.register(self.process_inn, ApplicationForm.waiting_for_inn)
        self.router.message.register(self.process_purpose, ApplicationForm.waiting_for_purpose)


    async def start_application(self, message: Message, state: FSMContext):
        """Начало создания заявки"""
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

        await self.logic_service.create_new_application({
            'amount': amount,
            'inn': inn,
            'purpose': purpose,
            'chat_id': message.from_user.id
        })

        await message.answer(
            f"✅ Ваша заявка создана!\n\n"
            f"Сумма: {amount} руб.\n"
            f"ИНН: {inn}\n"
            f"Назначение: {purpose}\n\n"
            f"Спасибо за использование нашего бота!"
        )
        await state.clear()

    async def start_command(self, message: Message):
        await message.answer("Welcome to the Payment Bot! How can I assist you today?")