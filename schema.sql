-- AI Newsletter — migration 0001: initial schema (PostgreSQL 16)
-- Single source of truth for the database schema. models.py mirrors this file.

BEGIN;

-- ---------------------------------------------------------------------------
-- Enum types
-- ---------------------------------------------------------------------------

CREATE TYPE user_role        AS ENUM ('subscriber', 'admin');
CREATE TYPE channel_type     AS ENUM ('telegram', 'email', 'discord');
CREATE TYPE source_type      AS ENUM ('rss', 'html', 'api');
-- Order matters: dispatch compares `level >= threshold`.
CREATE TYPE importance_level AS ENUM ('low', 'medium', 'high');
-- 'body' matches news_items.body, or summary when the body was not fetched.
CREATE TYPE match_field      AS ENUM ('title', 'body');
CREATE TYPE delivery_status  AS ENUM ('queued', 'sent', 'failed', 'permanent_failure');
CREATE TYPE cycle_type       AS ENUM ('scrape', 'classify', 'dispatch');

-- ---------------------------------------------------------------------------
-- Tables (dependency order)
-- ---------------------------------------------------------------------------

-- Account
CREATE TABLE users (
    user_id        bigserial     NOT NULL,
    email          varchar(254)  NOT NULL,  -- unique case-insensitively, see uq_users_email_lower (C1)
    password_hash  text          NOT NULL,  -- Argon2id/bcrypt output; plaintext never stored
    role           user_role     NOT NULL DEFAULT 'subscriber',
    created_at     timestamptz   NOT NULL DEFAULT now(),
    last_login_at  timestamptz   NULL,
    CONSTRAINT pk_users PRIMARY KEY (user_id)
);

-- Session
CREATE TABLE sessions (
    session_id  bigserial    NOT NULL,
    user_id     bigint       NOT NULL,
    token_hash  char(64)     NOT NULL,  -- hex SHA-256 of the cookie token
    created_at  timestamptz  NOT NULL DEFAULT now(),
    expires_at  timestamptz  NOT NULL,
    CONSTRAINT pk_sessions PRIMARY KEY (session_id),
    CONSTRAINT fk_sessions_user_id FOREIGN KEY (user_id)
        REFERENCES users (user_id) ON DELETE CASCADE,
    CONSTRAINT uq_sessions_token_hash UNIQUE (token_hash),
    CONSTRAINT ck_sessions_expires_after_created CHECK (expires_at > created_at)
);

-- SubscriberProfile (one-to-one with users)
CREATE TABLE subscriber_profiles (
    user_id            bigint            NOT NULL,
    default_threshold  importance_level  NOT NULL DEFAULT 'high',
    -- C8: true = receive every source; false = only rows in followed_sources.
    follows_all        boolean           NOT NULL DEFAULT true,
    updated_at         timestamptz       NOT NULL DEFAULT now(),
    CONSTRAINT pk_subscriber_profiles PRIMARY KEY (user_id),
    CONSTRAINT fk_subscriber_profiles_user_id FOREIGN KEY (user_id)
        REFERENCES users (user_id) ON DELETE CASCADE
);

