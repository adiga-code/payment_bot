# bot/services/honest_business_api.py

import logging
from datetime import datetime
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# Маппинг risk_level → цвет
RISK_COLOR_MAP = {
    'низкий': 'green',
    'средний': 'yellow',
    'высокий': 'red',
}

COLOR_EMOJI = {
    'green': '🟢',
    'yellow': '🟡',
    'red': '🔴',
}

COLOR_NAME_RU = {
    'green': 'Зелёный',
    'yellow': 'Жёлтый',
    'red': 'Красный',
}


def get_zcb_color(risk_level: str | None) -> str | None:
    """Получить цвет по risk_level"""
    if not risk_level:
        return None
    return RISK_COLOR_MAP.get(risk_level.lower())


def format_zcb_color(risk_level: str | None) -> str:
    """Форматированный цвет с эмодзи для отображения"""
    color = get_zcb_color(risk_level)
    if not color:
        return '⚪ Не проверен'
    emoji = COLOR_EMOJI.get(color, '⚪')
    name = COLOR_NAME_RU.get(color, 'Неизвестно')
    return f'{emoji} {name}'


class ZCBService:
    """Сервис для работы с API ЗАЧЕСТНЫЙБИЗНЕС"""

    BASE_URL = 'https://zachestnyibiznesapi.ru/paid/data'

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def _request(self, method: str, params: dict) -> Optional[dict]:
        """Общий метод запроса к API"""
        if not self.api_key:
            logger.warning("ZCB API key не настроен")
            return None

        url = f'{self.BASE_URL}/{method}'
        params['api_key'] = self.api_key
        params['_format'] = 'json'

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        logger.error(f"ZCB API HTTP {resp.status} для {method} {params}")
                        return None

                    data = await resp.json(content_type=None)

                    if data.get('status') != '200':
                        logger.error(f"ZCB API ошибка: {data.get('message')} для {method}")
                        return None

                    return data.get('body', {})
        except aiohttp.ClientError as e:
            logger.error(f"ZCB API сетевая ошибка для {method}: {e}")
            return None
        except Exception as e:
            logger.error(f"ZCB API неожиданная ошибка для {method}: {e}")
            return None

    async def search(self, inn: str) -> Optional[dict]:
        """
        Поиск компании по ИНН. Возвращает первый результат.

        Returns:
            dict с данными компании (id=ОГРН, inn, name и т.д.)
            или None если не найдено
        """
        body = await self._request('search', {'string': inn})
        if not body:
            return None

        docs = body.get('docs', [])
        if not docs:
            logger.info(f"ZCB search: ничего не найдено для ИНН {inn}")
            return None

        # Берём первый результат
        item = docs[0] if isinstance(docs, list) else None
        if not item:
            return None

        # Логируем что вернул API для отладки
        logger.info(f"ZCB search result for {inn}: {item}")

        return {
            'ogrn': item.get('id') or item.get('ogrn'),
            'inn': item.get('inn', inn),
            'name': item.get('name') or item.get('fullName') or item.get('shortName'),
            'kpp': item.get('kpp'),
            'address': item.get('address') or item.get('legalAddress'),
            'status': item.get('status'),
            'raw': item,
        }

    async def get_cbr_rating(self, ogrn: str) -> Optional[dict]:
        """
        Получить уровень риска ЦБ РФ по ОГРН.

        Returns:
            dict с ключами: level (success/warning/danger), facts, history
            или None если запрос не удался
        """
        body = await self._request('cbr-rating', {'id': ogrn})
        if not body:
            return None

        return {
            'level': body.get('level'),  # success, warning, danger
            'facts': body.get('facts', {}),  # {danger: [...], warning: [...]}
            'history': body.get('history', []),
            'checked_at': datetime.utcnow().isoformat(),
        }

    async def get_rating(self, ogrn: str) -> Optional[dict]:
        """
        УСТАРЕЛ: Использовать get_cbr_rating вместо этого метода.
        Получить рейтинг компании по ОГРН.

        Returns:
            dict с ключами: rating_category, risk_level, stop, point
            или None если запрос не удался
        """
        body = await self._request('rating', {'id': ogrn})
        if not body:
            return None

        return {
            'rating_category': body.get('rating_category'),
            'risk_level': body.get('risk_level'),
            'stop': body.get('stop', False),
            'point': body.get('point'),
            'checked_at': datetime.utcnow(),
        }

    async def check_zakupki(self, inn: str) -> Optional[dict]:
        """
        Проверка госзакупок по ИНН.
        Проверяет участие компании как поставщика (participant).

        Returns:
            dict с ключами: count (общее количество), total_sum (общая сумма)
            или None если запрос не удался
        """
        body = await self._request('zakupki-top', {'id': inn, 'top_type': 'participant'})
        if body is None:
            return None

        total = body.get('total', 0)
        if isinstance(total, str):
            total = int(total) if total.isdigit() else 0

        # Считаем общую сумму по всем контрактам
        docs = body.get('docs', [])
        total_sum = 0
        for doc in docs:
            doc_sum = doc.get('sum', 0)
            if isinstance(doc_sum, str):
                doc_sum = int(doc_sum) if doc_sum.isdigit() else 0
            total_sum += doc_sum

        return {
            'count': total,
            'total_sum': total_sum,
        }

    async def check_payer(self, inn: str) -> dict:
        """
        Полная проверка плательщика по ИНН:
        1. Поиск компании (ИНН → ОГРН + название)
        2. Получение риска ЦБ РФ по ОГРН
        3. Проверка госзакупок

        Returns:
            dict с результатами проверки (всегда возвращает dict, даже при ошибках)
        """
        result = {
            'inn': inn,
            'name': None,
            'ogrn': None,
            'kpp': None,
            'address': None,
            'rating_category': None,
            'risk_level': None,
            'stop': None,
            'point': None,
            'color': None,
            'cbr_risk': None,  # {'level': 'success/warning/danger', 'facts': {...}}
            'zakupki': None,  # {'count': N, 'total_sum': X}
            'checked_at': datetime.utcnow().isoformat(),
            'errors': [],
        }

        # 1. Поиск по ИНН
        search_data = await self.search(inn)
        if not search_data:
            result['errors'].append('search_failed')
            return result

        result['name'] = search_data.get('name')
        result['ogrn'] = search_data.get('ogrn')
        result['kpp'] = search_data.get('kpp')
        result['address'] = search_data.get('address')

        # 2. Риск ЦБ РФ по ОГРН
        ogrn = search_data.get('ogrn')
        if not ogrn:
            result['errors'].append('ogrn_not_found')
            return result

        cbr_risk = await self.get_cbr_rating(ogrn)
        if not cbr_risk:
            result['errors'].append('cbr_rating_failed')
        else:
            result['cbr_risk'] = cbr_risk

        # 3. Проверка госзакупок
        zakupki = await self.check_zakupki(inn)
        if zakupki:
            result['zakupki'] = zakupki

        return result


