# bot/utils/formatters.py


def format_application_number(app, for_client: bool = True) -> str:
    """
    Форматировать номер заявки для отображения.

    Args:
        app: Объект Application
        for_client: True для клиента (использует client_display_number),
                   False для банка (использует bank_display_number)

    Returns:
        Строка вида "Заявка №123" или "APP-xxx" если номер не установлен
    """
    if for_client and app.client_display_number:
        return f"Заявка №{app.client_display_number}"
    elif not for_client and app.bank_display_number:
        return f"Заявка №{app.bank_display_number}"
    else:
        # Fallback на external_id если display_number не установлен
        return app.external_id
