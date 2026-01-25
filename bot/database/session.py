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
            Создает все таблицы базы данных
        '''
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)