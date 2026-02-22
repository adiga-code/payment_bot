"""Тесты для DocumentService (форматирование, рендеринг)"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'bot'))

import pytest
from decimal import Decimal
from datetime import datetime

from services.document import _format_amount, _format_date_ru, _fix_split_placeholders


class TestFormatAmount:
    """Тесты форматирования сумм"""

    # _format_amount использует неразрывный пробел \u00a0 как разделитель тысяч
    NBSP = '\u00a0'

    def test_integer(self):
        assert _format_amount(1000) == f"1{self.NBSP}000,00"

    def test_large_integer(self):
        assert _format_amount(3002700) == f"3{self.NBSP}002{self.NBSP}700,00"

    def test_with_decimals(self):
        assert _format_amount(1234.56) == f"1{self.NBSP}234,56"

    def test_zero(self):
        assert _format_amount(0) == "0,00"

    def test_small(self):
        assert _format_amount(1) == "1,00"

    def test_decimal_type(self):
        assert _format_amount(Decimal("999999.99")) == f"999{self.NBSP}999,99"

    def test_millions(self):
        result = _format_amount(15000000)
        assert result == f"15{self.NBSP}000{self.NBSP}000,00"

    def test_kopecks_rounding(self):
        assert _format_amount(100.555) == "100,56"


class TestFormatDateRu:
    """Тесты форматирования даты на русском"""

    def test_january(self):
        dt = datetime(2026, 1, 23)
        assert _format_date_ru(dt) == "23 января 2026 г."

    def test_february(self):
        dt = datetime(2026, 2, 1)
        assert _format_date_ru(dt) == "1 февраля 2026 г."

    def test_december(self):
        dt = datetime(2025, 12, 31)
        assert _format_date_ru(dt) == "31 декабря 2025 г."

    def test_march(self):
        dt = datetime(2026, 3, 8)
        assert _format_date_ru(dt) == "8 марта 2026 г."


class TestFixSplitPlaceholders:
    """Тесты исправления плейсхолдеров, разбитых Word на несколько XML-ранов"""

    def _make_run(self, text: str, rpr: str = '') -> str:
        return f'<w:r>{rpr}<w:t>{text}</w:t></w:r>'

    def _wrap_para(self, *runs: str) -> str:
        return '<w:p>' + ''.join(runs) + '</w:p>'

    def test_single_run_unchanged(self):
        """Плейсхолдер в одном ране не трогается."""
        para = self._wrap_para(self._make_run('{{invoice_date}}'))
        result = _fix_split_placeholders(para)
        assert '{{invoice_date}}' in result

    def test_split_across_two_runs(self):
        """Плейсхолдер разбит на 2 рана — должен склеиться."""
        para = self._wrap_para(
            self._make_run('{{invoice_'),
            self._make_run('date}}'),
        )
        result = _fix_split_placeholders(para)
        assert '{{invoice_date}}' in result

    def test_split_across_three_runs(self):
        """Плейсхолдер разбит на 3 рана (типичный случай Word)."""
        para = self._wrap_para(
            self._make_run('{{'),
            self._make_run('invoice_date'),
            self._make_run('}}'),
        )
        result = _fix_split_placeholders(para)
        assert '{{invoice_date}}' in result

    def test_prooferr_removed(self):
        """Элементы <w:proofErr/> удаляются."""
        xml = (
            '<w:p>'
            '<w:r><w:t>{{</w:t></w:r>'
            '<w:proofErr w:type="spellStart"/>'
            '<w:r><w:t>invoice_date</w:t></w:r>'
            '<w:proofErr w:type="spellEnd"/>'
            '<w:r><w:t>}}</w:t></w:r>'
            '</w:p>'
        )
        result = _fix_split_placeholders(xml)
        assert 'proofErr' not in result
        assert '{{invoice_date}}' in result

    def test_multiple_split_placeholders_in_para(self):
        """Несколько разбитых плейсхолдеров в одном параграфе.

        В реальном Word-XML текст между плейсхолдерами всегда в отдельном ране;
        каждый плейсхолдер разбит независимо.
        """
        para = self._wrap_para(
            self._make_run('{{'),
            self._make_run('supplier.bank_name'),
            self._make_run('}}'),
            self._make_run(' и '),        # обычный текст между плейсхолдерами
            self._make_run('{{'),
            self._make_run('supplier.bank_bik'),
            self._make_run('}}'),
        )
        result = _fix_split_placeholders(para)
        assert '{{supplier.bank_name}}' in result
        assert '{{supplier.bank_bik}}' in result

    def test_rpr_preserved_from_first_run(self):
        """Форматирование (<w:rPr>) берётся из первого рана."""
        rpr = '<w:rPr><w:b/></w:rPr>'
        para = self._wrap_para(
            self._make_run('{{', rpr=rpr),
            self._make_run('invoice_date'),
            self._make_run('}}'),
        )
        result = _fix_split_placeholders(para)
        assert '<w:b/>' in result
        assert '{{invoice_date}}' in result

    def test_split_on_opening_braces(self):
        """Плейсхолдер разбит прямо по {{ : один { в одном ране, {name}} в следующем."""
        para = self._wrap_para(
            self._make_run('ИНН {'),
            self._make_run('{supplier.inn}}'),
        )
        result = _fix_split_placeholders(para)
        assert '{{supplier.inn}}' in result

    def test_split_on_opening_braces_with_prooferr(self):
        """{{ разбит с proofErr между ранами."""
        xml = (
            '<w:p>'
            '<w:r><w:t xml:space="preserve">ИНН {</w:t></w:r>'
            '<w:proofErr w:type="gramEnd"/>'
            '<w:r><w:t>{supplier.inn}}</w:t></w:r>'
            '</w:p>'
        )
        result = _fix_split_placeholders(xml)
        assert 'proofErr' not in result
        assert '{{supplier.inn}}' in result

    def test_non_placeholder_runs_unchanged(self):
        """Раны без плейсхолдеров не склеиваются."""
        para = self._wrap_para(
            self._make_run('Обычный текст'),
            self._make_run(' продолжение'),
        )
        result = _fix_split_placeholders(para)
        assert 'Обычный текст' in result
        assert ' продолжение' in result
        # Оба рана должны остаться раздельными (два <w:t>)
        assert result.count('<w:t>') == 2


class TestInvoiceTemplate:
    """Тесты рендеринга HTML-шаблона"""

    def test_template_exists(self):
        template_path = os.path.join(
            os.path.dirname(__file__), '..', 'bot', 'templates', 'invoice_template.html'
        )
        assert os.path.exists(template_path), "invoice_template.html не найден"

    def test_template_renders(self):
        from jinja2 import Environment, FileSystemLoader

        templates_path = os.path.join(
            os.path.dirname(__file__), '..', 'bot', 'templates'
        )
        env = Environment(loader=FileSystemLoader(templates_path), autoescape=True)
        template = env.get_template('invoice_template.html')

        html = template.render(
            invoice_number='1',
            invoice_date='1 января 2026 г.',
            supplier={
                'name': 'Test Company',
                'inn': '1234567890',
                'kpp': '123456789',
                'legal_address': 'Test Address',
                'bank_name': 'Test Bank',
                'bank_bik': '044525225',
                'bank_account': '40702810000000000001',
                'bank_corr_account': '30101810000000000225',
                'director_name': 'Ivanov I.I.',
                'accountant_name': 'Petrova P.P.',
            },
            customer={
                'name': 'Client LLC',
                'inn': '0987654321',
                'kpp': '987654321',
                'address': 'Client Address',
            },
            contract={'number': '001', 'date': '01.01.2026'},
            items=[{
                'name': 'Test item',
                'quantity': '1,00',
                'unit': 'шт',
                'price': '100 000,00',
                'total': '100 000,00',
            }],
            items_count=1,
            total='100 000,00',
            vat='18 032,79',
            total_words='Сто тысяч рублей 00 копеек',
            payment_deadline='04.01.2026',
        )

        assert 'Test Company' in html
        assert 'Client LLC' in html
        assert '100 000,00' in html
        assert 'Сто тысяч рублей' in html

    def test_pdf_generation(self):
        """Проверяем что WeasyPrint генерирует PDF"""
        from jinja2 import Environment, FileSystemLoader
        from weasyprint import HTML

        templates_path = os.path.join(
            os.path.dirname(__file__), '..', 'bot', 'templates'
        )
        env = Environment(loader=FileSystemLoader(templates_path), autoescape=True)
        template = env.get_template('invoice_template.html')

        html = template.render(
            invoice_number='42',
            invoice_date='2 февраля 2026 г.',
            supplier={
                'name': 'OOO Test', 'inn': '1234567890', 'kpp': '123456789',
                'legal_address': 'Moscow', 'bank_name': 'Test Bank',
                'bank_bik': '044525225', 'bank_account': '40702810000000000001',
                'bank_corr_account': '30101810000000000225',
                'director_name': 'Dir', 'accountant_name': 'Acc',
            },
            customer={'name': 'Client', 'inn': '0987654321', 'kpp': '', 'address': ''},
            contract={'number': '1', 'date': '01.01.2026'},
            items=[{'name': 'Item', 'quantity': '1,00', 'unit': 'шт',
                    'price': '1 000,00', 'total': '1 000,00'}],
            items_count=1, total='1 000,00', vat='180,33',
            total_words='Одна тысяча рублей 00 копеек',
            payment_deadline='05.02.2026',
        )

        pdf_bytes = HTML(string=html).write_pdf()
        assert pdf_bytes is not None
        assert len(pdf_bytes) > 0
        # PDF начинается с %PDF
        assert pdf_bytes[:5] == b'%PDF-'
