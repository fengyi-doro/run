"""Dify 1.17.1 Console adapter, reusing the installed CLI's saved session."""

from __future__ import annotations

import json
import re
import sys
import time
from contextlib import contextmanager
from typing import Any, Iterator

from dify_workflow.remote_client import DifyRemoteClient
from dify_workflow.remote_service import RemoteService


def redact(value: Any) -> Any:
    """Keep session and common provider credentials out of reports."""
    secret_fields = {
        "access_token", "refresh_token", "csrf_token", "api_key", "apikey",
        "password", "secret", "credentials", "authorization", "cookie",
    }
    if isinstance(value, dict):
        return {
            key: "[redacted]" if key.lower() in secret_fields else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)Bearer\s+[^\s\"']+", "Bearer [redacted]", value)
        return re.sub(r"\bsk-[A-Za-z0-9_-]+", "[redacted]", value)
    return value


def parse_sse(lines: Iterator[str]) -> Iterator[dict[str, Any]]:
    """Read complete SSE frames, including comments and multi-line data."""
    chunks: list[str] = []
    for line in lines:
        line = line.lstrip("\ufeff")
        if line == "":
            if chunks:
                raw = "\n".join(chunks)
                chunks.clear()
                if raw != "[DONE]":
                    payload = json.loads(raw)
                    if not isinstance(payload, dict):
                        raise ValueError("Expected a JSON object in the Dify event stream")
                    yield payload
        elif line.startswith("data:"):
            chunks.append(line[5:].lstrip(" "))
    # An unterminated frame is deliberately discarded: it may be truncated.


class ConsoleClient(DifyRemoteClient):
    """Small compatibility adapter for the pinned third-party client."""

    def json_request(
        self, method: str, path: str, *, body: dict | None = None,
        params: dict | None = None,
    ) -> Any:
        return self._request(method, path, json_body=body, params=params).json()

    def events(self, path: str, body: dict, timeout: float) -> Iterator[dict]:
        deadline = time.monotonic() + timeout
        # Refresh only after an authentication rejection, before execution begins.
        for attempt in range(2):
            headers = {**self._request_headers(True), "Accept": "text/event-stream"}
            with self._client.stream("POST", path, json=body, headers=headers) as response:
                self._update_session_from_cookies()
                if response.status_code == 401 and attempt == 0:
                    response.read()
                    self.refresh_session()
                    continue
                if response.status_code >= 400:
                    response.read()
                    raise self._build_error(response)
                if "text/event-stream" not in response.headers.get("content-type", ""):
                    response.read()
                    raise ValueError("Dify did not return an SSE stream for draft execution")

                def timed_lines() -> Iterator[str]:
                    for line in response.iter_lines():
                        if time.monotonic() > deadline:
                            raise TimeoutError("Draft run exceeded the configured timeout")
                        yield line

                yield from parse_sse(timed_lines())
                return


@contextmanager
def console(profile_name: str | None, timeout: float = 120) -> Iterator[ConsoleClient]:
    service = RemoteService(timeout=timeout)
    credentials, name, profile = service._load_profile(profile_name)
    original = service._client_for_profile(profile)
    session = original.session
    original.close()
    with ConsoleClient(profile.server, session=session, timeout=timeout) as client:
        try:
            service._ensure_workspace(client, profile)
            yield client
        finally:
            service._persist_profile(credentials, name, profile, client)


def stop_run(client: ConsoleClient, app_id: str, task_id: str) -> Any:
    return client.json_request(
        "POST", f"/apps/{app_id}/workflow-runs/tasks/{task_id}/stop", body={},
    )


def run_draft(
    client: ConsoleClient, app_id: str, inputs: dict[str, Any], *,
    timeout: float = 120, quiet: bool = False,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "app_id": app_id, "status": "incomplete", "outputs": {},
        "workflow_run_id": None, "task_id": None, "nodes": [], "events": [],
    }
    try:
        for event in client.events(
            f"/apps/{app_id}/workflows/draft/run", {"inputs": inputs, "files": []}, timeout,
        ):
            event = redact(event)
            report["events"].append(event)
            kind = event.get("event")
            fields = event.get("data") or {}
            report["task_id"] = event.get("task_id") or report["task_id"]
            report["workflow_run_id"] = event.get("workflow_run_id") or report["workflow_run_id"]
            if kind == "workflow_started":
                report["workflow_run_id"] = fields.get("id") or report["workflow_run_id"]
            if kind in {"node_finished", "node_failed", "node_retry"}:
                node = {key: fields.get(key) for key in (
                    "node_id", "node_type", "title", "status", "error", "elapsed_time",
                )}
                report["nodes"].append(node)
                if not quiet:
                    print(f"{node['node_id']}: {node['status']} {node['error'] or ''}", file=sys.stderr)
            if kind == "error":
                report.update(status="failed", error=event.get("message", "Dify stream error"))
            if kind == "workflow_finished":
                for key in ("status", "outputs", "error", "elapsed_time", "total_tokens", "total_steps"):
                    if key in fields:
                        report[key] = fields[key]
                return report
    except (Exception, KeyboardInterrupt) as exc:
        report.update(status="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                      error=str(redact(str(exc))) or type(exc).__name__)
        if report["task_id"]:
            try:
                stop_run(client, app_id, report["task_id"])
                report["stop_requested"] = True
            except Exception:
                report["stop_requested"] = False
    if report["status"] == "incomplete":
        report["error"] = "Event stream ended without workflow_finished; success is unverified"
    return report
