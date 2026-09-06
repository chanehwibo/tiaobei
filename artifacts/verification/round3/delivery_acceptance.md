# 第三轮独立交付验收

日期：2026-09-06。代码与材料基线：0e92518（Q01–Q04 已分别提交）。

- 独立候选目录：dist/round3-quality-candidate/03_源代码与说明/project。
- 独立目录 python -S 全量回归：91 项通过；v3 --require-quality：通过，正例 11/12、无答案 6/6、统一阈值 0.265。
- 独立目录 Python 3.10 语法/隐私扫描及 Node 页面脚本检查：通过。逐命令结果见 delivery_checks.json。
- 生成的 PPT/Word 数值与 evidence_summary.json 核对通过；摘要引用的原始文件 SHA-256 核对通过。
- wheel 无依赖构建成功；SHA-256：50076d354825baa0dfc470fa066228824c756d1bed0dbeba0859fe23c9a9c502。
- v3 数据和生成器相较 5a1c6b2 无 Git 差异；没有改标签、删题或缩小分母。

Q05 最终归档在独立复测后另建干净 staging，保留 INCOMPLETE 标识；归档哈希见同名 .sha256 与 archive_report.json，不在本报告中自引用。后续只补发布记录，不覆盖既有只读 ZIP。

边界：两项 85% 只针对公开合成内部回归；1 条设备借还改写仍漏召回，8 项外部验证未完成。打包工具要求的 4 类外部文件不等于验证清单的 8 项流程与证据。不得宣称真实 SDK、银河麒麟、独立盲测或赛事完整提交已通过。
