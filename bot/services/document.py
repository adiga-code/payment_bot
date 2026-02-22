# bot/services/document.py

import io
import logging
import os
import re
import shutil
import subprocess
import zipfile
from datetime import datetime, timedelta
from decimal import Decimal

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logging.getLogger(__name__).warning(
        "Pillow не установлен — изображения в счёте не будут масштабированы. "
        "Установите: pip install Pillow"
    )

from database import DocumentRepository, ApplicationRepository, CompanyRepository, UserRepository
from utils.amount_words import amount_to_words

logger = logging.getLogger(__name__)

DOCUMENTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'documents')
TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates', 'template.docx')


# ===========================================================================
# Форматирование
# ===========================================================================

def _format_amount(amount) -> str:
    """100000.00 -> '100 000,00'"""
    amount = Decimal(str(amount))
    integer = int(amount)
    frac = int(round((amount - integer) * 100))
    int_str = f"{integer:,}".replace(",", "\u00a0")  # неразрывный пробел
    return f"{int_str},{frac:02d}"


def _format_date_ru(dt: datetime) -> str:
    """datetime -> '21 февраля 2026 г.'"""
    months = [
        '', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
        'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'
    ]
    return f"{dt.day} {months[dt.month]} {dt.year} г."


def _xml_escape(text: str) -> str:
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;'))


def _extract_name_inner(full_name: str) -> str:
    """Извлекает краткое имя из кавычек: 'ООО "ТЕХСНАБ ГРУПП"' -> 'ТЕХСНАБ ГРУПП'"""
    m = re.search(r'["\u00ab\u201c\u201e]([^"\u00bb\u201d\u201f]+)["\u00bb\u201d\u201f]', full_name)
    if m:
        return m.group(1)
    parts = full_name.split(None, 1)
    return parts[-1] if parts else full_name


# ===========================================================================
# Исправление разбитых плейсхолдеров (артефакт Word)
# ===========================================================================

_RUN_RE = re.compile(r'<w:r\b[^>]*>.*?</w:r>', re.DOTALL)
_T_TEXT_RE = re.compile(r'<w:t(?:\s[^>]*)?>([^<]*)</w:t>')


def _fix_split_placeholders(doc_xml: str) -> str:
    """
    Word разбивает плейсхолдеры {{...}} на несколько <w:r> из-за маркеров
    проверки орфографии/грамматики (<w:proofErr/>). Функция:
    1. Удаляет элементы <w:proofErr/> — они ничего не рендерят.
    2. В каждом абзаце склеивает соседние раны, которые вместе образуют плейсхолдер.
    """
    doc_xml = re.sub(r'<w:proofErr\b[^/]*/>', '', doc_xml)
    return re.sub(
        r'<w:p[ >].*?</w:p>',
        lambda m: _fix_para_runs(m.group(0)),
        doc_xml,
        flags=re.DOTALL,
    )


def _fix_para_runs(para: str) -> str:
    """Склеивает раны параграфа, которые вместе образуют плейсхолдер {{...}}."""
    runs = list(_RUN_RE.finditer(para))
    if len(runs) < 2:
        return para

    run_texts = []
    for r in runs:
        tm = _T_TEXT_RE.search(r.group(0))
        run_texts.append(tm.group(1) if tm else '')

    merge_groups = []
    i = 0
    while i < len(run_texts):
        text = run_texts[i]
        # Ран начинает плейсхолдер, но не завершает его
        if ('{{' in text or text.endswith('{')) and not re.search(r'\{\{[^}]+\}\}', text):
            for j in range(i + 1, len(run_texts) + 1):
                combined = ''.join(run_texts[i:j])
                if '}}' in combined:
                    if j > i + 1:
                        merge_groups.append((i, j - 1))
                    i = j
                    break
            else:
                i += 1
        else:
            i += 1

    if not merge_groups:
        return para

    # Применяем в обратном порядке, чтобы не сбивать позиции
    for start_idx, end_idx in reversed(merge_groups):
        merged_text = ''.join(run_texts[start_idx:end_idx + 1])
        first_run_xml = runs[start_idx].group(0)
        rpr_m = re.search(r'<w:rPr>.*?</w:rPr>', first_run_xml, re.DOTALL)
        rpr = rpr_m.group(0) if rpr_m else ''
        space_attr = ' xml:space="preserve"' if ' ' in merged_text else ''
        new_run = f'<w:r>{rpr}<w:t{space_attr}>{merged_text}</w:t></w:r>'
        para = para[:runs[start_idx].start()] + new_run + para[runs[end_idx].end():]

    return para


