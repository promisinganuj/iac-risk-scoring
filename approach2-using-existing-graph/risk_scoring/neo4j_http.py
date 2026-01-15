from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional


class Neo4jHttpError(RuntimeError):
    pass


_READONLY_FORBIDDEN = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|CALL|LOAD\s+CSV)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Neo4jHttpConfig:
    http_url: str
    username: str
    password: str
    database: str = "neo4j"
    timeout_secs: float = 10.0

    @staticmethod
    def from_env() -> "Neo4jHttpConfig":
        http_url = (os.environ.get("NEO4J_HTTP_URL") or "").strip()
        if not http_url:
            host = (os.environ.get("NEO4J_HOST") or "localhost").strip() or "localhost"
            port = (os.environ.get("NEO4J_HTTP_PORT") or "7474").strip() or "7474"
            http_url = f"http://{host}:{port}"

        username = (os.environ.get("NEO4J_USERNAME") or "neo4j").strip() or "neo4j"
        password = (os.environ.get("NEO4J_PASSWORD") or "").strip()
        if not password:
            raise Neo4jHttpError(
                "Missing NEO4J_PASSWORD. Ensure you've loaded approach2-using-existing-graph/.env before running."
            )

        database = (os.environ.get("NEO4J_DATABASE") or "neo4j").strip() or "neo4j"

        timeout_raw = (os.environ.get("NEO4J_HTTP_TIMEOUT_SECS") or "").strip()
        timeout_secs = 10.0
        if timeout_raw:
            try:
                timeout_secs = float(timeout_raw)
            except ValueError as e:
                raise Neo4jHttpError(f"Invalid NEO4J_HTTP_TIMEOUT_SECS: {timeout_raw!r}") from e

        return Neo4jHttpConfig(
            http_url=http_url.rstrip("/"),
            username=username,
            password=password,
            database=database,
            timeout_secs=timeout_secs,
        )


def _assert_readonly(cypher: str) -> None:
    if _READONLY_FORBIDDEN.search(cypher):
        raise Neo4jHttpError("Refusing to run non-read-only Cypher (forbidden keyword found).")


def run_cypher_readonly(
    *,
    config: Neo4jHttpConfig,
    cypher: str,
    params: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    """Run read-only Cypher via Neo4j transactional HTTP endpoint.

    Returns a list of dict rows mapping column names to values.
    """

    _assert_readonly(cypher)

    url = f"{config.http_url}/db/{config.database}/tx/commit"
    body = json.dumps({"statements": [{"statement": cypher, "parameters": dict(params)}]}).encode(
        "utf-8"
    )

    token = base64.b64encode(f"{config.username}:{config.password}".encode("utf-8")).decode(
        "ascii"
    )

    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Basic {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=config.timeout_secs) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        # Try to surface the response body for debugging (auth, db not ready, etc.).
        try:
            detail = e.read().decode("utf-8")
        except Exception:
            detail = ""
        raise Neo4jHttpError(f"Neo4j HTTP error {e.code}: {detail or e.reason}") from e
    except urllib.error.URLError as e:
        raise Neo4jHttpError(
            "Failed to reach Neo4j over HTTP. Is the docker container running and ports exposed?"
        ) from e

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise Neo4jHttpError(f"Invalid JSON from Neo4j HTTP endpoint: {raw[:2000]}") from e

    errors = payload.get("errors") or []
    if errors:
        first = errors[0]
        code = first.get("code")
        message = first.get("message")
        raise Neo4jHttpError(f"Neo4j query failed: {code}: {message}")

    results = payload.get("results") or []
    if not results:
        return []

    result0 = results[0]
    columns = result0.get("columns") or []
    data = result0.get("data") or []

    rows: List[Dict[str, Any]] = []
    for entry in data:
        # Each entry has "row": [..] (and optionally "meta").
        values = entry.get("row")
        if not isinstance(values, list):
            continue
        row: Dict[str, Any] = {}
        for idx, col in enumerate(columns):
            if not isinstance(col, str):
                continue
            row[col] = values[idx] if idx < len(values) else None
        rows.append(row)

    return rows
