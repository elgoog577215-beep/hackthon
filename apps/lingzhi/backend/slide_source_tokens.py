"""Shared source-faithfulness token rules."""
import re
_PROTECTED_NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?%?")
_PROTECTED_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_.]{2,}\b")
_CODE_SPAN_RE = re.compile(r"```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`")
_EMPHASIZED_PREFIX_RE = re.compile(
    r"(?<![A-Za-z0-9_.])(?P<marker>\*\*|__|\*|_)(?P<prefix>[A-Za-z][A-Za-z0-9.]*)"
    r"(?P=marker)(?P<suffix>[A-Za-z0-9.]+)(?![A-Za-z0-9_.])"
)

def _protected_tokens(text: str) -> set[str]:
    # Markdown can emphasize an acronym's initial letter: **S**ubstitute.
    # Accept its displayed spelling without rewriting literal source ranges
    # or joining operators inside code examples.
    rendered_identifiers = {
        variant
        for match in _EMPHASIZED_PREFIX_RE.finditer(_CODE_SPAN_RE.sub("", text))
        for variant in _identifier_token_variants(match["prefix"] + match["suffix"])
    }
    # Escaped percent is TeX markup inside delimited math. The editable slide
    # projection displays 80\% as 80%, retaining the number and its unit.
    from ppt_formula_projection import _MATH_SPAN
    rendered_numbers = {
        number.group(0).lower()
        for span in _MATH_SPAN.finditer(_CODE_SPAN_RE.sub("", text))
        for number in _PROTECTED_NUMBER_RE.finditer(span.group(0).replace(r"\%", "%"))
    }
    return {
        *rendered_identifiers,
        *rendered_numbers,
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
