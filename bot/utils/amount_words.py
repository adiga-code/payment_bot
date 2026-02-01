# bot/utils/amount_words.py

"""Конвертация суммы в рубли прописью (русский язык)"""

_ONES_M = [
    '', 'один', 'два', 'три', 'четыре',
    'пять', 'шесть', 'семь', 'восемь', 'девять'
]
_ONES_F = [
    '', 'одна', 'две', 'три', 'четыре',
    'пять', 'шесть', 'семь', 'восемь', 'девять'
]
_TEENS = [
    'десять', 'одиннадцать', 'двенадцать', 'тринадцать', 'четырнадцать',
    'пятнадцать', 'шестнадцать', 'семнадцать', 'восемнадцать', 'девятнадцать'
]
_TENS = [
    '', '', 'двадцать', 'тридцать', 'сорок',
    'пятьдесят', 'шестьдесят', 'семьдесят', 'восемьдесят', 'девяносто'
]
_HUNDREDS = [
    '', 'сто', 'двести', 'триста', 'четыреста',
    'пятьсот', 'шестьсот', 'семьсот', 'восемьсот', 'девятьсот'
]

_ORDERS = [
    # (единичное, 2-4, 5-20, род: m/f)
    ('', '', '', 'm'),
    ('тысяча', 'тысячи', 'тысяч', 'f'),
    ('миллион', 'миллиона', 'миллионов', 'm'),
    ('миллиард', 'миллиарда', 'миллиардов', 'm'),
]


def _plural(n: int, one: str, two: str, five: str) -> str:
    """Склонение по числу"""
    n = abs(n) % 100
    if 11 <= n <= 19:
        return five
    n = n % 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return two
    return five


def _triplet(n: int, gender: str) -> str:
    """Три цифры в слова"""
    if n == 0:
        return ''
    h = n // 100
    t = (n % 100) // 10
    o = n % 10

    parts = []
    if h:
        parts.append(_HUNDREDS[h])
    if t == 1:
        parts.append(_TEENS[o])
    else:
        if t:
            parts.append(_TENS[t])
        if o:
            ones = _ONES_F if gender == 'f' else _ONES_M
            parts.append(ones[o])

    return ' '.join(parts)


def amount_to_words(amount) -> str:
    """
    Конвертация суммы в рубли прописью.

    amount_to_words(3002700) -> "Три миллиона две тысячи семьсот рублей 00 копеек"
    amount_to_words(1500.50) -> "Одна тысяча пятьсот рублей 50 копеек"
    """
    from decimal import Decimal
    amount = Decimal(str(amount))
    rubles = int(amount)
    kopecks = int(round((amount - rubles) * 100))

    if rubles == 0:
        result = 'Ноль'
    else:
        groups = []
        n = rubles
        order = 0
        while n > 0:
            triplet = n % 1000
            n //= 1000
            if triplet:
                one, two, five, gender = _ORDERS[order]
                t_str = _triplet(triplet, gender)
                order_str = _plural(triplet, one, two, five)
                groups.append(f"{t_str} {order_str}".strip())
            order += 1

        groups.reverse()
        result = ' '.join(groups)
        result = result[0].upper() + result[1:]

    rub_word = _plural(rubles, 'рубль', 'рубля', 'рублей')
    kop_word = _plural(kopecks, 'копейка', 'копейки', 'копеек')

    return f"{result} {rub_word} {kopecks:02d} {kop_word}"
