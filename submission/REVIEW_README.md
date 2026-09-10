# OS Agent 当前技术审阅材料

状态：**已完成初版，待赛事验收**。
本轮只完善工程、技术材料及允许列表预检，不创建提交目录或ZIP。
旧包不代表当前源码；待负责人审阅后另行授权打包。

## 阅读顺序

1. [四项反馈复核与验收](../docs/42_四项反馈复核与验收.md)及[落实记录](../docs/37_出题方反馈落实.md)：核对已处理动作和剩余风险。
2. [39页Word](../deliverables/review-20260910-implementation/OS_Agent_技术方案与复测报告.docx)及[23页PPT](../deliverables/review-20260910-implementation/OS_Agent_反馈落实答辩稿.pptx)：当前技术方案、相关工作、评测口径、复杂场景和实验失败。
3. [当前测试入口](../docs/测试报告.md)：Windows原始证据、两套复杂集、开发反例、历史等输出配对及SDK风险。
4. 工程根目录的`src/`、`tests/`、`data/`与`scripts/`：可运行源码、固定数据及复现工具。

未来经授权构建时，允许列表计划使用`00_阅读说明`、`01_当前技术材料`、
`02_复测证据`和`03_源代码与说明/project`四个分区；目前这些不是本轮已生成的提交目录。

## 重要边界

- 当前材料使用本次源码的Windows结果：350项测试无失败、跳过1项，17项工程检查通过；
  冻结五项的80查询P95为40.762ms。V11当前版服务部署待独立复验。
- 真实SDK为**待复测风险项**：旧ABI单次13,390.615ms，不是P95，不以HashEmbedding代替。
- 原120请求、1万条/75%相似填充：正例Recall@3为94.44%，三轮P95为39.971/38.730/39.301ms，
  近主题无答案正确率仅4.17%。67.755ms至39.023ms是历史等输出配对，不能冒充当前成绩。
- 新48请求同规模/干扰：约束关闭/开启首轮P95为67.599/29.279ms，Recall@3为91.67%/95.83%，
  无答案正确率为16.67%/66.67%。开启后的后两轮P95为74.901/111.129ms，
  反而慢于关闭约束的52.884/51.216ms，不能宣称稳定加速；关系缺证据和多文档召回仍有风险。
- 正文证据实验增加拒答但损害召回，追加开发反例仅召回0/6；默认仍为`similarity`，
  不推荐业务启用`content_coverage_v1`。30个开发请求不是独立盲测，不与复杂集分母合并。
- 相关工作仅比较机制及适用范围，不声称复现论文或取得创新性/可信度分数。
- 公开合成数据不能替代授权真实案例、第三方保管标签或真实Agent/Judge。
- 主办方部署、资源和评分认可按参赛者确认记录，原件仍需归档。
- 源码中的历史报告、旧Office和兼容脚本是追溯及测试依赖，不代表当前交付状态。
  原始失败和旧证据不改写，计划公开分区不再混放旧版PPT或旧成绩表。
- Word/PPT已用实际WPS渲染并逐页检查，报告另存；Word保留少量短尾页及续表分页，
  无观察到的裁切或遮挡。Agent视觉检查不替代负责人审阅。
- 预检保持`competition_ready=false`并列出外部缺项；不自动提交或发送邮件。

## 工程复现与只预检

在当前工程根目录执行，Python 3.10及以上，无需安装核心依赖。
未来授权封包后才使用`03_源代码与说明/project`作为解包工作目录：

```powershell
python -X utf8 -S -m unittest discover -s tests -v
python -X utf8 -S scripts/check_source.py
python -X utf8 -S scripts/evaluate_requests.py --size 10000 --require-frozen --output artifacts/runtime/review-requests.json
python -X utf8 -S scripts/generate_review_materials.py --check-only
python -B -X utf8 -S scripts/build_review_submission.py --preflight-only --preflight-report artifacts/runtime/review-preflight-new.json
```

复杂数据复测、约束开关、正文证据实验及历史配对命令见第40/41/44号报告。
本轮材料目录为`deliverables/review-20260910-implementation/`，允许列表为
`submission/review_implementation_manifest.json`，原始证据位于
`artifacts/verification/feedback/implementation-20260910/`。
`review_manifest.json`、`review_followup_manifest.json`和`review_audit_manifest.json`仅对应历史版本。
Office重新生成需要可选的`python-docx`和`python-pptx`，不会覆盖已存在的输出。
只预检报告也拒绝覆盖；当前没有本轮ZIP摘要、独立解包结果或赛事验收回执。
