"""Synthetic local host policy around LangGraph. Not a production service."""

from __future__ import annotations

import hashlib
import json
import operator
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command, interrupt
from pydantic import BaseModel, ConfigDict, StrictBool
from typing_extensions import TypedDict


@dataclass(frozen=True)
class Principal:
    """Already-authenticated synthetic identity, supplied by the test harness."""

    tenant: str
    subject: str
    approver: bool = False


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approved: StrictBool
    action_digest: str


class MemoryState(TypedDict):
    messages: Annotated[list[str], operator.add]


class ActionState(TypedDict):
    handle: str
    action: dict
    action_digest: str
    outcome: str


def action_digest(action: dict) -> str:
    payload = json.dumps(action, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def memory_graph(saver):
    builder = StateGraph(MemoryState)
    builder.add_node("retain", lambda state: {})
    builder.add_edge(START, "retain")
    builder.add_edge("retain", END)
    return builder.compile(checkpointer=saver)


class LocalHost:
    """Fixture-owned ACL, registry and dummy effects. No HTTP, JWT or LLM."""

    def __init__(self, root: Path, backend: str = "memory", store=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.backend = backend
        self.db = sqlite3.connect(self.root / "host.sqlite", check_same_thread=False)
        self.db.executescript(
            """CREATE TABLE IF NOT EXISTS threads(
                handle TEXT PRIMARY KEY, tenant TEXT, subject TEXT, kind TEXT,
                action_json TEXT, digest TEXT, status TEXT);
            CREATE TABLE IF NOT EXISTS effects(
                handle TEXT PRIMARY KEY, digest TEXT NOT NULL);
            """
        )
        self.db.commit()
        self.checkpoint_conn = None
        if backend == "sqlite":
            self.checkpoint_conn = sqlite3.connect(
                self.root / "checkpoints.sqlite", check_same_thread=False
            )
            self.saver = SqliteSaver(self.checkpoint_conn)
        elif backend == "memory":
            self.saver = InMemorySaver()
        else:
            raise ValueError(backend)
        self.store = store if store is not None else InMemoryStore()
        self.memory = memory_graph(self.saver)
        self.action = self._action_graph()

    def close(self):
        if self.checkpoint_conn is not None:
            self.checkpoint_conn.close()
        self.db.close()

    def _thread(self, principal: Principal, handle: str, kind: str):
        row = self.db.execute(
            "SELECT tenant, subject, kind, action_json, digest, status "
            "FROM threads WHERE handle=?",
            (handle,),
        ).fetchone()
        if row is None or row[:3] != (principal.tenant, principal.subject, kind):
            raise PermissionError("thread not permitted")
        return row

    @staticmethod
    def _config(handle: str):
        return {"configurable": {"thread_id": handle}}

    @staticmethod
    def _namespace(principal: Principal):
        return ("users", principal.tenant, principal.subject, "notes")

    def new_thread(self, principal: Principal, kind="memory", action=None):
        if kind not in ("memory", "action"):
            raise ValueError(kind)
        if kind == "action" and action is None:
            raise ValueError("action required")
        # Handles are server-issued. Clients never supply saver configuration.
        handle = str(uuid4())
        encoded = json.dumps(action, sort_keys=True) if action is not None else None
        digest = action_digest(action) if action is not None else None
        self.db.execute(
            "INSERT INTO threads VALUES(?,?,?,?,?,?,?)",
            (handle, principal.tenant, principal.subject, kind, encoded, digest, "new"),
        )
        self.db.commit()
        return handle

    def append(self, principal, handle, message):
        self._thread(principal, handle, "memory")
        return self.memory.invoke({"messages": [message]}, self._config(handle))

    def state(self, principal, handle, kind="memory"):
        self._thread(principal, handle, kind)
        graph = self.memory if kind == "memory" else self.action
        return graph.get_state(self._config(handle))

    def history(self, principal, handle):
        self._thread(principal, handle, "memory")
        return list(self.memory.get_state_history(self._config(handle)))

    def delete_thread(self, principal, handle):
        self._thread(principal, handle, "memory")
        self.saver.delete_thread(handle)
        self.db.execute("DELETE FROM threads WHERE handle=?", (handle,))
        self.db.commit()

    def put_note(self, principal, key, value):
        self.store.put(self._namespace(principal), key, {"text": value})

    def get_note(self, principal, key):
        return self.store.get(self._namespace(principal), key)

    def search_notes(self, principal):
        return self.store.search(self._namespace(principal), limit=100)

    def delete_note(self, principal, key):
        self.store.delete(self._namespace(principal), key)

    def request_action(self, principal, handle):
        row = self._thread(principal, handle, "action")
        if row[5] != "new":
            raise ValueError("already requested")
        self.db.execute("UPDATE threads SET status='pending' WHERE handle=?", (handle,))
        self.db.commit()
        return self.action.invoke(
            {"handle": handle, "action": json.loads(row[3]), "action_digest": row[4]},
            self._config(handle),
        )

    def decide(self, principal, handle, *, approved, digest):
        row = self._thread(principal, handle, "action")
        if not principal.approver:
            raise PermissionError("approver role required")
        if row[5] != "pending":
            raise ValueError("no pending approval")
        if digest != row[4]:
            raise ValueError("approval does not match action")
        return self.action.invoke(
            Command(resume={"approved": approved, "action_digest": digest}),
            self._config(handle),
        )

    def effect_count(self):
        return self.db.execute("SELECT count(*) FROM effects").fetchone()[0]

    def _action_graph(self):
        def approval(state: ActionState):
            answer = interrupt(
                {"action": state["action"], "action_digest": state["action_digest"]},
                response_schema=Decision,
            )
            if answer.action_digest != state["action_digest"]:
                raise ValueError("action binding mismatch")
            # The protected effect is AFTER the gate, with explicit deny handling.
            if answer.approved is not True:
                self.db.execute(
                    "UPDATE threads SET status='denied' WHERE handle=?",
                    (state["handle"],),
                )
                self.db.commit()
                return {"outcome": "denied"}
            # A local SQL row is the entire effect; no email, payments or tools.
            self.db.execute(
                "INSERT OR IGNORE INTO effects(handle,digest) VALUES(?,?)",
                (state["handle"], state["action_digest"]),
            )
            self.db.execute(
                "UPDATE threads SET status='approved' WHERE handle=?",
                (state["handle"],),
            )
            self.db.commit()
            return {"outcome": "approved"}

        builder = StateGraph(ActionState)
        builder.add_node("approval", approval)
        builder.add_edge(START, "approval")
        builder.add_edge("approval", END)
        return builder.compile(checkpointer=self.saver)
