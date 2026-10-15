"""
MCP client for the Campus Customs backend.

Spawns mcp_server/server.py as a subprocess and talks to it over the real MCP
stdio transport (JSON-RPC 2.0). Every fact an agent states is fetched through
an actual tools/call round trip, so the tool names recorded in the audit trail
are evidence of calls that happened rather than labels.
"""

import contextvars
import json
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
PROTOCOL_VERSION = "2024-11-05"


class MCPError(RuntimeError):
    pass


class MCPClient:
    """One long-lived server subprocess, serialised behind a lock."""

    def __init__(self):
        self._proc = None
        self._next_id = 0
        self._lock = threading.Lock()
        self.call_log = []

    # -- lifecycle ---------------------------------------------------------

    def _spawn(self):
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "mcp_server.server"],
            cwd=str(PROJECT_ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._next_id = 0
        handshake = self._rpc("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "campus-customs-backend", "version": "1.0.0"},
        })
        self._notify("notifications/initialized")
        return handshake

    def _alive(self):
        return self._proc is not None and self._proc.poll() is None

    def _ensure(self):
        if not self._alive():
            self._spawn()

    def close(self):
        with self._lock:
            if self._alive():
                try:
                    self._proc.stdin.close()
                    self._proc.wait(timeout=5)
                except Exception:
                    self._proc.kill()
            self._proc = None

    # -- transport ---------------------------------------------------------

    def _write(self, message):
        self._proc.stdin.write(json.dumps(message) + "\n")
        self._proc.stdin.flush()

    def _notify(self, method, params=None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._write(msg)

    def _rpc(self, method, params=None):
        self._next_id += 1
        request_id = self._next_id
        msg = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            msg["params"] = params
        self._write(msg)

        line = self._proc.stdout.readline()
        if not line:
            err = self._proc.stderr.read() if self._proc.stderr else ""
            raise MCPError(f"MCP server closed the connection. {err.strip()}")
        response = json.loads(line)
        if "error" in response:
            raise MCPError(response["error"].get("message", "unknown MCP error"))
        return response.get("result", {})

    # -- public ------------------------------------------------------------

    def list_tools(self):
        with self._lock:
            self._ensure()
            return [t["name"] for t in self._rpc("tools/list").get("tools", [])]

    def call(self, name, **arguments):
        """Call one MCP tool and return its parsed result."""
        with self._lock:
            self._ensure()
            result = self._rpc("tools/call", {"name": name, "arguments": arguments})
            if result.get("isError"):
                raise MCPError(result["content"][0]["text"])
            payload = json.loads(result["content"][0]["text"])
            self.call_log.append({"tool": name, "arguments": arguments})
            return payload


mcp = MCPClient()


#
# Agents may delegate concurrently, so attribution cannot be a before/after
# diff on one shared list. Each delegated run gets its own context-local
# bucket; contextvars propagate into async tasks, so concurrent delegations
# never collect each other's calls.
#
_bucket: contextvars.ContextVar = contextvars.ContextVar("mcp_tool_bucket", default=None)


class ToolRecorder:
    """
    Wraps the client for one ticket run so each agent step records exactly the
    tools it actually called, in order, with no duplicates.
    """

    def __init__(self, client=mcp):
        self._client = client
        self._used = []

    def call(self, name, **arguments):
        value = self._client.call(name, **arguments)
        target = _bucket.get()
        if target is None:
            target = self._used
        if name not in target:
            target.append(name)
        return value

    def seen(self):
        """Tools called since the last take(), without resetting."""
        return tuple(self._used)

    def take(self):
        """Return the tools called since the last take() and reset."""
        used, self._used = self._used, []
        return used

    @contextmanager
    def scope(self):
        """
        Collect tool calls made inside this block separately, so one delegated
        agent's calls are never attributed to another.
        """
        own: list = []
        token = _bucket.set(own)
        try:
            yield own
        finally:
            _bucket.reset(token)
