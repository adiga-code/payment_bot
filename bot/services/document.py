# bot/services/document.py

import logging
import os
from datetime import datetime
from decimal import Decimal

from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

from database import DocumentRepository, ApplicationRepository

logger = logging.getLogger(__name__)

DOCUMENTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'documents')


def _format_amount(amount: Decimal) -> str:
    """Форматирование суммы: 100000.00 -> 100 000.00"""
    return f"{amount:,.2f}".replace(",", " ")


class DocumentService:
    """Сервис генерации документов (счетов на оплату)"""

    def __init__(self, document_repo: DocumentRepository, application_repo: ApplicationRepository):
        self.document_repo = document_repo
        self.application_repo = application_repo
        os.makedirs(DOCUMENTS_DIR, exist_ok=True)

    async def generate_invoice(self, app_id: int) -> str | None:
        """
        Генерирует счёт на оплату (DOCX) для одобренной заявки.

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

        # Формируем номер счёта: СЧ-00123
        invoice_number = f"СЧ-{doc_record.id:05d}"

        # Данные для счёта
        company_name = app.company.name if app.company else "—"
        company_inn = app.company.inn if app.company else "—"
        bank_name = app.bank.name if app.bank else "—"
        payer_name = app.payer_name or "—"
        payer_inn = app.payer_inn or "—"
        purpose = app.purpose or "—"
        amount = app.amount
        invoice_date = datetime.utcnow().strftime("%d.%m.%Y")

        # Генерируем DOCX
        file_name = f"{invoice_number}.docx"
        file_path = os.path.join(DOCUMENTS_DIR, file_name)

        try:
            self._build_invoice_docx(
                file_path=file_path,
                invoice_number=invoice_number,
                invoice_date=invoice_date,
                company_name=company_name,
                company_inn=company_inn,
                bank_name=bank_name,
                payer_name=payer_name,
                payer_inn=payer_inn,
                purpose=purpose,
                amount=amount,
                external_id=app.external_id,
            )
        except Exception as e:
            logger.error(f"Failed to generate invoice DOCX for app {app_id}: {e}")
            return None

        # Обновляем запись в БД
        await self.document_repo.update_by_id(
            doc_record.id,
            number=invoice_number,
            file_path=file_path,
        )

        # Обновляем статус заявки
        await self.application_repo.mark_invoice_generated(app_id)

        logger.info(f"Invoice {invoice_number} generated for application {app.external_id}")
        return file_path

    def _build_invoice_docx(
        self,
        file_path: str,
        invoice_number: str,
        invoice_date: str,
        company_name: str,
        company_inn: str,
        bank_name: str,
        payer_name: str,
        payer_inn: str,
        purpose: str,
        amount: Decimal,
        external_id: str,
    ):
        """Создаёт DOCX-файл счёта на оплату"""
        doc = Document()

        # Стиль по умолчанию
        style = doc.styles['Normal']
        style.font.name = 'Arial'
        style.font.size = Pt(10)

        # === Заголовок ===
        title = doc.add_paragraph()
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = title.add_run(f'СЧЁТ НА ОПЛАТУ № {invoice_number}')
        run.bold = True
        run.font.size = Pt(14)

        date_p = doc.add_paragraph()
        date_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        date_p.add_run(f'от {invoice_date}')

        doc.add_paragraph()

        # === Поставщик ===
        p = doc.add_paragraph()
        run = p.add_run('Поставщик: ')
        run.bold = True
        p.add_run(f'{company_name}, ИНН {company_inn}')

        # === Покупатель ===
        p = doc.add_paragraph()
        run = p.add_run('Покупатель: ')
        run.bold = True
        p.add_run(f'{payer_name}, ИНН {payer_inn}')

        # === Банк ===
        p = doc.add_paragraph()
        run = p.add_run('Банк: ')
        run.bold = True
        p.add_run(bank_name)

        doc.add_paragraph()

        # === Таблица ===
        table = doc.add_table(rows=2, cols=5)
        table.style = 'Table Grid'
        table.alignment = WD_TABLE_ALIGNMENT.CENTER

        headers = ['№', 'Назначение платежа', 'Кол-во', 'Цена, руб.', 'Сумма, руб.']
        for i, header in enumerate(headers):
            cell = table.rows[0].cells[i]
            cell.text = header
            for paragraph in cell.paragraphs:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for r in paragraph.runs:
                    r.bold = True
                    r.font.size = Pt(9)

        amount_str = _format_amount(amount)
        row_data = ['1', purpose, '1', amount_str, amount_str]
        for i, value in enumerate(row_data):
            cell = table.rows[1].cells[i]
            cell.text = value
            for paragraph in cell.paragraphs:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for r in paragraph.runs:
                    r.font.size = Pt(9)

        doc.add_paragraph()

        # === Итого ===
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        run = p.add_run(f'Итого: {amount_str} руб.')
        run.bold = True
        run.font.size = Pt(12)

        doc.add_paragraph()

        # === Номер заявки ===
        p = doc.add_paragraph()
        p.add_run(f'Номер заявки: {external_id}')

        doc.save(file_path)
