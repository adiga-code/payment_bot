# bot/middleware/auth.py

from typing import Callable, Dict, Any, Awaitable, Optional, List
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from database import UserRepository, DatabaseManager


class AuthMiddleware(BaseMiddleware):
    """
    Middleware для аутентификации и авторизации пользователей.

    Функции:
    1. Проверяет, зарегистрирован ли пользователь
    2. Загружает данные пользователя в handler data
    3. Проверяет роль для защищённых команд
    """

    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Получаем telegram_id из события
        user = None
        telegram_id = self._get_telegram_id(event)

        if telegram_id:
            # Загружаем пользователя из БД
            user = await self.user_repo.get_by_telegram_id(telegram_id)

        # Добавляем в data для использования в handlers
        data['db_user'] = user
        data['is_registered'] = user is not None
        data['user_role'] = user.role if user else None

        return await handler(event, data)

    def _get_telegram_id(self, event: TelegramObject) -> Optional[int]:
        """Извлекает telegram_id из разных типов событий"""
        if isinstance(event, Message):
            return event.from_user.id if event.from_user else None
        elif isinstance(event, CallbackQuery):
            return event.from_user.id if event.from_user else None
        return None


class RoleRequiredMiddleware(BaseMiddleware):
    """
    Middleware для проверки роли пользователя.

    Использование:
        router.message.middleware(RoleRequiredMiddleware(['manager', 'admin']))
    """

    def __init__(self, allowed_roles: List[str], user_repo: UserRepository):
        self.allowed_roles = allowed_roles
        self.user_repo = user_repo
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        telegram_id = self._get_telegram_id(event)

        if not telegram_id:
            return  # Игнорируем события без пользователя

        # Получаем пользователя
        user = await self.user_repo.get_by_telegram_id(telegram_id)

        if not user:
            await self._send_not_registered(event)
            return

        if not user.is_active:
            await self._send_deactivated(event)
            return

        if user.role not in self.allowed_roles:
            await self._send_no_access(event)
            return

        # Добавляем пользователя в data
        data['db_user'] = user

        return await handler(event, data)

    def _get_telegram_id(self, event: TelegramObject) -> Optional[int]:
        if isinstance(event, Message):
            return event.from_user.id if event.from_user else None
        elif isinstance(event, CallbackQuery):
            return event.from_user.id if event.from_user else None
        return None

    async def _send_not_registered(self, event: TelegramObject):
        """Сообщение для незарегистрированных"""
        text = "❌ Вы не зарегистрированы в системе.\nОбратитесь к администратору."
        if isinstance(event, Message):
            await event.answer(text)
        elif isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)

    async def _send_deactivated(self, event: TelegramObject):
        """Сообщение для деактивированных"""
        text = "❌ Ваш аккаунт деактивирован.\nОбратитесь к администратору."
        if isinstance(event, Message):
            await event.answer(text)
        elif isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)

    async def _send_no_access(self, event: TelegramObject):
        """Сообщение при отсутствии доступа"""
        text = "🚫 У вас нет доступа к этой функции."
        if isinstance(event, Message):
            await event.answer(text)
        elif isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)


def role_required(allowed_roles: List[str]):
    """
    Декоратор для проверки роли (альтернатива middleware).

    Использование:
        @router.message(Command("admin_panel"))
        @role_required(['admin'])
        async def admin_panel(message: Message, db_user: User):
            ...
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            db_user = kwargs.get('db_user')

            if not db_user:
                # Ищем message или callback в args
                event = args[0] if args else None
                if isinstance(event, (Message, CallbackQuery)):
                    await event.answer("❌ Вы не зарегистрированы в системе.")
                return

            if db_user.role not in allowed_roles:
                event = args[0] if args else None
                if isinstance(event, (Message, CallbackQuery)):
                    await event.answer("🚫 У вас нет доступа к этой функции.")
                return

            return await func(*args, **kwargs)
        return wrapper
    return decorator
