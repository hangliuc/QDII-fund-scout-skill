# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.models import FundInfo, FundDataResult
from core.sources.eastmoney import EastMoneySource
from core.sources.csrc import CSRCSource
from core.validate import validate_data, print_report
from adapters import get_adapter, list_adapters


CONFIG_DIR = os.path.expanduser("~/.fund-scout")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")


def _load_config(path: str | None = None) -> dict:
    p = path or CONFIG_PATH
    if not os.path.exists(p):
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _ensure_config_dir() -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)


class FundFetcher:
    def __init__(self):
        self.em = EastMoneySource()
        self.csrc = CSRCSource()

    def fetch_detail(self, code: str, holdings: bool = False, csrc: bool = False) -> FundInfo:
        info = self.em.fetch_detail(code)
        if holdings:
            year = time.localtime().tm_year
            info.top10_holdings = self.em._fetch_holdings(code, year)
        if csrc:
            info.market_distribution = self.csrc.fetch_market_distribution(
                code, info.short_name or info.name
            )
        return info

    def fetch_batch(self, codes: list[str]) -> list[FundInfo]:
        return self.em.fetch_batch(codes)

    def search(self, keyword: str, fund_type: str = "") -> list[dict]:
        return self.em.search_funds(keyword, fund_type)


def _format_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _format_csv(data: dict) -> str:
    funds = data.get("funds", [])
    if not funds:
        return ""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(funds[0].keys()))
    writer.writeheader()
    for f in funds:
        row = {}
        for k, v in f.items():
            if isinstance(v, (dict, list)):
                row[k] = json.dumps(v, ensure_ascii=False)
            else:
                row[k] = v
        writer.writerow(row)
    return buf.getvalue()


def _format_md(data: dict, style: str = "table") -> str:
    funds = data.get("funds", [])
    if not funds:
        return ""

    if style == "summary":
        lines = []
        for f in funds:
            name = f.get("name", "")
            code = f.get("code", "")
            ret = f.get("return_1y", "")
            status = f.get("purchase_status", "")
            lines.append(f"- **{name}** ({code})  近1年: {ret}  申购: {status}")
        return "\n".join(lines)

    if style == "card":
        blocks = []
        for f in funds:
            lines = [f"### {f.get('name', '')} ({f.get('code', '')})"]
            for k, v in f.items():
                if k in ("name", "code") or v is None or v == "" or v == [] or v == {}:
                    continue
                if isinstance(v, (dict, list)):
                    v = json.dumps(v, ensure_ascii=False)
                lines.append(f"- **{k}**: {v}")
            blocks.append("\n".join(lines))
        return "\n\n---\n\n".join(blocks)

    all_keys = []
    for f in funds:
        for k in f.keys():
            if k not in all_keys:
                all_keys.append(k)
    header = "| " + " | ".join(all_keys) + " |"
    sep = "| " + " | ".join(["---"] * len(all_keys)) + " |"
    rows = []
    for f in funds:
        cells = []
        for k in all_keys:
            v = f.get(k, "")
            if isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)
            cells.append(str(v))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, sep] + rows)


def _format_output(data: dict, fmt: str, style: str = "table") -> str:
    if fmt == "csv":
        return _format_csv(data)
    if fmt == "md":
        return _format_md(data, style=style)
    return _format_json(data)


def _write_output(content: str, output_dir: str, filename: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _push(content: str, adapter_name: str) -> None:
    cls = get_adapter(adapter_name)
    adapter = cls()
    adapter.send(content)


def _build_result(funds: list[FundInfo]) -> FundDataResult:
    return FundDataResult(
        update_date=time.strftime("%Y-%m-%d"),
        count=len(funds),
        funds=funds,
    )


def cmd_detail(args: argparse.Namespace) -> None:
    fetcher = FundFetcher()
    info = fetcher.fetch_detail(args.code, holdings=args.holdings, csrc=args.csrc)
    result = _build_result([info])
    data = result.to_dict()

    validation = validate_data(data, profile="detail")
    data["_validation"] = validation.to_dict()
    data["_warnings"] = validation.warnings
    print_report(validation)

    content = _format_output(data, args.format)
    print(content)

    ext = {"json": "json", "csv": "csv", "md": "md"}[args.format]
    filename = f"{args.code}_detail.{ext}"
    path = _write_output(content, args.output, filename)
    print(f"\n已保存: {path}")

    if args.push:
        _push(content, args.push)


def cmd_compare(args: argparse.Namespace) -> None:
    config = {}
    if args.config:
        config = _load_config(args.config)
    elif not args.codes:
        config = _load_config()

    if config and not args.codes:
        my_funds = config.get("my_funds", [])
        codes = [f["code"] for f in my_funds if "code" in f]
        if not codes:
            print("❌ 配置文件中没有基金代码，请编辑 ~/.fund-scout/config.json")
            sys.exit(1)
    else:
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]

    fetcher = FundFetcher()
    funds = fetcher.fetch_batch(codes)
    result = _build_result(funds)
    data = result.to_dict()

    profile = config.get("defaults", {}).get("profile", "compare")
    validation = validate_data(data, profile=profile)
    data["_validation"] = validation.to_dict()
    data["_warnings"] = validation.warnings
    print_report(validation)

    fmt = config.get("defaults", {}).get("format", args.format)
    style = config.get("defaults", {}).get("style", args.style)
    content = _format_output(data, fmt, style=style)
    print(content)

    ext = {"json": "json", "csv": "csv", "md": "md"}[fmt]
    filename = f"compare_{'_'.join(codes)}.{ext}"
    path = _write_output(content, args.output, filename)
    print(f"\n已保存: {path}")

    push_targets = []
    if args.push:
        push_targets = [p.strip() for p in args.push.split(",")]
    elif config.get("push", {}).get("feishu_webhook"):
        push_targets.append("feishu")
    elif config.get("push", {}).get("wechat_webhook"):
        push_targets.append("wechat")

    for target in push_targets:
        _push(content, target)


