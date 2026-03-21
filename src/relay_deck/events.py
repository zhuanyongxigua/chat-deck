from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from relay_deck.models import AgentEvent


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[AgentEvent]] = set()
        self._lock = asyncio.Lock()

    async def publish(self, event: AgentEvent) -> None:
        async with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            await queue.put(event)

    async def subscribe(self) -> asyncio.Queue[AgentEvent]:
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        async with self._lock:
            self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[AgentEvent]) -> None:
        async with self._lock:
            self._subscribers.discard(queue)

    async def stream(self) -> AsyncIterator[AgentEvent]:
        queue = await self.subscribe()
        try:
            while True:
                yield await queue.get()
        finally:
            await self.unsubscribe(queue)

