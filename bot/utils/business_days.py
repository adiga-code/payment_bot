# bot/utils/business_days.py

from datetime import datetime, timedelta
from typing import Optional


def add_business_days(start_date: datetime, days: int) -> datetime:
    """
    Добавить N рабочих дней к дате (без учёта сб/вс).

    Args:
        start_date: Начальная дата
        days: Количество рабочих дней (T+N)

    Returns:
        Дата выдачи

    Examples:
        Понедельник + T+1 = Вторник
        Пятница + T+1 = Понедельник
        Пятница + T+3 = Среда
    """
    current = start_date
    added = 0

    while added < days:
        current += timedelta(days=1)
        # 0=понедельник, 5=суббота, 6=воскресенье
        if current.weekday() < 5:  # Рабочий день
            added += 1

    return current


def format_payout_date(payout_date: datetime) -> str:
    """
    Форматирует дату выдачи в человекочитаемый формат.

    Args:
        payout_date: Дата выдачи

    Returns:
        Строка вида "23 января (понедельник)"
    """
    months = [
        '', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
        'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'
    ]
    weekdays = [
        'понедельник', 'вторник', 'среда', 'четверг',
        'пятница', 'суббота', 'воскресенье'
    ]

    day = payout_date.day
    month = months[payout_date.month]
    weekday = weekdays[payout_date.weekday()]

    return f"{day} {month} ({weekday})"


def get_payout_date(payout_format: str, payment_date: Optional[datetime] = None) -> datetime:
    """
    Получить дату выдачи по формату T+N.

    Args:
        payout_format: Формат выдачи ("T+1", "T+2", etc. или просто "1", "2")
        payment_date: Дата поступления средств (по умолчанию - сегодня)

    Returns:
        Дата выдачи
    """
    if payment_date is None:
        payment_date = datetime.utcnow()

    # Извлекаем число из формата (T+1 -> 1, или просто 1 -> 1)
    if payout_format.startswith('T+'):
        days = int(payout_format[2:])
    else:
        days = int(payout_format)

    return add_business_days(payment_date, days)
