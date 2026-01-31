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

    async def get_rating(self, ogrn: str) -> Optional[dict]:
        """
        Получить рейтинг компании по ОГРН.

        Returns:
            dict с ключами: rating_category, risk_level, stop, point
            или None если запрос не удался
        """
        if not self.api_key:
            logger.warning("ZCB API key не настроен")
            return None

        url = f'{self.BASE_URL}/rating'
        params = {
            'id': ogrn,
            'api_key': self.api_key,
            '_format': 'json',
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        logger.error(f"ZCB API HTTP {resp.status} для ОГРН {ogrn}")
                        return None

                    data = await resp.json(content_type=None)

                    if data.get('status') != '200':
                        logger.error(f"ZCB API ошибка: {data.get('message')} для ОГРН {ogrn}")
                        return None

                    body = data.get('body', {})
                    return {
                        'rating_category': body.get('rating_category'),
                        'risk_level': body.get('risk_level'),
                        'stop': body.get('stop', False),
                        'point': body.get('point'),
                        'checked_at': datetime.utcnow(),
                    }
        except aiohttp.ClientError as e:
            logger.error(f"ZCB API сетевая ошибка для ОГРН {ogrn}: {e}")
            return None
        except Exception as e:
            logger.error(f"ZCB API неожиданная ошибка для ОГРН {ogrn}: {e}")
            return None
