# -*- coding: utf-8 -*-
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

ADAPTER_REGISTRY: dict[str, type] = {}


class BaseAdapter(ABC):
    name: str = ""
    required_config: list[str] = []

    @abstractmethod
    def send(self, data: Any, fmt: str = "", **kwargs) -> bool:
        ...

    @abstractmethod
    def test_connection(self) -> bool:
        ...


def register(name: str, adapter_cls: type) -> None:
    ADAPTER_REGISTRY[name] = adapter_cls


def get_adapter(name: str) -> type:
    if name not in ADAPTER_REGISTRY:
        raise KeyError(f"adapter '{name}' not found, available: {list_adapters()}")
    return ADAPTER_REGISTRY[name]


def list_adapters() -> list[str]:
    return sorted(ADAPTER_REGISTRY.keys())


# 导入适配器模块以触发 register() 调用
from . import feishu  # noqa: E402
from . import wechat  # noqa: E402
