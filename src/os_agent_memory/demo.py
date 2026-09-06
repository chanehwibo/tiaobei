"""Synthetic scenarios confined to a reserved local demonstration tenant."""
DEMO_TENANT = "local-demo"
DEMO_USER = "presenter"


def scenario_records(name):
    scenarios = {
        "baseline": [("输出偏好", "输出请使用中文，保持简洁，用表格展示结果。"),
                     ("报销流程模板", "报销流程模板：先核验票据和金额，再提交审批，最后归档。")],
        "preference": [("输出偏好", "用户新的偏好：需要详细说明并给出原因，用表格展示结果。")],
        "conflict": [("外设规则", "外设安全流程允许使用未登记移动介质，使用后保存审计记录。"),
                     ("外设规则更新", "外设安全流程禁止使用未登记移动介质，使用后保存审计记录。")],
    }
    if name not in scenarios:
        raise ValueError("unknown demonstration scenario")
    return [{
        "id": f"demo-{name}-{i}", "tenant_id": DEMO_TENANT, "user_id": DEMO_USER,
        "source_type": "manual_config", "scene": "office",
        "timestamp": f"2026-01-0{2 if name == 'preference' else 1}T0{i}:00:00+00:00",
        "content": content, "metadata": {"title": title},
    } for i, (title, content) in enumerate(scenarios[name])]
