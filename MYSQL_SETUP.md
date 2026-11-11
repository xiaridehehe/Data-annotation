# MySQL 接入步骤

先关闭正在运行的后端窗口，迁移期间不要运行网站或修改数据库。

在项目根目录的 PowerShell 终端执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m backend.configure_mysql
```

填写 127.0.0.1、3306、annotation_app、annotation_db 和该账号的密码。
配置保存在 backend/mysql.local.json（包含明文密码，已加入 Git 忽略，请仅保留在服务器本机）。
密码通过 SQLAlchemy URL.create 传入，可以包含 @ 等特殊字符。
数据库必须预先创建，账号需要 SELECT、INSERT、UPDATE、DELETE、CREATE、INDEX、ALTER 权限。

如果需要保留原网站的 SQLite 数据，在第一次启动新后端之前执行：

```powershell
.\.venv\Scripts\python.exe -m backend.migrate_sqlite
```

迁移会在事务中复制旧数据，不删除源数据库，不覆盖目标记录；遇到不同内容的同 ID 记录会报错并回滚。
配置后请先迁移，再启动网站，避免默认病害初始化数据与旧数据冲突。
原始影像仍在 backend/data，请继续保留并备份该目录。

然后双击 start-windows.bat 启动网站。
未配置 MySQL 时后端会明确报错，不会自动退回 SQLite。
如设置了 ANNOTATION_DATABASE_URL 环境变量，它会优先于本地配置；普通使用不需要设置该变量。

在 Navicat 刷新 annotation_db，可以看到自动创建的 records 表：

| 列 | 用途 |
| --- | --- |
| kind | patients、studies、series、instances、diseases、assessments、lesions、boxes、groups、segmentations、snapshots、deleted_imports |
| id | 唯一记录 ID，区分大小写 |
| data | JSON 文本，保存现有网站的完整字段 |

在网站保存或修改一条标注后，在 Navicat 执行：

```sql
SELECT kind, COUNT(*) AS total FROM records GROUP BY kind;
SELECT id, data FROM records WHERE kind = 'assessments';
SELECT id, data FROM records WHERE kind = 'boxes';
SELECT id, data FROM records WHERE kind = 'snapshots';
```

修改标注会更新对应记录，点击项目保存会另外新增 snapshots 记录。
目前采用兼容现有项目的通用记录表，并非十一张独立实体表。
此步骤仅切换存储，跨网络访问仍需后续配置网站入口、HTTPS 和访问认证。
MySQL 和后端位于同一电脑时，数据库保持本机访问，不需要向公网开放 3306。

实现依据：SQLAlchemy MySQL 方言支持 INSERT ... ON DUPLICATE KEY UPDATE：
https://docs.sqlalchemy.org/en/20/dialects/mysql.html
