"""Internal, hand-authored topic/template split; never an independent blind test."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Each split uses different topics, procedural forms and query formulations.
CASES = {
    "train": [
        ("票据验真", "票据验真流程：扫描发票二维码，匹配税号，异常票据转人工审核。", "发票二维码税号如何校验", "票据验真流程", "火星岩石成分"),
        ("会议预约", "会议预约步骤：选择空闲会议室，发送日历邀请，参会人确认后锁定时段。", "空闲会议室日历邀请", "会议预约步骤", "会议室装修预算"),
        ("字体配置", "字体配置模板：正文使用宋体，标题采用黑体，保存为公文样式。", "正文宋体标题黑体样式", "字体配置模板", "字体版权采购价格"),
        ("文件归档", "文件归档流程：依据年度分类，计算文件校验值，复制到归档磁盘。", "年度分类校验值归档", "文件归档流程", "归档设备市场售价"),
        ("密码轮换", "密码轮换步骤：验证旧凭据，生成独立口令，注销旧登录会话。", "旧凭据独立口令注销", "密码轮换步骤", "密码管理器排行榜"),
        ("客户答复", "客户答复模板：明确问题编号，列出解决进展，约定下一次反馈日期。", "问题编号解决进展反馈", "客户答复模板", "客户股票投资建议"),
    ],
    "dev": [
        ("差旅预借", "办理差旅预借需要行程单和预算明细。流程在财务核准额度后安排付款。", "预借款要带哪些行程预算材料", "差旅预借财务付款流程", "差旅报销汇率预测"),
        ("访客登记", "访客登记流程要求前台核实预约单位；临时通行证当天离场时交还。", "来访人员通行证何时交还", "访客登记离场通行证", "访客酒店住宿折扣"),
        ("印章申请", "印章申请步骤由经办人登记文件份数，部门负责人签字后交印章保管员操作。", "盖章文件份数负责人签字", "印章申请保管员操作步骤", "印章雕刻店铺地址"),
        ("备份恢复", "备份恢复流程以最近通过完整性检查的快照为准，恢复后抽查目录和文件大小。", "快照完整性通过后如何还原", "备份恢复抽查目录大小", "备份云服务优惠码"),
        ("补丁验证", "补丁验证流程仅在测试终端执行。重启两次且应用自检通过后才纳入发布候选。", "测试终端重启应用自检", "补丁验证发布候选流程", "补丁漏洞利用代码"),
        ("合同续期", "合同续期模板记录原合同编号、服务变更和续期起止日，双方确认后留存副本。", "延长合同需要登记哪些日期", "合同续期服务变更副本", "合同律师联系方式"),
    ],
    "test": [
        ("设备借还", "设备借还流程设借出与归还两张清单：借出登记资产编号，归还核验配件是否齐全。", "借出的电脑归还时检查什么", "设备借还资产编号配件清单", "设备二手交易行情"),
        ("培训签到", "培训签到流程采用名单核销。迟到人员补填到场时间，结束后导出实际出勤名单。", "培训迟到如何补填到场", "培训签到实际出勤导出", "培训讲师出场费用"),
        ("版本发布", "版本发布流程分审批与执行两个阶段。审批记录构建摘要，执行完成记录回退版本号。", "上线后要记录哪个回退编号", "版本发布审批构建摘要", "版本产品商业定价"),
        ("打印审计", "打印审计流程记录作业页数及终端编号；涉密作业由登记人员领取并签收。", "涉密打印作业如何领取签收", "打印审计页数终端编号", "打印机墨盒购物优惠"),
        ("离职交接", "离职交接流程的验收条件为资料移交、账号关闭与资产清点均已确认，缺项退回补办。", "员工离开前账号资料资产怎样验收", "离职交接缺项退回流程", "离职劳动赔偿判决"),
        ("工单升级", "工单升级流程规定响应超时转二线支持；升级单附故障时间线和已执行诊断结果。", "超时工单转二线要附什么", "工单升级故障时间线诊断", "工单软件行业排名"),
    ],
}


def generate():
    records, queries, labels = [], [], []
    for split, cases in CASES.items():
        for index, (title, content, question, keyword_query, missing) in enumerate(cases):
            # Repeated evidence has distinct times; it is not a replay of the same event.
            for occurrence in range(2):
                records.append({
                    "id": f"{split}-{index}-{occurrence}", "split": split,
                    "template_family": f"{split}-procedure-{index}",
                    "tenant_id": f"v3-{split}", "user_id": "operator",
                    "source_type": "tool_result", "tool_status": "succeeded",
                    "scene": "office", "authority": 0.8,
                    "timestamp": f"2026-01-01T0{occurrence}:0{index}:00+00:00",
                    "content": content, "metadata": {"title": title, "topic": title},
                })
            for kind, query, expected in (
                ("paraphrase", question, [title]), ("keyword", keyword_query, [title]),
                ("unanswerable", missing, []),
            ):
                queries.append({
                    "id": f"{split}-{index}-{kind}", "split": split, "query": query,
                    "tenant_id": f"v3-{split}", "user_id": "operator",
                    "expected_titles": expected, "expected_empty": not expected,
                    "difficulty": kind,
                })
        preference = {
            "train": "偏好设置：请用中文输出，保持简洁，输出格式用表格。",
            "dev": "我的输出偏好为简体中文，结果保持简洁，并用表格显示。",
            "test": "输出请使用中文并保持简洁；我选择用表格呈现结果。",
        }[split]
        records.append({
            "id": f"{split}-preference", "split": split, "template_family": f"{split}-preference",
            "tenant_id": f"v3-{split}", "user_id": "operator", "source_type": "manual_config",
            "timestamp": "2026-01-02T00:00:00+00:00", "scene": "office",
            "content": preference, "metadata": {"title": "偏好"},
        })
        for key, value in (("output.language", "zh-CN"), ("output.verbosity", "brief"), ("output.format", "table")):
            labels.append({"split": split, "tenant_id": f"v3-{split}", "user_id": "operator", "key": key, "value": value})
        # Scope distractor: similar terminology but not accessible to this user.
        records.append({
            "id": f"{split}-private", "split": split, "template_family": f"{split}-private",
            "tenant_id": f"v3-{split}", "user_id": "someone-else", "source_type": "manual_config",
            "timestamp": "2026-01-02T00:00:00+00:00", "scene": "office",
            "content": cases[0][1] + f" 私有补充：{cases[-1][0]}由专人处理。",
            "metadata": {"title": f"{cases[0][0]}私有补充"},
        })
    return {
        "name": "office_memory_eval_v3", "provenance": {"type": "synthetic", "independent_blind": False},
        "split_policy": "Different topics, authored text and template families per split; labels public.",
        "records": records, "retrieval_queries": queries, "preference_labels": labels,
        "conflict_cases": [], "forget_cases": [],
        "targets": {"knowledge_recall_at_k": {"min": 0.85}, "forget_misdelete_rate": {"max": 0}},
        "limitations": ["42 input events, 18 topics, 54 queries only; not statistical proof of generalization.",
                        "Conflict/forget adversarial behavior is evaluated separately, not as empty-case accuracy."],
    }


def audit_splits(suite):
    report = {}
    for left, right in (("train", "dev"), ("train", "test"), ("dev", "test")):
        rows = [[r for r in suite["records"] if r["split"] == split] for split in (left, right)]
        report[f"{left}/{right}"] = {
            "shared_content": len({r["content"] for r in rows[0]} & {r["content"] for r in rows[1]}),
            "shared_template_families": len({r["template_family"] for r in rows[0]} & {r["template_family"] for r in rows[1]}),
        }
    return report


if __name__ == "__main__":
    suite = generate()
    suite["split_audit"] = audit_splits(suite)
    target = ROOT / "data/eval/office_memory_eval_v3.json"
    target.write_text(json.dumps(suite, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(suite["split_audit"]))
