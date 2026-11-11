"""Interactive configuration: python -m backend.configure_mysql."""
import getpass
import json
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from backend.database import CONFIG, create_database_engine


def main():
    config = dict(
        host=input('主机 [127.0.0.1]：').strip() or '127.0.0.1',
        port=int(input('端口 [3306]：').strip() or '3306'),
        username=input('账号 [annotation_app]：').strip() or 'annotation_app',
        database=input('数据库 [annotation_db]：').strip() or 'annotation_db',
        password=getpass.getpass('MySQL 密码（输入时不显示）：'),
    )
    engine = create_engine(URL.create('mysql+pymysql', **config, query={'charset': 'utf8mb4'}))
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
    finally:
        engine.dispose()
    CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    configured = create_database_engine()
    configured.dispose()
    print('连接成功，records 表已准备好。配置保存在 backend/mysql.local.json，请勿分享此文件。')


if __name__ == '__main__':
    main()
