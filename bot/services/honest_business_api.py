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

        return {
            'ogrn': item.get('id') or item.get('ogrn'),
            'inn': item.get('inn', inn),
            'name': item.get('name') or item.get('fullName') or item.get('shortName'),
            'status': item.get('status'),
            'raw': item,
        }

    async def get_rating(self, ogrn: str) -> Optional[dict]:
        """
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

    async def check_payer(self, inn: str) -> dict:
        """
        Полная проверка плательщика по ИНН:
        1. Поиск компании (ИНН → ОГРН + название)
        2. Получение рейтинга по ОГРН

        Returns:
            dict с результатами проверки (всегда возвращает dict, даже при ошибках)
        """
        result = {
            'inn': inn,
            'name': None,
            'ogrn': None,
            'rating_category': None,
            'risk_level': None,
            'stop': None,
            'point': None,
            'color': None,
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

        # 2. Рейтинг по ОГРН
        ogrn = search_data.get('ogrn')
        if not ogrn:
            result['errors'].append('ogrn_not_found')
            return result

        rating = await self.get_rating(ogrn)
        if not rating:
            result['errors'].append('rating_failed')
            return result

        result['rating_category'] = rating['rating_category']
        result['risk_level'] = rating['risk_level']
        result['stop'] = rating['stop']
        result['point'] = rating['point']
        result['color'] = get_zcb_color(rating['risk_level'])

        return result


def format_payer_check(check_result: dict) -> str:
    """Форматирование результатов проверки плательщика для отображения"""
    if not check_result:
        return '⚪ Проверка ЗЧБ: не выполнена'

    lines = ['<b>Проверка ЗЧБ:</b>']

    if check_result.get('name'):
        lines.append(f"📛 {check_result['name']}")

    if check_result.get('ogrn'):
        lines.append(f"🔢 ОГРН: {check_result['ogrn']}")

    if check_result.get('risk_level'):
        color_text = format_zcb_color(check_result['risk_level'])
        lines.append(f"🎨 Цвет: {color_text}")
        lines.append(f"📊 Индекс: {check_result.get('rating_category', '?')} ({check_result.get('point', '?')})")
        lines.append(f"🚫 Стоп-факт: {'Да' if check_result.get('stop') else 'Нет'}")
    elif check_result.get('errors'):
        errors = check_result['errors']
        if 'search_failed' in errors:
            lines.append('⚠️ Компания не найдена в ЗЧБ')
        elif 'ogrn_not_found' in errors:
            lines.append('⚠️ ОГРН не определён')
        elif 'rating_failed' in errors:
            lines.append('⚠️ Не удалось получить рейтинг')

    return '\n'.join(lines)
