-- Создание расширений
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Создание таблиц

-- 1. Банки (создаём первыми, т.к. users ссылается на banks)
CREATE TABLE banks (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    bik VARCHAR(9),
    corr_account VARCHAR(20),
    chat_id BIGINT UNIQUE,

    daily_limit DECIMAL(15,2) DEFAULT 0,
    weekly_limit DECIMAL(15,2) DEFAULT 0,

    current_daily_used DECIMAL(15,2) DEFAULT 0,
    current_weekly_used DECIMAL(15,2) DEFAULT 0,

    priority INT DEFAULT 100,
    is_active BOOLEAN DEFAULT TRUE,
    is_available BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 2. Пользователи
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(100),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    role VARCHAR(20) NOT NULL CHECK (role IN ('client', 'manager', 'bank', 'accountant', 'supervisor', 'admin')),
    bank_id INT REFERENCES banks(id) ON DELETE SET NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 3. Компании
CREATE TABLE companies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    inn VARCHAR(12) NOT NULL UNIQUE,
    ogrn VARCHAR(15) UNIQUE,

    -- Юридические реквизиты
    kpp VARCHAR(9),
    legal_address VARCHAR(500),
    director_name VARCHAR(255),
    accountant_name VARCHAR(255),

    -- Лимиты
    daily_limit DECIMAL(15,2) DEFAULT 0,
    weekly_limit DECIMAL(15,2) DEFAULT 0,
    monthly_limit DECIMAL(15,2) DEFAULT 0,

    current_daily_used DECIMAL(15,2) DEFAULT 0,
    current_weekly_used DECIMAL(15,2) DEFAULT 0,
    current_monthly_used DECIMAL(15,2) DEFAULT 0,

    -- ЗЧБ данные
    zcb_rating_category VARCHAR(50),
    zcb_risk_level VARCHAR(50),
    zcb_stop BOOLEAN,
    zcb_point INT,
    zcb_checked_at TIMESTAMP,

    -- Риск ЦБ РФ
    cbr_risk_level VARCHAR(50),
    cbr_risk_facts JSONB,
    cbr_checked_at TIMESTAMP,

    -- Подпись и печать
    signature_image_path VARCHAR(500),

    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 4. Связь компаний и банков (счета компании в банках)
CREATE TABLE company_banks (
    id SERIAL PRIMARY KEY,
    company_id INT REFERENCES companies(id) ON DELETE CASCADE,
    bank_id INT REFERENCES banks(id) ON DELETE CASCADE,
    account_number VARCHAR(20),
    is_preferred BOOLEAN DEFAULT FALSE,
    UNIQUE(company_id, bank_id)
);

-- 5. Заявки
CREATE TABLE applications (
    id SERIAL PRIMARY KEY,
    external_id VARCHAR(50) UNIQUE NOT NULL,

    -- Данные платежа
    amount DECIMAL(15,2) NOT NULL,
    payer_inn VARCHAR(12) NOT NULL,
    payer_name VARCHAR(500),
    payer_kpp VARCHAR(9),
    payer_address VARCHAR(500),
    purpose TEXT NOT NULL,

    -- Данные договора
    contract_number VARCHAR(100),
    contract_date VARCHAR(20),
    invoice_purpose TEXT,

    -- Связи
    company_id INT REFERENCES companies(id),
    bank_id INT REFERENCES banks(id),
    manager_id INT REFERENCES users(id),

    -- Статус
    status VARCHAR(50) DEFAULT 'new',

    -- Первичная проверка
    primary_check_status VARCHAR(50),
    primary_check_result JSONB,
    primary_check_flags JSONB,
    primary_check_at TIMESTAMP,

    -- Чаты
    client_chat_id BIGINT NOT NULL,
    client_message_id INT,

    -- Временные метки
    created_at TIMESTAMP DEFAULT NOW(),
    sent_to_bank_at TIMESTAMP,
    bank_response_at TIMESTAMP,
    approved_at TIMESTAMP,
    invoice_generated_at TIMESTAMP,
    invoice_sent_at TIMESTAMP,
    client_confirmed_at TIMESTAMP,
    payment_received_at TIMESTAMP,
    paid_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT NOW(),

    -- Выдача
    payout_format VARCHAR(10),
    payout_date TIMESTAMP,

    -- Отмена
    cancellation_reason TEXT,

    -- Дополнительно
    source VARCHAR(100),
    notes TEXT
);

-- 6. Подписи (мультиподпись)
CREATE TABLE approvals (
    id SERIAL PRIMARY KEY,
    application_id INT REFERENCES applications(id) ON DELETE CASCADE,

    role VARCHAR(50) NOT NULL,
    sequence INT NOT NULL,
    required BOOLEAN DEFAULT TRUE,

    user_id INT REFERENCES users(id),
    decision VARCHAR(50),
    comment TEXT,

    created_at TIMESTAMP DEFAULT NOW(),
    decided_at TIMESTAMP,

    UNIQUE(application_id, sequence)
);

-- 7. Документы
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    application_id INT REFERENCES applications(id) ON DELETE CASCADE,

    type VARCHAR(50) NOT NULL,
    number VARCHAR(100),
    file_path VARCHAR(500),
    file_url VARCHAR(500),

    generated_at TIMESTAMP DEFAULT NOW(),
    sent_to_client_at TIMESTAMP,

    is_active BOOLEAN DEFAULT TRUE
);

