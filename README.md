# OS Agent 多源融合记忆优化系统

本项目是“挑战杯·揭榜挂帅”赛题 XA-202612 的可运行研发原型，面向桌面 OS Agent 的偏好记忆、知识记忆、混合检索、冲突治理与可验证遗忘。设计原则是端侧优先、作用域隔离、证据可追溯和结论不过度外推。

## 当前状态

**已完成初版，待赛事验收。** 四项出题方反馈及本次改动以
[反馈落实记录](docs/37_出题方反馈落实.md)为准。该状态不等于原生SDK或赛事验收通过。

2026-09-10重新对照已发送版本的结论见[四项反馈复核](docs/42_四项反馈复核与验收.md)，
近期记忆系统和公开基准的机制对比见[相关工作补充](docs/43_近期相关工作与评测对照.md)。

已有多源记忆、显式授权的Markdown/YAML、偏好修正、混合检索、冲突隔离、可审计遗忘、
SQLite与本地HTTP服务；支持5会话50轮行动评测框架及逐请求指标核验。
真实Agent、独立Judge和第三方隐藏标签评测仍按
[正式评测交接](docs/36_正式评测资源与外部交接.md)推进。

真实SDK时延为**待复测风险项**：旧ABI只有一次13,390.615ms探针，包含进程、会话及
初始化成本，不是P95；新ABI缺符号，模型身份及向量数据库往返待核验。
HashEmbedding的成绩不代表原生SDK成绩，详见[SDK证据边界](docs/27_真实SDK接入与证据边界.md)。

原复杂回归有12场景、120请求。本轮当前源码在1万条/75%相似填充下三轮P95为
39.971/38.730/39.301ms，正例Recall@3为94.44%，但近主题无答案正确率仅4.17%。
历史等输出优化的67.755ms至39.023ms、1,440对结果一致另作追溯，不冒充当前时延。
数据、消融和失败明细见
[复杂检索复测](docs/40_复杂场景与检索性能复测.md)。

再新增6个复杂运维场景、48请求及显式`required_terms`约束对照。同一源码、1万条/75%
相似填充下，约束关闭/开启的首轮P95为67.599/29.279ms，正例Recall@3为91.67%/95.83%，
无答案正确率为16.67%/66.67%。开启后的后两轮为74.901/111.129ms，反而慢于关闭约束的
52.884/51.216ms，不能宣称稳定加速。关系缺证据和多文档漏召回仍有失败，不宣称复杂质量全部通过；
详见[复杂约束补测](docs/41_复杂约束场景补测.md)。

另实现默认关闭的`content_coverage_v1`正文证据检查，并保留20个开发请求及10个追加反例。
实验减少部分误返回，但两套复杂集召回均下降，追加反例仅召回0/6；
默认保持`similarity`，不推荐业务启用实验策略，见[实验与失败边界](docs/44_正文证据检查与反例.md)。

当前Windows源码运行350项测试，无失败、1项平台条件跳过，17项工程检查通过。
冻结五项的四项质量为100%，80个不同服务查询的P95为40.762ms；仅代表固定公开合成回归。
原始证据见`artifacts/verification/feedback/implementation-20260910/windows/`，
39页Word及23页PPT位于`deliverables/review-20260910-implementation/`，已完成实际渲染检查。
历史V11的HTTP连接曾被系统网络管控拒绝，核心仅7/8通过；当前源码的V11部署仍待复验，
不以Windows新结果或历史V11数值替代双环境验收。

V11磁盘安装、虚拟机资源和评分口径已按参赛者确认获主办方认可，不重复申请；
原始凭证待归档。客户机当前保留挂起快照，恢复和原入口服务复验见
[部署与恢复记录](docs/35_接管实施与交付记录.md)。最终双环境材料门禁保持严格，
初版技术审阅包与正式赛事交付分别处理。

历史证据、旧Office及封存包保留原始字节和摘要，位于`artifacts/verification/`、
`artifacts/release/`；它们只对应各自注明的源码版本。CI结果也必须对应实际推送HEAD。

## 能力概览

- 六类来源事件统一建模，带租户、用户、会话、场景、有效期、来源权威度与隐私级别。
- 输入校验、时间归一、去重、递归脱敏、失败工具降权、提示注入检测与错误隔离。
- 多维偏好、证据聚合、版本历史，以及短期—中期—长期生命周期。
- 词法候选召回、向量缓存和 embedding 重排；作用域不明确时拒答。
- 知识冲突默认隔离，支持新旧版本选择、双方保留、证据合并与人工确认队列。
- 自然语言遗忘的预览—确认两阶段协议、软/硬删除、索引同步和脱敏审计回执。
- 增量 SQLite、持久化去重/阶段证据、失败回滚、服务层、本地 HTTP API 与场景仪表盘。
- Precision/Recall/F1、Precision@K、Recall@K、MRR、nDCG、误删率、延迟与资源基准。

## 快速开始

