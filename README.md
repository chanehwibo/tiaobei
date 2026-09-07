# OS Agent 多源融合记忆优化系统

本项目是“挑战杯·揭榜挂帅”赛题 XA-202612 的可运行研发原型，面向桌面 OS Agent 的偏好记忆、知识记忆、混合检索、冲突治理与可验证遗忘。设计原则是端侧优先、作用域隔离、证据可追溯和结论不过度外推。

## 当前状态

第五轮已在 Windows 和真实安装的银河麒麟 **V11 虚拟机**完成冻结逐请求回归。强制部署环境为 V11，SDK 是推荐项；虚拟机部署形式是否被赛事接受仍需出题方确认。当前证据见 [第五轮验收报告](docs/32_第五轮验收报告.md)，进度见 [续作 TODO](docs/29_续作任务清单.md)。正式提交仍为 `INCOMPLETE`。

- 已增加显式授权的 Markdown/YAML 记忆、按需召回与逐项确认遗忘、否定及多字段偏好修正。
- 5会话50轮行动评测检查15个实际输出文件；替身通过只证明框架自检，真实Agent/容器/独立Judge仍待验证。
- 五项均有至少50个不同请求，逐请求完整评分，固定标签与配置；保留失败基线及修复后的完整结果。
- 真实Embedding旧ABI单探针成功；新ABI缺符号，模型身份未核实，向量数据库往返仍未完成。详见 [SDK诊断](docs/27_真实SDK接入与证据边界.md)，不把单探针称为生产集成或性能验收。
- [隔离实验室](docs/25_隔离实验室与赛后清理.md)使用独立venv、镜像和虚拟磁盘，不升级或卸载宿主Python/VMware；赛后可核查并可恢复撤除。
- 独立盲测、真实授权案例、视频和赛事凭证仍待补齐。

<!-- BEGIN ROUND5 EVIDENCE -->
公开合成冻结回归，不是第三方盲测或官方认证；两个环境均为 HashEmbedding 256 维、10,000 条记录、top_k=3、阈值 0.265，实际调用 MemoryService.search。

| 指标 | 门槛 | Windows | 麒麟 V11 虚拟机 | 请求数 |
| --- | --- | --- | --- | --- |
| 偏好逐请求准确率 | >=85% | 100.00% | 100.00% | 68 |
| 知识 Recall@3 | >=85% | 100.00% | 100.00% | 60 |
| 冲突正确率 | >=88% | 100.00% | 100.00% | 60 |
| 检索 P95 | <=500ms | 77.629ms | 156.977ms | 80 |
| 敏感实体 F1 | >=90% | 100.00% | 100.00% | 50 |

自动化测试：Windows 164 项（通过）；V11 164 项（通过）。两个报告各自绑定被测版本，最终交付需核对源码摘要。
五项及附加安全门槛：Windows True；V11 True。敏感识别为实体级微平均，Windows TP/FP/FN=30/0/0。
旧 ABI 原生单探针返回 768 维向量，耗时 13390.615ms；模型身份未验证，不是原生 P95 或质量达标证据。向量数据库往返、真实 Agent/容器和独立 Judge 尚未验证。

数据原始 SHA256：`51ce224491a4252b69d282138785b28f4a9b8a64212b512f587dd48bfbcd1a98`。
原始报告：`artifacts/verification/round5/windows/requests.json`、`artifacts/verification/round5/kylin_final/requests.json`；完整来源摘要见 `artifacts/verification/round5/evidence_summary.json`。
<!-- END ROUND5 EVIDENCE -->

第三、四轮原始报告及只读 ZIP 保留为历史，不用旧 v1/v2 满分或小样本诊断替代当前逐请求成绩。

R08第五轮[交付草案及校验说明](artifacts/release/README.md)已封存，独立解包后再次通过164项测试和14项发布检查，四项质量100%、P95 67.275ms。该封存版本的95个公开被测文件与当时双环境实测版本一致。

C03实际逐页检查DOCX后修复重复页脚和列表编号，11页/246个非空段落/27个编号已验收。上表及Office数值仍引用R08原始证据；生成器和材料测试2项变更后的当前源码由C05独立补验，不沿用旧整包一致性结论。详见[交付复核](docs/33_第五轮交付复核.md)。正式提交仍为 `INCOMPLETE`。

C05A/C05B已完成当前源码的双环境补验：Windows和真实V11各166项测试通过，Windows14项发布检查、V11全部核心检查通过。四项质量均100%，P95分别105.002ms和127.145ms，固定分母68/60/60/80/50；95项公开被测文件的原始/LF摘要在双环境与当前工作树一致。新原始报告及独立核对位于 `artifacts/verification/round5/resume/`，历史报告及ZIP不改写。

C05C新的[续作双环境草案](artifacts/release/README.md)包含已视觉验收的DOCX、完整演示补验及最新双环境证据。422个内容文件已通过独立解包和重建核对；包内源码再次通过166项测试和14项发布检查，四项质量100%、P95 92.752ms。Git检出95项源码的LF摘要及155项受保护文件原始字节核对通过，隐私复核无异常。C05本地补验已完成，C04/R09统一推送与新CI核对仍待完成，不将草案冒充正式提交。

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

当前固定证据位于 `artifacts/verification/round5/`。逐请求命令对五项数值、样本数和附加安全门槛执行硬检查，未达标返回非零。完整验收还执行源码编译、全部测试、v1/v2 历史诊断、v3 检索回归、消融、规模性能、兼容性、演示预检、材料及隐私检查，通常需数分钟。`local_release_checks_passed` 与 `competition_submission_ready` 分开；真实 SDK/新领域需重新校准，0.265 不保证通用。

## 提交包草案

```powershell
python .\scripts\build_submission.py --allow-incomplete
```

默认输出到 Git 忽略的 `dist/competition_submission_draft/`。缺少真实视频、报名表、授权案例或麒麟验证报告时，脚本只生成 `incomplete_draft`，不会把草案标成正式包。结构和完整参数见 `submission/README.md`。

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
- 测试与证据：`docs/测试报告.md`、`docs/32_第五轮验收报告.md`
- 快速演示：`docs/08_演示快跑指南.md`、`docs/演示操作手册.md`
- 部署与复现：`docs/12_部署手册.md`、`docs/14_可复现指南.md`
- API 与模块：`docs/13_API文档.md`、`docs/15_源代码模块说明.md`
- 适配边界：`docs/07_银河麒麟适配说明.md`
- 整改进度：`docs/29_续作任务清单.md`；历史总表 `docs/05_整改任务总清单.md`

## 许可与隐私

项目原创代码以 MIT 许可证发布，详见 `LICENSE`。第三方依赖和素材来源见 `THIRD_PARTY_NOTICES.md`，漏洞报告见 `SECURITY.md`，真实案例和个人报名信息的发布边界见 `docs/16_原创性与隐私发布边界.md`。公开仓库中的数据均为合成数据，不得用真实个人资料替换后直接提交。
