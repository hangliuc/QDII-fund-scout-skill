from __future__ import annotations

from pathlib import Path
from typing import Any

from core.models import FundDataResult, DISCLAIMER

FIELD_CN = {
    "code": "基金代码",
    "name": "基金名称",
    "short_name": "简称",
    "type": "基金类型",
    "nav": "最新净值",
    "nav_date": "净值日期",
    "scale": "规模(亿)",
    "total_fee": "总费率",
    "return_1w": "近1周",
    "return_1m": "近1月",
    "return_3m": "近3月",
    "return_6m": "近6月",
    "return_1y": "近1年",
    "return_3y": "近3年",
    "return_ytd": "年初至今",
    "return_since_inception": "成立以来",
    "purchase_status": "申购状态",
    "purchase_limit": "限购额度",
    "effectively_closed": "实质暂停",
    "drawdown_1y": "近1年回撤",
    "risk_level": "风险等级",
    "manager_name": "基金经理",
    "manager_tenure": "任职年限",
    "company": "基金公司",
    "found_date": "成立日期",
}

PERCENT_FIELDS = {
    "total_fee", "return_1w", "return_1m", "return_3m", "return_6m",
    "return_1y", "return_3y", "return_ytd", "return_since_inception",
    "drawdown_1y", "manager_return",
}

TABLE_FIELDS = [
    "code", "name", "return_1y", "total_fee", "scale",
    "purchase_status", "purchase_limit", "effectively_closed",
    "drawdown_1y", "risk_level", "manager_name",
]


def _fmt_val(key: str, value: Any) -> str:
    if value is None:
        return "-"
    if key in PERCENT_FIELDS and isinstance(value, (int, float)):
        return f"{value}%"
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)


def _fmt_table(data: FundDataResult) -> str:
    lines = []
    header = [FIELD_CN.get(f, f) for f in TABLE_FIELDS]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---"] * len(TABLE_FIELDS)) + " |")
    for fund in data.funds:
        d = fund.to_dict()
        row = [_fmt_val(f, d.get(f)) for f in TABLE_FIELDS]
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _fmt_card(data: FundDataResult) -> str:
    blocks = []
    for fund in data.funds:
        d = fund.to_dict()
        lines = [f"### {d.get('name', '-')}（{d.get('code', '-')}）", ""]
        card_fields = [
            ("type", "类型"), ("return_1y", "近1年收益"), ("return_ytd", "年初至今"),
            ("total_fee", "总费率"), ("scale", "规模(亿)"), ("drawdown_1y", "近1年回撤"),
            ("purchase_status", "申购状态"), ("purchase_limit", "限购额度"),
            ("effectively_closed", "实质暂停"), ("risk_level", "风险等级"),
            ("manager_name", "基金经理"), ("manager_tenure", "任职年限"),
            ("company", "基金公司"), ("found_date", "成立日期"),
        ]
        for key, label in card_fields:
            v = d.get(key)
            if v is not None and v != "" and v != False:
                lines.append(f"- **{label}**: {_fmt_val(key, v)}")
        lines.append("")
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


def _fmt_summary(data: FundDataResult) -> str:
    funds = data.funds
    if not funds:
        return "无基金数据。"

    lines = [f"## 数据速读（共 {len(funds)} 只基金）", ""]

    return_vals = []
    fee_vals = []
    scale_vals = []
    limit_funds = []

    for fund in funds:
        d = fund.to_dict()
        r1y = d.get("return_1y")
        if r1y is not None and r1y != "":
            try:
                rv = float(str(r1y).replace("%", ""))
                return_vals.append((rv, d["name"], d["code"]))
            except (ValueError, TypeError):
                pass
        tf = d.get("total_fee")
        if tf is not None and tf != "" and tf != 0:
            try:
                fv = float(str(tf).replace("%", ""))
                fee_vals.append((fv, d["name"], d["code"]))
            except (ValueError, TypeError):
                pass
        sc = d.get("scale")
        if sc is not None and sc != "":
            try:
                sv = float(str(sc).replace("亿", ""))
                scale_vals.append((sv, d["name"], d["code"]))
            except (ValueError, TypeError):
                pass
        pl = d.get("purchase_limit")
        if pl and pl not in ("", "不限", "无限制"):
            limit_funds.append((pl, d["name"], d["code"]))

    if return_vals:
        sorted_r = sorted(return_vals, key=lambda x: x[0], reverse=True)
        lines.append("**收益 Top3**")
        for i, (v, n, c) in enumerate(sorted_r[:3], 1):
            lines.append(f"{i}. {n}（{c}）：{v}%")
        avg_r = sum(v for v, _, _ in return_vals) / len(return_vals)
        max_r = sorted_r[0]
        min_r = sorted_r[-1]
        lines.append(f"- 均值：{avg_r:.2f}% | 极值：最高 {max_r[0]}%（{max_r[1]}），最低 {min_r[0]}%（{min_r[1]}）")
        lines.append("")

    if fee_vals:
        sorted_f = sorted(fee_vals, key=lambda x: x[0])
        lines.append("**费率最低 Top3**")
        for i, (v, n, c) in enumerate(sorted_f[:3], 1):
            lines.append(f"{i}. {n}（{c}）：{v}%")
        avg_f = sum(v for v, _, _ in fee_vals) / len(fee_vals)
        lines.append(f"- 均值：{avg_f:.2f}%")
        lines.append("")

    if scale_vals:
        sorted_s = sorted(scale_vals, key=lambda x: x[0], reverse=True)
        lines.append("**规模 Top3**")
        for i, (v, n, c) in enumerate(sorted_s[:3], 1):
            lines.append(f"{i}. {n}（{c}）：{v}亿")
        avg_s = sum(v for v, _, _ in scale_vals) / len(scale_vals)
        lines.append(f"- 均值：{avg_s:.2f}亿")
        lines.append("")

    lines.append("**极值标注**")
    if return_vals:
        best = max(return_vals, key=lambda x: x[0])
        lines.append(f"- 🏆 收益最高：{best[1]}（{best[2]}）{best[0]}%")
    if fee_vals:
        cheapest = min(fee_vals, key=lambda x: x[0])
        lines.append(f"- 💰 费率最低：{cheapest[1]}（{cheapest[2]}）{cheapest[0]}%")
    if limit_funds:
        strictest = min(limit_funds, key=lambda x: x[0])
        lines.append(f"- 🔒 限购最严：{strictest[1]}（{strictest[2]}）{strictest[0]}")
    if scale_vals:
        largest = max(scale_vals, key=lambda x: x[0])
        lines.append(f"- 📊 规模最大：{largest[1]}（{largest[2]}）{largest[0]}亿")
    lines.append("")

    return "\n".join(lines)


def format(data: FundDataResult, output_path: str, style: str = "table") -> str:
    if style == "table":
        body = _fmt_table(data)
    elif style == "card":
        body = _fmt_card(data)
    elif style == "summary":
        body = _fmt_summary(data)
    else:
        raise ValueError(f"Unknown style: {style}, expected 'table', 'card', or 'summary'")

    content = f"# 基金数据报告（{data.update_date}）\n\n{body}\n\n---\n\n*{DISCLAIMER}*\n"

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)
