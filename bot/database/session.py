from .models import Base
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

class DatabaseManager:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = create_async_engine(url=self.database_url)
        self.async_session = async_sessionmaker(
            self.engine,
            expire_on_commit=True)

    async def initialise(self):
        '''
            Создает все таблицы базы данных и применяет миграции
        '''
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Миграции для существующих таблиц
        await self._apply_migrations()

    async def _apply_migrations(self):
        '''Добавление новых колонок в существующие таблицы'''
        from sqlalchemy import text

        async with self.engine.begin() as conn:
            # Добавить bank_id в users (если не существует)
            await conn.execute(text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                "bank_id INTEGER REFERENCES banks(id) ON DELETE SET NULL"
            ))

            # Сделать banks.chat_id nullable (если ещё NOT NULL)
            await conn.execute(text(
                "ALTER TABLE banks ALTER COLUMN chat_id DROP NOT NULL"
            ))

            # Добавить ogrn и поля ЗЧБ в companies
            await conn.execute(text(
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS "
                "ogrn VARCHAR(15) UNIQUE"
            ))
            await conn.execute(text(
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS "
                "zcb_rating_category VARCHAR(50)"
            ))
            await conn.execute(text(
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS "
                "zcb_risk_level VARCHAR(50)"
            ))
            await conn.execute(text(
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS "
                "zcb_stop BOOLEAN"
            ))
            await conn.execute(text(
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS "
                "zcb_point INTEGER"
            ))
            await conn.execute(text(
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS "
                "zcb_checked_at TIMESTAMP"
            ))

            # Юридические реквизиты компании
            await conn.execute(text(
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS "
                "kpp VARCHAR(9)"
            ))
            await conn.execute(text(
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS "
                "legal_address VARCHAR(500)"
            ))
            await conn.execute(text(
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS "
                "director_name VARCHAR(255)"
            ))
            await conn.execute(text(
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS "
                "accountant_name VARCHAR(255)"
            ))

            # Банковские реквизиты компании
            await conn.execute(text(
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS "
                "bank_name VARCHAR(255)"
            ))
            await conn.execute(text(
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS "
                "bank_bik VARCHAR(9)"
            ))
            await conn.execute(text(
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS "
                "bank_account VARCHAR(20)"
            ))
            await conn.execute(text(
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS "
                "bank_corr_account VARCHAR(20)"
            ))

            # Данные покупателя и договора в заявках
            await conn.execute(text(
                "ALTER TABLE applications ADD COLUMN IF NOT EXISTS "
                "payer_kpp VARCHAR(9)"
            ))
            await conn.execute(text(
                "ALTER TABLE applications ADD COLUMN IF NOT EXISTS "
                "payer_address VARCHAR(500)"
            ))
            await conn.execute(text(
                "ALTER TABLE applications ADD COLUMN IF NOT EXISTS "
                "contract_number VARCHAR(100)"
            ))
            await conn.execute(text(
                "ALTER TABLE applications ADD COLUMN IF NOT EXISTS "
                "contract_date VARCHAR(20)"
            ))
            await conn.execute(text(
                "ALTER TABLE applications ADD COLUMN IF NOT EXISTS "
                "invoice_purpose TEXT"
            ))

            # Печать компании
            await conn.execute(text(
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS "
                "stamp_image_path VARCHAR(500)"
            ))