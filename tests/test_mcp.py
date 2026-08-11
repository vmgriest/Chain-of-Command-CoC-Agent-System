"""MCP sandbox + registry tests.  (M3)

Docker itself is not exercised here — a suite that requires Docker is a suite
nobody runs (same reasoning as conftest.py's stance on Ollama). Sandbox tests
check argv construction and the allowlist; registry tests fake
MultiServerMCPClient. Both were additionally live-verified by hand against a
real Docker daemon and a real running internal_server.py during development.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# assert_binary_allowed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("binary", ["uvx", "npx", "docker"])
def test_assert_binary_allowed_accepts_allowlisted(binary: str) -> None:
    from backend.mcp.sandbox import assert_binary_allowed

    assert_binary_allowed(binary)  # must not raise


@pytest.mark.parametrize("binary", ["bash", "sh", "python", "/usr/bin/bash", "cmd.exe"])
def test_assert_binary_allowed_rejects_disallowed(binary: str) -> None:
    from backend.mcp.sandbox import SandboxViolation, assert_binary_allowed

    with pytest.raises(SandboxViolation):
        assert_binary_allowed(binary)


def test_assert_binary_allowed_rejects_symlink_resolving_off_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A binary named `npx` that resolves (via PATH/symlink) to something else
    entirely must still be rejected — the basename check alone isn't enough."""
    from backend.mcp.sandbox import SandboxViolation, assert_binary_allowed

    monkeypatch.setattr("shutil.which", lambda _cmd: "/usr/bin/bash")
    with pytest.raises(SandboxViolation):
        assert_binary_allowed("npx")


# ---------------------------------------------------------------------------
# docker escape args
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_args",
    [
        ["--privileged"],
        ["--network=host"],
        ["--pid=host"],
        ["-v", "/var/run/docker.sock:/var/run/docker.sock"],
    ],
)
def test_docker_argv_rejects_escape_args(bad_args: list[str]) -> None:
    from backend.config.schema import MCPServerConfig, Tier
    from backend.mcp.sandbox import SandboxViolation, docker_argv_for_server

    config = MCPServerConfig(
        name="evil", transport="stdio", command="docker", args=bad_args, tiers=[Tier.MANAGER]
    )
    with pytest.raises(SandboxViolation):
        docker_argv_for_server(config)


def test_docker_argv_wraps_uvx_in_isolated_container() -> None:
    from backend.config.schema import MCPServerConfig, Tier
    from backend.mcp.sandbox import docker_argv_for_server

    config = MCPServerConfig(
        name="orders",
        transport="stdio",
        command="uvx",
        args=["acme-orders-mcp"],
        tiers=[Tier.MANAGER],
    )
    argv = docker_argv_for_server(config)
    assert argv[0] == "docker"
    assert "--read-only" in argv
    assert "--cap-drop" in argv
    # MCP_SERVER_POLICY allows network (servers need to reach their declared
    # endpoints) — unlike the code sandbox, "--network none" is NOT forced.
    assert "--network" not in argv
    assert "uvx" in argv
    assert "acme-orders-mcp" in argv


def test_docker_argv_gives_writable_executable_tmp_under_read_only_rootfs() -> None:
    """Regression test: a read-only rootfs + the nobody user (no home
    directory) breaks anything needing scratch space — found live in two
    stages: npx first failed outright trying to write its cache ("mkdir
    '/nonexistent': ENOENT"), and after adding a tmpfs mount, failed AGAIN
    with "Permission denied" running the package it had just downloaded,
    because Docker's tmpfs defaults to noexec unless told otherwise. A tmpfs
    mount at /tmp with explicit `exec`, plus HOME=/tmp, fixes both without
    loosening the read-only guarantee: tmpfs is memory-backed and wiped with
    the container, never touching the image or host disk."""
    from backend.config.schema import MCPServerConfig, Tier
    from backend.mcp.sandbox import docker_argv_for_server

    config = MCPServerConfig(
        name="web_search", transport="stdio", command="npx", args=["-y", "pkg"], tiers=[Tier.CEO]
    )
    argv = docker_argv_for_server(config)
    assert "--read-only" in argv
    tmpfs_idx = argv.index("--tmpfs")
    tmpfs_opts = argv[tmpfs_idx + 1]
    assert tmpfs_opts.startswith("/tmp:")  # noqa: S108 - path inside an isolated container tmpfs, not the host's
    assert "exec" in tmpfs_opts.split(":", 1)[1].split(",")
    assert "noexec" not in tmpfs_opts
    assert "HOME=/tmp" in argv


