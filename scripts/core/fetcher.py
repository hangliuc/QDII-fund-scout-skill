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

MIN_RATE_LIMIT = 0.5

STATUS_STRICTNESS = {"开放": 1, "限大额": 2, "限小额": 3, "暂停": 4, "未知": 0}

CROSS_VAL_THRESHOLDS: dict[str, dict] = {
    "return_1y": {"diff": 1.0, "unit": "百分点"},
    "return_3y": {"diff": 2.0, "unit": "百分点"},
    "return_1m": {"diff": 1.0, "unit": "百分点"},
    "return_3m": {"diff": 1.0, "unit": "百分点"},
    "nav": {"diff": 0.005, "unit": "元", "fmt": ".4f"},
    "total_fee": {"diff": 0.05, "unit": "百分点", "fmt": ".4f"},
    "scale": {"rel_diff": 0.20, "unit": ""},
}


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
    # 自动仲裁：申购状态 / 限额
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_purchase(primary: FundInfo, backup: FundInfo) -> dict | None:
        p_rank = STATUS_STRICTNESS.get(primary.purchase_status, 0)
        b_rank = STATUS_STRICTNESS.get(backup.purchase_status, 0)

        if p_rank == b_rank:
            return None

        if b_rank > p_rank:
            resolved_status = backup.purchase_status
            resolved_limit = FundFetcher._resolve_limit_by_status(resolved_status, primary.purchase_limit, backup.purchase_limit)
            old_status = primary.purchase_status
            old_limit = primary.purchase_limit
            primary.purchase_status = resolved_status
            primary.purchase_limit = resolved_limit
            return {
                "field": "purchase_status",
                "reason": "保守仲裁（取更严格值）",
                "primary_original": old_status,
                "backup_value": backup.purchase_status,
                "resolved": resolved_status,
            }
        return None

    @staticmethod
    def _resolve_limit_by_status(status: str, primary_limit: str, backup_limit: str) -> str:
        if status == "暂停":
            return "0"
        if status == "开放":
            return "无限制"
        pl = FundFetcher._parse_limit_amount(primary_limit)
        bl = FundFetcher._parse_limit_amount(backup_limit)
        candidates = [(pl, primary_limit), (bl, backup_limit)]
        valid = [(v, s) for v, s in candidates if v is not None]
        if not valid:
            return primary_limit or backup_limit or ""
        valid.sort(key=lambda x: x[0])
        return valid[0][1]

    @staticmethod
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

    # ------------------------------------------------------------------
    # 自动仲裁：申购限额
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_purchase_limit(primary: FundInfo, backup: FundInfo) -> dict | None:
        if primary.purchase_status == backup.purchase_status and primary.purchase_limit == backup.purchase_limit:
            return None
        pv = FundFetcher._parse_limit_amount(primary.purchase_limit)
        bv = FundFetcher._parse_limit_amount(backup.purchase_limit)
        if pv is None and bv is None:
            return None
        if pv is not None and bv is not None and abs(pv - bv) < 0.01:
            return None
        old_limit = primary.purchase_limit
        primary.purchase_limit = FundFetcher._resolve_limit_by_status(primary.purchase_status, primary.purchase_limit, backup.purchase_limit)
        return {
            "field": "purchase_limit",
            "reason": "保守仲裁（取更低限额）",
            "primary_original": old_limit,
            "backup_value": backup.purchase_limit,
            "resolved": primary.purchase_limit,
        }

    # ------------------------------------------------------------------
    # 自动仲裁：数值字段
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_numeric(primary: FundInfo, backup: FundInfo, field: str, rule: dict) -> dict | None:
        pv = FundFetcher._to_float(getattr(primary, field, None))
        bv = FundFetcher._to_float(getattr(backup, field, None))
        if pv is None or bv is None:
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
            if ratio <= rel_diff * 3:
                return {
                    "field": field,
                    "action": "auto_resolved",
                    "reason": "差异在可接受范围，使用主源数据",
                    "primary": format(pv, fmt_str),
                    "backup": format(bv, fmt_str),
                    "diff": format(diff, fmt_str),
                }
            return {
                "field": field,
                "action": "warning",
                "reason": f"差异 {ratio*100:.0f}% 超出可接受范围",
                "primary": format(pv, fmt_str),
                "backup": format(bv, fmt_str),
                "diff": format(diff, fmt_str),
            }

        if diff <= base_threshold:
            return None
        if diff <= base_threshold * 3:
            return {
                "field": field,
                "action": "auto_resolved",
                "reason": f"小差异 ({diff:.2f}{rule.get('unit', '')})，信任主源",
                "primary": format(pv, fmt_str),
                "backup": format(bv, fmt_str),
                "diff": format(diff, fmt_str),
            }
        return {
            "field": field,
            "action": "warning",
            "reason": f"重大差异 ({diff:.2f}{rule.get('unit', '')})，怀疑数据质量问题",
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

        limit_resolved = self._resolve_purchase_limit(primary, backup)
        if limit_resolved:
            resolved_items.append(limit_resolved)

        for field, rule in CROSS_VAL_THRESHOLDS.items():
            result = self._resolve_numeric(primary, backup, field, rule)
            if result is None:
                continue
            if result.get("action") == "warning":
                warnings.append(result)
            else:
                resolved_items.append(result)

        primary._cross_resolved = resolved_items
        primary._cross_validation = warnings

        if resolved_items:
            logger.info("交叉校验 %s: 自动仲裁 %d 处差异 %s",
                        primary.code, len(resolved_items),
                        ", ".join(f"{d['field']}" for d in resolved_items))
        if warnings:
            logger.warning("交叉校验 %s: 发现 %d 处无法仲裁的异常: %s",
                           primary.code, len(warnings),
                           ", ".join(f"{d['field']}({d['primary']}/{d['backup']})" for d in warnings))

        return primary

    # ------------------------------------------------------------------
    # 公开方法
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
            result._warnings.append(f"⚠ {unavailable_count}/{len(funds)} 只基金数据暂不可用（所有数据源均失败）")

        unresolved_count = sum(1 for f in funds if f._cross_validation)
        resolved_count = sum(1 for f in funds if f._cross_resolved)
        if resolved_count > 0:
            result._warnings.append(f"ℹ️ {resolved_count}/{len(funds)} 只基金多源差异已自动仲裁（保守取最小值）")
        if unresolved_count > 0:
            result._warnings.append(f"⚠ {unresolved_count}/{len(funds)} 只基金存在无法自动仲裁的数据差异（详见基金详情）")

        return result

    @staticmethod
    def _to_float(val) -> float | None:
        if val is None:
            return None
        try:
            return float(str(val).replace("%", "").replace(",", "").strip()) or None
        except (ValueError, TypeError):
            return None
