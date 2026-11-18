# Knee MRI Annotation

面向小团队的膝关节 MRI 浏览器标注系统。DICOM 文件在浏览器中解析，像素缓存在本机 IndexedDB，不上传服务器；服务器 MySQL 仅保存患者/检查/序列匹配元数据、标注、账号、审核记录和审计日志。

## 当前架构

- 前端：React、Vite、Cornerstone、dicom-parser。
- 后端：FastAPI、SQLAlchemy、MySQL。
- 数据接口：`/api/workspaces/{workspace_id}/...` 关系型接口。
- 权限：标注员、审核员、管理员，使用 HttpOnly Cookie 会话。
- 审核：提交、驳回、重新提交、通过及版本差异记录。
- 本地影像：目录或 ZIP 导入、IndexedDB 缓存、重新导入 UID 匹配。

旧版 `records` API（`/api/state`、`/api/import`、`/api/{kind}`、`/api/imported/...` 等）已停用且不再注册。当前业务不得把 DICOM 像素写入服务器。

## 本地启动

先按 [MYSQL_SETUP.md](MYSQL_SETUP.md) 配置 MySQL。Windows 双击 `start-windows.bat`；Linux 运行 `bash start-linux.sh`。开发地址为 `http://127.0.0.1:5173`，Vite 将 `/api` 转发至本机 8000 端口。

## 统一验证

Windows：

```powershell
.venv\Scripts\python.exe verify.py
```

Linux：

```bash
.venv/bin/python verify.py
```

该命令使用临时 SQLite 数据库运行全部 Python 测试、前端回归检查和生产构建，不连接本机或服务器 MySQL。Windows 标准部署脚本调用同一验证入口，验证失败时不会启动新服务。

## 数据与部署

- 关系表结构见 `backend/models.py` 和 `backend/schema.sql`。
- Windows 部署见 `deployment/configure-windows.ps1`。
- MySQL 自动备份见 `deployment/install-mysql-backup.ps1`。
- 生产环境由 Caddy 提供 HTTPS，并将 `/api` 反向代理至 FastAPI。
