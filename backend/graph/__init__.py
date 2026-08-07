"""LangGraph orchestration: state, tiers, handoff protocol, supervisor.

Build order matters here. handoff.py defines the contract every tier consumes,
and tiers/base.py defines the loop every tier instantiates. Write those two
before any individual tier — see PLAN.md.
"""
