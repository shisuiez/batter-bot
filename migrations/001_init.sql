CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    name VARCHAR(128) NOT NULL,
    phone VARCHAR(32) NOT NULL,
    age INTEGER NOT NULL
    -- позже добавим поля для статистики, достижений и т.д.
);

CREATE TABLE IF NOT EXISTS admins (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL
); 