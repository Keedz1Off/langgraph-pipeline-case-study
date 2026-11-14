"""Normal-operation follow-up; all processes/identities/data are synthetic."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from langgraph.store.sqlite import AsyncSqliteStore, SqliteStore

from local_host import LocalHost, Principal
from test_controls import no_network  # noqa: F401 - shared autouse fixture

ALICE = Principal("tenant-one", "alice", True)
BOB = Principal("tenant-one", "bob", True)
OTHER = Principal("tenant-two", "alice", True)
MARKERS = {
    "alice": "SYNTHETIC-ALICE",
    "bob": "SYNTHETIC-BOB",
    "other": "SYNTHETIC-OTHER",
}


def child(root, mode, bundle=None, **extra):
    command = [sys.executable, str(Path(__file__).with_name("process_probe.py"))]
    env = dict(os.environ)
    env.update(
        LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false", PYTHONHASHSEED="0"
    )
    result = subprocess.run(
        command,
        input=json.dumps(
            {"root": str(root.resolve()), "mode": mode, "bundle": bundle, **extra}
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)
    assert observed["pid"] != os.getpid()
    trace_dir = Path(
        os.environ.get("LG_FOLLOWUP_TRACE_DIR", str(root / "process-traces"))
    )
    trace_dir.mkdir(exist_ok=True, parents=True)
    trace = {
        "parent_pid": os.getpid(),
        "child_exit": result.returncode,
        "observed": observed,
        "stderr": result.stderr,
    }
    (trace_dir / f"{observed['instance']}.json").write_text(
        json.dumps(trace, indent=2), encoding="utf-8"
    )
    return observed


@pytest.mark.parametrize("approved", [True, False], ids=["approve", "deny"])
def test_clean_process_checkpoint_memory_and_approval(tmp_path, approved):
    seed = child(tmp_path, "seed")
    bundle = seed["bundle"]
    assert seed["snapshot"]["effects"] == 0
    inspect = child(tmp_path, "inspect", bundle)
    assert inspect["instance"] != seed["instance"]
    assert inspect["snapshot"]["messages"] == {
        name: [marker] for name, marker in MARKERS.items()
    }
    assert inspect["snapshot"]["notes"] == {
        name: {"text": marker} for name, marker in MARKERS.items()
    }
    assert len(inspect["denied"]) == 4
    assert inspect["snapshot"]["pending"] == {
        "alice": ["approval"],
        "bob": ["approval"],
    }
    decided = child(tmp_path, "decide", bundle, principal="alice", approved=approved)
    assert decided["outcome"] == ("approved" if approved else "denied")
    verified = child(tmp_path, "inspect", bundle)
    assert verified["snapshot"]["effects"] == int(approved)
    assert verified["snapshot"]["pending"] == {"alice": [], "bob": ["approval"]}
    repeated = child(tmp_path, "repeat", bundle)
    assert repeated["repeat_rejected"] is True
    assert repeated["snapshot"]["effects"] == int(approved)


def test_store_update_delete_survive_separate_processes(tmp_path):
    seed = child(tmp_path, "seed")
    bundle = seed["bundle"]
    child(tmp_path, "update", bundle)
    updated = child(tmp_path, "inspect", bundle)["snapshot"]
    assert updated["notes"]["alice"] == {"text": "SYNTHETIC-UPDATED"}
    assert updated["notes"]["bob"] == {"text": MARKERS["bob"]}
    child(tmp_path, "delete", bundle)
    deleted = child(tmp_path, "inspect", bundle)["snapshot"]
    assert deleted["notes"]["alice"] is None and deleted["search"]["alice"] == []
    assert deleted["notes"]["bob"] == {"text": MARKERS["bob"]}
    assert deleted["notes"]["other"] == {"text": MARKERS["other"]}


def test_memory_store_negative_persistence_control(tmp_path):
    seed = child(tmp_path, "seed", store_backend="memory")
    assert seed["snapshot"]["notes"]["alice"] == {"text": MARKERS["alice"]}
    fresh = child(tmp_path, "inspect", seed["bundle"], store_backend="memory")
    assert fresh["snapshot"]["notes"] == {name: None for name in MARKERS}
    # SQLite graph/checkpoint memory and host registry survive; RAM store does not.
    assert fresh["snapshot"]["messages"] == {
        name: [marker] for name, marker in MARKERS.items()
    }


@pytest.mark.parametrize("checkpoint_backend", ["memory", "sqlite"])
def test_host_with_actual_persistent_store(tmp_path, checkpoint_backend):
    with SqliteStore.from_conn_string(str(tmp_path / "notes.sqlite")) as store:
        store.setup()
        host = LocalHost(tmp_path, checkpoint_backend, store=store)
        try:
            for principal, marker in [(ALICE, "A"), (BOB, "B"), (OTHER, "C")]:
                host.put_note(principal, "note", marker)
            assert [item.value for item in host.search_notes(ALICE)] == [{"text": "A"}]
            handle = host.new_thread(ALICE)
            with pytest.raises(PermissionError):
                host.append(BOB, handle, "not-permitted")
            host.delete_note(ALICE, "note")
            assert host.get_note(BOB, "note").value == {"text": "B"}
        finally:
            host.close()


@pytest.mark.parametrize("subject", ["alice", "alice2", "Alice"])
def test_sqlite_normal_namespace_segment_and_case_scoping(tmp_path, subject):
    with SqliteStore.from_conn_string(str(tmp_path / "notes.sqlite")) as store:
        store.setup()
        for user in ["alice", "alice2", "Alice"]:
            store.put(("users", "tenant", user, "notes"), "same-key", {"owner": user})
        found = store.search(("users", "tenant", subject))
        assert [item.value for item in found] == [{"owner": subject}]


def test_sync_then_async_readback_same_database(tmp_path):
    path = str(tmp_path / "notes.sqlite")
    namespace = ("users", "tenant", "alice", "notes")
    with SqliteStore.from_conn_string(path) as store:
        store.setup()
        store.put(namespace, "note", {"text": "SYNC"})

    async def async_roundtrip():
        async with AsyncSqliteStore.from_conn_string(path) as store:
            await store.setup()
            assert (await store.aget(namespace, "note")).value == {"text": "SYNC"}
            await store.aput(namespace, "note", {"text": "ASYNC"})

    asyncio.run(async_roundtrip())
    with SqliteStore.from_conn_string(path) as store:
        store.setup()
        assert store.get(namespace, "note").value == {"text": "ASYNC"}


def test_async_sqlite_principal_namespaces_and_reopen(tmp_path):
    path = str(tmp_path / "notes.sqlite")

    async def run():
        async with AsyncSqliteStore.from_conn_string(path) as store:
            await store.setup()
            for principal, marker in [(ALICE, "A"), (BOB, "B"), (OTHER, "C")]:
                await store.aput(
                    LocalHost._namespace(principal), "note", {"text": marker}
                )
        async with AsyncSqliteStore.from_conn_string(path) as store:
            await store.setup()
            found = await store.asearch(LocalHost._namespace(ALICE))
            assert [item.value for item in found] == [{"text": "A"}]
            await store.adelete(LocalHost._namespace(ALICE), "note")
            assert await store.aget(LocalHost._namespace(ALICE), "note") is None
            assert (await store.aget(LocalHost._namespace(BOB), "note")).value == {
                "text": "B"
            }

    asyncio.run(run())