def cmd_search(args: argparse.Namespace) -> None:
    fetcher = FundFetcher()
    results = fetcher.search(args.keyword, fund_type=args.type or "")

    if args.cls:
        results = [r for r in results if args.cls in r.get("name", "")]

    data = {
        "update_date": time.strftime("%Y-%m-%d"),
        "count": len(results),
        "funds": results,
    }

    content = _format_output(data, args.format)
    print(content)

    ext = {"json": "json", "csv": "csv", "md": "md"}[args.format]
    filename = f"search_{args.keyword}.{ext}"
    path = _write_output(content, args.output, filename)
    print(f"\n已保存: {path}")

    if args.push:
        _push(content, args.push)


def cmd_validate(args: argparse.Namespace) -> None:
    with open(args.file, "r", encoding="utf-8") as f:
        data = json.load(f)

    profile = args.profile or "compare"
    result = validate_data(data, profile=profile)
    print_report(result)

    if result.fatal_count > 0:
        sys.exit(1)


def cmd_test(args: argparse.Namespace) -> None:
    try:
        cls = get_adapter(args.adapter)
        adapter = cls()
        ok = adapter.test_connection()
        if ok:
            print(f"✅ {args.adapter} 连接正常")
        else:
            print(f"❌ {args.adapter} 连接失败")
            sys.exit(1)
    except KeyError as e:
        print(f"❌ {e}")
        sys.exit(1)


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=["json", "csv", "md"], default="json")
    parser.add_argument("--push", default="", help="推送目标 (feishu/wechat/feishu,wechat)")
    parser.add_argument("--output", default=".")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fund-scout", description="基金数据获取与校验工具")
    sub = parser.add_subparsers(dest="command")

    p_detail = sub.add_parser("detail", help="单只基金详情")
    p_detail.add_argument("code", help="基金代码")
    p_detail.add_argument("--holdings", action="store_true", help="包含持仓")
    p_detail.add_argument("--csrc", action="store_true", help="包含证监会季报")
    _add_common_args(p_detail)
    p_detail.set_defaults(func=cmd_detail)

    p_compare = sub.add_parser("compare", help="批量对比")
    p_compare.add_argument("codes", nargs="?", default="", help="逗号分隔的基金代码")
    p_compare.add_argument("--config", default="", help="配置文件路径（默认 ~/.fund-scout/config.json）")
    p_compare.add_argument("--style", choices=["table", "card", "summary"], default="table", help="md 格式专用")
    _add_common_args(p_compare)
    p_compare.set_defaults(func=cmd_compare)

    p_search = sub.add_parser("search", help="关键词搜索")
    p_search.add_argument("keyword", help="搜索关键词")
    p_search.add_argument("--type", default="", help="基金类型筛选")
    p_search.add_argument("--class", dest="cls", default="", help="份额类别筛选 (A/C)")
    _add_common_args(p_search)
    p_search.set_defaults(func=cmd_search)

    p_validate = sub.add_parser("validate", help="校验已有数据文件")
    p_validate.add_argument("file", help="数据文件路径")
    p_validate.add_argument("--profile", choices=["quick", "compare", "detail", "qdii"], default="compare")
    p_validate.set_defaults(func=cmd_validate)

    p_test = sub.add_parser("test", help="测试适配器连接")
    p_test.add_argument("adapter", choices=["feishu", "wechat"], help="适配器名称")
    p_test.set_defaults(func=cmd_test)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
