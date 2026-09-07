# OS Agent 多源融合记忆优化系统

本项目是“挑战杯·揭榜挂帅”赛题 XA-202612 的可运行研发原型，面向桌面 OS Agent 的偏好记忆、知识记忆、混合检索、冲突治理与可验证遗忘。设计原则是端侧优先、作用域隔离、证据可追溯和结论不过度外推。

## 当前状态

第四轮按官方资料整改。强制部署环境为银河麒麟 **V11**；SDK 是推荐项。当前五项指标及环境实测状态见 [第四轮验收报告](docs/28_第四轮验收报告.md)，逐项进度见 [整改清单](docs/24_官方对齐整改清单.md)。正式提交仍为 `INCOMPLETE`。

- 已增加显式授权的 Markdown/YAML 记忆、按需召回与逐项确认遗忘、否定及多字段偏好修正。
- 5会话50轮行动评测检查15个实际输出文件；替身通过只证明框架自检，真实Agent/容器/独立Judge仍待验证。
- 五项内部诊断：偏好准确率46.15%（13槽位）、知识Recall@3 91.67%（12查询）、冲突100%（2案例）、检索P95与敏感F1各50请求。前三项样本不足，偏好未达85%，不宣称官方全部达标。
- 已依据官方C ABI增加真实Embedding子进程适配；实际库/模型/服务连通状态由 [SDK诊断](docs/27_真实SDK接入与证据边界.md) 证明，向量数据库桥接仍未完成。
- [隔离实验室](docs/25_隔离实验室与赛后清理.md)使用独立venv、镜像和虚拟磁盘，不升级或卸载宿主Python/VMware；赛后可核查并可恢复撤除。
- 独立盲测、真实授权案例、视频和赛事凭证仍待补齐。

第三轮的91项回归、91.67%正例召回及100%无答案正确率是历史内部证据，见 [第三轮报告](docs/22_第三轮验收报告.md)。它们不等同于官方“偏好准确率＋知识召回率”两个85%。历史报告和只读ZIP保留。

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
python .\scripts\verify_release.py --artifact-dir artifacts/runtime/verification --sizes 100,1000,5000,10000 --rounds 30
```

当前固定证据位于 `artifacts/verification/round4/`，第三轮目录保留为历史。完整验收会执行源码编译、全部测试、v1/v2 诊断、v3 两项 85% 门槛、消融、性能、兼容性、演示预检、材料检查和隐私扫描，通常需数分钟。它明确区分 `local_release_checks_passed` 与 `competition_submission_ready`；任一质量目标未达标时返回非零退出码。真实 SDK/新领域需重新校准，0.265 不保证通用。

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
- 测试与证据：`docs/测试报告.md`、`artifacts/verification/round4/final_verification.md`
- 快速演示：`docs/08_演示快跑指南.md`、`docs/演示操作手册.md`
- 部署与复现：`docs/12_部署手册.md`、`docs/14_可复现指南.md`
- API 与模块：`docs/13_API文档.md`、`docs/15_源代码模块说明.md`
- 适配边界：`docs/07_银河麒麟适配说明.md`
- 整改进度：`docs/05_整改任务总清单.md`

## 许可与隐私

项目原创代码以 MIT 许可证发布，详见 `LICENSE`。第三方依赖和素材来源见 `THIRD_PARTY_NOTICES.md`，漏洞报告见 `SECURITY.md`，真实案例和个人报名信息的发布边界见 `docs/16_原创性与隐私发布边界.md`。公开仓库中的数据均为合成数据，不得用真实个人资料替换后直接提交。
