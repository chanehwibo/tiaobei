# OS Agent 当前技术审阅包

状态：**已完成初版，待赛事验收**。

## 阅读顺序

1. `00_阅读说明`：先读《四项反馈复核与验收》，再读落实记录；核对已处理事项和仍有风险的指标。
2. `01_当前技术材料`：29页DOCX、18页PPT、正文、相关工作、评测口径及两套复杂场景报告；复核包另含2025—2026年相关工作补充。
3. `02_复测证据`：本次Windows、当前复杂集及约束对照、分开的历史配对、SDK风险和来源。
4. `03_源代码与说明/project`：可解包运行的源码、测试、固定数据及历史测试依赖。

## 重要边界

- 当前材料使用本次源码的Windows结果：327项测试无失败、跳过1项，17项工程检查通过；
  冻结五项的80查询P95为41.485ms。V11当前版服务部署待独立复验。
- 真实SDK为**待复测风险项**：旧ABI单次13,390.615ms，不是P95，不以HashEmbedding代替。
- 原120请求、1万条/75%相似填充：正例Recall@3为94.44%，当前P95为38.248ms，
  近主题无答案正确率仅4.17%。67.755ms至39.023ms是历史等输出配对，不能冒充当前成绩。
- 新48请求同规模/干扰：约束关闭/开启P95为41.244/16.795ms，Recall@3为91.67%/95.83%，
  无答案正确率为16.67%/66.67%；关系缺证据和多文档漏召回仍有风险。
- 相关工作仅比较机制及适用范围，不声称复现论文或取得创新性/可信度分数。
- 公开合成数据不能替代授权真实案例、第三方保管标签或真实Agent/Judge。
- 主办方部署、资源和评分认可按参赛者确认记录，原件仍需归档。
- 源码中的历史报告、旧Office和兼容脚本是追溯及测试依赖，不代表当前交付状态。
  原始失败和旧证据不改写，外层不再混放旧版PPT或旧成绩表。
- `PACKAGE_STATUS.md`列出仍需的外部材料；本包不是最终赛事提交，也不自动发送邮件。

## 解包复现

进入`03_源代码与说明/project`，Python 3.10及以上，无需安装核心依赖：

```powershell
python -X utf8 -S -m unittest discover -s tests -v
python -X utf8 -S scripts/check_source.py
python -X utf8 -S scripts/evaluate_requests.py --size 10000 --require-frozen --output artifacts/runtime/review-requests.json
python -X utf8 -S scripts/generate_review_materials.py --check-only
```

复杂数据的当前复测、约束开关及历史配对命令、固定参数、分母和局限见两份复杂场景报告。
本轮材料目录为`deliverables/review-20260910-followup/`，允许列表为
`submission/review_followup_manifest.json`；四项意见复核扩展清单为`submission/review_audit_manifest.json`，
旧`review_manifest.json`只对应历史审阅包。扩展包保留已核验Office原始字节，新增补充文档及复核证据。
Office重新生成需要可选的`python-docx`和`python-pptx`，不会覆盖已存在的输出。
所有成员可用根目录`SHA256SUMS.txt`核对，ZIP本身另有`.sha256`伴随文件。
