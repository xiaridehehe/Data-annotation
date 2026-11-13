# 新版 MySQL 建表与前后端关联教程

当前浏览器标注使用九张关系表。核心业务字段直接存列；JSON 只用于病种表单配置、允许的评估目标和可变标注属性。不包含数据迁移、登录、角色权限、任务分配。

## 一、创建数据库和数据库账号权限

在 Navicat / MySQL Workbench 使用管理员连接执行：

```sql
CREATE DATABASE IF NOT EXISTS annotation_db
  CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
```

使用已经存在的 annotation_app 数据库账号时，管理员可授权：

```sql
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, REFERENCES
ON annotation_db.* TO 'annotation_app'@'localhost';
```

这里假设账号已经存在。如果实际账号的 Host 不是 localhost，应按实际账号授权。REFERENCES 用于建立外键；缺少它会出现 1142 错误。数据库账号不是网站登录账号。

在项目根目录 PowerShell 执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m backend.configure_mysql
```

默认主机、端口、账号和数据库直接回车，再输入数据库密码。连接配置写入 backend/mysql.local.json。设置了 ANNOTATION_DATABASE_URL 时，后端优先使用该环境变量。

配置脚本及后端启动会创建缺失的表。也可以先选中 annotation_db，手动执行 [backend/schema.sql](backend/schema.sql)。建议 MySQL 8.0.16+，以执行 CHECK 约束。脚本不删除已有表，不迁移旧 annotation_* 数据，也不修改同名表已有列结构。

## 二、九张表

所有表的内部主键为 BIGINT 自增 id，时间字段 created_at、updated_at 为 UTC DATETIME(6)。标注坐标与空间坐标使用 DOUBLE。

| 表 | 核心字段 | 约束及用途 |
| --- | --- | --- |
| workspaces | public_id、name | public_id 为唯一空间 UUID |
| patients | workspace_id、client_id、patient_code、issuer、version | (workspace_id, client_id) 唯一；患者编号本身不设唯一 |
| studies | workspace_id、patient_id、study_uid、accession_number、description、study_date、study_time、deleted_at、version | (workspace_id, study_uid) 唯一 |
| series | study_id、series_uid、series_number、description、modality、plane、deleted_at、version | (study_id, series_uid) 唯一 |
| images | series_id、sop_instance_uid、instance_number、width、height、sort_order、位置及方向列、像素间距列、version | (series_id, sop_instance_uid) 唯一；按序列与 sort_order 建索引 |
| diseases | workspace_id、code、name、box_policy、overall_schema、lesion_schema、target_keys、active、version | (workspace_id, code) 唯一 |
| assessments | series_id、disease_id、target_key、attributes、status、deleted_at、version | (series_id, disease_id, target_key) 唯一 |
| lesions | series_id、disease_id、public_id、target_key、attributes、color、deleted_at、version | (series_id, public_id) 唯一 |
| boxes | series_id、lesion_id、image_id、public_id、x_min、y_min、x_max、y_max、source_box_id、deleted_at、version | (lesion_id, image_id) 唯一；每病灶每切片一个框 |

images 的独立空间字段：position_x/y/z、row_cosine_x/y/z、column_cosine_x/y/z、pixel_spacing_row/column。

只有 diseases.overall_schema、lesion_schema、target_keys，以及 assessments.attributes、lesions.attributes 使用 JSON。不存在用于包装整条记录的 data 列。

患者到检查、检查到序列、序列到切片和标注均通过外键关联。boxes 使用复合外键 (lesion_id, series_id)、(image_id, series_id)，数据库可以拒绝跨序列关联。患者与检查也通过复合外键保证空间一致。病种与标注的空间一致性由后端额外校验。

标注中的 public_id 是浏览器生成的 UUID，内部关联仍用 BIGINT。patients.client_id 是前端稳定匹配患者的技术标识，与显示的 patient_code 不同。

## 三、同一患者的多次检查

患者有明确编号和来源（Issuer of Patient ID，缺失时使用 Institution Name）时，前端按来源加患者编号生成稳定标识。检查分别使用 Study Instance UID，互不覆盖。

若患者编号或来源不足，按检查 UID 生成独立患者技术标识，避免不同患者被错误合并。因此来源缺失时，多次检查不会自动推断为同一患者。

```text
patients.id=10
  studies.id=21，study_uid=第一次检查 UID
    series → images → boxes
  studies.id=22，study_uid=复查 UID
    series → images → boxes
```

导入时不允许现有检查、序列或切片被改挂到其他上级。当前单帧 DICOM 模式会明确拒绝多帧文件。

## 四、半月板内外侧

病种 MENISCUS_INJURY 的 target_keys 固定为：

```json
["MEDIAL_MENISCUS", "LATERAL_MENISCUS"]
```

普通病种使用 ["OVERALL"]。后端校验整体评估及局部病灶的 target_key。

同一序列内，内侧与外侧分别保存 assessments 记录，各自拥有 attributes 和 version。例如内侧部分撕裂、外侧正常。整体评估当前按序列保存，不跨序列共用。

## 五、前后端代码如何连接数据库

```text
main.tsx：画框、改属性、切换侧别
 → local.ts：缓存当前页面状态，比较修改前后列表
 → POST /api/workspaces/{UUID}/changes：仅发送新增/修改/删除的记录
 → relational_api.py：检查空间、关联、坐标、侧别、版本
 → models.py：独立数据库列、外键、索引、唯一约束
 → MySQL
