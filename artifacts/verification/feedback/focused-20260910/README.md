# 聚焦证据策略的开发过程

本目录是2026-09-10的中间诊断，不是当前源码的最终验收。
原始JSON保留生成时的源码摘要、失败请求和耗时，不回写或覆盖。

- `diagnostic*`：聚焦问句、属性支持、数量表达及同主题章节补全的迭代诊断。
- `complex-matrix.json`、`constraints-matrix.json`：中间源码的三策略矩阵。
- `complex-nonregression.json`、`constraints-nonregression.json`：对应中间矩阵的核对。
- `constraints-unfiltered.json`：未提供显式约束时的追加检查，暴露字面主体保留问题。
- `requests-default-check.json`：默认策略切换后的冻结五项检查，不替代最终完整验收。

诊断期间的结果用于开发，不能挑选其中通过的配置称为独立测试。
最终证据见相邻的`focused-20260911/`；其中也保留中间诊断和首次失败的Windows报告，
以该目录README区分用途。本轮没有打包或生成实际提交目录。
