from database import ApplicationRepository, UserRepository, ApprovalRepository, LogRepository, DatabaseManager
from utils import generate_unique_id

class LogicService:
    def __init__(
            self, 
            db_manager: DatabaseManager,
            application_repo: ApplicationRepository, 
            user_repo: UserRepository,
            approval_repo: ApprovalRepository,
            logger_repo: LogRepository
            ):
        self.db_manager = db_manager
        self.application_repo = application_repo
        self.user_repo = user_repo
        self.approval_repo = approval_repo
        self.logger_repo = logger_repo
    async def create_new_application(self, data: dict):
        # 1. Создать заявку
        app = await self.application_repo.create(
            external_id=f"APP-{generate_unique_id()}",
            amount=data['amount'],
            payer_inn=data['inn'],
            purpose=data['purpose'],
            client_chat_id=data['chat_id'],
            status='new'
        )
        
        # 2. Создать workflow подписей
        await self.approval_repo.create_workflow(app.id, [
            {'role': 'manager', 'sequence': 1},
            {'role': 'bank', 'sequence': 2},
            {'role': 'supervisor', 'sequence': 3}
        ])
        
        # 3. Логировать
        log_repo = LogRepository(self.db_manager)
        await log_repo.create_log(
            action='application_created',
            application_id=app.id,
            details={'external_id': app.external_id}
        )
        
        return app