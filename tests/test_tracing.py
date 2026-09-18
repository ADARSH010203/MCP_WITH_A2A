import threading

from app.routing.tracing import CollaborationTrace


def test_trace_records_ordered_events():
    trace = CollaborationTrace(trace_id="trace-test")

    trace.record("plan_created", "planner", "completed")
    trace.record(
        "specialist_completed",
        "code",
        "completed",
        duration_ms=12.34,
        attempt=1,
    )

    snapshot = trace.snapshot()

    assert snapshot["trace_id"] == "trace-test"
    assert snapshot["event_count"] == 2
    assert [event["sequence"] for event in snapshot["events"]] == [1, 2]
    assert snapshot["events"][1]["duration_ms"] == 12.34
    assert snapshot["events"][1]["attempt"] == 1


def test_trace_keeps_sequence_safe_under_concurrent_writes():
    trace = CollaborationTrace()
    barrier = threading.Barrier(5)

    def record_event(index: int) -> None:
        barrier.wait()
        trace.record(
            "specialist_completed",
            f"agent-{index}",
            "completed",
        )

    threads = [
        threading.Thread(target=record_event, args=(index,))
        for index in range(5)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    snapshot = trace.snapshot()

    assert snapshot["event_count"] == 5
    assert sorted(event["sequence"] for event in snapshot["events"]) == [1, 2, 3, 4, 5]
