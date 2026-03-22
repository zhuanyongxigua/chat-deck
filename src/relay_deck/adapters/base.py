from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from relay_deck.models import AgentEvent, AgentSpec

EventCallback = Callable[[AgentEvent], Awaitable[None]]


class AgentAdapter(ABC):
    def __init__(self, spec: AgentSpec, emit: EventCallback) -> None:
        self.spec = spec
        self.emit = emit

    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def send(self, message: str, *, display_message: str | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    async def interrupt(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        raise NotImplementedError
