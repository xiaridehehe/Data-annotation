"""Database configuration shared by the API and migration tool."""
import json
import os
from pathlib import Path
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import URL

CONFIG = Path(__file__).parent / 'mysql.local.json'


def create_database_engine():
    override = os.environ.get('ANNOTATION_DATABASE_URL')
    if override:
        url = override
    else:
        if not CONFIG.exists():
            raise RuntimeError('请先运行 .venv\\Scripts\\python.exe -m backend.configure_mysql 配置 MySQL')
        config = json.loads(CONFIG.read_text(encoding='utf-8'))
        url = URL.create('mysql+pymysql', **config, query={'charset': 'utf8mb4'})
    engine = create_engine(url, pool_pre_ping=True, pool_recycle=1800)
    with engine.begin() as connection:
        if engine.dialect.name == 'mysql':
            connection.execute(text('''CREATE TABLE IF NOT EXISTS records (
                kind VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
                id VARCHAR(512) COLLATE utf8mb4_bin PRIMARY KEY,
                data LONGTEXT NOT NULL,
                INDEX ix_records_kind (kind)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin'''))
        elif engine.dialect.name == 'sqlite':
            connection.execute(text('CREATE TABLE IF NOT EXISTS records (kind TEXT, id TEXT PRIMARY KEY, data TEXT NOT NULL)'))
        else:
            raise RuntimeError('只支持 MySQL 或显式指定的 SQLite 测试数据库')
    from backend.models import metadata
    metadata.create_all(engine)
    # create_all does not add columns to tables created by an earlier release.
    columns = {column['name'] for column in inspect(engine).get_columns('assessments')}
    if 'deleted_at' not in columns:
        column_type = 'DATETIME(6)' if engine.dialect.name == 'mysql' else 'DATETIME'
        with engine.begin() as connection:
            connection.execute(text('ALTER TABLE assessments ADD COLUMN deleted_at ' + column_type + ' NULL'))
    return engine


def upsert_sql(engine):
    if engine.dialect.name == 'mysql':
        return text('INSERT INTO records (kind,id,data) VALUES (:k,:i,:d) ON DUPLICATE KEY UPDATE kind=:k, data=:d')
    return text('INSERT INTO records (kind,id,data) VALUES (:k,:i,:d) ON CONFLICT(id) DO UPDATE SET kind=:k, data=:d')
