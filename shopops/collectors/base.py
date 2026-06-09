from __future__ import annotations

from abc import ABC, abstractmethod

from shopops.models import OrderCollectResult, PromotionCollectResult


class OrderCollector(ABC):
    @abstractmethod
    def fetch_today(self) -> OrderCollectResult:
        raise NotImplementedError


class PromotionCollector(ABC):
    @abstractmethod
    def fetch_today(self) -> PromotionCollectResult:
        raise NotImplementedError
