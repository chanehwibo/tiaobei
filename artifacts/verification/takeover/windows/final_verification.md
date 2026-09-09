# 最终本地验收报告

生成时间（UTC）：2026-09-09T08:26:14+00:00

- 本地发布检查：通过
- 赛事完整提交就绪：否
- 自动化测试：275 项，通过
- 冻结逐请求五项发布门槛：True
- 五项实测数值：{'preference_accuracy': 1.0, 'knowledge_recall': 1.0, 'conflict_accuracy': 1.0, 'retrieval_p95_ms': 67.73020001128316, 'sensitive_f1': 1.0}
- 请求分母：{'preference_accuracy': 68, 'knowledge_recall': 60, 'conflict_accuracy': 60, 'retrieval_p95_ms': 80, 'sensitive_f1': 50}；原始逐条记录见 requests.json
- 五项数值、冻结字节、固定配置、分母一致性和附加安全检查均参与退出码，不能仅凭报告布尔值通过。
- v3 test 正例 Recall@3：0.9167
- v3 test 无答案正确率：1.0000
- v3 test 平衡得分：0.9583
- 历史内部检索门槛满足：True（不是官方两个85%指标）
- 官方五项指标证据就绪：False
- 官方口径内部诊断：{'preference_accuracy': 0.4615, 'knowledge_recall': 0.9167, 'conflict_accuracy': 1.0, 'retrieval_p95_ms': 106.75329994410276, 'sensitive_f1': 1.0}
- 分母及单位：{'preference_accuracy': 13, 'knowledge_recall': 12, 'conflict_accuracy': 2, 'retrieval_p95_ms': 50, 'sensitive_f1': 50}；详见 official_diagnostics.json
- v1/v2 旧标签含单条低证据事件，门控后有目标未满足；保留原始结果，不能沿用旧版满分宣称。
- 10000 条开发机热查询 p99：208.87 ms
- 隐私扫描异常：0 项

## 本地检查项

| 检查 | 结果 |
| --- | :---: |
| `compile` | 通过 |
| `unit_tests` | 通过 |
| `source_syntax_and_privacy` | 通过 |
| `frozen_request_gate` | 通过 |
| `frozen_dataset_bytes` | 通过 |
| `source_unchanged_during_checks` | 通过 |
| `request_source_snapshot` | 通过 |
| `evaluation_protocol` | 通过 |
| `internal_quality_85` | 通过 |
| `benchmark_500ms` | 通过 |
| `service_workload_integrity` | 通过 |
| `decay_diagnostics` | 通过 |
| `action_framework` | 通过 |
| `local_preflight` | 通过 |
| `materials` | 通过 |
| `editable_materials` | 通过 |
| `privacy_scan` | 通过 |

## 仍需人工/外部完成

- X01：第三方保管标签的独立盲测、正式Agent/容器与独立Judge
- X02：主办方认可已由参赛者确认；原始凭证、适用配置、运行资源及评分版本待归档核验
- X03：经授权且匿名化的真实应用案例
- X04：不超过7分钟的最终视频复核、平台审核及盖章报名表；既有DOCX分页已验收
- X05：用户确认后的正式提交和邮件回执

> 本报告只证明当前开发机、本地 HashEmbedding 与仓库合成数据的检查结果。它不能作为真实麒麟环境、真实 SDK、独立盲测、真实用户案例或赛事流程回执。