-- 8. Логи действий
CREATE TABLE logs (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id),
    application_id INT REFERENCES applications(id),

    action VARCHAR(100) NOT NULL,
    details JSONB,

    created_at TIMESTAMP DEFAULT NOW()
);

-- 9. Настройки системы
CREATE TABLE settings (
    key VARCHAR(100) PRIMARY KEY,
    value JSONB,
    description TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Индексы
CREATE INDEX idx_users_telegram_id ON users(telegram_id);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_bank_id ON users(bank_id);

CREATE INDEX idx_companies_inn ON companies(inn);

CREATE INDEX idx_banks_chat_id ON banks(chat_id);
CREATE INDEX idx_banks_bik ON banks(bik);

CREATE INDEX idx_applications_status ON applications(status);
CREATE INDEX idx_applications_primary_check ON applications(primary_check_status);
CREATE INDEX idx_applications_created_at ON applications(created_at DESC);
CREATE INDEX idx_applications_external_id ON applications(external_id);
CREATE INDEX idx_applications_manager_id ON applications(manager_id);
CREATE INDEX idx_applications_company_id ON applications(company_id);
CREATE INDEX idx_applications_bank_id ON applications(bank_id);

CREATE INDEX idx_approvals_app ON approvals(application_id);
CREATE INDEX idx_approvals_decision ON approvals(decision);
CREATE INDEX idx_approvals_pending ON approvals(application_id, decision) WHERE decision IS NULL;

CREATE INDEX idx_documents_application ON documents(application_id);
CREATE INDEX idx_documents_type ON documents(type);

CREATE INDEX idx_logs_user ON logs(user_id);
CREATE INDEX idx_logs_application ON logs(application_id);
CREATE INDEX idx_logs_created_at ON logs(created_at DESC);

-- Вставка начальных данных
INSERT INTO settings (key, value, description) VALUES
    ('invoice_counter', '0', 'Счетчик номеров счетов'),
    ('contract_counter', '0', 'Счетчик номеров договоров'),
    ('daily_report_time', '"19:00"', 'Время ежедневного отчета');

-- Комментарии к таблицам
COMMENT ON TABLE banks IS 'Банки с реквизитами';
COMMENT ON TABLE users IS 'Пользователи бота';
COMMENT ON TABLE companies IS 'Компании-получатели платежей';
COMMENT ON TABLE company_banks IS 'Счета компаний в банках';
COMMENT ON TABLE applications IS 'Платежные заявки';
COMMENT ON TABLE approvals IS 'Этапы подписи (мультиподпись)';
COMMENT ON TABLE documents IS 'Счета и договоры';
COMMENT ON TABLE logs IS 'Аудит действий пользователей';
