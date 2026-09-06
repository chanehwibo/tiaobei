# OS Agent 多源融合记忆优化系统

本项目是“挑战杯·揭榜挂帅”赛题 XA-202612 的可运行研发原型，面向桌面 OS Agent 的偏好记忆、知识记忆、混合检索、冲突治理与可验证遗忘。设计原则是端侧优先、作用域隔离、证据可追溯和结论不过度外推。

## 当前状态

- 第二轮本地 14 项整改的实现、验收与推送记录见 [第二轮清单](docs/17_第二轮整改清单.md)。
- 第三轮 [质量提升清单](docs/21_第三轮质量提升清单.md)：自动化测试 91 项通过，两项内部质量门槛均已达到。
- v3 内部合成评测：42 事件、18 主题、54 查询；数据和标签未改，dev 可用区间中心统一阈值 0.265，已同步服务与 HTTP 默认入口。
- 混合检索 test 正例 Recall@3 **91.67%（11/12）**，无答案正确率 **100%（6/6）**；两项均 ≥85%。测试集曾被开发者多次接触，属于小样本内部回归，不是盲测或真实场景准确率。
- Windows + HashEmbedding、10,000 条：冷查询 246.796ms、热 p99 362.265ms；实际服务 1,000 条 HTTP 查询 p99 32.438ms。新增汉字索引增加延迟与内存，仍满足本次 500ms 门槛。
- [当前验收报告](docs/22_第三轮验收报告.md)与 PPT 共用 [证据摘要](artifacts/verification/round3/evidence_summary.json)。第二轮及此前归档保留为历史，旧 v1/v2 满分不能沿用。
- 真实银河麒麟、SDK、独立盲测、授权案例、视频及赛事凭证仍缺失；当前为开发机交付草案。

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
python -m pip install -e .
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\run_demo.ps1" -NoServer
```

第一条命令只安装核心包，核心运行时没有第三方 Python 依赖。若需重新生成可编辑 PPT/Word 材料：

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
python .\scripts\verify_release.py --artifact-dir artifacts/runtime/verification --sizes 100,1000,5000,10000 --rounds 30
```

当前固定证据位于 `artifacts/verification/round3/`。完整验收会执行源码编译、全部测试、v1/v2 诊断、v3 两项 85% 门槛、消融、性能、兼容性、演示预检、材料检查和隐私扫描，通常需数分钟。它明确区分 `local_release_checks_passed` 与 `competition_submission_ready`；任一质量目标未达标时返回非零退出码。真实 SDK/新领域需重新校准，0.265 不保证通用。

## 提交包草案

```powershell
python .\scripts\build_submission.py --allow-incomplete
```

默认输出到 Git 忽略的 `dist/competition_submission_draft/`。缺少真实视频、报名表、授权案例或麒麟验证报告时，脚本只生成 `incomplete_draft`，不会把草案标成正式包。结构和完整参数见 `submission/README.md`。

## 目录

```text
artifacts/verification/  固定评测、性能、兼容性与最终验收证据
case_studies/            真实案例流程说明与空白模板；私有材料不入库
data/                    合成样例及 v1/v2 标注评测集
deliverables/            可编辑 PPT、Word 技术报告与视频交付说明
docs/                    技术方案、测试、部署、API、演示和答辩材料
scripts/                 数据、PPT、演示、验收与打包工具
src/os_agent_memory/     核心实现
submission/              提交目录模板和允许列表清单
tests/                   单元、集成、HTTP E2E、安全与打包测试
```

## 文档入口

- 技术方案：`docs/09_技术方案正文.md`
- 测试与证据：`docs/测试报告.md`、`artifacts/verification/round3/final_verification.md`
- 快速演示：`docs/08_演示快跑指南.md`、`docs/演示操作手册.md`
- 部署与复现：`docs/12_部署手册.md`、`docs/14_可复现指南.md`
- API 与模块：`docs/13_API文档.md`、`docs/15_源代码模块说明.md`
- 适配边界：`docs/07_银河麒麟适配说明.md`
- 整改进度：`docs/05_整改任务总清单.md`

## 许可与隐私

项目原创代码以 MIT 许可证发布，详见 `LICENSE`。第三方依赖和素材来源见 `THIRD_PARTY_NOTICES.md`，漏洞报告见 `SECURITY.md`，真实案例和个人报名信息的发布边界见 `docs/16_原创性与隐私发布边界.md`。公开仓库中的数据均为合成数据，不得用真实个人资料替换后直接提交。
