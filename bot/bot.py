import logging
import secrets
import string
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.types import ChatMemberUpdated
from aiogram.filters import ChatMemberUpdatedFilter, IS_NOT_MEMBER, MEMBER, ADMINISTRATOR

from handlers import ClientHandlers, ManagerHandlers, AdminHandlers, BankHandlers, SupervisorHandlers
from database import DatabaseManager
from database import ApplicationRepository, UserRepository, LogRepository, ApprovalRepository, BankRepository, CompanyRepository, DocumentRepository, SettingRepository
from services import LogicService
logging.basicConfig(level=logging.INFO)


def generate_group_code() -> str:
    """Генерация 6-символьного кода подтверждения"""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(6))


class PaymentBot:
    def __init__(self, config):
        self.Bot = Bot(token=config.BOT_TOKEN)
        self.dp = Dispatcher()
        self.config = config
        self.pending_group_codes: dict = {}  # {code: {"chat_id": int, "chat_title": str, "created_at": datetime}}


    async def _setup_database(self):
        self.db_manager = DatabaseManager(self.config.DATABASE_URL)
        await self.db_manager.initialise()

    async def _setup_repositories(self):
        self.user_repo = UserRepository(self.db_manager.async_session)
        self.application_repo = ApplicationRepository(self.db_manager.async_session)
        self.log_repo = LogRepository(self.db_manager.async_session)
        self.approval_repo = ApprovalRepository(self.db_manager.async_session)
        self.company_repo = CompanyRepository(self.db_manager.async_session)
        self.bank_repo = BankRepository(self.db_manager.async_session)
        self.document_repo = DocumentRepository(self.db_manager.async_session)
        self.setting_repo = SettingRepository(self.db_manager.async_session)

    async def _setup_services(self):
        self.bot_logic = LogicService(
            db_manager=self.db_manager,
            application_repo=self.application_repo,
            user_repo=self.user_repo,
            approval_repo=self.approval_repo,
            logger_repo=self.log_repo
        )

    async def _setup_handlers(self):
        # Обработчик добавления бота в группу (на уровне dispatcher, без middleware)
        self.dp.my_chat_member(
            ChatMemberUpdatedFilter(
                member_status_changed=IS_NOT_MEMBER >> (MEMBER | ADMINISTRATOR)
            )
        )(self._on_bot_added_to_group)

        # Клиентские хендлеры
        self.client_handlers = ClientHandlers(
            logic_service=self.bot_logic,
            user_repo=self.user_repo
        )

        # Хендлеры менеджера
        self.manager_handlers = ManagerHandlers(
            user_repo=self.user_repo,
            application_repo=self.application_repo,
            approval_repo=self.approval_repo,
            company_repo=self.company_repo,
            bank_repo=self.bank_repo,
            log_repo=self.log_repo,
            bot=self.Bot
        )

        # Хендлеры администратора
        self.admin_handlers = AdminHandlers(
            user_repo=self.user_repo,
            company_repo=self.company_repo,
            bank_repo=self.bank_repo,
            application_repo=self.application_repo,
            log_repo=self.log_repo,
            pending_group_codes=self.pending_group_codes
        )

        # Хендлеры банка
        self.bank_handlers = BankHandlers(
            user_repo=self.user_repo,
            application_repo=self.application_repo,
            approval_repo=self.approval_repo,
            bank_repo=self.bank_repo,
            log_repo=self.log_repo,
            bot=self.Bot
        )

        # Хендлеры руководителя
        self.supervisor_handlers = SupervisorHandlers(
            user_repo=self.user_repo,
            application_repo=self.application_repo,
            approval_repo=self.approval_repo,
            company_repo=self.company_repo,
            bank_repo=self.bank_repo,
            log_repo=self.log_repo,
            document_repo=self.document_repo,
            bot=self.Bot
        )

        # Регистрация роутеров
        self.dp.include_router(self.client_handlers.router)
        self.dp.include_router(self.manager_handlers.router)
        self.dp.include_router(self.admin_handlers.router)
        self.dp.include_router(self.bank_handlers.router)
        self.dp.include_router(self.supervisor_handlers.router)

    async def _on_bot_added_to_group(self, event: ChatMemberUpdated):
        """Обработка добавления бота в группу/супергруппу"""
        chat = event.chat

        # Только группы и супергруппы
        if chat.type not in ('group', 'supergroup'):
            return

        # Очищаем старые коды (старше 30 минут)
        now = datetime.utcnow()
        expired = [
            code for code, data in self.pending_group_codes.items()
            if (now - data['created_at']).total_seconds() > 1800
        ]
        for code in expired:
            del self.pending_group_codes[code]

        # Генерируем код подтверждения
        code = generate_group_code()
        self.pending_group_codes[code] = {
            'chat_id': chat.id,
            'chat_title': chat.title or '',
            'created_at': now
        }

        # Отправляем код в группу
        try:
            await event.bot.send_message(
                chat_id=chat.id,
                text=(
                    f"<b>Код привязки группы:</b> <code>{code}</code>\n\n"
                    f"Отправьте этот код боту в личные сообщения "
                    f"для привязки группы к банку."
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"Failed to send group code to {chat.id}: {e}")


    async def start(self):
        logging.info("Bot is starting...")
        await self._setup_database()
        await self._setup_repositories()
        await self._setup_services()
        await self._setup_handlers()
        await self.dp.start_polling(self.Bot)
