# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from typing import Any

import requests

from adapters import BaseAdapter, register
from core.models import FundDataResult, DISCLAIMER


class WechatAdapter(BaseAdapter):
    name = "wechat"
    required_config = ["webhook_url"]

    def __init__(self, webhook_url: str = ""):
        self.webhook_url = webhook_url or os.environ.get("WECHAT_WEBHOOK_URL", "")

    def send(self, data: FundDataResult, fmt: str = "markdown", **kwargs) -> bool:
        if not self.webhook_url:
            print("[wechat] webhook_url 未配置")
            return False
        if fmt == "markdown" or fmt == "card":
            payload = self._build_markdown(data)
        elif fmt == "text":
            payload = self._build_text(data)
        elif fmt == "image":
            print("[wechat] image 格式暂不支持")
            return False
        else:
            payload = self._build_markdown(data)
        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            result = resp.json()
            return result.get("errcode", -1) == 0
        except Exception as e:
            print(f"[wechat] 发送失败: {e}")
            return False

    def test_connection(self) -> bool:
        if not self.webhook_url:
            return False
        payload = {
            "msg_type": "markdown",
            "markdown": {"content": "### 🔔 QDII-fund-scout 连接测试\n> 企业微信适配器连接成功 ✅"},
        }
        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            result = resp.json()
            return result.get("errcode", -1) == 0
        except Exception as e:
            print(f"[wechat] 连接测试失败: {e}")
            return False

    def _build_markdown(self, data: FundDataResult) -> dict[str, Any]:
        lines = []
        lines.append(f"### 📊 QDII 基金日报")
        lines.append(f"> 📅 <font color=\"info\">{data.update_date}</font>  ·  共 {data.count} 只基金")
        lines.append("")

        lines.append("| 基金 | 申购 | 近1年 | 限额 |")
        lines.append("|:-----|:----:|:-----:|:----:|")

        for fund in data.funds:
            name = fund.short_name or fund.name or "-"
            if len(name) > 8:
                name = name[:8]

            if fund.purchase_status == "开放":
                status = "开放"
            elif fund.purchase_status == "限大额":
                status = "限大额"
            elif fund.purchase_status == "限小额":
                status = "限小额"
            elif fund.purchase_status == "暂停":
                status = "暂停"
            else:
                status = fund.purchase_status or "-"

            r1y = self._fmt_return(fund.return_1y)
            limit = fund.purchase_limit or "-"
            if not fund.purchase_limit or fund.purchase_limit in ("无限制", ""):
                limit = "-"

            lines.append(f"| {name}({fund.code}) | {status} | {r1y} | {limit} |")

        lines.append("")

        if data._warnings:
            for w in data._warnings:
                lines.append(f"> ⚠️ {w}")
            lines.append("")

        lines.append(f"> <font color=\"comment\">{DISCLAIMER}</font>")

        return {
            "msg_type": "markdown",
            "markdown": {"content": "\n".join(lines)},
        }

    def _build_text(self, data: FundDataResult) -> dict[str, Any]:
        lines = [f"📊 QDII 基金数据日报 {data.update_date}", ""]
        for fund in data.funds:
            name = fund.short_name or fund.name
            r1y = self._fmt_return(fund.return_1y)
            status = fund.purchase_status
            lines.append(f"  {fund.code} {name}")
            lines.append(f"    净值:{fund.nav:.4f if fund.nav else '-'} 年:{r1y} 申购:{status}")
        if data._warnings:
            lines.append("")
            for w in data._warnings:
                lines.append(f"⚠️ {w}")
        lines.append("")
        lines.append(DISCLAIMER)
        return {
            "msg_type": "text",
            "text": {"content": "\n".join(lines)},
        }

    @staticmethod
    def _to_float(val) -> float | None:
        if val is None:
            return None
        try:
            return float(str(val).replace("%", "").replace(",", "").strip()) or None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _fmt_return(val, invert: bool = False) -> str:
        v = WechatAdapter._to_float(val)
        if v is None:
            return "-"
        sign = "+" if v > 0 else ""
        return f"{sign}{v:.2f}%"


register(WechatAdapter.name, WechatAdapter)