-- ChannelConnection
CREATE TABLE channel_connections (
    channel_id              bigserial         NOT NULL,
    user_id                 bigint            NOT NULL,
    channel_type            channel_type      NOT NULL,
    contact_encrypted       bytea             NOT NULL,  -- chat ID / email / webhook URL, encrypted by the app
    -- C5: HMAC-SHA256 (hex) of the normalized contact, keyed by a server secret.
    contact_hash            char(64)          NOT NULL,
    is_enabled              boolean           NOT NULL DEFAULT true,
    is_verified             boolean           NOT NULL DEFAULT false,
    verified_at             timestamptz       NULL,
    min_importance          importance_level  NULL,      -- NULL = use profile default_threshold
    verification_code_hash  char(64)          NULL,
    code_expires_at         timestamptz       NULL,
    failed_attempts         smallint          NOT NULL DEFAULT 0,
    created_at              timestamptz       NOT NULL DEFAULT now(),
    CONSTRAINT pk_channel_connections PRIMARY KEY (channel_id),
    CONSTRAINT fk_channel_connections_user_id FOREIGN KEY (user_id)
        REFERENCES subscriber_profiles (user_id) ON DELETE CASCADE,
    CONSTRAINT uq_channel_connections_user_channel UNIQUE (user_id, channel_type),
    CONSTRAINT uq_channel_connections_channel_contact UNIQUE (channel_type, contact_hash),
    CONSTRAINT ck_channel_connections_failed_attempts CHECK (failed_attempts BETWEEN 0 AND 3),
    -- C3: two-directional.
    CONSTRAINT ck_channel_connections_verified CHECK (is_verified = (verified_at IS NOT NULL)),
    CONSTRAINT ck_channel_connections_code_pair
        CHECK ((verification_code_hash IS NULL) = (code_expires_at IS NULL))
);

-- Source
CREATE TABLE sources (
    source_id        bigserial     NOT NULL,
    name             varchar(120)  NOT NULL,
    source_type      source_type   NOT NULL,
    url                   text          NOT NULL,
    base_weight           smallint      NOT NULL,
    is_active             boolean       NOT NULL DEFAULT true,
    -- Per-type scraper settings: CSS selectors (html), headers / query params (api).
    -- Secrets such as API keys belong in the environment; store only their names here.
    config                jsonb         NOT NULL DEFAULT '{}'::jsonb,
    -- HTTP validators echoed back as If-None-Match / If-Modified-Since on the next fetch.
    etag                  text          NULL,
    last_modified         text          NULL,  -- raw header value, sent back verbatim
    last_checked_at       timestamptz   NULL,  -- last attempt, successful or not
    last_success_at       timestamptz   NULL,
    consecutive_failures  integer       NOT NULL DEFAULT 0,
    last_error            text          NULL,
    created_at            timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT pk_sources PRIMARY KEY (source_id),
    CONSTRAINT uq_sources_url UNIQUE (url),
    CONSTRAINT ck_sources_base_weight CHECK (base_weight BETWEEN 0 AND 30),
    CONSTRAINT ck_sources_config_object CHECK (jsonb_typeof(config) = 'object'),
    CONSTRAINT ck_sources_consecutive_failures CHECK (consecutive_failures >= 0)
);

-- SubscriberProfile.followedSources (only consulted when follows_all = false)
CREATE TABLE followed_sources (
    user_id    bigint  NOT NULL,
    source_id  bigint  NOT NULL,
    CONSTRAINT pk_followed_sources PRIMARY KEY (user_id, source_id),
    CONSTRAINT fk_followed_sources_user_id FOREIGN KEY (user_id)
        REFERENCES subscriber_profiles (user_id) ON DELETE CASCADE,
    CONSTRAINT fk_followed_sources_source_id FOREIGN KEY (source_id)
        REFERENCES sources (source_id) ON DELETE CASCADE
);

