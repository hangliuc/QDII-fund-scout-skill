from __future__ import annotations

import csv
from pathlib import Path

from core.models import FundDataResult

FIELD_CN = {
    "code": "基金代码",
    "name": "基金名称",
    "short_name": "简称",
    "type": "基金类型",
    "benchmark": "业绩基准",
    "nav": "最新净值",
    "nav_date": "净值日期",
    "scale": "规模(亿)",
    "mgmt_fee": "管理费率",
    "custody_fee": "托管费率",
    "service_fee": "销售服务费",
    "total_fee": "总费率",
    "return_1w": "近1周收益",
    "return_1m": "近1月收益",
    "return_3m": "近3月收益",
    "return_6m": "近6月收益",
    "return_1y": "近1年收益",
    "return_3y": "近3年收益",
    "return_ytd": "年初至今收益",
    "return_since_inception": "成立以来收益",
    "purchase_status": "申购状态",
    "purchase_limit": "限购额度",
    "effectively_closed": "实质暂停",
    "drawdown_1y": "近1年回撤",
    "risk_level": "风险等级",
    "manager_name": "基金经理",
    "manager_avatar": "经理头像",
    "manager_tenure": "任职年限",
    "manager_return": "任职回报",
    "top10_holdings": "前十大持仓",
    "market_distribution": "市场分布",
    "company": "基金公司",
    "found_date": "成立日期",
    "tracking_error": "跟踪误差",
}

PERCENT_FIELDS = {
    "mgmt_fee", "custody_fee", "service_fee", "total_fee",
    "return_1w", "return_1m", "return_3m", "return_6m",
    "return_1y", "return_3y", "return_ytd", "return_since_inception",
    "drawdown_1y", "manager_return", "tracking_error",
}

SKIP_FIELDS = {"top10_holdings", "market_distribution", "manager_avatar", "_purchase_info"}


def _format_value(key: str, value) -> str:
    if value is None:
        return ""
    if key in PERCENT_FIELDS and isinstance(value, (int, float)):
        return f"{value}%"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    if isinstance(value, dict):
        return "; ".join(f"{k}:{v}" for k, v in value.items())
    return str(value)


def format(data: FundDataResult, output_path: str, fields: list[str] | None = None) -> str:
    all_keys = []
    for fund in data.funds:
        d = fund.to_dict()
        for k, v in d.items():
            if k in SKIP_FIELDS:
                continue
            if v is not None and v != "" and v != [] and v != {}:
                if k not in all_keys:
                    all_keys.append(k)

    if fields:
        selected = [f for f in fields if f in all_keys]
    else:
        selected = all_keys

    cn_row = [FIELD_CN.get(f, f) for f in selected]
    en_row = selected

    rows = []
    for fund in data.funds:
        d = fund.to_dict()
        rows.append([_format_value(f, d.get(f)) for f in selected])

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(cn_row)
        writer.writerow(en_row)
        writer.writerows(rows)

    return str(path)
