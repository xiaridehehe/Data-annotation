# 本地影像 + 服务器标注

DICOM 文件夹和 ZIP 在浏览器中解析，像素不上传。标注、患者/检查/序列标识及影像尺寸等匹配元数据保存到服务器 MySQL 的 records 表，kind 为 browser_projects，每个浏览器独立标注空间。此标识是调试阶段的数据隔离方式，尚未接入用户登录和权限系统。

Windows 双击 start-windows.bat，同时启动前端和后端。需按 MYSQL_SETUP.md 配置 MySQL。访问 http://127.0.0.1:5173，Vite 将 /api 转发至本机 8000 端口。统一部署时，需将网站同源 /api 反向代理到 Python 后端。

刷新后重新选择本地影像，按 DICOM UID 匹配服务器标注。此前浏览器 IndexedDB 中的标注，在该浏览器的服务器标注空间尚不存在时自动迁入数据库。旧版服务端导入的标注尚未迁入新的浏览器空间。

标注每次编辑后写入数据库，保存按钮记录保存时间。服务端不可用时会显示保存错误。影像不会写入 backend/data。

验证：npm --prefix frontend run build；使用独立测试数据库运行 python -m pytest tests。

---

以下为旧版服务端模式的历史说明：

# Knee MRI Annotation

本地膝关节 MRI 标注项目。Windows 双击 start-windows.bat；Linux 运行 bash start-linux.sh。需要 Python 3.11+、Node.js 20+，首次启动联网安装依赖。访问 http://127.0.0.1:5173，API 文档 http://127.0.0.1:8000/docs。

数据保存在 backend/data，备份时复制整个目录。原始 DICOM 不发送到第三方；服务仅监听本机。ZIP 和目录导入支持无扩展名文件、真实序列名称、空间排序。压缩传输语法的支持取决于浏览器解码器。

ACL 整体评价以检查、病害、目标键唯一保存，切换序列共用。绘框完成后建立独立病灶并显示局部属性。复制上一层保留实例 ID，已有框跳过。半月板内外侧独立评价。积液和滑膜无框。骨损伤选择后进入绘框状态。

验证：python -m pytest tests；npm --prefix frontend run build。

当前交付为可继续开发的首版，尚未达到提示词全部验收项：框采用坐标输入编辑，尚缺影像上的框叠加和拖动编辑；撤销重做尚未覆盖删除和复合操作；部分内置病害字段需进一步按教程精确补齐；病害配置使用 JSON 编辑，尚缺完整可视化字段编辑、归档管理；数据库使用 SQLAlchemy 通用记录存储，未拆成要求的十一张实体表；尚未实现分割服务、跨序列分组交互与完整标注状态管理。尚未完成真实临床 DICOM 的浏览器端验收，不应将构建成功等同于完整业务验收。

### 当前关系表存储
浏览器标注使用 workspaces、patients、studies、series、images、diseases、assessments、lesions、boxes 九张关系表，核心字段独立存列。前端只提交变化记录，按记录版本防止覆盖；半月板内外侧分别评估。SQL 和完整接入说明见 [MYSQL_SETUP.md](MYSQL_SETUP.md) 与 [backend/schema.sql](backend/schema.sql)。
不执行旧数据迁移，不包含账号、权限、任务分配。旧服务端接口仍使用 records，不与新表同步。当前读取仍是全空间加载，尚未实现分页。
