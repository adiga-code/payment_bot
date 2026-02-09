import logging
from datetime import datetime

from database import ApplicationRepository, UserRepository, ApprovalRepository, LogRepository, DatabaseManager
from utils import generate_unique_id

logger = logging.getLogger(__name__)


class LogicService:
    def __init__(
            self,
            db_manager: DatabaseManager,
            application_repo: ApplicationRepository,
            user_repo: UserRepository,
            approval_repo: ApprovalRepository,
            logger_repo: LogRepository,
            zcb_service=None
            ):
        self.db_manager = db_manager
        self.application_repo = application_repo
        self.user_repo = user_repo
        self.approval_repo = approval_repo
        self.logger_repo = logger_repo
        self.zcb_service = zcb_service

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

        # 3. Проверка плательщика в ЗЧБ
        if self.zcb_service:
            try:
                check_result = await self.zcb_service.check_payer(data['inn'])
                has_errors = bool(check_result.get('errors'))

                # Проверяем наличие госзакупок
                zakupki = check_result.get('zakupki')
                has_gov_contracts = zakupki is not None and zakupki.get('count', 0) > 0

                # Получаем уровень риска ЦБ РФ
                cbr_risk = check_result.get('cbr_risk', {})
                cbr_risk_level = cbr_risk.get('level') if cbr_risk else None

                await self.application_repo.update_primary_check(
                    app.id,
                    status='completed' if not has_errors else 'partial',
                    result=check_result,
                    flags={
                        'color': check_result.get('color'),
                        'stop': check_result.get('stop'),
                        'payer_name': check_result.get('name'),
                        'has_gov_contracts': has_gov_contracts,
                        'gov_contracts_count': zakupki.get('count', 0) if zakupki else 0,
                        'gov_contracts_sum': zakupki.get('total_sum', 0) if zakupki else 0,
                        'cbr_risk_level': cbr_risk_level,  # success, warning, danger
                    }
                )
                # Обновляем данные плательщика из ЗЧБ
                update_fields = {}
                if check_result.get('name'):
                    update_fields['payer_name'] = check_result['name']
                if check_result.get('kpp'):
                    update_fields['payer_kpp'] = check_result['kpp']
                if check_result.get('address'):
                    update_fields['payer_address'] = check_result['address']
                if update_fields:
                    await self.application_repo.update_by_id(app.id, **update_fields)

                # Если есть госзакупки — отправляем на ручную проверку менеджеру
                if has_gov_contracts:
                    await self.application_repo.update_status(app.id, 'manager_review')
                    logger.info(f"Application {app.external_id} sent to manager_review due to gov contracts")
            except Exception as e:
                logger.error(f"ZCB check failed for {data['inn']}: {e}")
                await self.application_repo.update_primary_check(
                    app.id,
                    status='error',
                    result={'error': str(e)},
                    flags={}
                )

        # 4. Логировать
        await self.logger_repo.create_log(
            action='application_created',
            application_id=app.id,
            details={'external_id': app.external_id}
        )

        return app