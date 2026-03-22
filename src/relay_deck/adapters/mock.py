from __future__ import annotations

import asyncio

from relay_deck.adapters.base import AgentAdapter
from relay_deck.models import AgentEvent, AgentState, EventType


class MockAdapter(AgentAdapter):
    def __init__(self, spec, emit) -> None:
        super().__init__(spec, emit)
        self._closed = False

    async def start(self) -> None:
        await self.emit(
            AgentEvent(
                type=EventType.STARTED,
                agent_id=self.spec.agent_id,
                message="Mock agent ready",
                state=AgentState.IDLE,
            )
        )
        await self.emit(
            AgentEvent(
                type=EventType.SUMMARY_UPDATED,
                agent_id=self.spec.agent_id,
                message="Mock agent is ready for input",
            )
        )

    async def send(self, message: str) -> None:
        if self._closed:
            return
        await self.emit(
            AgentEvent(
                type=EventType.MESSAGE_SENT,
                agent_id=self.spec.agent_id,
                message=message,
                state=AgentState.WORKING,
            )
        )
        await self.emit(
            AgentEvent(
                type=EventType.STATE_CHANGED,
                agent_id=self.spec.agent_id,
                message="Mock agent working",
                state=AgentState.WORKING,
            )
        )
        await asyncio.sleep(0.05)
        await self.emit(
            AgentEvent(
                type=EventType.OUTPUT,
                agent_id=self.spec.agent_id,
                message=f"Handled: {message}",
                state=AgentState.WORKING,
            )
        )
        await self.emit(
            AgentEvent(
                type=EventType.SUMMARY_UPDATED,
                agent_id=self.spec.agent_id,
                message=f"Handled: {message}",
            )
        )
        await self.emit(
            AgentEvent(
                type=EventType.STATE_CHANGED,
                agent_id=self.spec.agent_id,
                message="Mock agent waiting",
                state=AgentState.WAITING,
            )
        )

    async def interrupt(self) -> None:
        await self.emit(
            AgentEvent(
                type=EventType.STATE_CHANGED,
                agent_id=self.spec.agent_id,
                message="Mock agent interrupted",
                state=AgentState.WAITING,
            )
        )

    async def stop(self) -> None:
        self._closed = True
