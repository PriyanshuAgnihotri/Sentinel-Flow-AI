import re
from dataclasses import dataclass

INJECTION_PATTERNS = [
    r"ignore (all )?(previous|prior) instructions",
    r"jailbreak",
    r"reveal (the )?(system prompt|secrets)",
    r"give me admin access",
    r"bypass (your )?(guardrails|security)",
]
DESTRUCTIVE_SQL = re.compile(
    r"\b(DROP|DELETE|TRUNCATE|UPDATE|ALTER|GRANT|REVOKE|CREATE|INSERT|MERGE|EXEC(?:UTE)?)\b", re.I
)
PII_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)


@dataclass
class GuardrailResult:
    allowed: bool
    sanitized_text: str
    category: str | None = None
    reason: str | None = None
    policy_rule: str | None = None


def inspect_input(text: str) -> GuardrailResult:
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text, re.I):
            return GuardrailResult(
                False, "", "prompt_injection", "Potential prompt injection detected", "INPUT-001"
            )
    if len(text.strip()) < 2:
        return GuardrailResult(False, "", "unsupported", "Input is too short", "INPUT-002")
    # Do not echo likely credentials/secrets; email addresses are not automatically unsafe.
    return GuardrailResult(True, text.strip())


def validate_sql(query: str) -> bool:
    """Return True only for read-only SQL; free-form SQL is never exposed as a tool."""
    stripped = query.strip().rstrip(";")
    if not re.match(r"^(SELECT|WITH)\b", stripped, re.I):
        return False
    if DESTRUCTIVE_SQL.search(stripped):
        return False
    if "--" in stripped or "/*" in stripped or "*/" in stripped:
        return False
    return True
