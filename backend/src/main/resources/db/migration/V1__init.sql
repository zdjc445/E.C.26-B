CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(64) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(128),
    role VARCHAR(32) NOT NULL DEFAULT 'USER',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id VARCHAR(64) PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    title VARCHAR(128) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_updated
    ON chat_sessions(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS chat_messages (
    message_id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
    role VARCHAR(16) NOT NULL,
    text TEXT,
    image_ids JSONB,
    selected_option_ids JSONB,
    agent_reply JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session
    ON chat_messages(session_id, created_at ASC);

CREATE TABLE IF NOT EXISTS favorites (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    product_id VARCHAR(64) NOT NULL,
    title VARCHAR(255) NOT NULL,
    platform VARCHAR(64) NOT NULL,
    price NUMERIC(12, 2) NOT NULL,
    shop_name VARCHAR(128),
    brand VARCHAR(64),
    image_url TEXT,
    product_url TEXT,
    snapshot JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, product_id)
);

CREATE INDEX IF NOT EXISTS idx_favorites_user
    ON favorites(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS price_alerts (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    product_id VARCHAR(64) NOT NULL,
    title VARCHAR(255) NOT NULL,
    platform VARCHAR(64) NOT NULL,
    target_price NUMERIC(12, 2) NOT NULL,
    triggered BOOLEAN NOT NULL DEFAULT FALSE,
    last_observed_price NUMERIC(12, 2),
    note VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_price_alerts_user
    ON price_alerts(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    payload JSONB NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
