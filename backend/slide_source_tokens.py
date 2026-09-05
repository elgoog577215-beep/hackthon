"""Shared source-faithfulness token rules."""
import re
_PROTECTED_NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?%?")
_PROTECTED_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_.]{2,}\b")

def _protected_tokens(text: str) -> set[str]:
    return {
        *(match.group(0).lower() for match in _PROTECTED_NUMBER_RE.finditer(text)),
        *(
            variant
            for match in _PROTECTED_IDENTIFIER_RE.finditer(text)
            for variant in _identifier_token_variants(match.group(0))
        ),
    }


def _identifier_token_variants(value: str) -> set[str]:
    """Keep dotted identifiers strict while accepting a source-backed prefix.

    Course prose commonly introduces a file or qualified symbol such as
    ``FieldAuditRunner.py`` or ``System.Collections.Generic`` and later refers
    to ``FieldAuditRunner`` or ``System.Collections``. Those are not new facts;
    they are exact prefixes of the frozen identifier. Suffixes and unrelated
    identifiers remain unsupported.
    """

    normalized = str(value or "").casefold()
    variants = {normalized}
    parts = normalized.split(".")
    for index in range(1, len(parts)):
        prefix = ".".join(parts[:index])
        if _PROTECTED_IDENTIFIER_RE.fullmatch(prefix):
            variants.add(prefix)
    return variants
