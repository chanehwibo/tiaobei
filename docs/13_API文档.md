# MemoryService 与本地 HTTP API

## 1. 作用域和数据格式

作用域读取、冲突决策及遗忘确认均要求 tenant_id、user_id；修改接口还要求目标 ID。/api/stats 为全局开发统计，/api/demo 仅操作专属合成租户。请求/响应使用 UTF-8 JSON，HTTP 请求体最大 1,000,000 字节。

```json
{"error": "错误原因"}
```

当前 API 用于 localhost 演示，没有身份认证。调用方传入的 tenant/user 必须由可信上层身份系统绑定，不能直接信任终端用户任意填写。

## 2. Python 服务层

```python
from os_agent_memory.service import MemoryService

service = MemoryService(database_path="artifacts/runtime/memory.sqlite")
```

### `ingest(raw_records, persist=True)`

接收事件字典迭代器；返回 accepted/rejected/duplicate 数、issues、偏好、知识、promotion_decisions 和 stats。单条低证据留在中期；跨请求与重启去重。配置数据库时增量原子提交，失败回滚服务状态。

事件 ID 在 `(tenant_id, user_id)` 内唯一；不同所有者可以使用同一个来源 ID，
导入响应中的偏好和知识也按该作用域关联来源。短期记忆使用同样的键，避免同名事件互相覆盖。
同一批中同作用域、同 ID 而正文等指纹字段不同的事件报告 `event_id_conflict`。
`authority` 必须为有限数值（不接受布尔值）；`ttl_seconds` 接受正整数或整数字符串，
拒绝布尔值、小数和超出日期范围的值；非法行计入 issues，其余有效行继续处理。
直接使用 `ShortTermMemoryBuffer.remove` 时也必须传入 `tenant_id` 与 `user_id`。

### `preferences(tenant_id, user_id, scene=None)`

返回当前 active 偏好，按 key 排序。scene 存在时只返回全局或适用该场景的偏好。

### `search(query, tenant_id, user_id, scene=None, top_k=5, min_score=0.265, include_pending=False, retrieval_mode="hybrid", required_terms=None, evidence_policy="focused_evidence_v2")`

返回带综合、词法、语义分数的知识列表。业务回答不得把 `include_pending` 设为 true；该选项仅用于冲突诊断。

`retrieval_mode` 可为 `hybrid`、`lexical`、`semantic`。`required_terms` 是调用方明确提供的
证据约束，最多16个字符串，每个1至128字符；所有词项都必须在同一条知识的标题或正文中出现。
例如 `["AE-17", "v2.4"]` 可以排除相似设备和其他版本，过滤发生在候选截断之前。
全角英数字按半角处理，英文忽略大小写并要求完整词边界，标签和来源ID不能充当正文证据。
空数组等同未提供显式约束，非法类型、空白项和纯标点返回参数错误。
默认v2仍可从无歧义的明确请求保留格式化设备/版本身份；空数组并非关闭所有主体保护。

显式约束本身不是自动抽取条件、语义蕴含判断或可靠拒答器。调用方不得从评测标签反推约束；
出现词项不代表文档支持其中的条件关系，也不代表内容可信。多条知识分别提供不同证据时，
应拆分请求或只指定各条共同的实体约束，不能要求每条同时包含所有答案词。

`evidence_policy` 默认`focused_evidence_v2`，库、服务、HTTP及复杂评测入口保持一致：

- 明确问句、指令及前置条件请求：聚焦所问内容，允许中文数量等价，检查授权标题/正文的支持。
  主种子须达到请求的`min_score`（默认0.265）；同一精确主题的不同章节按新增证据补全，
  最多返回top_k条。调低阈值不继承固定配置下的验收结论。
  仅实际返回的文档可证明覆盖，不能借用未返回、已删除或其他作用域的文档。
- 未提供非空显式约束时，保留无歧义的格式化设备/版本身份，例如`AE-17`和`v2.4`；
  也保留带实体类别词的紧凑型号，例如`Sensor H7`、`device Q12`、`传感器H7`。
  类别词和型号共同作为字面约束，H70不能替代H7；裸`SHA256`、`UTF8`不被当作设备。
  明确排除的设备及叙述中的邻机不作为目标，多个目标有歧义时返回空数组。
  非空调用方约束优先；这不是任意实体识别、指代消解或从标签生成条件。
- 普通关键词查找：保留原候选、分数及排序，结果标记为`ranked_lookup`，不宣称已回答问题。
- 属性问题另检查正文片段；覆盖不足0.5时返回空数组。标签、来源ID和评测标签均不充当支持。

结果增加`evidence`字段：`origin`区分`direct`、`subject_companion`及`ranked_lookup`；
`seed_id`给出主题束的种子；`document_score`、`passage_score`和`direct_score`保留计分来源。
章节补全的顶层`score`为主题束相关度，**不等于该章节独立相似度或答案正确概率**。
`coverage`只表示词面支持比例；关键词查找时为null。片段计分复用已有查询向量，不新增模型调用。

