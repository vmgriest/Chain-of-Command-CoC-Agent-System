"""LangGraph orchestration: state, tiers, handoff protocol, supervisor.

Build order matters here. handoff.py defines the contract every tier consumes,
and tiers/base.py defines the loop every tier instantiates — those two exist
before any individual tier.
"""
