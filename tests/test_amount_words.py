"""Тесты для конвертации суммы в слова (русский язык)"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'bot'))

import pytest
from utils.amount_words import amount_to_words


class TestAmountToWords:
    """Тесты amount_to_words"""

    def test_zero(self):
        assert amount_to_words(0) == "Ноль рублей 00 копеек"

    def test_one(self):
        result = amount_to_words(1)
        assert result == "Один рубль 00 копеек"

    def test_two(self):
        result = amount_to_words(2)
        assert result == "Два рубля 00 копеек"

    def test_five(self):
        result = amount_to_words(5)
        assert result == "Пять рублей 00 копеек"

    def test_eleven(self):
        result = amount_to_words(11)
        assert result == "Одиннадцать рублей 00 копеек"

    def test_twenty_one(self):
        result = amount_to_words(21)
        assert result == "Двадцать один рубль 00 копеек"

    def test_hundred(self):
        result = amount_to_words(100)
        assert result == "Сто рублей 00 копеек"

    def test_one_thousand(self):
        result = amount_to_words(1000)
        assert result == "Одна тысяча рублей 00 копеек"

    def test_two_thousand(self):
        result = amount_to_words(2000)
        assert result == "Две тысячи рублей 00 копеек"

    def test_five_thousand(self):
        result = amount_to_words(5000)
        assert result == "Пять тысяч рублей 00 копеек"

    def test_million(self):
        result = amount_to_words(1000000)
        assert result == "Один миллион рублей 00 копеек"

    def test_three_million_complex(self):
        result = amount_to_words(3002700)
        assert result == "Три миллиона две тысячи семьсот рублей 00 копеек"

    def test_with_kopecks_decimal(self):
        result = amount_to_words(1234.56)
        assert result == "Одна тысяча двести тридцать четыре рубля 56 копеек"

    def test_large_amount(self):
        result = amount_to_words(999999999)
        assert "миллионов" in result
        assert "рублей" in result

    def test_twelve(self):
        result = amount_to_words(12)
        assert result == "Двенадцать рублей 00 копеек"

    def test_rub_plural_forms(self):
        """Проверяем склонение 'рубль/рубля/рублей'"""
        assert "рубль" in amount_to_words(1)
        assert "рубля" in amount_to_words(2)
        assert "рублей" in amount_to_words(5)
        assert "рублей" in amount_to_words(11)
        assert "рубль" in amount_to_words(21)
        assert "рубля" in amount_to_words(22)
        assert "рублей" in amount_to_words(100)

    def test_thousand_feminine_gender(self):
        """Тысяча — женский род: одна/две"""
        result_1000 = amount_to_words(1000)
        assert "Одна тысяча" in result_1000

        result_2000 = amount_to_words(2000)
        assert "Две тысячи" in result_2000

    def test_first_letter_capitalized(self):
        """Первая буква заглавная"""
        result = amount_to_words(42)
        assert result[0].isupper()
