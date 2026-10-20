import re
from dataclasses import dataclass

INJECTION_PATTERNS = [
    r"ignore (all )?(previous|prior) instructions",
    r"reveal (the |your )?(system prompt|instructions)",
    r"bypass (your )?(guardrails|security)",
    r"give me admin access",
    r"jailbreak",
]
DESTRUCTIVE_SQL = re.compile(
    r"\b(DROP|DELETE|TRUNCATE|UPDATE|ALTER|GRANT|REVOKE|CREATE|INSERT|MERGE|EXEC(?:UTE)?)\b",
    re.IGNORECASE,
)
PII_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)


@dataclass
class GuardrailResult:
    allowed: bool
    sanitized_text: str
    category: str = "safe"
    reason: str = ""
    rule_id: str = ""


def inspect_input(text: str) -> GuardrailResult:
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
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
    if not re.match(r"^(SELECT|WITH)\b", stripped, re.IGNORECASE):
        return False
    if DESTRUCTIVE_SQL.search(stripped):
        return False
    return not ("--" in stripped or "/*" in stripped or "*/" in stripped)