def test_docker_argv_is_idempotent_shape_for_repeated_calls() -> None:
    """Each call gets a fresh unique container name but the same structure —
    two servers with identical config must not collide on --name."""
    from backend.config.schema import MCPServerConfig, Tier
    from backend.mcp.sandbox import docker_argv_for_server

    config = MCPServerConfig(
        name="orders", transport="stdio", command="npx", args=["-y", "pkg"], tiers=[Tier.MANAGER]
    )
    argv1 = docker_argv_for_server(config)
    argv2 = docker_argv_for_server(config)
    name1 = argv1[argv1.index("--name") + 1]
    name2 = argv2[argv2.index("--name") + 1]
    assert name1 != name2


# ---------------------------------------------------------------------------
# env-var passthrough (external MCP servers, e.g. Brave Search)
# ---------------------------------------------------------------------------


def test_resolve_env_expands_host_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.mcp.sandbox import resolve_env

    monkeypatch.setenv("BRAVE_API_KEY", "sk-real-secret-value")
    resolved = resolve_env({"BRAVE_API_KEY": "${BRAVE_API_KEY}"})
    assert resolved == {"BRAVE_API_KEY": "sk-real-secret-value"}


def test_resolve_env_passes_through_literal_values() -> None:
    from backend.mcp.sandbox import resolve_env

    resolved = resolve_env({"MODE": "production"})
    assert resolved == {"MODE": "production"}


def test_resolve_env_drops_unset_host_variable_with_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from backend.mcp.sandbox import resolve_env

    monkeypatch.delenv("SOME_UNSET_VAR", raising=False)
    with caplog.at_level("WARNING"):
        resolved = resolve_env({"API_KEY": "${SOME_UNSET_VAR}"})
    assert resolved == {}
    assert "SOME_UNSET_VAR" in caplog.text


def test_resolve_env_expands_reference_embedded_in_larger_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test: an earlier version only matched a value that was
    ENTIRELY "${VAR}" — a real-world header like "Bearer ${TAVILY_API_KEY}"
    (Tavily's MCP server auth) silently passed through unresolved, with the
    literal "${TAVILY_API_KEY}" sent as the token."""
    from backend.mcp.sandbox import resolve_env

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-real-key")
    resolved = resolve_env({"Authorization": "Bearer ${TAVILY_API_KEY}"})
    assert resolved == {"Authorization": "Bearer tvly-real-key"}


def test_resolve_env_drops_value_with_any_missing_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A value must not be sent half-resolved — if even one of several
    references inside it is unset, drop the whole key/value pair."""
    from backend.mcp.sandbox import resolve_env

    monkeypatch.setenv("SET_VAR", "known")
    monkeypatch.delenv("UNSET_VAR", raising=False)
    resolved = resolve_env({"X-Combo": "${SET_VAR}-${UNSET_VAR}"})
    assert resolved == {}


def test_docker_argv_includes_resolved_env_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.config.schema import MCPServerConfig, Tier
    from backend.mcp.sandbox import docker_argv_for_server

    monkeypatch.setenv("BRAVE_API_KEY", "sk-real-secret-value")
    config = MCPServerConfig(
        name="web_search",
        transport="stdio",
        command="npx",
        args=["-y", "@brave/brave-search-mcp-server", "--transport", "stdio"],
        tiers=[Tier.VICE_PRESIDENT],
        env={"BRAVE_API_KEY": "${BRAVE_API_KEY}"},
    )
    argv = docker_argv_for_server(config)
    assert "BRAVE_API_KEY=sk-real-secret-value" in argv
    idx = argv.index("BRAVE_API_KEY=sk-real-secret-value")
    assert argv[idx - 1] == "-e"
    # env flags must land BEFORE the image name, i.e. as docker run options —
    # anything after the image is passed to the container's entrypoint instead.
    image_idx = argv.index("node:20-slim")
    assert idx < image_idx


def test_redact_argv_for_log_masks_env_values() -> None:
    from backend.mcp.sandbox import _redact_argv_for_log

    argv = ["docker", "run", "-e", "BRAVE_API_KEY=sk-real-secret-value", "node:20-slim"]
    rendered = _redact_argv_for_log(argv)
    assert "sk-real-secret-value" not in rendered
    assert "BRAVE_API_KEY=***" in rendered


# ---------------------------------------------------------------------------
# run_sandboxed_code
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_sandboxed_code_refuses_non_python() -> None:
    from backend.mcp.sandbox import run_sandboxed_code

    result = await run_sandboxed_code("console.log(1)", language="javascript")
    assert "Refused" in result


@pytest.mark.asyncio
async def test_run_sandboxed_code_reports_missing_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from backend.mcp import sandbox

    async def _raise_not_found(*_a: object, **_kw: object) -> None:
        raise FileNotFoundError

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _raise_not_found)
    result = await sandbox.run_sandboxed_code("print(1)")
    assert "unavailable" in result.lower()


