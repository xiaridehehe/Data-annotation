"""Copy legacy records without overwriting MySQL records. Stop the API first."""
import sqlite3
from pathlib import Path
from sqlalchemy import text
from backend.database import create_database_engine


def main():
    source = Path(__file__).parent / 'data' / 'annotations.db'
    if not source.exists():
        raise SystemExit('未找到原 SQLite 数据库，无需迁移。')
    engine = create_database_engine()
    if engine.dialect.name != 'mysql':
        raise SystemExit('迁移目标必须是 MySQL')
    with sqlite3.connect(f'{source.resolve().as_uri()}?mode=ro', uri=True) as old:
        records = old.execute('SELECT kind,id,data FROM records').fetchall()
    copied = skipped = 0
    with engine.begin() as connection:
        for kind, record_id, data in records:
            existing = connection.execute(text('SELECT data FROM records WHERE id=:i'), {'i': record_id}).first()
            if existing:
                if existing[0] != data:
                    raise RuntimeError(f'记录冲突：{kind}/{record_id}。已回滚此次迁移，请勿在新库修改数据前重复迁移。')
                skipped += 1
                continue
            connection.execute(text('INSERT INTO records (kind,id,data) VALUES (:k,:i,:d)'), {'k':kind,'i':record_id,'d':data})
            copied += 1
    engine.dispose()
    print(f'迁移完成：新增 {copied} 条，相同记录跳过 {skipped} 条。原 SQLite 和影像文件保持不变。')


if __name__ == '__main__':
    main()
