"""packages/kb/schema.py — SQLite-схема и инициализация"""
import os
import sqlite3
import logging
import traceback
import sys

log = logging.getLogger('newton-api.kb')

KB_DIR = '/opt/beget/n8n/kb'
KB_DB = os.path.join(KB_DIR, 'research.db')


def init_kb():
    """Инициализация SQLite-схемы. ВСЕГДА в try/except (LESSONS §2.9)."""
    os.makedirs(KB_DIR, exist_ok=True)
    con = sqlite3.connect(KB_DB)
    cur = con.cursor()
    cur.executescript('''
    CREATE TABLE IF NOT EXISTS sources (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        url         TEXT UNIQUE NOT NULL,
        kind        TEXT NOT NULL,
        external_id TEXT,
        title       TEXT,
        added_at    TEXT NOT NULL,
        rating_avg  REAL DEFAULT 0,
        rating_count INTEGER DEFAULT 0,
        last_seen   TEXT
    );
    CREATE TABLE IF NOT EXISTS claims (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id   INTEGER REFERENCES sources(id),
        ts_in_video REAL,
        text        TEXT NOT NULL,
        lang        TEXT,
        url         TEXT,
        claim_type  TEXT,
        created_at  TEXT NOT NULL,
        UNIQUE(source_id, text, ts_in_video)
    );
    CREATE TABLE IF NOT EXISTS digests (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        period_from TEXT,
        period_to   TEXT,
        created_at  TEXT NOT NULL,
        items_json  TEXT NOT NULL,
        html_path   TEXT,
        tg_msg_ids  TEXT,
        user_id     INTEGER
    );
    CREATE TABLE IF NOT EXISTS actions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        digest_id   INTEGER REFERENCES digests(id),
        user_id     INTEGER,
        text        TEXT NOT NULL,
        subject     TEXT,
        trigger     TEXT,
        confidence  REAL,
        acted       INTEGER DEFAULT 0,
        acted_at    TEXT,
        feedback    TEXT
    );
    CREATE TABLE IF NOT EXISTS user_profile (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_claims_source ON claims(source_id);
    CREATE INDEX IF NOT EXISTS idx_claims_created ON claims(created_at);
    CREATE INDEX IF NOT EXISTS idx_actions_digest ON actions(digest_id);
    ''')
    con.commit()
    con.close()
    log.info('KB schema ready at %s', KB_DB)


# Авто-инициализация при импорте модуля (безопасна: try/except вокруг)
try:
    init_kb()
except Exception as e:
    log.error('KB init failed: %s', e)
    log.error(traceback.format_exc())
    print(f'[KB] FAILED: {e}', file=sys.stderr, flush=True)
    print(traceback.format_exc(), file=sys.stderr, flush=True)
    sys.exit(1)