-- NewsItem
-- C7: duplicate_of must reference an original (a row whose duplicate_of IS NULL).
--     Enforced by NewsItemRepository.insert_if_new, not by a trigger.
--     Duplicates are classified but never delivered (DeliveryRepository.enqueue_for_item).
CREATE TABLE news_items (
    item_id              bigserial         NOT NULL,
    source_id            bigint            NOT NULL,
    title                text              NOT NULL,
    summary              text              NULL,
    body                 text              NULL,      -- full article text when the scraper fetched it
    url                  text              NOT NULL,
    canonical_url        text              NOT NULL,  -- tracking params stripped
    published_at         timestamptz       NULL,
    collected_at         timestamptz       NOT NULL DEFAULT now(),
    duplicate_of         bigint            NULL,
    corroboration_count  smallint          NOT NULL DEFAULT 1,
    importance_score     numeric(5,2)      NULL,
    importance_level     importance_level  NULL,
    classified_at        timestamptz       NULL,
    dispatched_at        timestamptz       NULL,
    CONSTRAINT pk_news_items PRIMARY KEY (item_id),
    CONSTRAINT fk_news_items_source_id FOREIGN KEY (source_id)
        REFERENCES sources (source_id) ON DELETE RESTRICT,
    CONSTRAINT fk_news_items_duplicate_of FOREIGN KEY (duplicate_of)
        REFERENCES news_items (item_id) ON DELETE SET NULL,
    CONSTRAINT uq_news_items_canonical_url UNIQUE (canonical_url),
    CONSTRAINT ck_news_items_not_self_duplicate CHECK (duplicate_of <> item_id),
    CONSTRAINT ck_news_items_corroboration_count CHECK (corroboration_count >= 1),
    CONSTRAINT ck_news_items_importance_score CHECK (importance_score BETWEEN 0 AND 100),
    -- C6: score, level and classified_at are set together or not at all.
    CONSTRAINT ck_news_items_classification_complete CHECK (
        (importance_level IS NULL) = (classified_at IS NULL)
        AND (importance_score IS NULL) = (classified_at IS NULL)
    )
);

-- ScoringRule
CREATE TABLE scoring_rules (
    rule_id    smallserial  NOT NULL,
    code       varchar(8)   NOT NULL,  -- R1..R8
    name       varchar(80)  NOT NULL,
    pattern    text         NOT NULL,  -- Python `re` syntax (applied by the classifier, not Postgres)
    weight     smallint     NOT NULL,
    is_active  boolean      NOT NULL DEFAULT true,
    CONSTRAINT pk_scoring_rules PRIMARY KEY (rule_id),
    CONSTRAINT uq_scoring_rules_code UNIQUE (code),
    CONSTRAINT ck_scoring_rules_weight CHECK (weight BETWEEN -50 AND 50)
);

-- Application of a ScoringRule to a NewsItem
CREATE TABLE rule_matches (
    item_id       bigint        NOT NULL,
    rule_id       smallint      NOT NULL,
    field         match_field   NOT NULL,
    contribution  numeric(5,2)  NOT NULL,
    -- C4: a rule matching both title and body yields two rows.
    CONSTRAINT pk_rule_matches PRIMARY KEY (item_id, rule_id, field),
    CONSTRAINT fk_rule_matches_item_id FOREIGN KEY (item_id)
        REFERENCES news_items (item_id) ON DELETE CASCADE,
    CONSTRAINT fk_rule_matches_rule_id FOREIGN KEY (rule_id)
        REFERENCES scoring_rules (rule_id) ON DELETE RESTRICT
);

-- Delivery
CREATE TABLE deliveries (
    delivery_id      bigserial        NOT NULL,
    item_id          bigint           NOT NULL,
    -- C2: nullable + SET NULL so history survives channel removal (REQ-14 metric).
    channel_id       bigint           NULL,
    status           delivery_status  NOT NULL DEFAULT 'queued',
    attempts         smallint         NOT NULL DEFAULT 0,
    next_attempt_at  timestamptz      NOT NULL DEFAULT now(),
    sent_at          timestamptz      NULL,
    last_error       text             NULL,
    created_at       timestamptz      NOT NULL DEFAULT now(),
    CONSTRAINT pk_deliveries PRIMARY KEY (delivery_id),
    CONSTRAINT fk_deliveries_item_id FOREIGN KEY (item_id)
        REFERENCES news_items (item_id) ON DELETE RESTRICT,
    CONSTRAINT fk_deliveries_channel_id FOREIGN KEY (channel_id)
        REFERENCES channel_connections (channel_id) ON DELETE SET NULL,
    CONSTRAINT uq_deliveries_item_channel UNIQUE (item_id, channel_id),
    CONSTRAINT ck_deliveries_attempts CHECK (attempts BETWEEN 0 AND 5),
    CONSTRAINT ck_deliveries_sent_at CHECK ((sent_at IS NOT NULL) = (status = 'sent'))
);

