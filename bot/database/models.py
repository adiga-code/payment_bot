# bot/database/models.py

from sqlalchemy import BigInteger, ForeignKey, DateTime, Text, String, Integer, Numeric, Boolean, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncAttrs
from datetime import datetime
from decimal import Decimal


def utcnow():
    """Текущее время UTC"""
    return datetime.utcnow()


# Базовый класс
class Base(AsyncAttrs, DeclarativeBase):
    pass


# 1. Пользователи
class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True
    )  # 'manager', 'bank', 'accountant', 'supervisor', 'admin'
    bank_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('banks.id', ondelete='SET NULL'),
        nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    # Связи
    bank: Mapped["Bank"] = relationship(
        'Bank',
        back_populates='employees',
        foreign_keys=[bank_id]
    )
    managed_applications: Mapped[list["Application"]] = relationship(
        'Application',
        back_populates='manager',
        foreign_keys='Application.manager_id'
    )
    approvals: Mapped[list["Approval"]] = relationship(
        'Approval',
        back_populates='user'
    )
    logs: Mapped[list["Log"]] = relationship(
        'Log',
        back_populates='user'
    )

    def __repr__(self):
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, role={self.role})>"


# 2. Компании
class Company(Base):
    __tablename__ = 'companies'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    inn: Mapped[str] = mapped_column(String(12), unique=True, nullable=False, index=True)
    
    daily_limit: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    weekly_limit: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    monthly_limit: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    
    current_daily_used: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    current_weekly_used: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    current_monthly_used: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    # Связи
    applications: Mapped[list["Application"]] = relationship(
        'Application',
        back_populates='company'
    )
    company_banks: Mapped[list["CompanyBank"]] = relationship(
        'CompanyBank',
        back_populates='company'
    )

    def __repr__(self):
        return f"<Company(id={self.id}, name={self.name}, inn={self.inn})>"


# 3. Банки
class Bank(Base):
    __tablename__ = 'banks'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True, index=True)
    
    daily_limit: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    weekly_limit: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    
    current_daily_used: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    current_weekly_used: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    
    priority: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    # Связи
    employees: Mapped[list["User"]] = relationship(
        'User',
        back_populates='bank',
        foreign_keys='User.bank_id'
    )
    applications: Mapped[list["Application"]] = relationship(
        'Application',
        back_populates='bank'
    )
    company_banks: Mapped[list["CompanyBank"]] = relationship(
        'CompanyBank',
        back_populates='bank'
    )

    def __repr__(self):
        return f"<Bank(id={self.id}, name={self.name})>"


# 4. Связь компаний и банков
class CompanyBank(Base):
    __tablename__ = 'company_banks'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('companies.id', ondelete='CASCADE'),
        nullable=False
    )
    bank_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('banks.id', ondelete='CASCADE'),
        nullable=False
    )
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=False)

    # Связи
    company: Mapped["Company"] = relationship(
        'Company',
        back_populates='company_banks'
    )
    bank: Mapped["Bank"] = relationship(
        'Bank',
        back_populates='company_banks'
    )

    def __repr__(self):
        return f"<CompanyBank(company_id={self.company_id}, bank_id={self.bank_id})>"


# 5. Заявки
class Application(Base):
    __tablename__ = 'applications'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    
    # Данные
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    payer_inn: Mapped[str] = mapped_column(String(12), nullable=False)
    payer_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Связи
    company_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('companies.id'),
        nullable=True
    )
    bank_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('banks.id'),
        nullable=True
    )
    manager_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('users.id'),
        nullable=True
    )
    
    # Статус
    status: Mapped[str] = mapped_column(String(50), default='new', index=True)
    
    # Первичная проверка
    primary_check_status: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    primary_check_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    primary_check_flags: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    primary_check_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    
    # Чаты
    client_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    client_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    # Временные метки
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    sent_to_bank_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    bank_response_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    invoice_generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    
    # Дополнительно
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Связи
    company: Mapped["Company"] = relationship(
        'Company',
        back_populates='applications'
    )
    bank: Mapped["Bank"] = relationship(
        'Bank',
        back_populates='applications'
    )
    manager: Mapped["User"] = relationship(
        'User',
        back_populates='managed_applications',
        foreign_keys=[manager_id]
    )
    approvals: Mapped[list["Approval"]] = relationship(
        'Approval',
        back_populates='application',
        cascade='all, delete-orphan'
    )
    documents: Mapped[list["Document"]] = relationship(
        'Document',
        back_populates='application',
        cascade='all, delete-orphan'
    )
    logs: Mapped[list["Log"]] = relationship(
        'Log',
        back_populates='application'
    )

    def __repr__(self):
        return f"<Application(id={self.id}, external_id={self.external_id}, status={self.status})>"


# 6. Подписи (мультиподпись)
class Approval(Base):
    __tablename__ = 'approvals'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('applications.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('users.id'),
        nullable=True
    )
    decision: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Связи
    application: Mapped["Application"] = relationship(
        'Application',
        back_populates='approvals'
    )
    user: Mapped["User"] = relationship(
        'User',
        back_populates='approvals'
    )

    def __repr__(self):
        return f"<Approval(id={self.id}, role={self.role}, decision={self.decision})>"


# 7. Документы
class Document(Base):
    __tablename__ = 'documents'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('applications.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    
    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sent_to_client_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Связи
    application: Mapped["Application"] = relationship(
        'Application',
        back_populates='documents'
    )

    def __repr__(self):
        return f"<Document(id={self.id}, type={self.type}, number={self.number})>"


# 8. Логи действий
class Log(Base):
    __tablename__ = 'logs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('users.id'),
        nullable=True,
        index=True
    )
    application_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey('applications.id'),
        nullable=True,
        index=True
    )
    
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    # Связи
    user: Mapped["User"] = relationship(
        'User',
        back_populates='logs'
    )
    application: Mapped["Application"] = relationship(
        'Application',
        back_populates='logs'
    )

    def __repr__(self):
        return f"<Log(id={self.id}, action={self.action})>"


# 9. Настройки системы
class Setting(Base):
    __tablename__ = 'settings'

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    def __repr__(self):
        return f"<Setting(key={self.key})>"