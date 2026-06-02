from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Injection patterns
# ---------------------------------------------------------------------------

INJECTION_PATTERNS: list[dict] = [
    # CATEGORY 1 — Role override
    {
        "pattern": r"ignore\s+(all\s+|previous\s+|your\s+)?(instructions|rules|guidelines)",
        "flag_code": "ROLE_OVERRIDE_IGNORE",
        "severity": "high",
    },
    {
        "pattern": r"you\s+are\s+now\b",
        "flag_code": "ROLE_OVERRIDE_YOU_ARE_NOW",
        "severity": "high",
    },
    {
        "pattern": r"pretend\s+(you\s+are|to\s+be)",
        "flag_code": "ROLE_OVERRIDE_PRETEND",
        "severity": "high",
    },
    {
        "pattern": r"act\s+as\s+(if\s+you\s+are|a\s+)?(different|new|another)",
        "flag_code": "ROLE_OVERRIDE_ACT_AS",
        "severity": "high",
    },
    {
        "pattern": r"your\s+(new\s+|real\s+|true\s+)?role\s+is",
        "flag_code": "ROLE_OVERRIDE_ROLE_IS",
        "severity": "high",
    },
    {
        "pattern": r"forget\s+(everything|all|your\s+instructions)",
        "flag_code": "ROLE_OVERRIDE_FORGET",
        "severity": "high",
    },
    {
        "pattern": r"disregard\s+(all\s+|previous\s+|your\s+)?(instructions|rules)",
        "flag_code": "ROLE_OVERRIDE_DISREGARD",
        "severity": "high",
    },
    # CATEGORY 2 — Developer / system impersonation
    {
        "pattern": r"as\s+(a\s+|an\s+)?(developer|admin|administrator|system)\b",
        "flag_code": "IMPERSONATION_DEV_ADMIN",
        "severity": "high",
    },
    {
        "pattern": r"in\s+(developer|admin|test|debug|maintenance)\s+mode",
        "flag_code": "IMPERSONATION_MODE",
        "severity": "high",
    },
    {
        "pattern": r"system\s+(prompt|message|instruction)",
        "flag_code": "IMPERSONATION_SYSTEM_PROMPT",
        "severity": "high",
    },
    {
        "pattern": r"\[system\]",
        "flag_code": "IMPERSONATION_SYSTEM_TAG",
        "severity": "high",
    },
    {
        "pattern": r"\b(anthropic|openai)\b",
        "flag_code": "IMPERSONATION_PROVIDER",
        "severity": "high",
    },
    # CATEGORY 3 — Instruction injection
    {
        "pattern": r"new\s+instruction",
        "flag_code": "INSTRUCTION_INJECT_NEW",
        "severity": "high",
    },
    {
        "pattern": r"updated\s+(policy|rules|guidelines)",
        "flag_code": "INSTRUCTION_INJECT_UPDATED",
        "severity": "high",
    },
    {
        "pattern": r"override\s+(the\s+|this\s+)?(policy|rules|decision)",
        "flag_code": "INSTRUCTION_INJECT_OVERRIDE",
        "severity": "high",
    },
    {
        "pattern": r"you\s+must\s+(now\s+|immediately\s+)?(approve|deny|ignore)",
        "flag_code": "INSTRUCTION_INJECT_MUST",
        "severity": "high",
    },
    # CATEGORY 4 — Context manipulation
    {
        "pattern": r"previous\s+(conversation|context|messages?)\s+(said|stated|showed)",
        "flag_code": "CONTEXT_MANIP_PREVIOUS",
        "severity": "medium",
    },
    {
        "pattern": r"you\s+(already\s+|previously\s+)?(approved|said|told\s+me)",
        "flag_code": "CONTEXT_MANIP_ALREADY",
        "severity": "medium",
    },
    {
        "pattern": r"the\s+(policy|rules?)\s+(say|state|allow)",
        "flag_code": "CONTEXT_MANIP_POLICY_CLAIM",
        "severity": "medium",
    },
    # CATEGORY 5 — Jailbreak
    {
        "pattern": r"\bDAN\b",
        "flag_code": "JAILBREAK_DAN",
        "severity": "high",
    },
    {
        "pattern": r"do\s+anything\s+now",
        "flag_code": "JAILBREAK_DO_ANYTHING",
        "severity": "high",
    },
    {
        "pattern": r"without\s+(any\s+|ethical\s+)?restrictions",
        "flag_code": "JAILBREAK_NO_RESTRICTIONS",
        "severity": "high",
    },
    {
        "pattern": r"no\s+(restrictions|limitations|rules)",
        "flag_code": "JAILBREAK_NO_RULES",
        "severity": "high",
    },
    {
        "pattern": r"bypass\s+(the\s+|your\s+)?(restrictions|rules|policy)",
        "flag_code": "JAILBREAK_BYPASS",
        "severity": "high",
    },
    # CATEGORY 6 — Data exfiltration
    {
        "pattern": r"show\s+(me\s+)?(your\s+|the\s+)?(system\s+prompt|instructions|rules)",
        "flag_code": "EXFILTRATION_SHOW",
        "severity": "medium",
    },
    {
        "pattern": r"what\s+(are\s+|is\s+)?(your|the)\s+(instructions|rules|prompt)",
        "flag_code": "EXFILTRATION_WHAT",
        "severity": "medium",
    },
    {
        "pattern": r"repeat\s+(your|the)\s+(instructions|system\s+prompt)",
        "flag_code": "EXFILTRATION_REPEAT",
        "severity": "medium",
    },
    {
        "pattern": r"reveal\s+(your|the)\s+(instructions|policy\s+thresholds)",
        "flag_code": "EXFILTRATION_REVEAL",
        "severity": "medium",
    },
]

_SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1, "none": 0}

# Pre-compile all patterns once at import time
_COMPILED_PATTERNS: list[tuple[re.Pattern, dict]] = []
for _p in INJECTION_PATTERNS:
    try:
        _COMPILED_PATTERNS.append((re.compile(_p["pattern"], re.IGNORECASE), _p))
    except re.error as _e:
        logger.error("Failed to compile injection pattern %s: %s", _p["flag_code"], _e)


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass
class InjectionCheckResult:
    detected: bool
    flags: list[str] = field(default_factory=list)
    severity: str = "none"
    matched_patterns: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def check_for_injection(message: str) -> InjectionCheckResult:
    try:
        normalized = message.strip().lower()
        fired: list[dict] = []
        matched: list[str] = []

        for compiled, meta in _COMPILED_PATTERNS:
            try:
                if compiled.search(normalized):
                    fired.append(meta)
                    matched.append(meta["pattern"])
            except re.error:
                continue

        if not fired:
            return InjectionCheckResult(detected=False)

        flags = [p["flag_code"] for p in fired]
        top_severity = max(
            (p["severity"] for p in fired),
            key=lambda s: _SEVERITY_RANK.get(s, 0),
        )
        logger.warning("Injection detected: flags=%s, severity=%s", flags, top_severity)

        return InjectionCheckResult(
            detected=True,
            flags=flags,
            severity=top_severity,
            matched_patterns=matched,
        )
    except Exception as exc:
        logger.error("check_for_injection error: %s", exc)
        return InjectionCheckResult(detected=False)


def sanitize_for_logging(message: str) -> str:
    truncated = message[:200]
    # Redact email-like patterns
    sanitized = re.sub(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", "[EMAIL]", truncated)
    # Redact long alphanumeric strings that look like API keys (20+ chars)
    sanitized = re.sub(r"[A-Za-z0-9_\-]{20,}", "[REDACTED]", sanitized)
    return sanitized


__all__ = [
    "InjectionCheckResult",
    "check_for_injection",
    "sanitize_for_logging",
    "INJECTION_PATTERNS",
]
