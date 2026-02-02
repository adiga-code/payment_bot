"""Тесты для DocumentService (форматирование, рендеринг)"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'bot'))

import pytest
from decimal import Decimal
from datetime import datetime

from services.document import _format_amount, _format_date_ru


class TestFormatAmount:
    """Тесты форматирования сумм"""

    def test_integer(self):
        assert _format_amount(1000) == "1 000,00"

    def test_large_integer(self):
        assert _format_amount(3002700) == "3 002 700,00"

    def test_with_decimals(self):
        assert _format_amount(1234.56) == "1 234,56"

    def test_zero(self):
        assert _format_amount(0) == "0,00"

    def test_small(self):
        assert _format_amount(1) == "1,00"

    def test_decimal_type(self):
        assert _format_amount(Decimal("999999.99")) == "999 999,99"

    def test_millions(self):
        result = _format_amount(15000000)
        assert result == "15 000 000,00"

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
