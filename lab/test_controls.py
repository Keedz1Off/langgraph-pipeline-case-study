"""Defensive controls tests. Every identity and record is synthetic."""

import asyncio
import ipaddress
import socket

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command, interrupt
from pydantic import ValidationError
from typing_extensions import TypedDict

from local_host import LocalHost, Principal, action_digest, memory_graph

ALICE = Principal("tenant-one", "alice", approver=True)
BOB = Principal("tenant-one", "bob", approver=True)
OTHER_TENANT = Principal("tenant-two", "alice", approver=True)
NO_ROLE = Principal("tenant-one", "alice", approver=False)
ACTION = {"operation": "record_demo", "record": "synthetic-only"}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Network disabled in local controls tests")

    original_connect = socket.socket.connect

    def external_connect_blocked(sock, address):
        # Windows asyncio socketpair needs loopback TCP for its internal self-pipe.
        if isinstance(address, tuple):
            try:
                loopback = ipaddress.ip_address(address[0]).is_loopback
            except ValueError:
                loopback = False
            if loopback:
                return original_connect(sock, address)
        raise AssertionError("External network disabled in local controls tests")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", external_connect_blocked)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")


@pytest.fixture(params=["memory", "sqlite"])
def host(request, tmp_path):
    instance = LocalHost(tmp_path, request.param)
    yield instance
    instance.close()


def start_action(host, principal=ALICE):
    handle = host.new_thread(principal, "action", ACTION)
    output = host.request_action(principal, handle)
    assert len(output["__interrupt__"]) == 1
    return handle


def test_distinct_thread_checkpoints(host):
    a, b = host.new_thread(ALICE), host.new_thread(BOB)
    host.append(ALICE, a, "ALICE-CANARY")
    host.append(BOB, b, "BOB-CANARY")
    assert host.state(ALICE, a).values["messages"] == ["ALICE-CANARY"]
    assert host.state(BOB, b).values["messages"] == ["BOB-CANARY"]


def test_same_owner_distinct_threads(host):
    a, b = host.new_thread(ALICE), host.new_thread(ALICE)
    host.append(ALICE, a, "FIRST")
    host.append(ALICE, b, "SECOND")
    assert host.state(ALICE, a).values["messages"] == ["FIRST"]
    assert host.state(ALICE, b).values["messages"] == ["SECOND"]


def test_same_subject_distinct_tenants(host):
    a, b = host.new_thread(ALICE), host.new_thread(OTHER_TENANT)
    host.append(ALICE, a, "TENANT-ONE")
    host.append(OTHER_TENANT, b, "TENANT-TWO")
    assert host.state(ALICE, a).values["messages"] == ["TENANT-ONE"]
    assert host.state(OTHER_TENANT, b).values["messages"] == ["TENANT-TWO"]


def test_thread_continuity(host):
    a = host.new_thread(ALICE)
    host.append(ALICE, a, "one")
    host.append(ALICE, a, "two")
    assert host.state(ALICE, a).values["messages"] == ["one", "two"]


@pytest.mark.parametrize("operation", ["state", "history", "append", "delete"])
def test_host_denies_nonowner(host, operation):
    handle = host.new_thread(ALICE)
    host.append(ALICE, handle, "PRIVATE-SYNTHETIC")
    with pytest.raises(PermissionError):
        if operation == "append":
            host.append(BOB, handle, "no")
        elif operation == "delete":
            host.delete_thread(BOB, handle)
        else:
            getattr(host, operation)(BOB, handle)
    assert host.state(ALICE, handle).values["messages"] == ["PRIVATE-SYNTHETIC"]


def test_host_denies_cross_tenant(host):
    handle = host.new_thread(ALICE)
    with pytest.raises(PermissionError):
        host.state(OTHER_TENANT, handle)


