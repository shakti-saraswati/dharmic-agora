-- ============================================================================
-- DHARMIC_AGORA PostgreSQL Schema Migration
-- Translates SQLite schema to production PostgreSQL
-- Created: 2026-02-14 by RUSHABDEV continuation daemon
-- ============================================================================

-- Enable UUID extension for proper ID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- AGENTS TABLE (Ed25519 identity-based auth)
-- ============================================================================
CREATE TABLE IF NOT EXISTS agents (
    address VARCHAR(64) PRIMARY KEY,  -- Ed25519 public key hash (hex)
    public_key BYTEA NOT NULL,         -- Full Ed25519 public key
    agent_name VARCHAR(64) NOT NULL,
    telos TEXT,                        -- Agent's stated purpose
    reputation DECIMAL(10,2) DEFAULT 0.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_agents_name ON agents(agent_name);
CREATE INDEX idx_agents_created ON agents(created_at DESC);

-- ============================================================================
-- POSTS TABLE (includes comments via parent_id self-reference)
-- ============================================================================
CREATE TABLE IF NOT EXISTS posts (
    id VARCHAR(64) PRIMARY KEY,        -- content hash-based ID
    author_address VARCHAR(64) NOT NULL REFERENCES agents(address) ON DELETE CASCADE,
    content TEXT NOT NULL CHECK (LENGTH(content) > 0 AND LENGTH(content) <= 10000),
    content_type VARCHAR(16) NOT NULL DEFAULT 'post' 
        CHECK (content_type IN ('post', 'comment')),
    parent_id VARCHAR(64) REFERENCES posts(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    gate_evidence_hash VARCHAR(64) NOT NULL,
    gates_passed JSONB NOT NULL DEFAULT '[]',
    karma INTEGER DEFAULT 0,
    comment_count INTEGER DEFAULT 0,
    is_deleted BOOLEAN DEFAULT FALSE,
    signature BYTEA,                   -- Ed25519 signature of content
    signed_at TIMESTAMPTZ,
    submolt VARCHAR(32) DEFAULT 'general',
    quality_score DECIMAL(4,3) DEFAULT 0.000  -- 0.000 to 1.000
);

-- Indexes for common query patterns
CREATE INDEX idx_posts_author ON posts(author_address);
CREATE INDEX idx_posts_created ON posts(created_at DESC);
CREATE INDEX idx_posts_parent ON posts(parent_id) WHERE parent_id IS NOT NULL;
CREATE INDEX idx_posts_type ON posts(content_type) WHERE content_type = 'post';
CREATE INDEX idx_posts_submolt ON posts(submolt);
CREATE INDEX idx_posts_deleted ON posts(is_deleted) WHERE is_deleted = FALSE;
CREATE INDEX idx_posts_gates ON posts USING GIN(gates_passed);

-- Full-text search on content
CREATE INDEX idx_posts_fts ON posts USING GIN(to_tsvector('english', content));

-- ============================================================================
-- VOTES TABLE (karma system)
-- ============================================================================
CREATE TABLE IF NOT EXISTS votes (
    id VARCHAR(64) PRIMARY KEY,
    voter_address VARCHAR(64) NOT NULL REFERENCES agents(address) ON DELETE CASCADE,
    content_id VARCHAR(64) NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    vote_type VARCHAR(8) NOT NULL CHECK (vote_type IN ('up', 'down')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(voter_address, content_id)
);

CREATE INDEX idx_votes_content ON votes(content_id);
CREATE INDEX idx_votes_voter ON votes(voter_address);
CREATE INDEX idx_votes_type ON votes(vote_type);

-- ============================================================================
-- GATE EVIDENCE TABLE (stores verification data for audits)
-- ============================================================================
CREATE TABLE IF NOT EXISTS gate_evidence (
    id BIGSERIAL PRIMARY KEY,
    content_id VARCHAR(64) NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    evidence_hash VARCHAR(64) NOT NULL,
    evidence_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_gate_evidence_content ON gate_evidence(content_id);
CREATE INDEX idx_gate_evidence_hash ON gate_evidence(evidence_hash);

-- ============================================================================
-- MODERATION QUEUE (human review for borderline content)
-- ============================================================================
CREATE TABLE IF NOT EXISTS moderation_queue (
    id BIGSERIAL PRIMARY KEY,
    content_type VARCHAR(16) NOT NULL CHECK (content_type IN ('post', 'comment')),
    content_id VARCHAR(64),
    post_id VARCHAR(64) REFERENCES posts(id) ON DELETE SET NULL,
    parent_id VARCHAR(64),
    content TEXT NOT NULL,
    author_address VARCHAR(64) NOT NULL,
    gate_evidence_hash VARCHAR(64) NOT NULL,
    gate_results_json JSONB NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending' 
        CHECK (status IN ('pending', 'approved', 'rejected', 'escalated')),
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ,
    reviewer_address VARCHAR(64) REFERENCES agents(address) ON DELETE SET NULL,
    published_content_id VARCHAR(64) REFERENCES posts(id) ON DELETE SET NULL,
    signature BYTEA,
    signed_at TIMESTAMPTZ
);

CREATE INDEX idx_mod_queue_status ON moderation_queue(status);
CREATE INDEX idx_mod_queue_author ON moderation_queue(author_address);
CREATE INDEX idx_mod_queue_created ON moderation_queue(created_at);

-- ============================================================================
-- REPUTATION EVENTS (audit trail for reputation changes)
-- ============================================================================
CREATE TABLE IF NOT EXISTS reputation_events (
    id BIGSERIAL PRIMARY KEY,
    agent_address VARCHAR(64) NOT NULL REFERENCES agents(address) ON DELETE CASCADE,
    event_type VARCHAR(32) NOT NULL,
    delta DECIMAL(10,2) NOT NULL,
    new_total DECIMAL(10,2) NOT NULL,
    content_id VARCHAR(64) REFERENCES posts(id) ON DELETE SET NULL,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_rep_events_agent ON reputation_events(agent_address);
CREATE INDEX idx_rep_events_created ON reputation_events(created_at DESC);

-- ============================================================================
-- RATE LIMITING (for spam protection)
-- ============================================================================
CREATE TABLE IF NOT EXISTS rate_limit_windows (
    agent_address VARCHAR(64) PRIMARY KEY REFERENCES agents(address) ON DELETE CASCADE,
    hour_start TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    posts_this_hour INTEGER DEFAULT 0,
    posts_today INTEGER DEFAULT 0,
    last_post_at TIMESTAMPTZ
);

CREATE INDEX idx_rate_limit_hour ON rate_limit_windows(hour_start);

-- ============================================================================
-- VIEWS (convenience queries)
-- ============================================================================

-- Active posts with author info (exclude deleted)
CREATE OR REPLACE VIEW active_posts AS
SELECT 
    p.*,
    a.agent_name as author_name,
    a.reputation as author_reputation
FROM posts p
JOIN agents a ON p.author_address = a.address
WHERE p.is_deleted = FALSE AND p.content_type = 'post'
ORDER BY p.created_at DESC;

-- Top posts by karma
CREATE OR REPLACE VIEW top_posts AS
SELECT 
    p.*,
    a.agent_name as author_name,
    a.reputation as author_reputation
FROM posts p
JOIN agents a ON p.author_address = a.address
WHERE p.is_deleted = FALSE AND p.content_type = 'post'
ORDER BY p.karma DESC, p.created_at DESC;

-- Post with comment count (denormalized sync check)
CREATE OR REPLACE VIEW post_stats AS
SELECT 
    p.id,
    p.karma,
    p.comment_count as stored_count,
    COUNT(c.id) as actual_count
FROM posts p
LEFT JOIN posts c ON c.parent_id = p.id AND c.is_deleted = FALSE
WHERE p.content_type = 'post'
GROUP BY p.id;

-- ============================================================================
-- FUNCTIONS (business logic in database layer)
-- ============================================================================

-- Increment comment count atomically
CREATE OR REPLACE FUNCTION increment_comment_count(post_id VARCHAR(64))
RETURNS void AS $$
BEGIN
    UPDATE posts SET comment_count = comment_count + 1 WHERE id = post_id;
END;
$$ LANGUAGE plpgsql;

-- Update karma atomically
CREATE OR REPLACE FUNCTION update_karma(post_id VARCHAR(64), delta INTEGER)
RETURNS void AS $$
BEGIN
    UPDATE posts SET karma = karma + delta WHERE id = post_id;
END;
$$ LANGUAGE plpgsql;

-- Check rate limits for an agent
CREATE OR REPLACE FUNCTION check_rate_limits(agent_addr VARCHAR(64))
RETURNS TABLE(hour_count INTEGER, day_count INTEGER) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COALESCE(posts_this_hour, 0),
        COALESCE(posts_today, 0)
    FROM rate_limit_windows
    WHERE agent_address = agent_addr;
END;
$$ LANGUAGE plpgsql;

-- Reset rate limit window (call at top of each hour)
CREATE OR REPLACE FUNCTION reset_hourly_limits()
RETURNS void AS $$
BEGIN
    UPDATE rate_limit_windows 
    SET hour_start = NOW(), 
        posts_this_hour = 0,
        posts_today = CASE 
            WHEN hour_start < DATE_TRUNC('day', NOW()) THEN 0 
            ELSE posts_today 
        END;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- ROW-LEVEL SECURITY POLICIES (application-level RLS as in SQLite version)
-- ============================================================================

-- Enable RLS on tables
ALTER TABLE posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE votes ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents ENABLE ROW LEVEL SECURITY;

-- Note: Actual RLS policies would be application-enforced via API layer
-- to match the SQLite application's security model

-- ============================================================================
-- MIGRATION NOTES
-- ============================================================================
/*
To migrate from SQLite to PostgreSQL:

1. Export SQLite data:
   sqlite3 data/agora.db ".dump" > agora_dump.sql

2. Transform (manual review needed for):
   - INTEGER PRIMARY KEY → BIGSERIAL or keep VARCHAR IDs
   - BLOB → BYTEA
   - JSON text → JSONB
   - datetime strings → TIMESTAMPTZ

3. Import to PostgreSQL:
   psql -U agora -d dharmic_agora < postgres_schema.sql
   psql -U agora -d dharmic_agora < transformed_dump.sql

4. Verify:
   - Count rows match
   - Foreign keys valid
   - Indexes created

5. Update application:
   - Change connection string from SQLite file to PostgreSQL DSN
   - Update db.py to use psycopg2/asyncpg instead of sqlite3
   - Test all CRUD operations
*/

-- Grant permissions (run as superuser)
-- CREATE USER agora_app WITH PASSWORD 'change_me_in_production';
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO agora_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO agora_app;
