from __future__ import annotations

import logging
import re
import time
from datetime import datetime

from core.models import FundInfo, FundDataResult
from core.validate import validate_data
from core.sources.base import SourceError
from core.sources.eastmoney import EastMoneySource
from core.sources.howbuy import HowbuySource
from core.sources.csrc import CSRCSource

logger = logging.getLogger(__name__)

MIN_RATE_LIMIT = 0.3

CROSS_VAL_THRESHOLDS: dict[str, dict] = {
    "return_1y": {"diff": 1.0, "unit": "百分点"},
    "return_3y": {"diff": 2.0, "unit": "百分点"},
    "return_1m": {"diff": 1.0, "unit": "百分点"},
    "return_3m": {"diff": 1.0, "unit": "百分点"},
    "nav": {"diff": 0.01, "unit": "元", "fmt": ".4f"},
    "total_fee": {"diff": 0.10, "unit": "百分点", "fmt": ".4f"},
    "scale": {"rel_diff": 0.30, "unit": ""},
}


def _build_purchase_info(status: str, limit: str, effectively_closed: bool) -> str:
    if effectively_closed or status == "暂停":
        return "暂停申购"
    if status == "限小额":
        amt = _parse_limit_amount(limit)
        if amt and amt < 100000:
            return f"限小额 {limit}"
        return f"限小额（{limit}）" if limit else "限小额"
    if status == "限大额":
        return f"限大额（{limit}）" if limit else "限大额"
    if status in ("开放", "开放申购"):
        return "开放申购（无限额）"
    return f"{status}（{limit}）" if limit else status


def _parse_limit_amount(limit_str: str | None) -> float | None:
    if not limit_str or limit_str in ("无限制", "0", "-"):
        return None
    m = re.search(r"([\d.]+)\s*(万|元)?", str(limit_str))
    if not m:
        return None
    amt = float(m.group(1))
    if m.group(2) == "万":
        amt *= 10000
    return amt


def _semantic_purchase_match(s1: str, l1: str, s2: str, l2: str) -> bool:
    if s1 == s2 and l1 == l2:
        return True
    if s1 == "暂停" and s2 == "暂停":
        return True
    if s1 == "暂停" and s2 in ("限小额", "限大额"):
        return False
    if s1 in ("限小额", "限大额") and s2 == "暂停":
        return False
    if s1 in ("限小额", "限大额") and s2 in ("限小额", "限大额"):
        a1 = _parse_limit_amount(l1)
        a2 = _parse_limit_amount(l2)
        if a1 is not None and a2 is not None:
            if abs(a1 - a2) < 0.01:
                return True
            smaller = min(a1, a2)
            larger = max(a1, a2)
            if larger / smaller <= 2.0:
                return True
    return False


