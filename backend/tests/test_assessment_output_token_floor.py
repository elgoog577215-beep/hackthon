"""The assessment output ceilings must be re-calibratable per deployed model.

Context for whoever owns this module next: the ceilings in
`assessment_orchestrator` were calibrated against DeepSeek.  Run against the
self-hosted `qwen3.6-35b-a3b` endpoint, the review call truncated at
`max_tokens=2048` and emitted `chars=0`, which failed JSON extraction and
blocked the release gate — the full generation chain could not get past the
practice stage at all.

Direct measurement against that endpoint (trivial review question):

    ceiling 2048, json_mode      -> stop,   261 chars, 1874 completion tokens
    ceiling 2048, thinking off   -> length,  16 chars, 2048 completion tokens
    ceiling 8192, json_mode      -> stop,   183 chars, 1956 completion tokens

The cost before any answer is written is fixed (~1900) rather than
proportional, so a floor is the correct shape of fix and a multiplier is not.

These tests pin the two properties that make the knob safe to ship: it is a
no-op unless configured, and it can only raise a ceiling, never lower one.
"""

from __future__ import annotations

import pytest

from assessment_orchestrator import _out_tokens


CEILINGS = [1536, 2048, 3072, 4096, 6144, 8192, 12288]


def test_unset_env_preserves_every_existing_ceiling(monkeypatch):
    """The default must not re-calibrate another deployment's pipeline."""
    monkeypatch.delenv("ASSESSMENT_MIN_OUTPUT_TOKENS", raising=False)

    assert [_out_tokens(c) for c in CEILINGS] == CEILINGS


def test_floor_raises_only_the_ceilings_below_it(monkeypatch):
    monkeypatch.setenv("ASSESSMENT_MIN_OUTPUT_TOKENS", "4096")

    assert [_out_tokens(c) for c in CEILINGS] == [
        4096, 4096, 4096, 4096, 6144, 8192, 12288
    ]


def test_floor_never_lowers_a_ceiling(monkeypatch):
    """A larger call must never be shrunk into truncation by this knob."""
    monkeypatch.setenv("ASSESSMENT_MIN_OUTPUT_TOKENS", "2048")

    assert _out_tokens(12288) == 12288


@pytest.mark.parametrize("value", ["", "abc", "-5", "0", "3.5"])
def test_unusable_values_fall_back_to_the_configured_ceiling(monkeypatch, value):
    """A typo in a deployment env must not silently shrink every call."""
    monkeypatch.setenv("ASSESSMENT_MIN_OUTPUT_TOKENS", value)

    assert [_out_tokens(c) for c in CEILINGS] == CEILINGS


def test_absurd_floor_is_capped_rather_than_passed_to_the_provider(monkeypatch):
    """Providers reject oversized ceilings; clamp instead of failing the call."""
    monkeypatch.setenv("ASSESSMENT_MIN_OUTPUT_TOKENS", "999999")

    assert _out_tokens(2048) == 16000


def test_every_orchestrator_ceiling_goes_through_the_floor(monkeypatch):
    """A ceiling added later must not silently reintroduce the 2048 problem."""
    import re
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "assessment_orchestrator.py"
    text = source.read_text(encoding="utf-8")
    # Every literal max_tokens= argument must be wrapped; the keyword-passthrough
    # forms (max_tokens=max_tokens) and signatures are not ceilings.
    unwrapped = [
        line.strip()
        for line in text.splitlines()
        if re.search(r"max_tokens=(?!_out_tokens|max_tokens\b)", line)
        and "def " not in line
    ]

    assert unwrapped == []
