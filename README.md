# OS Agent 多源融合记忆优化系统

本项目是“挑战杯·揭榜挂帅”赛题 XA-202612 的可运行研发原型，面向桌面 OS Agent 的偏好记忆、知识记忆、混合检索、冲突治理与可验证遗忘。设计原则是端侧优先、作用域隔离、证据可追溯和结论不过度外推。

首次操作请从[傻瓜式测试操作指南](docs/OPERATION_MANUAL.md)开始：按窗口、命令、预期结果、
故障处理和证据保存逐项说明。本次实际试跑、已知失败与未执行范围见
[指南核验记录](docs/48_测试操作指南核验.md)，不要把手册中的预期结果直接当作实测结果。

## 当前状态

**已完成初版，待赛事验收。** 四项出题方反馈及本次改动以
[反馈落实记录](docs/37_出题方反馈落实.md)为准。该状态不等于原生SDK或赛事验收通过。

2026-09-11继续优化后的结论见[四项反馈复核](docs/42_四项反馈复核与验收.md)，
近期记忆系统和公开基准的机制对比见[相关工作补充](docs/43_近期相关工作与评测对照.md)。
按最新反馈修订的
[20页精简项目报告PPT](deliverables/submission-materials-20260911-revised/OS_Agent_项目报告_20页精简版_20260911.pptx)和
[66页评分重点详述Word](deliverables/submission-materials-20260911-revised/OS_Agent_技术方案_评分重点详述版_20260911.docx)
已生成并核验，详见[修订核验记录](docs/47_精简PPT与评分重点Word修订核验.md)。
Word新增12节，详细展开相关工作、技术创新性、评测口径和性能可信度；
原53页PPT与54页Word保留在[原版交付记录](docs/46_项目报告与技术方案交付核验.md)。

已有多源记忆、显式授权的Markdown/YAML、偏好修正、混合检索、冲突隔离、可审计遗忘、
SQLite与本地HTTP服务；支持5会话50轮行动评测框架及逐请求指标核验。
真实Agent、独立Judge和第三方隐藏标签评测仍按
[正式评测交接](docs/36_正式评测资源与外部交接.md)推进。

真实SDK时延为**待复测风险项**：旧ABI只有一次13,390.615ms探针，包含进程、会话及
初始化成本，不是P95；新ABI缺符号，模型身份及向量数据库往返待核验。
HashEmbedding的成绩不代表原生SDK成绩，详见[SDK证据边界](docs/27_真实SDK接入与证据边界.md)。

当前默认`focused_evidence_v2`已通过复杂拒答和完整召回回归。原12场景120请求中，
72/72正例找齐、24/24无答案正确拒答；另6场景48请求在显式约束开启和关闭时均为
24/24正例找齐、12/12正确拒答。全部多文档和作用域检查通过；
1千/1万条、0%/75%相似填充、各三轮均通过逐请求不退化及500ms门槛。

1万条/75%下三轮P95：原集67.605/66.067/66.724ms，约束开启16.150/15.600/15.456ms，
约束关闭16.447/15.452/15.696ms。原集比同次旧默认多了证据检查开销，不宣称普遍加速。
该配置正例返回仍有31.71%/23.08%的干扰片段，完整召回不等于零干扰或最终回答正确。
完整矩阵、分层计分和适用边界见[优化验收报告](docs/45_复杂拒答与完整召回优化验收.md)。

初始20个开发请求和追加10个反例中新策略也全部通过；它们是可见开发数据，不并入168个
复杂请求或冒充盲测。旧`similarity`和损害召回的`content_coverage_v1`仅保留为显式对照，
新默认不是直接打开旧实验；历史失败见[正文证据检查与反例](docs/44_正文证据检查与反例.md)。

指南实测另发现一个新增的H7/H70中英混合反例：无显式型号约束时错误返回H70，
有约束时才能找齐本例两份H7证据；旧v3测试切分也仍为11/12正例找齐。
这两项不被上述指定复杂回归的通过结论覆盖，详见[指南核验记录](docs/48_测试操作指南核验.md)。
本次只编写文档及复验，不改运行算法；不能宣称所有复杂输入均已解决。