class FundFetcher:
    _MAX_FAIL = 30

    def __init__(self, rate_limit: float = 1.0):
        self.rate_limit = max(rate_limit, MIN_RATE_LIMIT)
        self._primary = EastMoneySource()
        self._backup = HowbuySource()
        self._csrc = CSRCSource(rate_limit=self.rate_limit)
        self._fail_count = 0

    def _sleep(self) -> None:
        time.sleep(self.rate_limit)

    def _check_fail(self) -> None:
        if self._fail_count >= self._MAX_FAIL:
            raise RuntimeError(f"连续 {self._MAX_FAIL} 次失败，自动停止")

    def _record_fail(self) -> None:
        self._fail_count += 1
        self._check_fail()

    def _record_success(self) -> None:
        self._fail_count = 0

    def _fetch_with_fallback(self, code: str) -> FundInfo:
        try:
            info = self._primary.fetch_detail(code)
            self._record_success()
            return info
        except SourceError as e:
            logger.warning("主数据源(eastmoney)获取 %s 失败: %s，尝试备用源(howbuy)", code, e)
            self._record_fail()
        except Exception as e:
            logger.warning("主数据源(eastmoney)获取 %s 异常: %s，尝试备用源(howbuy)", code, e)
            self._record_fail()

        try:
            info = self._backup.fetch_detail(code)
            self._record_success()
            logger.info("备用源(howbuy)成功获取 %s", code)
            return info
        except SourceError as e:
            logger.warning("备用源(howbuy)获取 %s 也失败: %s", code, e)
            self._record_fail()
        except Exception as e:
            logger.warning("备用源(howbuy)获取 %s 异常: %s", code, e)
            self._record_fail()

        logger.error("所有数据源均无法获取基金 %s，返回降级结果", code)
        return FundInfo(
            code=code,
            data_source="unavailable",
            data_unavailable=True,
        )

    # ------------------------------------------------------------------
    # 准确性优先: 申购状态仲裁
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_purchase(primary: FundInfo, backup: FundInfo) -> dict | None:
        ps, pl = primary.purchase_status, primary.purchase_limit
        bs, bl = backup.purchase_status, backup.purchase_limit

        if ps == bs and pl == bl:
            return None

        if _semantic_purchase_match(ps, pl, bs, bl):
            if ps != bs or pl != bl:
                old_status = ps
                old_limit = pl
                primary.purchase_status = bs
                primary.purchase_limit = bl
                return {
                    "field": "purchase_status",
                    "reason": "语义等价，自动对齐",
                    "primary_original": old_status,
                    "backup_value": bs,
                    "resolved": bs,
                    "note": "两源数据实际含义一致，已取更完整描述",
                }
            return None

        a1 = _parse_limit_amount(pl)
        a2 = _parse_limit_amount(bl)
        if a1 is not None and a2 is not None and a1 != a2:
            min_amt = min(a1, a2)
            min_str = f"{min_amt:.0f}元" if min_amt < 10000 else f"{min_amt/10000:.0f}万元"
            if min_amt != a1:
                primary.purchase_limit = min_str
            return {
                "field": "purchase_limit",
                "reason": "限额不一致，取低值确保准确性",
                "primary_original": pl,
                "backup_value": bl,
                "resolved": min_str,
            }

        logger.warning("采购状态两源不一致: 主源=%s, 备用源=%s, 以主源为准", ps, bs)
        return {
            "field": "purchase_status",
            "reason": "两源不一致，以主源(eastmoney)为准",
            "primary_original": ps,
            "backup_value": bs,
            "resolved": ps,
        }

    # ------------------------------------------------------------------
    # 准确性优先: 数值字段仲裁
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_numeric(primary: FundInfo, backup: FundInfo, field: str, rule: dict) -> dict | None:
        pv = FundFetcher._to_float(getattr(primary, field, None))
        bv = FundFetcher._to_float(getattr(backup, field, None))
        if pv is None and bv is None:
            return None
        if pv is None and bv is not None:
            return None
        if bv is None:
            return None

        diff = abs(pv - bv)
        base_threshold = rule.get("diff", 1.0)
        rel_diff = rule.get("rel_diff")
        fmt_str = rule.get("fmt", ".2f")

        if rel_diff:
            max_v = max(abs(pv), abs(bv))
            if max_v == 0:
                return None
            ratio = diff / max_v
            if ratio <= rel_diff:
                return None
            return {
                "field": field,
                "action": "warning",
                "reason": f"差异 {ratio*100:.0f}%（主源={format(pv,fmt_str)}, 备用源={format(bv,fmt_str)}）",
                "primary": format(pv, fmt_str),
                "backup": format(bv, fmt_str),
                "diff": format(diff, fmt_str),
            }

        if diff <= base_threshold:
            return None
        return {
            "field": field,
            "action": "warning",
            "reason": f"差异 {diff:.2f}{rule.get('unit', '')}（主源={format(pv,fmt_str)}, 备用源={format(bv,fmt_str)}）",
            "primary": format(pv, fmt_str),
            "backup": format(bv, fmt_str),
            "diff": format(diff, fmt_str),
        }

    # ------------------------------------------------------------------
    # 交叉校验主入口
    # ------------------------------------------------------------------

    def _cross_validate_fund(self, primary: FundInfo) -> FundInfo:
        if primary.data_unavailable or not primary.code:
            return primary

        try:
            backup = self._backup.fetch_detail(primary.code)
        except Exception as e:
            logger.info("交叉校验 %s: 备用源不可用 (%s), 跳过", primary.code, e)
            return primary

        resolved_items: list[dict] = []
        warnings: list[dict] = []

        purchase_resolved = self._resolve_purchase(primary, backup)
        if purchase_resolved:
            resolved_items.append(purchase_resolved)

        for field, rule in CROSS_VAL_THRESHOLDS.items():
            result = self._resolve_numeric(primary, backup, field, rule)
            if result is None:
                continue
            warnings.append(result)

        primary._cross_resolved = resolved_items
        primary._cross_validation = warnings

        if resolved_items:
            logger.info("交叉校验 %s: 自动仲裁 %d 处 %s",
                        primary.code, len(resolved_items),
                        ", ".join(f"{d['field']}({d.get('reason','')})" for d in resolved_items))
        if warnings:
            logger.warning("交叉校验 %s: 发现 %d 处差异: %s",
                           primary.code, len(warnings),
                           ", ".join(f"{d['field']}({d['reason']})" for d in warnings))

        return primary

    # ------------------------------------------------------------------
    # 公共方法
    # ------------------------------------------------------------------

    def get_detail(self, code: str, include_holdings: bool = False, include_csrc: bool = False,
                   cross_validate: bool = True) -> FundInfo:
        self._check_fail()
        info = self._fetch_with_fallback(code)
        if info.data_unavailable:
            return info

        if cross_validate and info.data_source == "eastmoney":
            self._sleep()
            info = self._cross_validate_fund(info)

        info._purchase_info = _build_purchase_info(
            info.purchase_status, info.purchase_limit, info.effectively_closed
        )

        if include_holdings:
            self._sleep()
            try:
                year = datetime.now().year
                quarters = self._primary._fetch_holdings(code, year)
                if quarters:
                    info.top10_holdings = quarters[0].get("stocks", [])
                self._record_success()
            except Exception as e:
                logger.warning("获取 %s 持仓数据失败: %s", code, e)
                self._record_fail()

        if include_csrc:
            self._sleep()
            try:
                dist = self._csrc.fetch_market_distribution(code, info.short_name or info.name)
                info.market_distribution = dist
                self._record_success()
            except Exception as e:
                logger.warning("获取 %s CSRC 市场分布失败: %s", code, e)
                self._record_fail()

        validate_data(info.to_dict(), profile="detail")
        return info

    def compare(self, codes: list[str] | None = None, keyword: str = "", fund_type: str = "",
                cross_validate: bool = True) -> FundDataResult:
        fund_list: list[FundInfo] = []

        if codes:
            for code in codes:
                self._check_fail()
                self._sleep()
                info = self._fetch_with_fallback(code)
                if cross_validate and info.data_source == "eastmoney":
                    info = self._cross_validate_fund(info)
                info._purchase_info = _build_purchase_info(
                    info.purchase_status, info.purchase_limit, info.effectively_closed
                )
                fund_list.append(info)
        elif keyword or fund_type:
            try:
                search_results = self._primary.search_funds(keyword, fund_type)
            except SourceError as e:
                logger.warning("搜索基金失败: %s", e)
                search_results = []
            for item in search_results:
                self._check_fail()
                self._sleep()
                info = self._fetch_with_fallback(item["code"])
                if cross_validate and info.data_source == "eastmoney":
                    info = self._cross_validate_fund(info)
                info._purchase_info = _build_purchase_info(
                    info.purchase_status, info.purchase_limit, info.effectively_closed
                )
                fund_list.append(info)

        return self._validate_and_build_result(fund_list, profile="compare")

    def market_distribution(self, code: str, main_code: str = "", short_name: str = "") -> dict:
        self._check_fail()
        mc = main_code or code
        try:
            result = self._csrc.fetch_market_distribution(mc, short_name)
            self._record_success()
        except Exception as e:
            logger.warning("获取 %s CSRC 市场分布失败: %s", code, e)
            self._record_fail()
            result = {"_source": "unavailable", "_total_pct": 0, "_inferred": True, "_note": "all_sources_failed"}
        validate_data(result, profile="qdii")
        return result

    def _validate_and_build_result(self, funds: list[FundInfo], profile: str = "compare") -> FundDataResult:
        result = FundDataResult(
            count=len(funds),
            funds=funds,
        )
        if funds:
            result.update_date = time.strftime("%Y-%m-%d")

        data_dict = result.to_dict()
        validation = validate_data(data_dict, profile=profile)
        result._validation = validation.to_dict()
        result._warnings = validation.warnings

        unavailable_count = sum(1 for f in funds if f.data_unavailable)
        if unavailable_count > 0:
            result._warnings.append(f"⚠ {unavailable_count}/{len(funds)} 只基金数据暂不可用")

        unresolved_count = sum(1 for f in funds if f._cross_validation)
        resolved_count = sum(1 for f in funds if f._cross_resolved)
        if resolved_count > 0:
            result._warnings.append(f"ℹ {resolved_count}/{len(funds)} 只基金多源数据已校验对齐")
        if unresolved_count > 0:
            result._warnings.append(f"☒ {unresolved_count}/{len(funds)} 只基金多源数据存在差异，已标注于详情")

        return result

    @staticmethod
    def _to_float(val) -> float | None:
        if val is None:
            return None
        try:
            return float(str(val).replace("%", "").replace(",", "").strip()) or None
        except (ValueError, TypeError):
            return None