# ---------------------------------------------------------------------------
# shutdown_all
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shutdown_all_terminates_tracked_processes() -> None:
    import asyncio

    from backend.mcp import sandbox

    # A real, harmless long-running subprocess (not Docker) so shutdown_all's
    # terminate/wait logic is exercised against a genuine process handle.
    process = await asyncio.create_subprocess_exec(
        "python",
        "-c",
        "import time; time.sleep(30)",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    sandbox._spawned_processes.append(process)  # noqa: SLF001 - test needs internal access

    await sandbox.shutdown_all()

    assert process.returncode is not None
    assert sandbox._spawned_processes == []  # noqa: SLF001


# ---------------------------------------------------------------------------
# MCPRegistry
# ---------------------------------------------------------------------------


class _FakeMCPTool:
    def __init__(self, name: str, args_schema: dict | None = None) -> None:
        self.name = name
        self.description = "a fake mcp tool"
        if args_schema is not None:
            self.args_schema = args_schema


class _FakeMultiServerMCPClient:
    """Stands in for langchain_mcp_adapters.client.MultiServerMCPClient."""

    def __init__(self, connections: dict) -> None:
        self.connections = connections
        self.closed = False

    async def get_tools(self, server_name: str) -> list[_FakeMCPTool]:
        if server_name == "broken_server":
            msg = "simulated connection failure"
            raise RuntimeError(msg)
        if server_name == "web_search":
            return [
                _FakeMCPTool(
                    "tavily_search",
                    {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "topic": {"type": "string", "const": "general"},
                            "max_results": {"type": "integer", "default": 5},
                        },
                        "required": ["query"],
                    },
                )
            ]
        return [_FakeMCPTool("search"), _FakeMCPTool("lookup")]

    async def close(self) -> None:
        self.closed = True


def _mcp_config(config, servers: list):
    return config.model_copy(
        update={
            "mcp_servers": config.mcp_servers.model_copy(
                update={"internal": servers, "external": []}
            )
        }
    )


@pytest.mark.asyncio
async def test_registry_resolves_headers_for_http_servers(
    monkeypatch: pytest.MonkeyPatch, config
) -> None:
    """An http-transport server's headers must reach MultiServerMCPClient
    fully resolved (e.g. Tavily's "Authorization: Bearer ${TAVILY_API_KEY}"),
    never the literal unresolved ${VAR} template."""
    from backend.config.schema import MCPServerConfig, Tier
    from backend.mcp.registry import MCPRegistry

    monkeypatch.setattr(
        "langchain_mcp_adapters.client.MultiServerMCPClient", _FakeMultiServerMCPClient
    )
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-real-key")

    server = MCPServerConfig(
        name="web_search",
        transport="http",
        url="https://mcp.tavily.com/mcp/",
        tiers=[Tier.VICE_PRESIDENT],
        headers={"Authorization": "Bearer ${TAVILY_API_KEY}"},
    )
    registry = MCPRegistry(_mcp_config(config, [server]))
    await registry.startup()

    connection = registry._client.connections["web_search"]  # noqa: SLF001 - test asserting internal wiring
    assert connection["headers"] == {"Authorization": "Bearer tvly-real-key"}


@pytest.mark.asyncio
async def test_registry_namespaces_tools_and_respects_tiers(
    monkeypatch: pytest.MonkeyPatch, config
) -> None:
    from backend.config.schema import MCPServerConfig, Tier
    from backend.mcp.registry import MCPRegistry

    monkeypatch.setattr(
        "langchain_mcp_adapters.client.MultiServerMCPClient", _FakeMultiServerMCPClient
    )

    server = MCPServerConfig(
        name="orders",
        transport="http",
        url="http://localhost:9001/mcp",
        tiers=[Tier.MANAGER, Tier.VICE_PRESIDENT],
    )
    registry = MCPRegistry(_mcp_config(config, [server]))
    await registry.startup()

    manager_tools = {t.name for t in registry.tools_for_tier(Tier.MANAGER)}
    vp_tools = {t.name for t in registry.tools_for_tier(Tier.VICE_PRESIDENT)}
    ceo_tools = registry.tools_for_tier(Tier.CEO)

    assert manager_tools == {"orders.search", "orders.lookup"}
    assert vp_tools == manager_tools  # same server, both tiers listed
    assert ceo_tools == []  # CEO not in this server's tiers
    assert registry.health() == {"orders": True}


