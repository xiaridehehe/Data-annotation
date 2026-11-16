"""Run in the VS Code terminal: python test_mysql_connection.py"""

import getpass
import sys


def main():
    try:
        import pymysql
    except ImportError:
        print('缺少依赖，请先运行：python -m pip install "PyMySQL[rsa]"')
        return 1

    host = input("MySQL 主机 [127.0.0.1]：").strip() or "127.0.0.1"
    try:
        port = int(input("端口 [3306]：").strip() or "3306")
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        print("端口必须是 1 到 65535 之间的整数。")
        return 1
    user = input("用户名 [root]：").strip() or "root"
    database = input("数据库名称 [留空仅测试连接]：").strip() or None
    password = getpass.getpass("MySQL 密码（输入时不显示）：")

    try:
        with pymysql.connect(
            host=host, port=port, user=user, password=password,
            database=database, charset="utf8mb4", connect_timeout=5,
            read_timeout=5, write_timeout=5,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT VERSION(), CURRENT_USER(), DATABASE(), %s", ("中文测试成功",))
                version, account, selected_db, message = cursor.fetchone()
                print("\nMySQL 连接成功！")
                print(f"服务器版本：{version}")
                print(f"认证账号：{account}")
                print(f"当前数据库：{selected_db or '未选择'}")
                print(message)
        return 0
    except pymysql.MySQLError as error:
        print(f"\n连接失败：{error}")
        print("请对照 Navicat 检查主机、端口、用户名、密码和数据库名称。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
