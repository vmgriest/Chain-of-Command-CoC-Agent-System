"""Sandboxed execution.  (M3)  ← the security boundary of this project.

Local MCP servers are arbitrary third-party code, and so is anything the code
sandbox runs. Both are treated accordingly.

Two layers:

  1. BINARY ALLOWLIST — stdio transport may only launch uvx, npx, or docker.
     Validated at config parse time (backend/config/schema.py) for a good error
     message, and enforced AGAIN here at spawn. Parse-time validation is
     usability; spawn-time is security. Never rely on the parse-time check alone
     — config can be mutated in memory after loading.

  2. CONTAINER ISOLATION — non-root, read-only rootfs, dropped capabilities,
     explicit mount allowlist, restricted egress, resource caps.
"""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from backend.config.schema import ALLOWED_STDIO_BINARIES

if TYPE_CHECKING:
    from backend.config.schema import MCPServerConfig


class SandboxViolation(RuntimeError):
    """Raised when a spawn is refused. Never downgrade this to a warning."""


@dataclass(frozen=True)
class SandboxPolicy:
    """Container restrictions applied to every sandboxed process.

    Defaults are deliberately strict. A server needing more should have to say
    so explicitly in config, so the loosening is visible in review.
    """

    network: bool = False
    read_only_rootfs: bool = True
    run_as_user: str = "65534:65534"  # nobody:nogroup
    drop_capabilities: tuple[str, ...] = ("ALL",)
    memory_limit: str = "512m"
    cpu_limit: str = "1.0"
    pids_limit: int = 128
    timeout_seconds: int = 30
    allowed_mounts: tuple[str, ...] = field(default=())
    allowed_egress: tuple[str, ...] = field(default=())


CODE_SANDBOX_POLICY = SandboxPolicy()  # no network at all for run_code()

# MCP servers need egress to their declared endpoints only.
# TODO(M3): derive allowed_egress per server from company_config.json.
MCP_SERVER_POLICY = SandboxPolicy(network=True, timeout_seconds=120)


def assert_binary_allowed(command: str) -> None:
    """TODO(M3): raise SandboxViolation unless `command` is in the allowlist.

    Check the BASENAME, not the raw string — "/usr/bin/bash" and "bash" must both
    be rejected, and "npx" must be accepted whether or not it is absolute.

    TODO(M3): also resolve through shutil.which() and re-check the resolved
      basename. A symlink named `npx` pointing at a shell would otherwise pass.
    """
    raise NotImplementedError


async def spawn_mcp_server(config: MCPServerConfig) -> asyncio.subprocess.Process:
    """TODO(M3): launch a stdio MCP server under MCP_SERVER_POLICY.

      1. assert_binary_allowed(config.command)   <- before anything else
      2. Wrap in `docker run` with the policy flags applied
      3. Start with stdin/stdout pipes for the MCP transport
      4. Register for graceful shutdown (see shutdown_all below)

    TODO(M3): `docker` is itself an allowed binary, which means a config could ask
      to run a container that mounts the docker socket and escapes. Reject
      /var/run/docker.sock in args, and reject --privileged and --network=host.
      This is the sharpest edge in the allowlist design — do not skip it.
    """
    raise NotImplementedError


async def run_sandboxed_code(code: str, language: str = "python") -> str:
    """TODO(M2/M3): execute untrusted generated code under CODE_SANDBOX_POLICY.

    No network, read-only rootfs, non-root, hard timeout. Return combined
    stdout/stderr truncated to a sane length — an agent does not need 10MB of
    output, and neither does the context window.

    On timeout: kill the container (do not just cancel the coroutine — an
    orphaned container keeps burning CPU) and return a clear timeout message.
    """
    raise NotImplementedError


async def shutdown_all() -> None:
    """TODO(M3): terminate every spawned process and remove every container.

    Wire into the FastAPI lifespan shutdown hook. Orphaned containers after a
    dev-server restart get old fast.
    """
    raise NotImplementedError


_ = (shutil, ALLOWED_STDIO_BINARIES)  # staged for the implementations above
