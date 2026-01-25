# bot/keyboards/__init__.py

from .manager_kb import ManagerKeyboards
from .admin_kb import AdminKeyboards
from .bank_kb import BankKeyboards
from .supervisor_kb import SupervisorKeyboards

__all__ = [
    'ManagerKeyboards',
    'AdminKeyboards',
    'BankKeyboards',
    'SupervisorKeyboards'
]
