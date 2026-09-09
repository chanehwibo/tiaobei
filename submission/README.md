# 技术审阅与赛事提交

状态：**已完成初版，待赛事验收**。本目录只存结构和允许列表，不存身份证件、
报名表、签字原件、真实案例原件或平台回执。
当前版本及四项反馈以 `docs/37_出题方反馈落实.md` 为准。

技术审阅材料与历史归档分别管理。既有Office、测试报告和封存ZIP保留原始字节，
不充当当前源码成绩。不要再次直接压缩整个工程文件夹，尤其不能包含`.git/`、
`dist/`、缓存、模型、密钥、私有案例和重复构建包。

## 构建与归档

默认清单供工程复现，含历史测试所需材料；对外技术审阅使用本次独立清单，
具体路径见反馈落实记录。构建示例：

```powershell
python scripts/build_submission.py --allow-incomplete --output dist/initial-review
python scripts/archive_submission.py `
  --staging dist/initial-review `
  --archive artifacts/release/OS_Agent_初版_待赛事验收.zip `
  --allow-incomplete
```

输出路径必须不存在。新包显示“已完成初版，待赛事验收”，逐项列出外部缺项，
保留`competition_ready=false`。`--allow-incomplete`及机器状态`incomplete_draft`
是兼容既有自动化的内部标识，不是对外标题，也不跳过完整性检查。

压缩包附逐文件SHA256、包摘要和构建报告，封存后不回写。解压复验作为包外审计，
核对源码摘要并实际执行测试，不只验证ZIP能打开。仅包内测试通过不代表V11、
SDK、独立Judge或赛事验收通过。

## 正式材料

1. 当前项目PPT、技术报告及原始评测证据。
2. 可复现源码、测试、公开数据和许可说明。
3. 人工复核且不超过7分钟的演示视频。
4. 经授权脱敏的真实案例和真实环境验证材料。
5. 与平台一致的盖章报名表、人工确认和提交回执。

```powershell
python scripts/build_submission.py `
  --output dist/manual-review `
  --video "<最终视频路径>" `
  --registration-form "<盖章报名表路径>" `
  --real-case "<授权脱敏案例证明路径>" `
  --kylin-report "<真实环境与SDK验证报告路径>"
```

四类外部文件齐全时只标为`ready_for_manual_review`，仍不是审核或邮件发送成功。
主办方对V11虚拟机部署、运行资源与评分口径已按参赛者确认获认可，原始凭证待归档。
真实SDK仍为**待复测风险项**。脚本不自动发送赛事邮件。
