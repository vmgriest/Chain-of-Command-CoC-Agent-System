"""Sandboxed execution.  (M2/M3)  ← the security boundary of this project.

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
import contextlib
import logging
import shutil
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from backend.config.schema import ALLOWED_STDIO_BINARIES

if TYPE_CHECKING:
    from backend.config.schema import MCPServerConfig

logger = logging.getLogger("coc.mcp.sandbox")


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
CODE_SANDBOX_IMAGE = "python:3.12-slim"
MAX_OUTPUT_CHARS = 4000

# MCP servers need egress to their declared endpoints only.
# TODO(M3+): derive allowed_egress per server from company_config.json and
#   enforce it with a network policy rather than the blanket `network` flag —
#   currently any server declared with network access can reach anywhere.
MCP_SERVER_POLICY = SandboxPolicy(network=True, timeout_seconds=120)

# Args that let an otherwise-allowlisted `docker` invocation escape the
# sandbox entirely. Rejected regardless of where they appear in `args`.
_DOCKER_ESCAPE_ARGS = ("--privileged", "--network=host", "--pid=host", "--ipc=host")
_DOCKER_SOCKET_MARKERS = ("/var/run/docker.sock", "//./pipe/docker_engine")

_spawned_processes: list[asyncio.subprocess.Process] = []


def assert_binary_allowed(command: str) -> None:
    """Raise SandboxViolation unless `command` resolves to an allowlisted binary.

    Checks the BASENAME, not the raw string — "/usr/bin/bash" and "bash" must
    both be rejected, and "npx" must be accepted whether or not it is absolute.

    Also resolves through shutil.which() and re-checks the resolved basename —
    a symlink named `npx` pointing at a shell would otherwise pass.
    """
    from pathlib import PurePath

    basename = PurePath(command).name
    # Windows: `npx` may resolve as `npx.cmd`; compare the stem too.
    stem = PurePath(basename).stem
    if basename not in ALLOWED_STDIO_BINARIES and stem not in ALLOWED_STDIO_BINARIES:
        msg = (
            f"Refusing to spawn {command!r}: not in the stdio allowlist "
            f"{sorted(ALLOWED_STDIO_BINARIES)}."
        )
        raise SandboxViolation(msg)

    resolved = shutil.which(command)
    if resolved is not None:
        resolved_basename = PurePath(resolved).name
        resolved_stem = PurePath(resolved_basename).stem
        if (
            resolved_basename not in ALLOWED_STDIO_BINARIES
            and resolved_stem not in ALLOWED_STDIO_BINARIES
        ):
            msg = (
                f"Refusing to spawn {command!r}: resolves to {resolved!r}, "
                f"which is not in the stdio allowlist {sorted(ALLOWED_STDIO_BINARIES)}."
            )
            raise SandboxViolation(msg)


def _assert_no_docker_escape(args: list[str]) -> None:
    """Reject docker args that would let a sandboxed container escape.

    `docker` is itself an allowed binary, which means a config could ask to run
    a container that mounts the docker socket (container -> host escape) or
    runs `--privileged` / shares the host network/PID namespace. This is the
    sharpest edge in the allowlist design — do not skip it.
    """
    for arg in args:
        lowered = arg.lower()
        if lowered in _DOCKER_ESCAPE_ARGS or lowered.startswith("--privileged"):
            msg = f"Refusing docker invocation: {arg!r} would break sandbox isolation."
            raise SandboxViolation(msg)
        if any(marker in arg for marker in _DOCKER_SOCKET_MARKERS):
            msg = (
                f"Refusing docker invocation: {arg!r} mounts the docker socket (container escape)."
            )
            raise SandboxViolation(msg)


def resolve_env(env: dict[str, str]) -> dict[str, str]:
    """Expand every `${VAR_NAME}` reference in each value against the HOST's
    actual environment (see the field's docstring in
    backend/config/schema.py) — a value may be a bare reference
    ("${TAVILY_API_KEY}") or embed one inside a larger string
    ("Bearer ${TAVILY_API_KEY}"), same as ordinary shell-style interpolation.

    If ANY reference in a value points at an unset host var, that whole
    key/value pair is dropped with a warning rather than sent half-resolved
    — a literal "${VAR}" leaking into a real request header is worse than
    the header being silently absent. That server just won't authenticate,
    the same "one broken server doesn't take down startup" contract as a
    connection failure.
    """
    import os
    import re

    pattern = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
    resolved: dict[str, str] = {}
    for key, value in env.items():
        missing: list[str] = []
        pieces: list[str] = []
        cursor = 0
        for match in pattern.finditer(value):
            pieces.append(value[cursor : match.start()])
            var_name = match.group(1)
            host_value = os.environ.get(var_name)
            if host_value is None:
                missing.append(var_name)
            else:
                pieces.append(host_value)
            cursor = match.end()
        pieces.append(value[cursor:])

        if missing:
            logger.warning(
                "MCP server env var %r references host variable(s) %s, which "
                "are not set — dropping it. That server may fail to authenticate.",
                key,
                ", ".join(missing),
            )
            continue
        resolved[key] = "".join(pieces)
    return resolved


def _redact_argv_for_log(argv: list[str]) -> str:
    """Render argv for a log line with `-e KEY=VALUE` env values masked — the
    resolved env dict can carry real secrets (API keys), and a log line is
    not a safe place for those."""
    parts: list[str] = []
    mask_next = False
    for part in argv:
        if mask_next:
            key = part.split("=", 1)[0]
            parts.append(f"{key}=***")
            mask_next = False
            continue
        parts.append(part)
        mask_next = part == "-e"
    return " ".join(parts)


def _docker_run_flags(policy: SandboxPolicy, name: str) -> list[str]:
    flags = [
        "run",
        "--rm",  # auto-delete the container when it exits — nothing to clean up later
        "-i",  # keep stdin open, piped — required for the MCP stdio transport to talk to it
        "--name",
        name,
        "--user",
        policy.run_as_user,
        "--pids-limit",
        str(policy.pids_limit),
        "--memory",
        policy.memory_limit,
        "--cpus",
        policy.cpu_limit,
    ]
    if policy.read_only_rootfs:
        flags.append("--read-only")
        # A read-only rootfs plus the nobody user (no home directory at all —
        # its shell entry usually points at /nonexistent) breaks anything that
        # wants scratch space, which is most things: npx caching a package,
        # Python's tempfile module, etc. Found live — `npx` failed outright
        # with "mkdir '/nonexistent': ENOENT" trying to write its cache.
        # A tmpfs mount gives a small writable, memory-backed, non-persistent
        # scratch area without loosening the read-only guarantee on the
        # container's actual filesystem: it's wiped with the container on
        # exit, never touches the image layers, and isn't backed by host disk.
        # Suppresses ruff's flake8-bandit S108 below, which flags hardcoded
        # /tmp paths as an insecure-shared-directory risk — that rule is
        # about the HOST's /tmp; this is a path *inside* an isolated,
        # ephemeral, per-container tmpfs mount, not shared with anything.
        flags += ["--tmpfs", "/tmp:rw,exec,size=100m,mode=1777", "-e", "HOME=/tmp"]  # noqa: S108
    for cap in policy.drop_capabilities:
        flags += ["--cap-drop", cap]
    if not policy.network:
        flags += ["--network", "none"]
    for mount in policy.allowed_mounts:
        flags += ["--mount", mount]
    return flags


def docker_argv_for_server(config: MCPServerConfig) -> list[str]:
    """Build the full `docker run ...` argv that runs `config`'s stdio server
    inside a locked-down container.

      1. assert_binary_allowed(config.command)   <- before anything else
      2. Wrap in `docker run` with MCP_SERVER_POLICY's isolation flags applied

    Pure argument construction — does not spawn anything. Used by
    spawn_mcp_server() below (a direct asyncio spawn) AND by
    backend.mcp.registry, which hands the resulting (command="docker", args)
    pair to langchain-mcp-adapters' MultiServerMCPClient so THAT library owns
    the subprocess lifecycle. Either way, the isolation lives in the argv, not
    in who calls it.
    """
    if config.command is None:
        msg = f"MCP server {config.name!r}: stdio transport requires a command"
        raise SandboxViolation(msg)

    assert_binary_allowed(config.command)
    _assert_no_docker_escape(config.args)

    container_name = f"coc-mcp-{config.name}-{uuid.uuid4().hex[:8]}"

    env_flags: list[str] = []
    for key, value in resolve_env(config.env).items():
        env_flags += ["-e", f"{key}={value}"]

    if config.command == "docker":
        # Already a container invocation (e.g. `docker run <third-party-image>`).
        # Still route it through the isolation flags rather than trusting the
        # config's own docker invocation to be sandboxed.
        return [
            "docker",
            *_docker_run_flags(MCP_SERVER_POLICY, container_name),
            *env_flags,
            *config.args,
        ]

    # uvx / npx: run INSIDE a locked-down docker container rather than
    # directly on the host — a third-party stdio server is untrusted code
    # regardless of which package runner launches it.
    image = (
        "node:20-slim"
        if config.command == "npx"
        else "ghcr.io/astral-sh/uv:python3.12-bookworm-slim"
    )
    return [
        "docker",
        *_docker_run_flags(MCP_SERVER_POLICY, container_name),
        *env_flags,
        image,
        config.command,
        *config.args,
    ]


async def spawn_mcp_server(config: MCPServerConfig) -> asyncio.subprocess.Process:
    """Launch a stdio MCP server directly (stdin/stdout pipes for the MCP
    transport), registered for graceful shutdown (see shutdown_all below).

    backend.mcp.registry does NOT use this — it hands docker_argv_for_server()'s
    output to MultiServerMCPClient instead, which needs to own the subprocess
    itself to speak the MCP stdio protocol over it. This function exists for
    direct/manual spawning (tests, debugging) where nothing else needs the pipes.
    """
    argv = docker_argv_for_server(config)
    logger.info("Spawning MCP server %r: %s", config.name, _redact_argv_for_log(argv))
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _spawned_processes.append(process)
    return process


async def run_sandboxed_code(code: str, language: str = "python") -> str:
    """Execute untrusted generated code under CODE_SANDBOX_POLICY.

    No network, read-only rootfs, non-root, hard timeout. Return combined
    stdout/stderr truncated to a sane length — an agent does not need 10MB of
    output, and neither does the context window.

    On timeout: kill the container (do not just cancel the coroutine — an
    orphaned container keeps burning CPU) and return a clear timeout message.
    """
    if language != "python":
        return f"Refused: sandboxed execution only supports 'python' right now, got {language!r}."

    container_name = f"coc-sandbox-{uuid.uuid4().hex[:8]}"
    argv = [
        "docker",
        *_docker_run_flags(CODE_SANDBOX_POLICY, container_name),
        CODE_SANDBOX_IMAGE,
        "python",
        "-c",
        code,
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return "Sandbox unavailable: the `docker` binary was not found on this host."

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=CODE_SANDBOX_POLICY.timeout_seconds
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        # `docker run --rm` normally removes the container on exit, but a killed
        # process may not clean up in time — force it so a timed-out sandbox run
        # doesn't keep burning CPU on an orphaned container.
        kill_proc = await asyncio.create_subprocess_exec(
            "docker",
            "rm",
            "-f",
            container_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await kill_proc.wait()
        timeout = CODE_SANDBOX_POLICY.timeout_seconds
        return f"Sandboxed execution timed out after {timeout}s and was terminated."

    output = (stdout + stderr).decode(errors="replace")
    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + "\n... (truncated)"
    return output or "(no output)"


async def shutdown_all() -> None:
    """Terminate every spawned process and remove every container.

    Wired into the FastAPI lifespan shutdown hook. Orphaned containers after a
    dev-server restart get old fast.
    """
    while _spawned_processes:
        process = _spawned_processes.pop()
        if process.returncode is not None:
            continue
        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=5)
        except (TimeoutError, ProcessLookupError):
            with contextlib.suppress(ProcessLookupError):
                process.kill()
