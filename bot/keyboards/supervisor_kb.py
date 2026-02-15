# bot/keyboards/supervisor_kb.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


class SupervisorKeyboards:
    """Клавиатуры для руководителя (супервайзера)"""

    @staticmethod
    def main_menu() -> InlineKeyboardMarkup:
        """Главное меню руководителя"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="🔴 Требуют решения", callback_data="sv:pending")
        )
        builder.row(
            InlineKeyboardButton(text="🚨 Эскалации", callback_data="sv:escalations")
        )
        builder.row(
            InlineKeyboardButton(text="⚠️ Минимальный риск", callback_data="sv:min_risk")
        )
        builder.row(
            InlineKeyboardButton(text="📋 Все заявки", callback_data="sv:all")
        )
        builder.row(
            InlineKeyboardButton(text="📊 Статистика", callback_data="sv:stats")
        )
        return builder.as_markup()

    @staticmethod
    def applications_list(applications: list, list_type: str = "pending", page: int = 0, per_page: int = 5) -> InlineKeyboardMarkup:
        """Список заявок"""
        builder = InlineKeyboardBuilder()

        start = page * per_page
        end = start + per_page
        page_apps = applications[start:end]

        for app in page_apps:
            status_emoji = {
                'supervisor_review': '🔴',
                'min_risk_review': '⚠️',
                'approved': '✅',
                'rejected': '❌',
                'bank_review': '🏦'
            }.get(app.status, '📋')

            # Название компании или ИНН (обрезаем до 35 символов если длинное)
            company_name = app.payer_name or f"ИНН {app.payer_inn}"
            if len(company_name) > 35:
                company_name = company_name[:32] + "..."

            builder.row(
                InlineKeyboardButton(
                    text=f"{status_emoji} {company_name} | {app.amount:,.0f}₽",
                    callback_data=f"sv:app:{app.id}"
                )
            )

        # Пагинация
        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton(text="⬅️", callback_data=f"sv:page:{list_type}:{page - 1}")
            )
        if end < len(applications):
            nav_buttons.append(
                InlineKeyboardButton(text="➡️", callback_data=f"sv:page:{list_type}:{page + 1}")
            )
        if nav_buttons:
            builder.row(*nav_buttons)

        builder.row(
            InlineKeyboardButton(text="🔙 Назад", callback_data="sv:menu")
        )
        return builder.as_markup()

    @staticmethod
    def application_actions(app_id: int, is_escalation: bool = False, back_to: str = "pending") -> InlineKeyboardMarkup:
        """Действия с заявкой"""
        builder = InlineKeyboardBuilder()

        builder.row(
            InlineKeyboardButton(
                text="✅ Одобрить",
                callback_data=f"sv:approve:{app_id}"
            ),
            InlineKeyboardButton(
                text="❌ Отклонить",
                callback_data=f"sv:reject:{app_id}"
            )
        )

        if is_escalation:
            builder.row(
                InlineKeyboardButton(
                    text="↩️ Вернуть менеджеру",
                    callback_data=f"sv:return:{app_id}"
                )
            )

        builder.row(
            InlineKeyboardButton(text="🔙 К списку", callback_data=f"sv:{back_to}")
        )
        return builder.as_markup()

    @staticmethod
    def rejection_reasons(app_id: int) -> InlineKeyboardMarkup:
        """Причины отклонения"""
        builder = InlineKeyboardBuilder()

        reasons = [
            ("Недостаточно информации о компании", "insufficient_info"),
            ("Сомнительная деловая репутация", "bad_reputation"),
            ("Не соответствует политике банка", "policy_violation"),
            ("Риски по госзакупкам", "gov_contracts_risk"),
            ("Другое", "other")
        ]

        for text, reason in reasons:
            builder.row(
                InlineKeyboardButton(
                    text=text,
                    callback_data=f"sv:reject_reason:{app_id}:{reason}"
                )
            )

        builder.row(
            InlineKeyboardButton(text="🔙 Отмена", callback_data=f"sv:app:{app_id}")
        )
        return builder.as_markup()

    @staticmethod
    def confirm_action(action: str, app_id: int) -> InlineKeyboardMarkup:
        """Подтверждение действия"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Подтвердить",
                callback_data=f"sv:confirm_{action}:{app_id}"
            ),
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data=f"sv:app:{app_id}"
            )
        )
        return builder.as_markup()

    @staticmethod
    def back_to_menu() -> InlineKeyboardMarkup:
        """Кнопка возврата в меню"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="🔙 В меню", callback_data="sv:menu")
        )
        return builder.as_markup()

    @staticmethod
    def stats_menu() -> InlineKeyboardMarkup:
        """Меню выбора периода статистики"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="📅 Сегодня", callback_data="sv:stats:today")
        )
        builder.row(
            InlineKeyboardButton(text="📆 Неделя", callback_data="sv:stats:week"),
            InlineKeyboardButton(text="📊 Месяц", callback_data="sv:stats:month")
        )
        builder.row(
            InlineKeyboardButton(text="🗓 Произвольный период", callback_data="sv:stats:custom")
        )
        builder.row(
            InlineKeyboardButton(text="🔙 В меню", callback_data="sv:menu")
        )
        return builder.as_markup()

    @staticmethod
    def stats_detail_menu(start_date, end_date) -> InlineKeyboardMarkup:
        """Меню детализации статистики"""
        from datetime import date
        builder = InlineKeyboardBuilder()

        start_str = start_date.isoformat()
        end_str = end_date.isoformat()

        builder.row(
            InlineKeyboardButton(
                text="🏢 По компаниям",
                callback_data=f"sv:stats:detail:by_company:{start_str}:{end_str}"
            ),
            InlineKeyboardButton(
                text="🏦 По банкам",
                callback_data=f"sv:stats:detail:by_bank:{start_str}:{end_str}"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="👤 По клиентам",
                callback_data=f"sv:stats:detail:by_client:{start_str}:{end_str}"
            ),
            InlineKeyboardButton(
                text="📅 По датам",
                callback_data=f"sv:stats:detail:by_date:{start_str}:{end_str}"
            )
        )
        builder.row(
            InlineKeyboardButton(text="🔙 К статистике", callback_data="sv:stats")
        )
        return builder.as_markup()

    @staticmethod
    def back_to_stats() -> InlineKeyboardMarkup:
        """Кнопка возврата к статистике"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="🔙 К статистике", callback_data="sv:stats")
        )
        return builder.as_markup()
