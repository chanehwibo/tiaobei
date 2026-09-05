# OS Agent 多源融合记忆优化系统

本项目是“挑战杯·揭榜挂帅”赛题 XA-202612 的可运行研发原型，面向桌面 OS Agent 的偏好记忆、知识记忆、混合检索、冲突治理与可验证遗忘。设计原则是端侧优先、作用域隔离、证据可追溯和结论不过度外推。

## 当前状态

- 本地源码、合成评测、Windows 开发机性能、材料完整性和隐私扫描已通过自动化验收。
- 当前自动化测试为 61 项，完整结果见 `artifacts/verification/final_verification.md`。
- v2 数据集共 120 条合成事件，train/dev/test 各 40 条；test 分区偏好/冲突/遗忘 F1、Recall@3、MRR 和 nDCG@3 均为 1.0，Precision@3 为 0.9286。
- Windows + HashEmbedding 开发机在 10,000 条知识下冷查询 45.801ms、热查询 p99 57.641ms。
- 尚未取得真实银河麒麟系统、真实麒麟 embedding SDK、独立盲测、授权真实案例、最终视频和赛事流程回执，因此不能宣称赛题指定环境或全部交付已经达标。

上列数值对应 2026-09-05 固定报告；重新运行时以新生成的 JSON 为准。

## 能力概览

- 六类来源事件统一建模，带租户、用户、会话、场景、有效期、来源权威度与隐私级别。
- 输入校验、时间归一、去重、递归脱敏、失败工具降权、提示注入检测与错误隔离。
- 多维偏好、证据聚合、版本历史，以及短期—中期—长期生命周期。
- 词法候选召回、向量缓存和 embedding 重排；作用域不明确时拒答。
- 知识冲突默认隔离，支持新旧版本选择、双方保留、证据合并与人工确认队列。
- 自然语言遗忘的预览—确认两阶段协议、软/硬删除、索引同步和脱敏审计回执。
- SQLite v2 持久化、服务层、本地 HTTP API 与浏览器仪表盘。
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
python -m os_agent_memory.cli evaluate --suite ".\data\eval\office_memory_eval_v2.json" --split test --top-k 3 --summary-only
python .\scripts\verify_release.py --sizes 100,1000,5000,10000 --rounds 30
```

固定证据位于 `artifacts/verification/`。完整验收会执行源码编译、全部测试、v1/v2 评测、性能基准、兼容性、演示预检、材料检查和隐私扫描，通常需几十秒。它明确区分 `local_release_checks_passed` 与 `competition_submission_ready`。

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
- 测试与证据：`docs/测试报告.md`、`artifacts/verification/final_verification.md`
- 快速演示：`docs/08_演示快跑指南.md`、`docs/演示操作手册.md`
- 部署与复现：`docs/12_部署手册.md`、`docs/14_可复现指南.md`
- API 与模块：`docs/13_API文档.md`、`docs/15_源代码模块说明.md`
- 适配边界：`docs/07_银河麒麟适配说明.md`
- 整改进度：`docs/05_整改任务总清单.md`

## 许可与隐私

项目原创代码以 MIT 许可证发布，详见 `LICENSE`。第三方依赖和素材来源见 `THIRD_PARTY_NOTICES.md`，漏洞报告见 `SECURITY.md`，真实案例和个人报名信息的发布边界见 `docs/16_原创性与隐私发布边界.md`。公开仓库中的数据均为合成数据，不得用真实个人资料替换后直接提交。