def test_thread_delete_is_scoped(host):
    a, b = host.new_thread(ALICE), host.new_thread(BOB)
    host.append(ALICE, a, "A")
    host.append(BOB, b, "B")
    host.delete_thread(ALICE, a)
    assert host.saver.get_tuple(host._config(a)) is None
    with pytest.raises(PermissionError):
        host.state(ALICE, a)
    assert host.state(BOB, b).values["messages"] == ["B"]


def test_store_same_key_is_partitioned(host):
    host.put_note(ALICE, "note", "A")
    host.put_note(BOB, "note", "B")
    host.put_note(OTHER_TENANT, "note", "C")
    assert host.get_note(ALICE, "note").value == {"text": "A"}
    assert host.get_note(BOB, "note").value == {"text": "B"}
    assert host.get_note(OTHER_TENANT, "note").value == {"text": "C"}


def test_store_search_is_principal_scoped(host):
    for principal, marker in [(ALICE, "A"), (BOB, "B"), (OTHER_TENANT, "C")]:
        host.put_note(principal, "note", marker)
    assert [x.value for x in host.search_notes(ALICE)] == [{"text": "A"}]


def test_store_delete_is_scoped(host):
    host.put_note(ALICE, "note", "A")
    host.put_note(BOB, "note", "B")
    host.delete_note(ALICE, "note")
    assert host.get_note(ALICE, "note") is None
    assert host.get_note(BOB, "note").value == {"text": "B"}


def test_store_shared_across_same_user_threads(host):
    a, b = host.new_thread(ALICE), host.new_thread(ALICE)
    host.append(ALICE, a, "chat1")
    host.append(ALICE, b, "chat2")
    host.put_note(ALICE, "preference", "blue")
    assert host.get_note(ALICE, "preference").value == {"text": "blue"}
    assert host.state(ALICE, a).values != host.state(ALICE, b).values


def test_pending_approval_has_no_effect(host):
    handle = start_action(host)
    snapshot = host.state(ALICE, handle, kind="action")
    assert snapshot.next == ("approval",)
    assert host.effect_count() == 0


def test_denial_has_no_effect(host):
    handle = start_action(host)
    output = host.decide(ALICE, handle, approved=False, digest=action_digest(ACTION))
    assert output["outcome"] == "denied"
    assert host.effect_count() == 0
    assert host.state(ALICE, handle, kind="action").next == ()


def test_valid_approval_records_one_dummy_effect(host):
    handle = start_action(host)
    output = host.decide(ALICE, handle, approved=True, digest=action_digest(ACTION))
    assert output["outcome"] == "approved"
    assert host.effect_count() == 1
    assert host.state(ALICE, handle, kind="action").next == ()


def test_host_denies_nonowner_approval(host):
    handle = start_action(host)
    with pytest.raises(PermissionError):
        host.decide(BOB, handle, approved=True, digest=action_digest(ACTION))
    assert host.effect_count() == 0


def test_host_denies_missing_approver_role(host):
    handle = start_action(host)
    with pytest.raises(PermissionError):
        host.decide(NO_ROLE, handle, approved=True, digest=action_digest(ACTION))
    assert host.effect_count() == 0


def test_host_binds_approval_to_action(host):
    handle = start_action(host)
    with pytest.raises(ValueError, match="match action"):
        host.decide(ALICE, handle, approved=True, digest="not-the-pending-digest")
    assert host.effect_count() == 0
    assert host.state(ALICE, handle, kind="action").next == ("approval",)


def test_typed_decision_rejects_invalid_boolean_then_allows_correction(host):
    handle = start_action(host)
    with pytest.raises(ValidationError):
        host.decide(
            ALICE, handle, approved="not-a-boolean", digest=action_digest(ACTION)
        )
    assert host.effect_count() == 0
    assert host.state(ALICE, handle, kind="action").next == ("approval",)
    host.decide(ALICE, handle, approved=False, digest=action_digest(ACTION))
    assert host.effect_count() == 0


