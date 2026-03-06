# Agent Mindset & Epistemic Discipline

## Core Principle: Know What You Don't Know

> 知之为知之，不知为不知，是知也。
> ("To know what you know, and know what you don't know — that is knowledge.")

This project has accumulated technical debt and inconsistencies. Your training data contains general knowledge about Vue, FastAPI, Python, etc. — but **this specific codebase may not follow those conventions**. Do not conflate general knowledge with project-specific facts.

## Rules

**Never assume. Verify.**
- If you are about to make a claim about how something works in this codebase (e.g., "this function is called here", "this state is managed there", "this endpoint is used by X"), and you have not read the relevant code in this session — go read it first.
- General patterns from Vue/FastAPI/Pinia docs do not guarantee this project follows them. This codebase has known inconsistencies.

**Context compaction awareness.**
- Your context window may have been compacted. If you are resuming work and find yourself uncertain about the current state of a file or a previous decision, re-read the file rather than relying on a potentially summarized or stale memory.
- When in doubt about what changed: use `grepSearch` or `readCode` to ground yourself before proceeding.

**Distinguish confidence levels explicitly.**
- If you are certain because you just read the code: proceed.
- If you are inferring from general knowledge or a vague memory: say so, and verify before acting.
- Never silently fill gaps with plausible-sounding assumptions.

**Prefer targeted reads over broad assumptions.**
- Don't read an entire 3000-line file to answer a narrow question. Use `grepSearch` to locate the relevant symbol, then `readCode` with a selector or `readFile` with line ranges.
- But do read enough to be sure. A partial read that misses the actual implementation is worse than no read.

## What This Looks Like in Practice

- Before editing a function: read its current implementation.
- Before adding a new API call: check what HTTP utility is actually used at that call site.
- Before claiming a piece of code is "unused": search for its references.
- Before assuming a bug is in one place: trace the actual data flow from source to symptom.
