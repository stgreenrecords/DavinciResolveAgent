from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llm.client import LlmRequestContext, LlmResponse


class LlmProvider(ABC):
    @abstractmethod
    def request_actions(self, ctx: LlmRequestContext) -> LlmResponse:
        raise NotImplementedError

    @abstractmethod
    def test_connection(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def list_models(self) -> list[str]:
        raise NotImplementedError
