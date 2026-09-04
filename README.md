# OS Agent 记忆优化及高效应用研究

本项目用于“挑战杯 揭榜挂帅”赛题 XA-202612 的研发沉淀，目标是实现一套面向麒麟操作系统 OS Agent 的多源融合偏好记忆与知识记忆优化方案。

## 当前版本目标

首版先完成一个可运行闭环：

1. 接入工具执行结果、用户行为、手动配置等多源数据。
2. 对输入数据进行清洗、格式标准化、质量校验和敏感信息过滤。
3. 抽取用户偏好记忆，包括输出风格、工具选择、安全策略等。
4. 抽取知识记忆，包括流程、案例、模板和总结。
5. 提供轻量化知识检索、冲突标记、自然语言遗忘和基础评测。

## 目录结构

```text
os-agent-memory-optimizer/
  data/samples/             示例数据
  docs/                     赛题解读、技术路线、研发记录、问题记录
  scripts/                  辅助脚本
  src/os_agent_memory/      核心原型代码
  tests/                    基础测试
  pyproject.toml            Python 项目配置
```

## 快速运行

在 PowerShell 中执行：

```powershell
cd "C:\Users\CanhuiBao\Desktop\挑战杯 揭榜挂帅\os-agent-memory-optimizer"
$env:PYTHONPATH="$PWD\src"
python -m os_agent_memory.cli demo --input ".\data\samples\events.jsonl"
python -m os_agent_memory.cli evaluate --suite ".\data\eval\office_memory_eval.json" --top-k 3 --summary-only --output ".\data\eval\latest_report.json"
python -m os_agent_memory.cli build-store --input ".\data\samples\events.jsonl" --output ".\data\memory.sqlite"
python -m unittest discover -s tests
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\run_demo.ps1"
```

说明：`build-store` 生成的 SQLite 文件和 `evaluate --output` 生成的临时报告用于本地验证和演示，已通过 `.gitignore` 忽略，可按需重新生成。

## 核心指标

赛题基础指标如下，后续评测文档和测试报告会围绕这些指标展开：

- 偏好提取准确率 >= 85%
- 知识检索召回率 >= 85%
- 知识检索响应时间 <= 500ms
- 知识冲突处理正确率 >= 88%

## 近期研发重点

- 扩展正式评测数据集规模，覆盖更多自然语言表达和真实工具结果。
- 将当前规则原型升级为“规则 + 小模型/embedding + 置信度校准”的混合方案。
- 抽象银河麒麟 embedding SDK 适配层，保留离线 fallback。
- 完成可视化演示界面和真实办公场景 demo。

## 当前可验证能力

- `data/eval/office_memory_eval.json` 提供首版标注评测集。
- `evaluate` 命令输出偏好准确率、知识召回率、检索延迟、冲突准确率和遗忘准确率，并提供逐条偏好、检索、冲突、遗忘用例的命中明细。
- `evaluate --summary-only --output <path>` 支持终端轻量摘要和完整 JSON 报告落盘。
- `build-store` 命令可将内存记忆保存为本地 SQLite，支持后续演示和端侧部署验证。
- `scripts/run_demo.ps1` 可一键执行 demo、评测、报告生成、SQLite 构建和单元测试。
- `EmbeddingProvider` 抽象已就位，当前使用 `HashEmbedding` 离线 fallback，也可用 `CallableEmbeddingProvider` 或 `KylinEmbeddingProvider` 包装后续 SDK 的向量接口。
- `MemoryStore.resolve_knowledge_conflict()` 支持接受新版本、保留旧版本、保留双方、证据合并和人工确认队列等基础策略。
