# SPDX-License-Identifier: AGPL-3.0-or-later
"""Agent SUTs: deterministic tool mocks + a fake agent that emits a trace.

The engine *wraps* an agent that runs its own loop and emits observable steps; it
does not orchestrate the tool-calling loop itself. Tool mocks are recorded
fixtures keyed by (case, tool, args-hash) so an agent run is offline and
reproducible; live tools are non-reproducible and excluded from baselines.
"""

from validrig.agent.fake_agent import FakeAgent
from validrig.agent.mocks import MockStore, tool_args_hash

__all__ = ["FakeAgent", "MockStore", "tool_args_hash"]
