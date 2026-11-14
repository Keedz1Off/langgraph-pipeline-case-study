"""Synthetic child process: clean SQLite lifecycle, no real users or network."""

import json
import os
import socket
import sys
from contextlib import ExitStack
from pathlib import Path
from uuid import uuid4

from langgraph.store.memory import InMemoryStore
from langgraph.store.sqlite import SqliteStore

from local_host import LocalHost, Principal, action_digest

PRINCIPALS = {
    "alice": Principal("tenant-one", "alice", True),
    "bob": Principal("tenant-one", "bob", True),
    "other": Principal("tenant-two", "alice", True),
}
MARKERS = {
    "alice": "SYNTHETIC-ALICE",
    "bob": "SYNTHETIC-BOB",
    "other": "SYNTHETIC-OTHER",
}
ACTION = {"operation": "record_demo", "record": "synthetic-only"}


def deny_network(*args, **kwargs):
    raise AssertionError("Network disabled in synchronous synthetic child")


def snapshot(host, bundle):
    return {
        "messages": {
            name: host.state(principal, bundle["chats"][name]).values["messages"]
            for name, principal in PRINCIPALS.items()
        },
        "notes": {
            name: (
                item.value if (item := host.get_note(principal, "shared-key")) else None
            )
            for name, principal in PRINCIPALS.items()
        },
        "search": {
            name: [item.value for item in host.search_notes(principal)]
            for name, principal in PRINCIPALS.items()
        },
        "pending": {
            name: list(host.state(PRINCIPALS[name], handle, "action").next)
            for name, handle in bundle["actions"].items()
        },
        "effects": host.effect_count(),
    }


def main():
    # Fixture is synchronous: no loopback exception is required here.
    socket.create_connection = deny_network
    socket.socket.connect = deny_network
    request = json.load(sys.stdin)
    root = Path(request["root"]).resolve()
    root.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        if request.get("store_backend", "sqlite") == "sqlite":
            store = stack.enter_context(
                SqliteStore.from_conn_string(str(root / "notes.sqlite"))
            )
            store.setup()
        else:
            store = InMemoryStore()
        host = LocalHost(root, "sqlite", store=store)
        stack.callback(host.close)
        bundle = request.get("bundle")
        mode = request["mode"]
        result = {"pid": os.getpid(), "instance": str(uuid4()), "mode": mode}
        if mode == "seed":
            bundle = {"chats": {}, "actions": {}}
            for name, principal in PRINCIPALS.items():
                handle = host.new_thread(principal)
                bundle["chats"][name] = handle
                host.append(principal, handle, MARKERS[name])
                host.put_note(principal, "shared-key", MARKERS[name])
            for name in ("alice", "bob"):
                handle = host.new_thread(PRINCIPALS[name], "action", ACTION)
                bundle["actions"][name] = handle
                output = host.request_action(PRINCIPALS[name], handle)
                assert len(output["__interrupt__"]) == 1
            result["bundle"] = bundle
        elif mode == "inspect":
            denied = []
            for name, callback in [
                (
                    "other-owner-read",
                    lambda: host.state(PRINCIPALS["bob"], bundle["chats"]["alice"]),
                ),
                (
                    "other-tenant-read",
                    lambda: host.state(PRINCIPALS["other"], bundle["chats"]["alice"]),
                ),
                (
                    "other-owner-approval",
                    lambda: host.decide(
                        PRINCIPALS["bob"],
                        bundle["actions"]["alice"],
                        approved=True,
                        digest=action_digest(ACTION),
                    ),
                ),
                (
                    "missing-role-approval",
                    lambda: host.decide(
                        Principal("tenant-one", "alice", False),
                        bundle["actions"]["alice"],
                        approved=True,
                        digest=action_digest(ACTION),
                    ),
                ),
            ]:
                try:
                    callback()
                except PermissionError:
                    denied.append(name)
                else:
                    raise AssertionError(f"Host did not reject {name}")
            result["denied"] = denied
        elif mode == "decide":
            name = request["principal"]
            result["outcome"] = host.decide(
                PRINCIPALS[name],
                bundle["actions"][name],
                approved=request["approved"],
                digest=action_digest(ACTION),
            )["outcome"]
        elif mode == "repeat":
            try:
                host.decide(
                    PRINCIPALS["alice"],
                    bundle["actions"]["alice"],
                    approved=True,
                    digest=action_digest(ACTION),
                )
            except ValueError as exc:
                assert "no pending" in str(exc)
                result["repeat_rejected"] = True
            else:
                raise AssertionError("Sequential duplicate decision was accepted")
        elif mode == "update":
            host.put_note(PRINCIPALS["alice"], "shared-key", "SYNTHETIC-UPDATED")
        elif mode == "delete":
            host.delete_note(PRINCIPALS["alice"], "shared-key")
        else:
            raise ValueError(mode)
        result["snapshot"] = snapshot(host, bundle)
        result["resources"] = {
            "registry": str(root / "host.sqlite"),
            "checkpoints": str(root / "checkpoints.sqlite"),
            "notes": str(root / "notes.sqlite")
            if request.get("store_backend", "sqlite") == "sqlite"
            else "InMemoryStore",
        }
    # ExitStack has closed every owned connection before success is printed.
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
