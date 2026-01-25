import logging
from aiogram import Bot, Dispatcher

from handlers import ClientHandlers
from database import DatabaseManager
from database import ApplicationRepository, UserRepository, LogRepository, ApprovalRepository, BankRepository, CompanyRepository, DocumentRepository, SettingRepository
from services import LogicService
logging.basicConfig(level=logging.INFO)

class PaymentBot:
    def __init__(self, config):
        self.Bot = Bot(token=config.BOT_TOKEN)
        self.dp = Dispatcher()
        self.config = config
    

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
        self.client_handlers = ClientHandlers(
            logic_service=self.bot_logic,
            user_repo=self.user_repo
        )

        self.dp.include_router(self.client_handlers.router)


    async def start(self):
        logging.info("Bot is starting...")
        await self._setup_database()
        await self._setup_repositories()
        await self._setup_services()
        await self._setup_handlers()
        await self.dp.start_polling(self.Bot)