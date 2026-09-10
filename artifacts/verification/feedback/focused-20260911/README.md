# 复杂拒答与完整召回的最终回归证据

状态：**已完成初版，待赛事验收**。这些是Windows开发机、HashEmbedding256的公开合成回归，
不是独立盲测、真实Agent回答正确率、原生SDK或赛事验收。真实SDK仍为**待复测风险项**。

## 正式读取入口

| 原始测量 | 重算与不退化检查 | 用途 |
| --- | --- | --- |
| `complex-policies.json` | `complex-policy-comparison.json` | 原120请求，三策略、四组规模/干扰、各三轮 |
| `constraints-policies-enforce.json` | `constraints-comparison-enforce.json` | 48请求，显式约束开启，同样的完整矩阵 |
| `constraints-policies-none.json` | `constraints-comparison-none.json` | 同48请求，显式约束关闭，单独报告 |
| `development-final.json` | 逐请求结果及汇总 | 原20个开发请求，10个正例、10个无答案 |
| `development-challenge-final.json` | 逐请求结果及汇总 | 10个追加开发反例，6个正例、4个无答案 |
| `windows-final/final_verification.json` | `windows-final/requests.json`等同目录文件 | 当前完整源码的最终Windows验收 |

三个比较器的七项门禁全部通过。`focused_evidence_v2`在每组规模、干扰和每轮中均找齐全部
正例证据，正确拒答全部无答案请求；多文档、作用域、异常检查全部通过。
配对计数1,440/576/576是重复运行的比较数，仍只有120/48个不同请求。
三策略测量文件的总`all_targets_met=false`来自保留的旧对照策略失败，
不是新策略失败；候选结论须读取逐策略门禁和比较器的`optimization_gates_passed`。

Windows最终报告运行392项测试，无失败、1项平台条件跳过，17项工程检查通过。
冻结四项质量均为100%，80个查询P95为48.145ms，固定分母68/60/60/80/50不变。
`competition_submission_ready=false`、`competition_ready=false`保持。

## 版本与计时

最终检索实现见提交`68fdf1f`；之后`dae9257`只修复隐私扫描的数值误报及相应测试，
没有改变检索源码或复杂评测器。三份矩阵与当前检索源码/评测器的SHA256核对一致；
开发`*-final.json`和Windows最终报告绑定`dae9257`的完整被测源码快照。
Markdown、证据说明及允许列表不在执行源码摘要范围内，不替代逐文件核验。

性能矩阵串行测量，固定`PYTHONHASHSEED=0`、top_k=3、min_score=0.265和0.5覆盖规则。
1万条/75%相似填充的新策略P95（ms）：

- 原120请求：67.605 / 66.067 / 66.724；同源旧默认为39.399 / 39.311 / 38.950。
- 48请求、显式约束开启：16.150 / 15.600 / 15.456。
- 48请求、显式约束关闭：16.447 / 15.452 / 15.696。

新策略增加了证据检查和章节补全，不能宣称所有配置加速。所有候选配置的P95仍<=500ms。
原集正例返回中仍有39/123个干扰片段，约束集为9/39；完整召回不等于零干扰或最终答案正确。
旧`content_coverage_v1`继续保留为非默认对照，新默认不是简单打开旧实验。

## 必须保留的历史与失败

- `diagnostic-constraints01.json`、`diagnostic-constraints02.json`：主体保留的中间诊断。
- `development.json`、`development-challenge.json`：隐私扫描修复前的开发测量；
  不将其完整源码摘要说成最终快照。
- `requests.json`：独立冻结五项检查；最终汇总使用`windows-final/requests.json`。
- `windows/`：首次完整验收，运行389项测试、无失败、1项平台跳过；
  隐私扫描误将诊断中的17处浮点耗时识别成证件号，因此总门禁失败。
  修复仅识别明确JSON数值字段、float类型及[0,1]范围，未放行字符串、整数、任意字段、
  重复字段或其他秘密类型；原始失败报告和诊断均保留。
- 相邻`focused-20260910/`：更早的中间矩阵与诊断，不是最终成绩。

输出采用新文件名，未改原始数据、标签、阈值、失败分母或旧测量字节。
这是看到公开失败后进行的回归修复，不证明未知领域泛化；没有创建ZIP、提交目录或新的Office。