def test_duplicate_host_approval_does_not_repeat_effect(host):
    handle = start_action(host)
    host.decide(ALICE, handle, approved=True, digest=action_digest(ACTION))
    with pytest.raises(ValueError, match="no pending"):
        host.decide(ALICE, handle, approved=True, digest=action_digest(ACTION))
    assert host.effect_count() == 1


def test_two_pending_threads_have_independent_decisions(host):
    a, b = start_action(host, ALICE), start_action(host, BOB)
    host.decide(ALICE, a, approved=True, digest=action_digest(ACTION))
    assert host.state(BOB, b, kind="action").next == ("approval",)
    host.decide(BOB, b, approved=False, digest=action_digest(ACTION))
    assert host.effect_count() == 1


def test_sqlite_checkpoint_and_host_registry_survive_reopen(tmp_path):
    first = LocalHost(tmp_path, "sqlite")
    chat = first.new_thread(ALICE)
    first.append(ALICE, chat, "PERSISTED")
    action = start_action(first)
    first.close()
    second = LocalHost(tmp_path, "sqlite")
    try:
        assert second.state(ALICE, chat).values["messages"] == ["PERSISTED"]
        assert second.state(ALICE, action, kind="action").next == ("approval",)
        with pytest.raises(PermissionError):
            second.decide(BOB, action, approved=True, digest=action_digest(ACTION))
        second.decide(ALICE, action, approved=True, digest=action_digest(ACTION))
        assert second.effect_count() == 1
    finally:
        second.close()


def test_inmemory_saver_has_no_restart_persistence():
    old = memory_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "synthetic-demo"}}
    old.invoke({"messages": ["RAM-ONLY"]}, config)
    fresh = memory_graph(InMemorySaver())
    assert not fresh.get_state(config).values


def test_inmemory_store_has_no_restart_persistence():
    old = InMemoryStore()
    old.put(("demo", "alice"), "note", {"text": "RAM-ONLY"})
    fresh = InMemoryStore()
    assert fresh.get(("demo", "alice"), "note") is None


def test_resume_reexecutes_pre_gate_local_bookkeeping():
    class State(TypedDict):
        value: str

    entries, effects = [], []

    def gate(state):
        entries.append("node-entered")
        approved = interrupt("Approve synthetic action?")
        if approved is True:
            effects.append("dummy-effect")
        return {"value": "done"}

    builder = StateGraph(State)
    builder.add_node("gate", gate)
    builder.add_edge(START, "gate")
    builder.add_edge("gate", END)
    graph = builder.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "synthetic-demo"}}
    graph.invoke({"value": "initial"}, config)
    assert entries == ["node-entered"] and effects == []
    graph.invoke(Command(resume=True), config)
    assert entries == ["node-entered", "node-entered"]
    assert effects == ["dummy-effect"]


def test_async_distinct_threads_roundtrip():
    async def run():
        graph = memory_graph(InMemorySaver())

        async def conversation(number):
            config = {"configurable": {"thread_id": f"synthetic-{number}"}}
            await graph.ainvoke({"messages": [f"marker-{number}"]}, config)
            state = await graph.aget_state(config)
            return state.values["messages"]

        results = await asyncio.gather(*(conversation(i) for i in range(12)))
        assert results == [[f"marker-{i}"] for i in range(12)]

    asyncio.run(run())


def test_calibration_oracle_detects_deliberately_wrong_fixture_result():
    # Test the oracle, not a LangGraph bypass. These are plain Python records.
    def require_partition(records):
        assert records["alice"] == ["A"]
        assert records["bob"] == ["B"]

    require_partition({"alice": ["A"], "bob": ["B"]})
    with pytest.raises(AssertionError):
        require_partition({"alice": ["A", "B"], "bob": ["A", "B"]})


def test_calibration_oracle_detects_preapproval_dummy_effect():
    # No library or vulnerable adapter is involved in the negative control.
    def require_no_effect(effects):
        assert effects == []

    require_no_effect([])
    with pytest.raises(AssertionError):
        require_no_effect(["deliberately-wrong-dummy-effect"])
