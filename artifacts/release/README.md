# 发布归档说明

该目录保存由 `scripts/archive_submission.py` 生成的归档证据。

## 当前续作草案

C05C草案：`OS_Agent_第五轮_续作双环境_交付草案_INCOMPLETE.zip`。
422个内容文件，另含 `SHA256SUMS.txt`，ZIP体积1,550,493字节。
ZIP SHA256：`5b47d71af6a13e4f16c7b8aa604431225d087c761e8282b90fe422a5887123f4`。
包含C03实际视觉验收后的DOCX、C02完整UTF-8演示、新Windows/V11各166项测试及冻结逐请求原始证据。
独立解包后95项被测源码与新V11一致，113项受保护文件原始字节一致；再次通过166项测试和14项发布检查，四项质量100%、P95 92.752ms。
完整性、独立重建和隐私核对见 `artifacts/verification/round5/resume/package_integrity.json`，包内源码完整复验见 `artifacts/verification/round5/resume/package/`。Git检出核对95项源码LF摘要及155项受保护文件原始字节一致，最终扫描1,485个文本、22份Office、5个ZIP无异常，见 `artifacts/verification/round5/resume/git_index_check.json`。

## 历史封存草案

R08封存第五轮草案：`OS_Agent_第五轮_双环境_交付草案_INCOMPLETE.zip`。
338个内容文件，另含 `SHA256SUMS.txt`，ZIP体积1,112,103字节。
ZIP SHA256：`6bce17e442630fa5a3d2e45aef502f2896d8ae3ca1f91c9ce1be586526478da1`。
Windows和真实安装V11虚拟机各164项测试及冻结逐请求五项指标的原始结果已纳入包内，95个公开被测文件摘要一致。
独立解包重建、逐文件摘要、ZIP CRC和隐私审计见 `artifacts/verification/round5/package_integrity.json`；完整解包源码复验另见 `artifacts/verification/round5/package/`。

C03随后修复当前DOCX的重复页脚及独立列表编号，166项测试和11页实际视觉检查通过；该修复不在R08包内，已纳入上方C05C新包。旧ZIP保持原字节，只证明封存时版本。

前三轮ZIP均为历史证据，不改写。原 `OS_Agent_记忆优化_开发机交付草案_INCOMPLETE.zip` 是2026-09-05历史基线，不能当作本轮源码。

## 使用边界

当前归档仍是 `INCOMPLETE` 草案：最终视频、盖章报名表、授权案例、赛事部署认可和真实Agent/Judge证据尚未齐备。已有V11客户机测试和原生单探针不替代上述验收；SDK是推荐项，其完整原生质量与性能也尚未验证。

封存后的解包复验、Git检出复核和最终任务状态作为外置审计保留，不写回ZIP，避免自引用摘要。包内TODO是封存时快照，最终状态以仓库最新 `docs/29_续作任务清单.md`、`docs/33_第五轮交付复核.md` 和实际CI运行记录为准。

每次归档包含：

- `*.zip`：只读 ZIP，内部含逐文件 `SHA256SUMS.txt`；
- `*_CONTENTS_SHA256.txt`：归档内容逐文件摘要；
- `*.zip.sha256`：ZIP 本身摘要；
- `*_archive_report.json`：文件数、体积、完整性、只读状态和外部缺口。

只读属性在归档创建的本机设置，Git 克隆或复制到其他介质后可能不保留；文件内容是否一致以 SHA-256 校验为准。

校验 ZIP 摘要：

```powershell
$archive = ".\artifacts\release\OS_Agent_第五轮_续作双环境_交付草案_INCOMPLETE.zip"
$expected = (Get-Content "$archive.sha256" -Encoding UTF8).Split()[0]
$actual = (Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant()
$actual -eq $expected
```

外部材料齐全后，应重新运行打包脚本生成 `ready_for_manual_review` 暂存目录，再生成不带 `INCOMPLETE` 的新归档；不要改名冒充或覆盖本草案。
