-- Добавление поля для подписи и печати компании
ALTER TABLE companies
ADD COLUMN IF NOT EXISTS signature_image_path VARCHAR(500);

COMMENT ON COLUMN companies.signature_image_path IS 'Путь к файлу с подписью и печатью компании (PNG)';
