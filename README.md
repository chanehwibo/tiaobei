# OS Agent 多源融合记忆优化系统

本项目是“挑战杯·揭榜挂帅”赛题 XA-202612 的可运行研发原型，面向桌面 OS Agent 的偏好记忆、知识记忆、混合检索、冲突治理与可验证遗忘。设计原则是端侧优先、作用域隔离、证据可追溯和结论不过度外推。

## 当前状态

**已完成初版，待赛事验收。** 四项出题方反馈及本次改动以
[反馈落实记录](docs/37_出题方反馈落实.md)为准。该状态不等于原生SDK或赛事验收通过。

已有多源记忆、显式授权的Markdown/YAML、偏好修正、混合检索、冲突隔离、可审计遗忘、
SQLite与本地HTTP服务；支持5会话50轮行动评测框架及逐请求指标核验。
真实Agent、独立Judge和第三方隐藏标签评测仍按
[正式评测交接](docs/36_正式评测资源与外部交接.md)推进。

真实SDK时延为**待复测风险项**：旧ABI只有一次13,390.615ms探针，包含进程、会话及
初始化成本，不是P95；新ABI缺符号，模型身份及向量数据库往返待核验。
HashEmbedding的成绩不代表原生SDK成绩，详见[SDK证据边界](docs/27_真实SDK接入与证据边界.md)。

新增12场景、120请求的复杂回归。1万条/75%相似填充下，首轮P95从67.755ms降至
39.023ms，1,440对结果完全一致；正例Recall@3为94.44%，但近主题无答案正确率仅
4.17%，不能宣称复杂质量全部通过。数据、消融和失败明细见
[复杂检索复测](docs/40_复杂场景与检索性能复测.md)。

接续前的源码`f02cdeb`已有Windows 275项测试（1项预期POSIX跳过）及17项工程检查；
V11两轮275项测试通过，但HTTP连接被系统网络管控拒绝，核心仅7/8通过。
这组历史实测的四项冻结质量均100%，P95为Windows 67.730ms、V11 139.981/132.803ms。
本次代码变更后需要新源码复验，不将上述历史数据冒充新版本的双环境验收。

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

当前Windows固定证据位于 `artifacts/verification/takeover/windows/`，V11失败轮次位于 `takeover/kylin_initial/`；`round5/`、`x01-x02/` 和 `x01-judge/` 保留各自历史版本的结果。逐请求命令对五项数值、样本数和附加安全门槛执行硬检查，未达标返回非零。完整验收还执行源码编译、全部测试、v1/v2 历史诊断、v3 检索回归、衰减消融、真实服务命中与RSS、规模性能、兼容性、演示预检、材料及隐私检查，通常需数分钟。CI另执行当前版源绑定材料检查，当前该项尚未通过。`local_release_checks_passed` 与 `competition_submission_ready` 分开；真实 SDK/新领域需重新校准，0.265 不保证通用。

## 初版技术审阅包

```powershell
python .\scripts\build_submission.py --allow-incomplete
```

默认输出到 Git 忽略的 `dist/competition_submission_draft/`，展示状态为“已完成初版，待赛事验收”。
真实视频、报名表、授权案例或部署验证有缺项时，构建报告逐项列明并保持
`competition_ready=false`，不会自动变成正式包。结构和完整参数见 `submission/README.md`。

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