def format_amount_short(amount: int) -> str:
    """Форматирует сумму: 5000000 → '5 000 000₽'"""
    return f"{amount:,}₽".replace(",", " ")


def get_cbr_risk_emoji(level: str | None) -> str:
    """Получить эмодзи для уровня риска ЦБ РФ"""
    if not level:
        return '⚪'
    level_map = {
        'success': '🟢',
        'warning': '🟡',
        'danger': '🔴'
    }
    return level_map.get(level.lower(), '⚪')


def get_cbr_risk_name(level: str | None) -> str:
    """Получить название уровня риска ЦБ РФ"""
    if not level:
        return 'Не проверен'
    level_map = {
        'success': 'Низкий риск',
        'warning': 'Средний риск',
        'danger': 'Высокий риск'
    }
    return level_map.get(level.lower(), 'Неизвестно')


def format_cbr_rating(cbr_data: dict | None) -> str:
    """Форматирование результатов проверки риска ЦБ РФ"""
    if not cbr_data:
        return '⚪ Риск ЦБ РФ: не проверен'

    level = cbr_data.get('level')
    emoji = get_cbr_risk_emoji(level)
    name = get_cbr_risk_name(level)

    # Показываем только уровень риска, без деталей (убраны предупреждения для банка)
    return f'{emoji} <b>Риск ЦБ РФ: {name}</b>'


def format_payer_check(check_result: dict) -> str:
    """Форматирование результатов проверки плательщика для отображения"""
    if not check_result:
        return '⚪ Проверка не выполнена'

    lines = []

    if check_result.get('name'):
        lines.append(f"📛 <b>{check_result['name']}</b>")

    if check_result.get('ogrn'):
        lines.append(f"🔢 ОГРН: <code>{check_result['ogrn']}</code>")

    # Риск ЦБ РФ
    cbr_risk = check_result.get('cbr_risk')
    if cbr_risk:
        cbr_text = format_cbr_rating(cbr_risk)
        lines.append(f"\n{cbr_text}")
    elif 'cbr_rating_failed' in check_result.get('errors', []):
        lines.append('\n⚠️ Не удалось получить риск ЦБ РФ')
    elif check_result.get('errors'):
        errors = check_result['errors']
        if 'search_failed' in errors:
            lines.append('\n⚠️ Компания не найдена')
        elif 'ogrn_not_found' in errors:
            lines.append('\n⚠️ ОГРН не определён')

    # Госзакупки
    zakupki = check_result.get('zakupki')
    if zakupki and zakupki.get('count', 0) > 0:
        count = zakupki['count']
        total_sum = zakupki.get('total_sum', 0)
        lines.append(f"\n⚠️ <b>Госзакупки:</b> {count} контр. на {format_amount_short(total_sum)}")
    elif zakupki is not None:
        lines.append("\n✅ <b>Госзакупки:</b> проверка пройдена")

    return '\n'.join(lines)
