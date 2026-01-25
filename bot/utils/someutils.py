import uuid

def generate_unique_id() -> str:
    """Генерирует уникальный идентификатор"""
    return str(uuid.uuid4())