from __future__ import annotations

import time
from datetime import datetime

from core.models import FundInfo, FundDataResult
from core.validate import validate_data
from core.sources.eastmoney import EastMoneySource
from core.sources.csrc import CSRCSource

MIN_RATE_LIMIT = 0.5


class FundFetcher:
    _MAX_FAIL = 30

    def __init__(self, rate_limit: float = 1.0):
        self.rate_limit = max(rate_limit, MIN_RATE_LIMIT)
        self._eastmoney = EastMoneySource()
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

    def get_detail(self, code: str, include_holdings: bool = False, include_csrc: bool = False) -> FundInfo:
        self._check_fail()
        try:
            info = self._eastmoney.fetch_detail(code)
            self._record_success()
        except Exception:
            self._record_fail()
            raise

        if include_holdings:
            self._sleep()
            try:
                year = datetime.now().year
                quarters = self._eastmoney._fetch_holdings(code, year)
                if quarters:
                    info.top10_holdings = quarters[0].get("stocks", [])
                self._record_success()
            except Exception:
                self._record_fail()

        if include_csrc:
            self._sleep()
            try:
                dist = self._csrc.fetch_market_distribution(code, info.short_name)
                info.market_distribution = dist
                self._record_success()
            except Exception:
                self._record_fail()

        validate_data(info.to_dict(), profile="detail")
        return info

    def compare(self, codes: list[str] | None = None, keyword: str = "", fund_type: str = "") -> FundDataResult:
        fund_list: list[FundInfo] = []

        if codes:
            for code in codes:
                self._check_fail()
                self._sleep()
                try:
                    info = self._eastmoney.fetch_detail(code)
                    fund_list.append(info)
                    self._record_success()
                except Exception:
                    self._record_fail()
        elif keyword or fund_type:
            search_results = self._eastmoney.search_funds(keyword, fund_type)
            for item in search_results:
                self._check_fail()
                self._sleep()
                try:
                    info = self._eastmoney.fetch_detail(item["code"])
                    fund_list.append(info)
                    self._record_success()
                except Exception:
                    self._record_fail()

        return self._validate_and_build_result(fund_list, profile="compare")

    def market_distribution(self, code: str, main_code: str = "", short_name: str = "") -> dict:
        self._check_fail()
        mc = main_code or code
        try:
            result = self._csrc.fetch_market_distribution(mc, short_name)
            self._record_success()
        except Exception:
            self._record_fail()
            result = {}
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

        return result
