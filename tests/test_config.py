"""Config schema and loader tests.  (M1)"""

from __future__ import annotations

import pytest

# TODO(M1): test_example_config_parses
#   company_config.example.json must always validate. It is the onboarding
#   document — if it breaks, every new company's first boot breaks.

# TODO(M1): test_missing_required_section_fails
#   Drop `personas` -> ValidationError naming the missing section.

# TODO(M1): test_unknown_key_is_rejected
#   extra="forbid" means a typo like "persona" (singular) fails loudly instead of
#   being silently ignored and leaving the company wondering why their names
#   never showed up.

# TODO(M1): test_comment_key_is_stripped
#   The example carries "_comment". The loader must strip it before validation.

# TODO(M1): test_stdio_requires_command / test_http_requires_url
#   Mismatched transport/field combinations must be rejected.

# TODO(M1): test_unknown_tier_in_tiers_array_fails
#   "tiers": ["director"] -> ValidationError.

# TODO(M1): test_missing_config_file_error_is_actionable
#   Error must point at company_config.example.json, not just raise FileNotFound.

# TODO(M4): test_human_admin_requires_a_channel
#   All three channels null -> ValidationError. CEO escalation would have nowhere
#   to go, and that should surface at startup, not at 2am.

# TODO(M1): test_config_is_cached
#   get_config() twice returns the same object; the file is read once.

_ = pytest