上一轮Windows固定证据记录392项测试，无失败、1项平台条件跳过，17项工程检查通过。
冻结五项的四项质量为100%，80个不同服务查询的P95为48.145ms；固定分母及阈值不变。
原始证据见`artifacts/verification/feedback/focused-20260911/windows-final/`。
新版Word/PPT绑定上述当前源码和证据；Word保留25张框图，20页PPT选用10张可编辑框图。
该轮材料修订不修改运行算法或重测时延，23项新增材料工具测试和18项原工具测试另计。
本次指南新测仍为392项、无失败且跳过1项，冻结五项P95为50.828ms；
新旧时延分开留存，没有重跑整套17项，也没有以新结果替换Office绑定证据。
既有39页Word及23页PPT只对应`implementation-20260910`历史源码，继续保留而不覆盖。
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

新版材料生成器另使用Pillow绘图，渲染核验可选PyMuPDF；
依赖、字体、两次生成及严格核验见[材料工具说明](docs/materials_20260911_revision/README.md)。

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

当前Windows固定证据位于 `artifacts/verification/feedback/focused-20260911/windows-final/`，V11失败轮次位于 `artifacts/verification/takeover/kylin_initial/`；其他已封存目录只对应各自历史源码。逐请求命令对五项数值、样本数和附加安全门槛执行硬检查，未达标返回非零。完整验收还执行源码编译、全部测试、v1/v2 历史诊断、v3 检索回归、衰减消融、真实服务命中与RSS、规模性能、兼容性、演示预检、材料及隐私检查，通常需数分钟。CI另执行严格双环境源绑定材料检查，当前该项尚未通过；旧Office生成器绑定历史证据，不能用其旧检查结果证明本轮材料。新版使用`docs/materials_20260911_revision/qa.py`单独严格核验，材料检查不替代双环境或赛事验收。`local_release_checks_passed` 与 `competition_submission_ready` 分开；真实 SDK/新领域需重新校准，0.265 不保证通用。复杂集的严格复测及三策略不退化命令见第45号报告。

## 初版技术审阅

当前材料及阅读顺序见 [审阅说明](submission/REVIEW_README.md)。
**本轮不打包，等待负责人审阅后另行授权。** 本轮交付工程、Markdown及原始复测证据，
另按最新要求提供20页精简PPT与评分重点详述Word，位于`deliverables/submission-materials-20260911-revised/`。
本次只提供一个DOCX和一个PPTX及说明清单，不提供交付PDF，不生成赛事ZIP或上传。
新版使用独立生成器、当前运行源码摘要和固定证据，已实际渲染及逐页视觉检查。
旧Office、`review_implementation_manifest.json`及其他审阅清单仍绑定历史版本；
后续正式封包须重新更新允许列表，不能照搬旧预检报告。真实视频、报名表、授权案例及部署验证缺项保留，
`competition_ready=false`，不能把布局预检称为解包或赛事验收。
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

- 第一次测试：[傻瓜式测试操作指南](docs/OPERATION_MANUAL.md)；[本次实际核验与风险](docs/48_测试操作指南核验.md)
- 最新Word/PPT：[材料目录](deliverables/submission-materials-20260911-revised/README.md)；[修订核验](docs/47_精简PPT与评分重点Word修订核验.md)
- 技术方案：`docs/09_技术方案正文.md`
- 本次反馈与证据：`docs/37_出题方反馈落实.md`；接续历史：`docs/35_接管实施与交付记录.md`
- 复杂拒答、完整召回与不退化验收：`docs/45_复杂拒答与完整召回优化验收.md`
- 快速演示：`docs/08_演示快跑指南.md`、`docs/演示操作手册.md`
- 部署与复现：`docs/12_部署手册.md`、`docs/14_可复现指南.md`
- API 与模块：`docs/13_API文档.md`、`docs/15_源代码模块说明.md`
- 适配边界：`docs/07_银河麒麟适配说明.md`
- 正式评测与外部交接：`docs/36_正式评测资源与外部交接.md`
- 整改进度：`docs/35_接管实施与交付记录.md`；历史任务 `docs/29_续作任务清单.md`、`docs/05_整改任务总清单.md`

## 许可与隐私

项目原创代码以 MIT 许可证发布，详见 `LICENSE`。第三方依赖和素材来源见 `THIRD_PARTY_NOTICES.md`，漏洞报告见 `SECURITY.md`，真实案例和个人报名信息的发布边界见 `docs/16_原创性与隐私发布边界.md`。公开仓库中的数据均为合成数据，不得用真实个人资料替换后直接提交。