要求 Python 3.10 或更高版本。在克隆后的项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\run_demo.ps1" -NoServer
```

先创建独立venv，再将项目安装到其中；核心运行时没有第三方Python依赖。若需重新生成可编辑 PPT/Word 材料：

```powershell
python -m pip install -e ".[deliverables]"
```

不安装项目包时，也可临时设置模块路径：

```powershell
$env:PYTHONPATH="$PWD\src"
python -m os_agent_memory.cli doctor --workspace . --input ".\data\samples\events.jsonl" --suite ".\data\eval\office_memory_eval_v2.json"
python -m os_agent_memory.cli demo --input ".\data\samples\events.jsonl"
python -m unittest discover -s tests -v
```

启动本地仪表盘：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\run_demo.ps1"
```

浏览器访问 `http://127.0.0.1:8765`，按 `Ctrl+C` 停止。服务默认只绑定本机回环地址，不包含生产级认证或 TLS。

## 评测与最终本地验收

```powershell
$env:PYTHONPATH="$PWD\src"
python scripts/evaluate_v3.py --require-quality --embedding-config config/embedding.hash.json
python -X utf8 -S scripts/evaluate_requests.py --size 10000 --require-frozen --output artifacts/runtime/requests.json
python .\scripts\verify_release.py --artifact-dir artifacts/runtime/verification --sizes 100,1000,5000,10000 --rounds 30
```

当前Windows固定证据位于 `artifacts/verification/feedback/implementation-20260910/windows/`，V11失败轮次位于 `artifacts/verification/takeover/kylin_initial/`；`round5/`、`takeover/windows/`、`x01-x02/`、`x01-judge/` 和 `feedback/followup-20260910/` 保留各自历史版本的结果。逐请求命令对五项数值、样本数和附加安全门槛执行硬检查，未达标返回非零。完整验收还执行源码编译、全部测试、v1/v2 历史诊断、v3 检索回归、衰减消融、真实服务命中与RSS、规模性能、兼容性、演示预检、材料及隐私检查，通常需数分钟。CI另执行严格双环境源绑定材料检查，当前该项尚未通过；Windows审阅材料用`generate_review_materials.py --check-only`独立校验，不替代或放宽双环境门禁。`local_release_checks_passed` 与 `competition_submission_ready` 分开；真实 SDK/新领域需重新校准，0.265 不保证通用。

## 初版技术审阅

```powershell
python -B -X utf8 -S scripts/generate_review_materials.py --check-only
python -B -X utf8 -S scripts/build_review_submission.py --preflight-only --preflight-report artifacts/runtime/review-preflight-new.json
```

当前材料及阅读顺序见 [审阅说明](submission/REVIEW_README.md)。
**本轮不打包，等待负责人审阅后另行授权。** 上述命令只校验材料、生成当前允许列表及预检报告，
不创建提交目录或ZIP；报告路径必须不存在，历史报告不覆盖。
当前清单为`submission/review_implementation_manifest.json`。真实视频、报名表、授权案例或
部署验证缺项逐一保留，`competition_ready=false`，不能把布局预检称为解包或赛事验收。
后续封包边界见 `submission/README.md`。

## 目录

```text
artifacts/verification/  固定评测、性能、兼容性与最终验收证据
case_studies/            真实案例流程说明与空白模板；私有材料不入库
data/                    合成样例、v1/v2/v3 及冻结逐请求评测集
deliverables/            可编辑 PPT、Word 技术报告与视频交付说明
docs/                    技术方案、测试、部署、API、演示和答辩材料
scripts/                 数据、PPT、演示、验收与打包工具
src/os_agent_memory/     核心实现
submission/              提交目录模板和允许列表清单
tests/                   单元、集成、HTTP E2E、安全与打包测试
```

## 文档入口

- 技术方案：`docs/09_技术方案正文.md`
- 本次反馈与证据：`docs/37_出题方反馈落实.md`；接续历史：`docs/35_接管实施与交付记录.md`
- 快速演示：`docs/08_演示快跑指南.md`、`docs/演示操作手册.md`
- 部署与复现：`docs/12_部署手册.md`、`docs/14_可复现指南.md`
- API 与模块：`docs/13_API文档.md`、`docs/15_源代码模块说明.md`
- 适配边界：`docs/07_银河麒麟适配说明.md`
- 正式评测与外部交接：`docs/36_正式评测资源与外部交接.md`
- 整改进度：`docs/35_接管实施与交付记录.md`；历史任务 `docs/29_续作任务清单.md`、`docs/05_整改任务总清单.md`

## 许可与隐私

项目原创代码以 MIT 许可证发布，详见 `LICENSE`。第三方依赖和素材来源见 `THIRD_PARTY_NOTICES.md`，漏洞报告见 `SECURITY.md`，真实案例和个人报名信息的发布边界见 `docs/16_原创性与隐私发布边界.md`。公开仓库中的数据均为合成数据，不得用真实个人资料替换后直接提交。
