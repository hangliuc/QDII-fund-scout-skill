from __future__ import annotations

import logging
import random
import re
import time
from abc import ABC, abstractmethod

import requests

from core.models import FundInfo

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class SourceError(Exception):
    def __init__(self, source: str, message: str, original: Exception | None = None):
        self.source = source
        self.original = original
        super().__init__(f"[{source}] {message}")


class BaseSource(ABC):
    name: str = "base"

    def _get(self, url: str, timeout: int = 20, headers: dict | None = None) -> str:
        hdrs = headers or DEFAULT_HEADERS
        try:
            resp = requests.get(url, headers=hdrs, timeout=timeout)
            resp.encoding = "utf-8"
            if resp.status_code != 200:
                raise SourceError(self.name, f"HTTP {resp.status_code} - {url}")
            return resp.text
        except requests.RequestException as e:
            raise SourceError(self.name, f"请求失败 {url}", original=e) from e

    def _get_with_retry(self, url: str, retries: int = 2, timeout: int = 20, headers: dict | None = None) -> str | None:
        for i in range(retries + 1):
            try:
                return self._get(url, timeout=timeout, headers=headers)
            except SourceError as e:
                logger.warning("%s 请求失败 (%d/%d) %s - %s", self.name, i + 1, retries + 1, url, e)
                if i < retries:
                    self._sleep()
        return None

    def _sleep(self, lo: float = 0.5, hi: float = 2.0) -> None:
        time.sleep(random.uniform(lo, hi))

    @staticmethod
    def _strip_tags(html: str) -> str:
        text = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", text).strip()

    @abstractmethod
    def fetch_detail(self, code: str) -> FundInfo:
        ...

    @abstractmethod
    def fetch_batch(self, codes: list[str]) -> list[FundInfo]:
        ...

    @abstractmethod
    def search_funds(self, keyword: str, fund_type: str = "") -> list[dict]:
        ...
