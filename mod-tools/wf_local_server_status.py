#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fail-closed CN listener status probe for stopped-server publication."""
from __future__ import annotations

import errno
import os
import socket
from pathlib import Path


class ServerStatusError(RuntimeError):
    """The configured CN endpoint could not be classified safely."""


def _endpoint(repo_root: Path) -> tuple[str, int]:
    values: dict[str, str] = {}
    try:
        lines = (Path(repo_root) / ".env").read_text(
            encoding="utf-8"
        ).splitlines()
    except FileNotFoundError:
        lines = []
    except OSError as error:
        raise ServerStatusError(str(error)) from error
    for line in lines:
        token = line.strip()
        if not token or token.startswith("#") or "=" not in token:
            continue
        key, value = token.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")

    host = os.environ.get("CN_LISTEN_HOST")
    if host is None:
        host = values.get("CN_LISTEN_HOST", "127.0.0.1")
    port_token = os.environ.get("CN_LISTEN_PORT")
    if port_token is None:
        port_token = values.get("CN_LISTEN_PORT", "8001")
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    try:
        port = int(port_token)
    except (TypeError, ValueError) as error:
        raise ServerStatusError(f"invalid port {port_token!r}") from error
    if not host or not 1 <= port <= 65535:
        raise ServerStatusError(f"invalid endpoint {host!r}:{port}")
    return host, port


def server_running(repo_root: Path) -> bool:
    """Return false only for an explicit connection-refused result."""
    endpoint = _endpoint(Path(repo_root))
    try:
        with socket.create_connection(endpoint, timeout=0.3):
            return True
    except OSError as error:
        refused = (
            isinstance(error, ConnectionRefusedError)
            or error.errno == errno.ECONNREFUSED
            or getattr(error, "winerror", None) == 10061
        )
        if refused:
            return False
        raise ServerStatusError(str(error)) from error