# ===========================================================================
# Работа с изображениями
# ===========================================================================

def _get_image_slots(zip_path: str) -> dict:
    """Возвращает словарь rId -> {'target': ..., 'cx': EMU, 'cy': EMU} из шаблона."""
    with zipfile.ZipFile(zip_path, 'r') as z:
        rels_xml = z.read('word/_rels/document.xml.rels').decode('utf-8')
        doc_xml = z.read('word/document.xml').decode('utf-8')

    rid_to_target = {}
    for m in re.finditer(r'Id="(rId\d+)"[^>]*Type="[^"]*image[^"]*"[^>]*Target="([^"]+)"', rels_xml):
        rid_to_target[m.group(1)] = m.group(2)

    slots = {}
    for anchor in re.finditer(r'<wp:anchor[^>]*>.*?</wp:anchor>', doc_xml, re.DOTALL):
        a = anchor.group(0)
        rid_m = re.search(r'r:embed="(rId\d+)"', a)
        ext_m = re.search(r'<wp:extent cx="(\d+)" cy="(\d+)"', a)
        if rid_m and ext_m:
            rid = rid_m.group(1)
            if rid not in slots and rid in rid_to_target:
                slots[rid] = {
                    'target': rid_to_target[rid],
                    'cx': int(ext_m.group(1)),
                    'cy': int(ext_m.group(2)),
                }
    return slots


def _emu_to_px(emu: int, dpi: int = 150) -> int:
    return max(1, round(emu / 914400 * dpi))


