"""Token billing guard for AI operations.

Hard limits:
- --ai-max-findings=30  (cap on findings per page)
- --ai-budget=100K tokens (total output token budget)

Billing guard asserts that total output tokens stay within budget and that
the number of API calls is reasonable for the findings returned.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

# Default limits
DEFAULT_MAX_FINDINGS = 30
DEFAULT_BUDGET_TOKENS = 100_000
# Haiku pricing: $0.65/M input, $3.25/M output (approximate)
# For budget calculations
COST_PER_M_OUTPUT_TOKENS = 3.25  # dollars per million


@dataclass
class BillingRecord:
    call_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    findings_returned: int = 0
    gates_failed: int = 0
    started_at: float = field(default_factory=time.time)

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    def estimated_cost(self) -> float:
        """Rough cost in dollars."""
        return (self.total_output_tokens / 1_000_000) * COST_PER_M_OUTPUT_TOKENS


class BillingGuard:
    """Tracks token usage and enforces hard caps."""

    def __init__(
        self,
        max_findings: int = DEFAULT_MAX_FINDINGS,
        budget_tokens: int = DEFAULT_BUDGET_TOKENS,
        dry_run: bool = False,
    ):
        self.max_findings = max_findings
        self.budget_tokens = budget_tokens
        self.dry_run = dry_run
        self._record = BillingRecord()

    @property
    def record(self) -> BillingRecord:
        return self._record

    def record_call(
        self,
        input_tokens: int,
        output_tokens: int,
        findings_count: int,
        gate_failed: bool = False,
    ) -> None:
        """Record one API call's token usage."""
        if self.dry_run:
            return
        self._record.call_count += 1
        self._record.total_input_tokens += input_tokens
        self._record.total_output_tokens += output_tokens
        self._record.findings_returned += findings_count
        if gate_failed:
            self._record.gates_failed += 1

    def assert_within_budget(self) -> None:
        """Raise BillingExceeded if budget is exceeded."""
        if self.dry_run:
            return
        if self._record.total_output_tokens > self.budget_tokens:
            raise BillingExceeded(
                f"Token budget exceeded: {self._record.total_output_tokens:,} "
                f"output tokens > {self.budget_tokens:,} limit. "
                f"Reduce --ai-budget or use a smaller page."
            )

    def assert_call_count_reasonable(self, max_calls: int = 20) -> None:
        """Warn if too many API calls were made for the findings returned."""
        if self.dry_run:
            return
        # Billing alarm: if 100 findings but 20+ calls, something is wrong
        efficiency = self._record.findings_returned / max(self._record.call_count, 1)
        if self._record.call_count > max_calls and efficiency < 2:
            raise BillingExceeded(
                f"Suspicious pattern: {self._record.call_count} API calls "
                f"for only {self._record.findings_returned} findings. "
                f"Check that pages are not being re-scraped unnecessarily."
            )

    def summary(self) -> dict[str, Any]:
        """Return a usage summary dict."""
        return {
            "api_calls": self._record.call_count,
            "input_tokens": self._record.total_input_tokens,
            "output_tokens": self._record.total_output_tokens,
            "findings_returned": self._record.findings_returned,
            "gates_failed": self._record.gates_failed,
            "within_budget": self._record.total_output_tokens <= self.budget_tokens,
            "estimated_cost_usd": round(self._record.estimated_cost(), 6),
            "elapsed_seconds": round(time.time() - self._record.started_at, 2),
        }


class BillingExceeded(Exception):
    """Raised when AI operations exceed configured billing limits."""
    pass
