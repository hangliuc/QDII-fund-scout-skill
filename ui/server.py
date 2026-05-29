#!/usr/bin/env python3
"""QDII-fund-scout 本地 Web UI 后端服务"""

from __future__ import annotations

import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
CONFIG_DIR = os.path.expanduser("~/.fund-scout")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

sys.path.insert(0, SCRIPTS_DIR)

PORT = int(os.environ.get("FUND_UI_PORT", "8765"))


def _load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        return {"my_funds": [], "push": {"feishu_webhook": "", "wechat_webhook": ""}, "defaults": {}}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_config(cfg: dict) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _run_query(codes: list[str]) -> dict:
    from core.fetcher import FundFetcher
    fetcher = FundFetcher(rate_limit=0.3)
    result = fetcher.compare(codes=codes, cross_validate=True)

    rows = []
    for fund in result.funds:
        name = fund.short_name or fund.name or "-"
        cross_info = ""
        if fund._cross_validation:
            fields = ", ".join(d["field"] for d in fund._cross_validation)
            cross_info = f"\u26a0 {fields}\u6570\u636e\u5b58\u7591"
        elif fund._cross_resolved:
            fields = ", ".join(d["field"] for d in fund._cross_resolved)
            cross_info = f"\u2139 {fields}\u5df2\u6821\u9a8c"

        row = {
            "code": fund.code,
            "name": name,
            "nav": fund.nav,
            "nav_date": fund.nav_date,
            "return_1y": fund.return_1y,
            "return_3y": fund.return_3y,
            "purchase_status": fund.purchase_status,
            "purchase_limit": fund.purchase_limit or "-",
            "effectively_closed": fund.effectively_closed,
            "total_fee": fund.total_fee,
            "scale": fund.scale,
            "drawdown_1y": fund.drawdown_1y,
            "manager_name": fund.manager_name,
            "cross_info": cross_info,
        }
        rows.append(row)

    warnings = []
    if result._warnings:
        warnings = result._warnings

    return {"funds": rows, "warnings": warnings, "update_date": result.update_date, "count": result.count}


def _test_webhook(webhook_type: str, url: str) -> dict:
    try:
        if webhook_type == "feishu":
            from adapters.feishu import FeishuAdapter
            a = FeishuAdapter(webhook_url=url)
            ok = a.test_connection()
        elif webhook_type == "wechat":
            from adapters.wechat import WechatAdapter
            a = WechatAdapter(webhook_url=url)
            ok = a.test_connection()
        else:
            return {"ok": False, "error": f"\u672a\u77e5\u7c7b\u578b: {webhook_type}"}
        return {"ok": ok, "error": "" if ok else "\u8fde\u63a5\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u5730\u5740"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


class _Handler(BaseHTTPRequestHandler):

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path == "/":
            self._serve_index()
        elif path == "/api/config":
            self._send_json(_load_config())
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        body = self._read_body()

        if path == "/api/config":
            cfg = _load_config()
            if "my_funds" in body:
                cfg["my_funds"] = body["my_funds"]
            if "push" in body:
                push = cfg.setdefault("push", {})
                for k in ("feishu_webhook", "wechat_webhook"):
                    if k in body["push"]:
                        push[k] = body["push"][k]
            _save_config(cfg)
            self._send_json({"ok": True, "config": cfg})

        elif path == "/api/query":
            codes = body.get("codes", [])
            if not codes:
                cfg = _load_config()
                codes = [f["code"] for f in cfg.get("my_funds", []) if f.get("code")]
            if not codes:
                self._send_json({"error": "\u8bf7\u5148\u6dfb\u52a0\u57fa\u91d1\u4ee3\u7801", "funds": [], "warnings": ["\u672a\u914d\u7f6e\u57fa\u91d1\u5217\u8868"]})
                return
            try:
                result = _run_query(codes)
                self._send_json(result)
            except Exception as e:
                self._send_json({"error": str(e), "funds": [], "warnings": [f"\u67e5\u8be2\u5931\u8d25: {e}"]})

        elif path == "/api/test-webhook":
            result = _test_webhook(body.get("type", ""), body.get("url", ""))
            self._send_json(result)

        elif path == "/api/push":
            target = body.get("target", "")
            codes = body.get("codes", [])
            if not codes:
                cfg = _load_config()
                codes = [f["code"] for f in cfg.get("my_funds", []) if f.get("code")]
            if not codes:
                self._send_json({"ok": False, "error": "无基金代码"})
                return
            try:
                from core.fetcher import FundFetcher
                from adapters.feishu import FeishuAdapter
                from adapters.wechat import WechatAdapter
                cfg = _load_config()
                push_cfg = cfg.get("push", {})
                url = push_cfg.get(f"{target}_webhook", "")
                if not url:
                    self._send_json({"ok": False, "error": f"未配置 {target} Webhook"})
                    return
                fetcher = FundFetcher(rate_limit=0.5)
                result = fetcher.compare(codes=codes, cross_validate=True)
                if target == "feishu":
                    adapter = FeishuAdapter(webhook_url=url)
                else:
                    adapter = WechatAdapter(webhook_url=url)
                ok = adapter.send(result)
                self._send_json({"ok": ok, "error": "" if ok else "推送失败"})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)})

        else:
            self._send_json({"error": "not found"}, 404)

    def _serve_index(self) -> None:
        index_path = os.path.join(SCRIPT_DIR, "index.html")
        if not os.path.exists(index_path):
            self._send_json({"error": "index.html not found"}, 500)
            return
        with open(index_path, "rb") as f:
            content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, fmt, *args):
        pass


def main() -> None:
    server = HTTPServer(("0.0.0.0", PORT), _Handler)
    print(f"\n  QDII-fund-scout \u672c\u5730\u914d\u7f6e\u9875\u9762")
    print(f"  \u6253\u5f00\u6d4f\u89c8\u5668\u8bbf\u95ee\uff1a")
    print(f"  \u2192 http://localhost:{PORT}")
    print(f"\n  \u6309 Ctrl+C \u505c\u6b62\u670d\u52a1\u3002\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  \u670d\u52a1\u5df2\u505c\u6b62\u3002")
        server.server_close()


if __name__ == "__main__":
    main()