@pytest.mark.asyncio
async def test_registry_simplifies_tool_schemas_with_excess_optional_params(
    monkeypatch: pytest.MonkeyPatch, config
) -> None:
    """Regression test: a real Tavily tool call reliably failed with
    llama3.2:latest because tavily_search exposes 14 mostly-optional
    parameters, including a const-constrained `topic` field the model kept
    filling with an invalid empty string. startup() must hand tiers the
    schema-simplified version (backend/mcp/tool_simplify.py), not the raw
    MCP tool, for any tool with optional params to hide."""
    from backend.config.schema import MCPServerConfig, Tier
    from backend.mcp.registry import MCPRegistry

    monkeypatch.setattr(
        "langchain_mcp_adapters.client.MultiServerMCPClient", _FakeMultiServerMCPClient
    )

    server = MCPServerConfig(
        name="web_search",
        transport="http",
        url="https://mcp.tavily.com/mcp/",
        tiers=[Tier.VICE_PRESIDENT],
    )
    registry = MCPRegistry(_mcp_config(config, [server]))
    await registry.startup()

    tool = next(
        t
        for t in registry.tools_for_tier(Tier.VICE_PRESIDENT)
        if t.name == "web_search.tavily_search"
    )
    assert tool.args_schema["properties"].keys() == {"query"}
    assert tool.args_schema["required"] == ["query"]


@pytest.mark.asyncio
async def test_registry_front_desk_never_receives_tools_even_if_misconfigured(
    monkeypatch: pytest.MonkeyPatch, config
) -> None:
    """Config validation already rejects front_desk in a server's tiers[]; this
    is the SECOND line of defence at the registry itself, per the invariant in
    tests/test_invariants.py."""
    from backend.config.schema import MCPServerConfig, Tier
    from backend.mcp.registry import MCPRegistry

    monkeypatch.setattr(
        "langchain_mcp_adapters.client.MultiServerMCPClient", _FakeMultiServerMCPClient
    )

    server = MCPServerConfig.model_construct(
        name="sneaky",
        transport="http",
        command=None,
        args=[],
        url="http://localhost:9001/mcp",
        tiers=[Tier.FRONT_DESK, Tier.MANAGER],
    )
    registry = MCPRegistry(_mcp_config(config, [server]))
    await registry.startup()

    assert registry.tools_for_tier(Tier.FRONT_DESK) == []
    assert registry.tools_for_tier(Tier.MANAGER) != []


@pytest.mark.asyncio
async def test_registry_one_failing_server_does_not_take_down_startup(
    monkeypatch: pytest.MonkeyPatch, config
) -> None:
    from backend.config.schema import MCPServerConfig, Tier
    from backend.mcp.registry import MCPRegistry

    monkeypatch.setattr(
        "langchain_mcp_adapters.client.MultiServerMCPClient", _FakeMultiServerMCPClient
    )

    broken = MCPServerConfig(
        name="broken_server", transport="http", url="http://localhost:9999/mcp", tiers=[Tier.CEO]
    )
    healthy = MCPServerConfig(
        name="fine_server", transport="http", url="http://localhost:9001/mcp", tiers=[Tier.CEO]
    )
    registry = MCPRegistry(_mcp_config(config, [broken, healthy]))
    await registry.startup()  # must not raise

    assert registry.health() == {"broken_server": False, "fine_server": True}
    ceo_tools = {t.name for t in registry.tools_for_tier(Tier.CEO)}
    assert ceo_tools == {"fine_server.search", "fine_server.lookup"}


@pytest.mark.asyncio
async def test_registry_refuses_disallowed_stdio_binary_before_connecting(config) -> None:
    """A sandbox violation at spawn time must mark the server unavailable, not
    raise out of startup() — same "one broken server, not the whole boot"
    contract as a network failure."""
    from backend.config.schema import MCPServerConfig, Tier
    from backend.mcp.registry import MCPRegistry

    evil = MCPServerConfig.model_construct(
        name="evil",
        transport="stdio",
        command="docker",
        args=["run", "-v", "/var/run/docker.sock:/var/run/docker.sock", "image"],
        url=None,
        tiers=[Tier.CEO],
    )
    registry = MCPRegistry(_mcp_config(config, [evil]))
    await registry.startup()  # must not raise

    assert registry.health() == {"evil": False}
    assert registry.tools_for_tier(Tier.CEO) == []


def test_get_registry_falls_back_to_empty_unstarted_registry() -> None:
    """Building a tier subgraph in isolation (a test, or the brief window
    before the FastAPI lifespan finishes) must not crash just because
    set_registry() hasn't run yet."""
    from backend.config.schema import ORDER
    from backend.mcp import registry as registry_module

    registry_module._registry = None  # noqa: SLF001 - reset the module singleton for this test
    reg = registry_module.get_registry()
    for tier in ORDER:
        assert reg.tools_for_tier(tier) == []


def test_vice_president_real_tools_includes_manager_tools_plus_mcp(config) -> None:
    from backend.config.schema import Tier
    from backend.graph.tiers import vice_president
    from backend.mcp.registry import MCPRegistry, set_registry

    set_registry(MCPRegistry(config))  # empty, unstarted — zero MCP tools, no crash
    tools = vice_president.real_tools()
    names = {t.name for t in tools}
    assert names == {"rag_search", "scrape_url", "run_code"}
    _ = Tier
