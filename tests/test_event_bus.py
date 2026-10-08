import asyncio
from collections import defaultdict

import pytest

from app.a2a.base_task_manager import InMemoryTaskManager
from app.a2a.models import TaskStatus, TaskStatusUpdateEvent, TaskState
from app.a2a.task_store import SQLiteTaskStore


class ConcreteTaskManager(InMemoryTaskManager):
    async def on_send_task(self, request):
        return None

    async def on_send_task_subscribe(self, request):
        return None


class FakeEventBus:
    def __init__(self):
        self.channels = defaultdict(list)
        self.published = []

    async def ping(self):
        return True

    async def publish(self, task_id, event):
        self.published.append((task_id, event))
        for queue in list(self.channels[task_id]):
            await queue.put(event)

    async def subscribe(self, task_id):
        queue = asyncio.Queue()
        self.channels[task_id].append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self.channels[task_id].remove(queue)

    async def close(self):
        self.channels.clear()


def test_sse_event_round_trip():
    event = TaskStatusUpdateEvent(
        id="task-1",
        status=TaskStatus(state=TaskState.COMPLETED),
        final=True,
    )
    payload = ConcreteTaskManager._serialize_sse_event(event)
    restored = ConcreteTaskManager._deserialize_sse_event(payload)

    assert isinstance(restored, TaskStatusUpdateEvent)
    assert restored.id == "task-1"
    assert restored.final is True
    assert restored.status.state == TaskState.COMPLETED


def test_event_bus_bridges_events_between_worker_managers():
    async def scenario():
        manager_one = ConcreteTaskManager(store=SQLiteTaskStore(":memory:"))
        manager_two = ConcreteTaskManager(store=SQLiteTaskStore(":memory:"))
        bus = FakeEventBus()
        manager_one.event_bus = bus
        manager_two.event_bus = bus

        queue = await manager_two.setup_sse_consumer("distributed-task")
        bridge = manager_two.event_bridge_tasks[id(queue)]
        await asyncio.sleep(0)

        event = TaskStatusUpdateEvent(
            id="distributed-task",
            status=TaskStatus(state=TaskState.WORKING),
            final=False,
        )

        await manager_one.enqueue_events_for_sse("distributed-task", event)
        received = await asyncio.wait_for(queue.get(), timeout=1)

        assert isinstance(received, TaskStatusUpdateEvent)
        assert received.id == "distributed-task"
        assert bus.published

        bridge.cancel()
        await asyncio.gather(bridge, return_exceptions=True)
        manager_two.event_bridge_tasks.pop(id(queue), None)
        await manager_two.stop_event_bus()

    asyncio.run(scenario())


def test_event_bus_startup_is_fail_closed():
    class UnhealthyBus(FakeEventBus):
        async def ping(self):
            return False

    async def scenario():
        manager = ConcreteTaskManager(store=SQLiteTaskStore(":memory:"))
        manager.event_bus = UnhealthyBus()

        with pytest.raises(RuntimeError, match="event bus is unavailable"):
            await manager.start_event_bus()

    asyncio.run(scenario())


def test_event_bus_publish_failure_falls_back_to_local_subscriber():
    class BrokenBus(FakeEventBus):
        async def publish(self, task_id, event):
            raise RuntimeError("redis offline")

    async def scenario():
        manager = InMemoryTaskManager(store=SQLiteTaskStore(":memory:"))
        manager.event_bus = BrokenBus()
        queue = await manager.setup_sse_consumer("fallback-task")

        event = TaskStatusUpdateEvent(
            id="fallback-task",
            status=TaskStatus(state=TaskState.COMPLETED),
            final=True,
        )
        await manager.enqueue_events_for_sse("fallback-task", event)
        received = await asyncio.wait_for(queue.get(), timeout=1)

        assert isinstance(received, TaskStatusUpdateEvent)
        assert received.id == "fallback-task"

        bridge = manager.event_bridge_tasks.pop(id(queue), None)
        if bridge:
            bridge.cancel()
            await asyncio.gather(bridge, return_exceptions=True)

    asyncio.run(scenario())
