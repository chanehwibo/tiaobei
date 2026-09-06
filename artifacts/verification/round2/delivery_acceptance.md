# 第二轮交付验收

已在独立打包目录 dist/round2_submission_candidate/03_源代码与说明/project 中执行：

- python -S -m unittest discover -s tests -q：86 项通过。
- python scripts/check_source.py：48 个 Python 文件满足 3.10 语法，公开文本隐私异常 0 项。
- node scripts/check_dashboard.cjs：JavaScript 语法及 DOM 目标通过。

项目 wheel 已使用本机 setuptools 成功构建，包数据包含 dashboard.html。
本机 Edge 无窗口模式已加载真实本地服务页面，确认主要卡片和数据呈现；截图为忽略目录下的开发检查产物。
HTTP 测试覆盖演示场景、恢复保留其他租户、冲突作用域、遗忘确认等流程。

PPT 为 15 页，与 Word 均从当前 evidence_summary.json 派生，内容核对包含 86 项测试及
当前 10k p99；不含旧“65 项”声明，保留质量目标尚未全部满足的说明。

归档由 build_submission.py 和 archive_submission.py 生成；ZIP 自检 CRC、逐文件 SHA256、
清单与未列入文件检查，生成只读属性和外部摘要。2026-09-05 原归档保留作历史基线。
此草案不包含真实 SDK/麒麟报告、独立盲测、授权案例、人工视频或赛事凭证，不是正式完整比赛包。

GitHub Actions 配置覆盖 Windows/Linux、Python 3.10/3.14；本文件只确认本机及独立包测试，
远端运行情况在最终发布记录中确认。
