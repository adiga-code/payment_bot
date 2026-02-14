# bot/services/document.py

import logging
import os
from datetime import datetime, timedelta
from decimal import Decimal

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from database import DocumentRepository, ApplicationRepository, CompanyRepository
from utils.amount_words import amount_to_words

logger = logging.getLogger(__name__)

DOCUMENTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'documents')
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'bot', 'templates')


def _format_amount(amount) -> str:
    """100000.00 -> 100 000,00"""
    amount = Decimal(str(amount))
    integer = int(amount)
    frac = int(round((amount - integer) * 100))
    int_str = f"{integer:,}".replace(",", " ")
    return f"{int_str},{frac:02d}"


def _format_date_ru(dt: datetime) -> str:
    """datetime -> '23 января 2026 г.'"""
    months = [
        '', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
        'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'
    ]
    return f"{dt.day} {months[dt.month]} {dt.year} г."


class DocumentService:
    """Сервис генерации документов (счетов на оплату в PDF)"""

    def __init__(
        self,
        document_repo: DocumentRepository,
        application_repo: ApplicationRepository,
        company_repo: CompanyRepository = None
    ):
        self.document_repo = document_repo
        self.application_repo = application_repo
        self.company_repo = company_repo
        os.makedirs(DOCUMENTS_DIR, exist_ok=True)

        # Jinja2 окружение
        templates_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
        self.jinja_env = Environment(
            loader=FileSystemLoader(templates_path),
            autoescape=True
        )

    async def generate_invoice(self, app_id: int) -> str | None:
        """
        Генерирует счёт на оплату (PDF) для одобренной заявки.

        Returns:
            file_path — путь к сгенерированному файлу, или None при ошибке
        """
        app = await self.application_repo.get_with_relations(app_id)
        if not app:
            logger.error(f"Application {app_id} not found for invoice generation")
            return None

        # Деактивируем старые счета этой заявки
        await self.document_repo.deactivate_old(app_id, 'invoice')

        # Создаём запись документа в БД (чтобы получить ID для номера)
        doc_record = await self.document_repo.create(
            application_id=app_id,
            type='invoice',
        )

        invoice_number = str(doc_record.id)
        now = datetime.utcnow()

        # Данные компании-поставщика
        co = app.company
        bank = app.bank

        # Получаем номер счёта компании в этом банке
        account_number = ""
        if co and bank and self.company_repo:
            company_bank = await self.company_repo.get_company_bank_for_invoice(co.id, bank.id)
            if company_bank:
                account_number = company_bank.account_number or ""

        supplier = {
            'name': co.name if co else "—",
            'inn': co.inn if co else "—",
            'kpp': co.kpp if co and co.kpp else "",
            'legal_address': co.legal_address if co and co.legal_address else "",
            'bank_name': bank.name if bank else "",
            'bank_bik': bank.bik if bank and bank.bik else "",
            'bank_account': account_number,
            'bank_corr_account': bank.corr_account if bank and bank.corr_account else "",
            'director_name': co.director_name if co and co.director_name else "",
            'accountant_name': co.accountant_name if co and co.accountant_name else "",
        }

        # Данные покупателя
        customer = {
            'name': app.payer_name or "—",
            'inn': app.payer_inn or "—",
            'kpp': app.payer_kpp or "",
            'address': app.payer_address or "",
        }

        # Данные договора
        contract = {
            'number': app.contract_number or "",
            'date': app.contract_date or "",
        }

        invoice_purpose = app.invoice_purpose or app.purpose or ""
        amount = Decimal(str(app.amount))

        # НДС 22%
        nds = amount * Decimal('22') / Decimal('122')

        # Описание строки товара
        line_desc = f"Оплата по счету №{invoice_number} от {now.strftime('%d.%m.%Y')}"
        if contract['number']:
            line_desc += f" к договору №{contract['number']}"
            if contract['date']:
                line_desc += f" от {contract['date']}"
        if invoice_purpose:
            line_desc += f" за {invoice_purpose}"

        # Позиции
        items = [{
            'name': line_desc,
            'quantity': '1,00',
            'unit': 'шт',
            'price': _format_amount(amount),
            'total': _format_amount(amount),
        }]

        # Дата оплаты — +3 дня
        pay_by = now + timedelta(days=3)

        # Путь к подписи компании (конвертируем в абсолютный)
        signature_path = None
        if co and co.signature_image_path:
            # Если путь относительный - делаем абсолютным
            sig_path = co.signature_image_path
            logger.info(f"[SIGNATURE DEBUG] Original path from DB: {sig_path}")

            if not os.path.isabs(sig_path):
                # Относительный путь от корня проекта
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                logger.info(f"[SIGNATURE DEBUG] Project root: {project_root}")
                sig_path = os.path.join(project_root, sig_path)
                logger.info(f"[SIGNATURE DEBUG] Joined path: {sig_path}")

            # Проверяем что файл существует
            if os.path.exists(sig_path):
                signature_path = os.path.abspath(sig_path)
                logger.info(f"[SIGNATURE DEBUG] ✅ File exists! Absolute path: {signature_path}")
            else:
                logger.error(f"[SIGNATURE DEBUG] ❌ File NOT found at: {sig_path}")
                # Попробуем найти файл в других местах для отладки
                alt_paths = [
                    os.path.join('/app', sig_path),
                    os.path.join('/app/documents/signatures', os.path.basename(sig_path)),
                    sig_path
                ]
                for alt_path in alt_paths:
                    if os.path.exists(alt_path):
                        logger.info(f"[SIGNATURE DEBUG] Found file at alternative path: {alt_path}")
                        signature_path = os.path.abspath(alt_path)
                        break
        elif co:
            logger.warning(f"Company {co.id} ({co.name}) has no signature - invoice will be generated without signature")

        # Путь к печати компании (конвертируем в абсолютный)
        stamp_path = None
        if co and co.stamp_image_path:
            # Если путь относительный - делаем абсолютным
            st_path = co.stamp_image_path
            logger.info(f"[STAMP DEBUG] Original path from DB: {st_path}")

            if not os.path.isabs(st_path):
                # Относительный путь от корня проекта
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                logger.info(f"[STAMP DEBUG] Project root: {project_root}")
                st_path = os.path.join(project_root, st_path)
                logger.info(f"[STAMP DEBUG] Joined path: {st_path}")

            # Проверяем что файл существует
            if os.path.exists(st_path):
                stamp_path = os.path.abspath(st_path)
                logger.info(f"[STAMP DEBUG] ✅ File exists! Absolute path: {stamp_path}")
            else:
                logger.error(f"[STAMP DEBUG] ❌ File NOT found at: {st_path}")
                # Попробуем найти файл в других местах для отладки
                alt_paths = [
                    os.path.join('/app', st_path),
                    os.path.join('/app/documents/stamps', os.path.basename(st_path)),
                    st_path
                ]
                for alt_path in alt_paths:
                    if os.path.exists(alt_path):
                        logger.info(f"[STAMP DEBUG] Found file at alternative path: {alt_path}")
                        stamp_path = os.path.abspath(alt_path)
                        break
        elif co:
            logger.warning(f"Company {co.id} ({co.name}) has no stamp - invoice will be generated without stamp")

        # Контекст для шаблона
        context = {
            'invoice_number': invoice_number,
            'invoice_date': _format_date_ru(now),
            'supplier': supplier,
            'customer': customer,
            'contract': contract,
            'items': items,
            'items_count': len(items),
            'total': _format_amount(amount),
            'vat': _format_amount(nds),
            'total_words': amount_to_words(amount),
            'payment_deadline': pay_by.strftime('%d.%m.%Y'),
            'signature_path': signature_path,
            'stamp_path': stamp_path,
        }

        # Генерируем PDF
        file_name = f"СЧ-{invoice_number}.pdf"
        file_path = os.path.join(DOCUMENTS_DIR, file_name)

        try:
            template = self.jinja_env.get_template('invoice_template.html')
            html_content = template.render(**context)
            HTML(string=html_content).write_pdf(file_path)
        except Exception as e:
            logger.error(f"Failed to generate invoice PDF for app {app_id}: {e}")
            return None

        # Обновляем запись в БД
        display_number = f"СЧ-{invoice_number}"
        await self.document_repo.update_by_id(
            doc_record.id,
            number=display_number,
            file_path=file_path,
        )

        # Обновляем статус заявки
        await self.application_repo.mark_invoice_generated(app_id)

        logger.info(f"Invoice {display_number} generated for application {app.external_id}")
        return file_path
