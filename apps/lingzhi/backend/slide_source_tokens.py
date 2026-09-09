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
    """Accept source-backed prefixes and member suffixes of dotted names.

    Course prose commonly introduces a file or qualified symbol such as
    ``FieldAuditRunner.py`` or ``System.Collections.Generic`` and later refers
    to ``FieldAuditRunner`` or ``System.Collections``. Code teaching also often
    shortens ``Rigidbody.velocity`` to ``velocity``. These are exact parts of
    the frozen identifier; unrelated identifiers remain unsupported.
    """

    normalized = str(value or "").casefold()
    variants = {normalized}
    parts = normalized.split(".")
    for start in range(len(parts)):
        for end in range(start + 1, len(parts) + 1):
            segment = ".".join(parts[start:end])
            if _PROTECTED_IDENTIFIER_RE.fullmatch(segment):
                variants.add(segment)
    return variants