def _fit_image(src: 'Image.Image', target_w: int, target_h: int, mode: str = 'fit') -> 'Image.Image':
    src_w, src_h = src.size
    if mode == 'stretch':
        return src.resize((target_w, target_h), Image.LANCZOS)
    scale = min(target_w / src_w, target_h / src_h)
    new_w = max(1, round(src_w * scale))
    new_h = max(1, round(src_h * scale))
    resized = src.resize((new_w, new_h), Image.LANCZOS)
    if mode == 'fill':
        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        return resized.crop((left, top, left + target_w, top + target_h))
    # fit — центрируем на прозрачном холсте
    if resized.mode != 'RGBA':
        resized = resized.convert('RGBA')
    canvas = Image.new('RGBA', (target_w, target_h), (255, 255, 255, 0))
    canvas.paste(resized, ((target_w - new_w) // 2, (target_h - new_h) // 2), resized)
    return canvas


def prepare_image_for_slot(image_path: str, cx_emu: int, cy_emu: int,
                            dpi: int = 150, scale_mode: str = 'fit') -> bytes:
    """Масштабирует изображение под размер слота и возвращает PNG-байты."""
    if not PIL_AVAILABLE:
        with open(image_path, 'rb') as f:
            return f.read()
    target_w = _emu_to_px(cx_emu, dpi)
    target_h = _emu_to_px(cy_emu, dpi)
    img = Image.open(image_path)
    if img.mode not in ('RGBA', 'RGB', 'L'):
        img = img.convert('RGBA')
    fitted = _fit_image(img, target_w, target_h, mode=scale_mode)
    buf = io.BytesIO()
    fitted.save(buf, format='PNG', optimize=True)
    return buf.getvalue()


# ===========================================================================
# Работа с ZIP-архивом docx
# ===========================================================================

def _update_zip_files(zip_path: str, updates: dict) -> None:
    """Обновляет несколько файлов внутри ZIP за один проход."""
    tmp_path = zip_path + '.tmp'
    with zipfile.ZipFile(zip_path, 'r') as zin, \
         zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            zout.writestr(item, updates.get(item.filename) or zin.read(item.filename))
    os.replace(tmp_path, zip_path)


# ===========================================================================
# Конвертация docx → PDF через LibreOffice
# ===========================================================================

def _convert_docx_to_pdf(docx_path: str, output_dir: str) -> str | None:
    """Конвертирует docx в PDF через LibreOffice headless."""
    try:
        result = subprocess.run(
            ['libreoffice', '--headless', '--convert-to', 'pdf',
             '--outdir', output_dir, docx_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        logger.error("LibreOffice не найден. Установите libreoffice-writer.")
        return None
    except subprocess.TimeoutExpired:
        logger.error("LibreOffice: превышен таймаут конвертации (60 с)")
        return None

    if result.returncode != 0:
        logger.error(f"LibreOffice конвертация завершилась с ошибкой: {result.stderr}")
        return None

    pdf_name = os.path.splitext(os.path.basename(docx_path))[0] + '.pdf'
    pdf_path = os.path.join(output_dir, pdf_name)
    if not os.path.exists(pdf_path):
        logger.error(f"LibreOffice не создал файл: {pdf_path}")
        return None

    return pdf_path


# ===========================================================================
# Сервис генерации документов
# ===========================================================================

class DocumentService:
    """Сервис генерации счетов на оплату (docx-шаблон → PDF через LibreOffice)."""

    def __init__(
        self,
        document_repo: DocumentRepository,
        application_repo: ApplicationRepository,
        company_repo: CompanyRepository = None,
        user_repo: UserRepository = None,
    ):
        self.document_repo = document_repo
        self.application_repo = application_repo
        self.company_repo = company_repo
        self.user_repo = user_repo
        os.makedirs(DOCUMENTS_DIR, exist_ok=True)

    async def generate_invoice(self, app_id: int) -> str | None:
        """
        Генерирует счёт на оплату (PDF) для одобренной заявки.

        Returns:
            file_path — путь к сгенерированному PDF, или None при ошибке.
        """
        app = await self.application_repo.get_with_relations(app_id)
        if not app:
            logger.error(f"Application {app_id} not found for invoice generation")
            return None

        # Деактивируем старые счета
        await self.document_repo.deactivate_old(app_id, 'invoice')

        # Создаём запись в БД — получаем ID для номера счёта
        doc_record = await self.document_repo.create(
            application_id=app_id,
            type='invoice',
        )

        invoice_number = str(doc_record.id)
        now = datetime.utcnow()

        # Данные поставщика
        co = app.company
        bank = app.bank

        account_number = ""
        if co and bank and self.company_repo:
            company_bank = await self.company_repo.get_company_bank_for_invoice(co.id, bank.id)
            if company_bank:
                account_number = company_bank.account_number or ""

        supplier = {
            'name':              co.name if co else "—",
            'inn':               co.inn if co else "—",
            'kpp':               co.kpp if co and co.kpp else "",
            'legal_address':     co.legal_address if co and co.legal_address else "",
            'bank_name':         bank.name if bank else "",
            'bank_bik':          bank.bik if bank and bank.bik else "",
            'bank_account':      account_number,
            'bank_corr_account': bank.corr_account if bank and bank.corr_account else "",
            'director_name':     co.director_name if co and co.director_name else "",
            'accountant_name':   co.accountant_name if co and co.accountant_name else "",
        }

        # Данные покупателя
        customer = {
            'name':    app.payer_name or "—",
            'inn':     app.payer_inn or "—",
            'kpp':     app.payer_kpp or "",
            'address': app.payer_address or "",
        }

        # Данные договора
        contract = {
            'number': app.contract_number or "",
            'date':   app.contract_date or "",
        }

        # Назначение платежа (сначала от бухгалтера, потом из заявки)
        invoice_purpose = ""
        if self.user_repo:
            accountants = await self.user_repo.get_by_role('accountant')
            for acc in accountants:
                if acc.default_invoice_purpose:
                    invoice_purpose = acc.default_invoice_purpose
                    break
        if not invoice_purpose:
            invoice_purpose = app.invoice_purpose or app.purpose or ""

        amount = Decimal(str(app.amount))
        nds = amount * Decimal('22') / Decimal('122')

        invoice_date_short = now.strftime('%d.%m.%Y')

        # Описание строки товара
        line_desc = f"Оплата по счету №{invoice_number} от {invoice_date_short}"
        if contract['number']:
            line_desc += f" к договору №{contract['number']}"
            if contract['date']:
                line_desc += f" от {contract['date']} г"
        if invoice_purpose:
            line_desc += f" за {invoice_purpose}"
        line_desc += "."

        pay_by = now + timedelta(days=3)

        # Путь к подписи
        signature_path = self._resolve_image_path(
            co.signature_image_path if co else None, 'SIGNATURE'
        )
        # Путь к печати
        stamp_path = self._resolve_image_path(
            co.stamp_image_path if co else None, 'STAMP'
        )

        # Плейсхолдеры шаблона
        replacements = {
            '{{supplier.bank_name}}':         supplier['bank_name'],
            '{{supplier.bank_bik}}':          supplier['bank_bik'],
            '{{supplier.bank_corr_account}}': supplier['bank_corr_account'],
            '{{supplier.inn}}':               supplier['inn'],
            '{{supplier.kpp}}':               supplier['kpp'],
            '{{supplier.bank_account}}':      supplier['bank_account'],
            '{{supplier.name_inner}}':        _extract_name_inner(supplier['name']),
            '{{supplier.full_info}}':         (
                f"{supplier['name']}, ИНН {supplier['inn']}, "
                f"КПП {supplier['kpp']}, {supplier['legal_address']}"
            ),
            '{{supplier.director_name}}':     supplier['director_name'],
            '{{supplier.accountant_name}}':   supplier['accountant_name'],
            '{{customer.full_info}}':         (
                f"{customer['name']}, ИНН {customer['inn']}, "
                f"КПП {customer['kpp']}, {customer['address']}"
            ),
            '{{contract.number}}':            contract['number'],
            '{{contract.date}}':              contract['date'],
            '{{invoice_number}}':             invoice_number,
            '{{invoice_date}}':               _format_date_ru(now),
            '{{invoice_date_short}}':         invoice_date_short,
            '{{item_description}}':           line_desc,
            '{{total}}':                      _format_amount(amount),
            '{{vat}}':                        _format_amount(nds),
            '{{total_words}}':                amount_to_words(float(amount)),
            '{{items_count}}':                '1',
            '{{payment_deadline}}':           pay_by.strftime('%d.%m.%Y'),
        }

        # Генерируем docx из шаблона
        docx_name = f"СЧ-{invoice_number}.docx"
        docx_path = os.path.join(DOCUMENTS_DIR, docx_name)

        if not os.path.exists(TEMPLATE_PATH):
            logger.error(f"Шаблон счёта не найден: {TEMPLATE_PATH}")
            return None

        try:
            shutil.copy2(TEMPLATE_PATH, docx_path)

            with zipfile.ZipFile(docx_path, 'r') as z:
                doc_xml = z.read('word/document.xml').decode('utf-8')

            doc_xml = _fix_split_placeholders(doc_xml)

            for placeholder, value in replacements.items():
                doc_xml = doc_xml.replace(placeholder, _xml_escape(str(value)))

            remaining = re.findall(r'\{\{[^}]+\}\}', doc_xml)
            if remaining:
                logger.warning(f"Незаполненные плейсхолдеры в счёте: {set(remaining)}")

            zip_updates = {'word/document.xml': doc_xml.encode('utf-8')}

            # Вставляем изображения (печать rId5, подпись rId6)
            if signature_path or stamp_path:
                slots = _get_image_slots(TEMPLATE_PATH)
                image_map = {'rId5': stamp_path, 'rId6': signature_path}
                for rid, img_path in image_map.items():
                    if not img_path or not os.path.exists(img_path):
                        continue
                    slot = slots.get(rid)
                    if not slot:
                        logger.warning(f"Слот {rid} не найден в шаблоне")
                        continue
                    img_bytes = prepare_image_for_slot(img_path, slot['cx'], slot['cy'])
                    zip_updates[f'word/{slot["target"]}'] = img_bytes
                    logger.info(f"{rid} → {slot['target']} вставлен")

            _update_zip_files(docx_path, zip_updates)

        except Exception as e:
            logger.error(f"Ошибка генерации docx для заявки {app_id}: {e}")
            if os.path.exists(docx_path):
                os.remove(docx_path)
            return None

        # Конвертируем docx → PDF
        pdf_path = _convert_docx_to_pdf(docx_path, DOCUMENTS_DIR)

        # Удаляем промежуточный docx
        if os.path.exists(docx_path):
            os.remove(docx_path)

        if pdf_path is None:
            return None

        # Обновляем запись в БД
        display_number = f"СЧ-{invoice_number}"
        await self.document_repo.update_by_id(
            doc_record.id,
            number=display_number,
            file_path=pdf_path,
        )

        await self.application_repo.mark_invoice_generated(app_id)

        logger.info(f"Счёт {display_number} сгенерирован для заявки {app.external_id}")
        return pdf_path

    async def validate_invoice_data(self, app_id: int) -> list[dict]:
        """
        Проверяет обязательные поля для генерации счёта.

        Возвращает пустой список если всё OK, иначе список недостающих полей вида:
          [{'key': 'bank.bik', 'label': 'БИК банка',
            'model': 'bank', 'model_id': 5, 'attr': 'bik'}, ...]

        Дополнительные ключи для company_bank: 'company_id', 'bank_id'
        (нужны если запись CompanyBank ещё не создана и её нужно создать).
        """
        app = await self.application_repo.get_with_relations(app_id)
        if not app:
            return [{'key': 'app', 'label': 'Заявка не найдена',
                     'model': None, 'model_id': None, 'attr': None}]

        co = app.company
        bank = app.bank
        missing = []

        if bank:
            if not bank.bik:
                missing.append({
                    'key': 'bank.bik', 'label': 'БИК банка',
                    'model': 'bank', 'model_id': bank.id, 'attr': 'bik',
                })
            if not bank.corr_account:
                missing.append({
                    'key': 'bank.corr_account', 'label': 'Корреспондентский счёт банка',
                    'model': 'bank', 'model_id': bank.id, 'attr': 'corr_account',
                })

        if co:
            if not co.kpp:
                missing.append({
                    'key': 'company.kpp', 'label': 'КПП компании',
                    'model': 'company', 'model_id': co.id, 'attr': 'kpp',
                })
            if not co.director_name:
                missing.append({
                    'key': 'company.director_name', 'label': 'ФИО руководителя',
                    'model': 'company', 'model_id': co.id, 'attr': 'director_name',
                })
            if co and bank and self.company_repo:
                cb = await self.company_repo.get_company_bank_for_invoice(co.id, bank.id)
                if not cb or not cb.account_number:
                    missing.append({
                        'key': 'company_bank.account_number',
                        'label': 'Расчётный счёт компании в банке',
                        'model': 'company_bank',
                        'model_id': cb.id if cb else None,
                        'attr': 'account_number',
                        'company_id': co.id,
                        'bank_id': bank.id,
                    })

        return missing

    def _resolve_image_path(self, raw_path: str | None, label: str) -> str | None:
        """Разрешает путь к изображению (относительный или абсолютный)."""
        if not raw_path:
            return None

        path = raw_path
        if not os.path.isabs(path):
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            path = os.path.join(project_root, path)

        if os.path.exists(path):
            return os.path.abspath(path)

        # Запасные варианты
        for alt in [
            os.path.join('/app', raw_path),
            os.path.join('/app/documents', os.path.basename(raw_path)),
        ]:
            if os.path.exists(alt):
                logger.info(f"[{label}] Найден по альтернативному пути: {alt}")
                return os.path.abspath(alt)

        logger.error(f"[{label}] Файл не найден: {path}")
        return None
