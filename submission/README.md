# 技术审阅与赛事提交

状态：**已完成初版，待赛事验收**。本目录只存结构和允许列表，不存身份证件、
报名表、签字原件、真实案例原件或平台回执。
当前版本及四项反馈以 `docs/37_出题方反馈落实.md` 为准。

技术审阅材料与历史归档分别管理。既有Office、测试报告和封存ZIP保留原始字节，
不充当当前源码成绩。不要再次直接压缩整个工程文件夹，尤其不能包含`.git/`、
`dist/`、缓存、模型、密钥、私有案例和重复构建包。

## 本轮只预检

本轮不创建提交目录、不生成ZIP，等待负责人审阅后另行授权。
当前39页Word、23页PPT及摘要位于`deliverables/review-20260910-implementation/`，
当前源码证据位于`artifacts/verification/feedback/implementation-20260910/`。
在工程根目录执行：

```powershell
python -B -X utf8 -S scripts/generate_review_materials.py --check-only
python -B -X utf8 -S scripts/build_review_submission.py --preflight-only --preflight-report artifacts/runtime/review-preflight-new.json
```

该入口先核对当前材料、源码和数值，再生成
`submission/review_implementation_manifest.json`并检查允许列表及Markdown链接。
它不调用提交目录构建或归档，报告路径必须不存在；预检不能充当解包运行验收。

`review_manifest.json`、`review_followup_manifest.json`、`review_audit_manifest.json`
和通用脚本保留的默认旧清单仅用于兼容或历史重建，不是本轮最新材料入口。

## 审阅后封包边界

只有负责人明确授权后，才使用当前允许列表构建到新的输出目录并另行归档。
输出路径必须不存在，不能覆盖历史包。展示状态保持“已完成初版，待赛事验收”，逐项列出外部缺项，
保留`competition_ready=false`。`--allow-incomplete`及机器状态`incomplete_draft`
是兼容既有自动化的内部标识，不是对外标题，也不跳过完整性检查。

后续压缩包必须附逐文件SHA256、包摘要和构建报告，封存后不回写；
涉及归档自身摘要的审计必须放在ZIP外，避免自引用。解压复验作为包外审计，
核对源码摘要并实际执行测试，不只验证ZIP能打开。当前尚未执行这一封包流程。
即使以后包内测试通过，也不代表V11、
SDK、独立Judge或赛事验收通过。

## 正式材料

1. 当前项目PPT、技术报告及原始评测证据。
2. 可复现源码、测试、公开数据和许可说明。
3. 人工复核且不超过7分钟的演示视频。
4. 经授权脱敏的真实案例和真实环境验证材料。
5. 与平台一致的盖章报名表、人工确认和提交回执。

正式构建应显式指定当前清单，并分别提供真实的`--video`、`--registration-form`、
`--real-case`和`--kylin-report`，不能用合成材料补这些输入。
四类外部文件齐全时也只标为`ready_for_manual_review`，仍不是审核或邮件发送成功。
主办方对V11虚拟机部署、运行资源与评分口径已按参赛者确认获认可，原始凭证待归档。
真实SDK仍为**待复测风险项**。脚本不自动发送赛事邮件。