```

- backend/database.py：读取数据库连接配置，创建 SQLAlchemy engine 和缺失表。
- backend/models.py：九张表的唯一结构定义。
- backend/relational_api.py：当前浏览器工作流的读取、增量保存、软删除和恢复接口。
- frontend/local.ts：保持现有查看器的数据对象格式，将 changes 请求转换为关系表操作。

前端继续使用 DICOM UID 或 UUID 标识对象；后端解析这些公开标识，写入内部 BIGINT 外键。例如前端的 lesion_instance_id 对应 boxes.lesion_id；sop_instance_uid 对应 boxes.image_id。前端不会直接连接 MySQL。

## 六、接口示例

初次读取：

```text
GET /api/workspaces/{空间UUID}/state
```

返回 {"state": {...}}，每条记录带 version。新空间首次读取时初始化默认病种。groups、segmentations 为兼容现有查看器返回空列表，不对应数据库表；_deleted 包含支持撤销所需的软删除记录。

修改一个框：

```json
{
  "operations": [{
    "kind": "boxes",
    "action": "upsert",
    "expected_version": 3,
    "record": {
      "id": "框的UUID",
      "lesion_instance_id": "病灶的UUID",
      "sop_instance_uid": "切片的SOP实例UID",
      "x_min": 10, "y_min": 20, "x_max": 60, "y_max": 80
    }
  }]
}
```

发送到 POST /api/workspaces/{空间UUID}/changes。新增 expected_version=0，修改/删除填写已读取的版本。删除 action="delete"，record 只需 id。支持的 kind 为 patients、studies、series、instances、diseases、assessments、lesions、boxes；instances 对应 images 表。

整体评估公开 ID 格式为 序列UID|病种编码|target_key，后台仍使用自增主键和独立关联列，不在数据库中拼接外键。

成功响应只返回受影响记录的新版本和 saved_at。错误包括：422 数据不合法，404 关联记录不存在，409 版本或唯一约束冲突。单批最多 2000 条操作，整批事务失败即回滚。前端大批导入按 1000 条分批提交，前面成功的批次不会因后续批次失败而撤销；刷新后可以重新导入。

前端“保存标注”调用空 changes 请求确认服务器可访问，实际改动此前已逐条自动保存，不产生全空间快照。

移除/恢复检查或序列：POST /api/workspaces/{UUID}/visibility，填写 kind、id、expected_version、restore。软删除保留关联标注，恢复时显示原记录。

## 七、运行与查询

重启后端并刷新前端页面。旧 /api/browser-project 接口返回 410，避免旧页面继续写 JSON 空间。无需删除旧表。

```sql
SELECT id, public_id, name FROM workspaces;
SELECT id, workspace_id, patient_code, issuer FROM patients;
SELECT id, patient_id, study_uid, study_date FROM studies;
SELECT id, study_id, series_uid FROM series;
SELECT id, series_id, sop_instance_uid, width, height FROM images;
SELECT id, series_id, disease_id, target_key, attributes, version
FROM assessments;
SELECT id, lesion_id, image_id, x_min, y_min, x_max, y_max, version
FROM boxes WHERE deleted_at IS NULL;
```

检查某个患者的所有检查：

```sql
SELECT p.id AS patient_pk, p.patient_code, s.id AS study_pk,
       s.study_uid, s.study_date, s.description
FROM patients p JOIN studies s ON s.patient_id=p.id
WHERE p.id=10 AND s.deleted_at IS NULL;
```

## 八、当前边界

- 新浏览器工作流使用上述九张表。旧服务端上传/导出接口暂时保留，使用独立的 records 表，不与新表同步；当前前端不调用这些旧接口。旧 annotation_* 表不会被读取或自动删除。
- 当前首次读取和页面刷新仍拉取整个空间。增量写入已完成，读取分页和按序列懒加载尚未实现。
- 同一空间的短事务使用空间行锁保证读取快照与修改一致，记录版本独立；不同记录没有共享空间版本冲突，但同空间写事务仍会短暂排队。
- 软删除支持恢复，不提供任意历史版本追踪。
- 空间 UUID 只区分数据，不提供登录或权限控制。


## 共享标注与操作记录（当前行为）

当前前端统一使用共享空间 00000000-0000-4000-8000-000000000001，不再按浏览器创建独立空间。原有其他空间的数据不会自动合并。同一份 DICOM 重复导入关联共享记录，保留已有标注；文件仍需各人在本机选择。

页面先填写姓名或工号。浏览器保存该值，每次修改通过 X-Operator 请求头传入（中文使用 URI 编码）。后端拒绝空操作人。此标识由本人填写，不提供身份认证。

新增第十张业务表 change_logs：workspace_id、actor、entity_type、entity_key、action、before_value、after_value、created_at、updated_at。前后值使用 JSON 保存操作时的记录快照；当前表的核心字段仍为独立列。每次成功的创建、更新、删除、移除和恢复都在同一事务内追加日志。失败和版本冲突不记录为成功修改。

页面读取最新状态，不显示历史快照；空闲时约每 5 秒刷新。记录版本检查保留，不同人同时修改同一记录时，过期保存返回 409。

```sql
SELECT actor, entity_type, entity_key, action, created_at,
       before_value, after_value
FROM change_logs ORDER BY id DESC LIMIT 100;
```