-- CycleRun (operations log, no foreign keys)
CREATE TABLE cycle_runs (
    run_id           bigserial    NOT NULL,
    cycle_type       cycle_type   NOT NULL,
    started_at       timestamptz  NOT NULL DEFAULT now(),
    finished_at      timestamptz  NULL,
    items_processed  integer      NOT NULL DEFAULT 0,
    failures         integer      NOT NULL DEFAULT 0,
    notes            text         NULL,
    CONSTRAINT pk_cycle_runs PRIMARY KEY (run_id),
    CONSTRAINT ck_cycle_runs_finished_after_started
        CHECK (finished_at IS NULL OR finished_at >= started_at)
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

-- C1: case-insensitive email uniqueness.
CREATE UNIQUE INDEX uq_users_email_lower ON users (lower(email));

-- 1. Classifier work queue.
CREATE INDEX ix_news_items_unclassified ON news_items (collected_at)
    WHERE classified_at IS NULL;

-- 2. Dispatcher work queue.
CREATE INDEX ix_news_items_undispatched ON news_items (classified_at)
    WHERE classified_at IS NOT NULL AND dispatched_at IS NULL;

-- 3. Delivery retry queue.
CREATE INDEX ix_deliveries_due ON deliveries (next_attempt_at)
    WHERE status IN ('queued', 'failed');

-- 4. Duplicate detection within a 72-hour window.
CREATE INDEX ix_news_items_published_at ON news_items (published_at DESC);

-- Foreign-key columns not already covered by a PK/UNIQUE leading column.
-- (channel_connections.user_id, followed_sources.user_id, rule_matches.item_id
--  and deliveries.item_id are already covered.)
CREATE INDEX ix_sessions_user_id           ON sessions (user_id);
CREATE INDEX ix_followed_sources_source_id ON followed_sources (source_id);
CREATE INDEX ix_news_items_source_id       ON news_items (source_id);
CREATE INDEX ix_news_items_duplicate_of    ON news_items (duplicate_of) WHERE duplicate_of IS NOT NULL;
CREATE INDEX ix_rule_matches_rule_id       ON rule_matches (rule_id);
CREATE INDEX ix_deliveries_channel_id      ON deliveries (channel_id);

COMMIT;

-- ---------------------------------------------------------------------------
-- Sample data and constraint tests (run manually, one statement at a time)
-- ---------------------------------------------------------------------------
/*
INSERT INTO users (email, password_hash)
VALUES ('alice@example.com', '$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA');
INSERT INTO subscriber_profiles (user_id)
SELECT user_id FROM users WHERE email = 'alice@example.com';

INSERT INTO channel_connections (user_id, channel_type, contact_encrypted, contact_hash, is_verified, verified_at)
SELECT user_id, 'telegram', '\x00'::bytea, repeat('a', 64), true, now()
FROM users WHERE email = 'alice@example.com';

INSERT INTO sources (name, source_type, url, base_weight)
VALUES ('Example AI Blog', 'rss', 'https://example.com/feed.xml', 20);
INSERT INTO sources (name, source_type, url, base_weight, config)
VALUES ('Example Lab News', 'html', 'https://lab.example.com/news', 15,
        '{"item_selector": "article", "title_selector": "h2 a", "link_selector": "h2 a"}');

INSERT INTO scoring_rules (code, name, pattern, weight)
VALUES ('R1', 'Model release', '(?i)\b(release[sd]?|launch(es|ed)?)\b', 25);

INSERT INTO news_items (source_id, title, url, canonical_url, published_at)
SELECT source_id, 'New model released', 'https://example.com/a?utm_source=x',
       'https://example.com/a', now() - interval '1 hour'
FROM sources WHERE url = 'https://example.com/feed.xml';

UPDATE news_items
SET importance_score = 82.50, importance_level = 'high', classified_at = now()
WHERE canonical_url = 'https://example.com/a';

INSERT INTO rule_matches (item_id, rule_id, field, contribution)
SELECT n.item_id, r.rule_id, f.field, 25.00
FROM news_items n, scoring_rules r, (VALUES ('title'::match_field), ('body'::match_field)) AS f(field)
WHERE n.canonical_url = 'https://example.com/a' AND r.code = 'R1';

INSERT INTO deliveries (item_id, channel_id)
SELECT n.item_id, c.channel_id
FROM news_items n, channel_connections c
WHERE n.canonical_url = 'https://example.com/a' AND c.contact_hash = repeat('a', 64);

INSERT INTO sessions (user_id, token_hash, expires_at)
SELECT user_id, repeat('b', 64), now() + interval '7 days' FROM users WHERE email = 'alice@example.com';

-- should fail: second delivery of the same item to the same channel (uq_deliveries_item_channel)
INSERT INTO deliveries (item_id, channel_id)
SELECT n.item_id, c.channel_id
FROM news_items n, channel_connections c
WHERE n.canonical_url = 'https://example.com/a' AND c.contact_hash = repeat('a', 64);

-- should fail: second Telegram channel for one subscriber (uq_channel_connections_user_channel)
INSERT INTO channel_connections (user_id, channel_type, contact_encrypted, contact_hash)
SELECT user_id, 'telegram', '\x01'::bytea, repeat('c', 64)
FROM users WHERE email = 'alice@example.com';

-- should fail: verified channel with no verified_at (ck_channel_connections_verified)
INSERT INTO channel_connections (user_id, channel_type, contact_encrypted, contact_hash, is_verified)
SELECT user_id, 'email', '\x02'::bytea, repeat('d', 64), true
FROM users WHERE email = 'alice@example.com';

-- should fail: importance_score = 101 (ck_news_items_importance_score)
UPDATE news_items SET importance_score = 101 WHERE canonical_url = 'https://example.com/a';

-- should fail: delivery with status = 'sent' and no sent_at (ck_deliveries_sent_at)
UPDATE deliveries SET status = 'sent', sent_at = NULL;

-- should fail: failed_attempts = 4 (ck_channel_connections_failed_attempts)
UPDATE channel_connections SET failed_attempts = 4 WHERE contact_hash = repeat('a', 64);

-- should fail: duplicate_of equal to own item_id (ck_news_items_not_self_duplicate)
UPDATE news_items SET duplicate_of = item_id WHERE canonical_url = 'https://example.com/a';

-- should fail: session with expires_at before created_at (ck_sessions_expires_after_created)
INSERT INTO sessions (user_id, token_hash, expires_at)
SELECT user_id, repeat('e', 64), now() - interval '1 minute' FROM users WHERE email = 'alice@example.com';

-- should fail: same email differing only in case (uq_users_email_lower, C1)
INSERT INTO users (email, password_hash) VALUES ('Alice@Example.com', 'x');

-- should fail: same Telegram chat registered by a second account (uq_channel_connections_channel_contact, C5)
INSERT INTO users (email, password_hash) VALUES ('bob@example.com', 'x');
INSERT INTO subscriber_profiles (user_id) SELECT user_id FROM users WHERE email = 'bob@example.com';
INSERT INTO channel_connections (user_id, channel_type, contact_encrypted, contact_hash)
SELECT user_id, 'telegram', '\x03'::bytea, repeat('a', 64) FROM users WHERE email = 'bob@example.com';

-- should fail: level set without score (ck_news_items_classification_complete, C6)
UPDATE news_items SET importance_score = NULL WHERE canonical_url = 'https://example.com/a';

-- should fail: source config that is not a JSON object (ck_sources_config_object)
UPDATE sources SET config = '[]' WHERE url = 'https://example.com/feed.xml';
*/