显式`similarity`仍可复现旧相似度检索；`content_coverage_v1`保留为非默认历史实验，
只检查原top_k且不改排序，其已知误拒与召回损失见[正文证据检查与反例](44_正文证据检查与反例.md)。
HTTP支持同名字段，未知值返回400。0.265沿用旧v3开发集校准，新策略未重新调阈值。
词面检查和精确标题章节关联不是语义蕴含、否定推理或通用多跳推理；调用方仍须核验答案，
真实SDK或新领域不能直接沿用本地合成回归结论。
原120请求及约束48请求的完整矩阵、开发反例、不退化门禁和残余干扰见
[优化验收报告](45_复杂拒答与完整召回优化验收.md)。

### conflicts(tenant_id, user_id) / resolve_conflict(memory_id, tenant_id, user_id, strategy="auto")

列出待决冲突，或用 `auto`、`accept_incoming`、`keep_existing`、`keep_both`、`merge`、`manual_review` 处理指定知识。

### forget_preview(...) / forget_confirm(plan_id, tenant_id, user_id)

preview 参数：instruction、tenant_id、user_id、hard_delete=False、ttl_seconds=300。preview 零修改；confirm 才执行，并返回 affected IDs 和 audit_id。

### `stats()`

返回 active 偏好、版本数、active 知识、待决冲突、未确认遗忘计划、审计数和冲突决策数。

## 3. HTTP 路由

### `GET /`

返回本地单页演示界面。

### `GET /api/stats`

成功 `200`：

```json
{
  "preferences": 8,
  "preference_versions": 8,
  "knowledge": 5,
  "knowledge_conflicts": 1,
  "pending_forget_plans": 0,
  "audit_events": 0,
  "conflict_decisions": 0
}
```

### `GET /api/preferences`

查询参数：`tenant_id`、`user_id` 必填，`scene` 可选。

```text
GET /api/preferences?tenant_id=default&user_id=u-demo&scene=office_report
```

### `GET /api/conflicts`

查询参数：`tenant_id`、`user_id` 必填。只返回 conflict_pending。

### `POST /api/ingest`

```json
{
  "records": [
    {
      "id": "evt-web-1",
      "tenant_id": "default",
      "user_id": "u-demo",
      "session_id": "session-1",
      "source_type": "manual_config",
      "scene": "office_report",
      "timestamp": "2026-09-05T09:00:00+08:00",
      "content": "用户偏好：请使用中文并保持简洁。",
      "metadata": {"title": "输出偏好"}
    }
  ]
}
```

记录级错误不会让整批失败，详见响应 `issues`。

### `POST /api/search`

```json
{
  "query": "报销邮件模板",
  "tenant_id": "default",
  "user_id": "u-demo",
  "scene": "office_report",
  "top_k": 5,
  "min_score": 0.265
}
```

成功返回数组；低于阈值时返回空数组，不虚构答案。

HTTP也支持 `retrieval_mode` 和 `required_terms`，例如：

```json
{
  "query": "AE-17 v2.4升级前置条件和失败回滚依据",
  "tenant_id": "default",
  "user_id": "u-demo",
  "top_k": 3,
  "required_terms": ["AE-17", "v2.4"]
}
```

无可见候选或所有候选均不满足证据约束时，不调用embedding模型，直接返回空数组。
普通相似度检索仍有近主题误召回风险；非空结果不能直接视作已验证答案。

默认阈值 0.265 仅按 v3 dev 校准，服务/HTTP 与内部评测一致；更换 SDK 或领域需重新校准。结果额外包含 character_score：标题及正文的汉字集合余弦覆盖值，不是置信概率。

### `POST /api/conflicts/resolve`

```json
{"memory_id": "知识ID", "tenant_id": "default", "user_id": "u-demo", "strategy": "auto"}
```

目标不存在或不属于当前作用域返回 403；策略不支持返回 400。

### `POST /api/forget/preview`

```json
{
  "instruction": "删除报销模板相关记忆",
  "tenant_id": "default",
  "user_id": "u-demo",
  "hard_delete": false
}
```

响应含 `id`、`matched_keywords`、`preference_ids`、`knowledge_ids`、`expires_at`、`confirmed=false`。

### `POST /api/forget/confirm`

```json
{"plan_id": "预览返回的计划ID", "tenant_id": "default", "user_id": "u-demo"}
```

成功响应含 confirmed=true、affected IDs 和 audit_id。同作用域重复确认返回原回执；过期拒绝，错误作用域拒绝。回执可跨重启恢复。

GET /api/overview?tenant_id=...&user_id=... 返回当前作用域偏好、版本历史、知识及中期簇。
POST /api/demo 接收 {"name":"baseline","reset":true}；name 可为 baseline、preference、conflict。仅重置 local-demo 合成数据，其他租户保留。

## 4. 状态码

| 状态 | 含义 |
| ---: | --- |
| 200 | 请求成功，包括合法空结果 |
| 400 | JSON、字段、参数、目标或策略错误 |
| 404 | 路由不存在 |
| 409 | 服务运行状态冲突 |
| 403 | 作用域不匹配或跨源写入 |
| 503 | 持久化或调用超时失败 |

## 5. 安全约束

- 默认只监听 `127.0.0.1`。
- 不把 include_pending 用于业务回答。
- 硬删除前必须由 UI 或上层流程展示 preview 并取得明确确认。
- API 响应可能包含内部目标 ID，不应记录到公开分析系统。
- 若扩展到局域网，先完成认证授权、TLS、CSRF、防重放、限流和审计权限分级。
