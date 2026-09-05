"""Stable quote choices: select exact source artifacts without rewriting them."""
import hashlib
import re


def source_excerpt_catalog(sources):
    catalog = []
    for source in sources.values():
        text = source["full_text"]
        spans = {(m.start(), m.end()) for m in re.finditer(r"[^\n。！？]+[。！？]?", text) if m.group().strip()}
        spans.update((m.start(), m.end()) for m in re.finditer(r"\$\$[\s\S]*?\$\$|(?<!\$)\$[^$\n]+\$|```[\s\S]*?```|`[^`\n]+`", text))
        for start, end in sorted(spans):
            token = f"{source['block_id']}:{source['block_revision']}:{start}:{end}"
            catalog.append({"quote_id": "q_" + hashlib.sha256(token.encode()).hexdigest()[:12],
                            "block_id": source["block_id"], "block_revision": source["block_revision"],
                            "start": start, "end": end, "quote": text[start:end]})
    return catalog


def resolve_quote_choice(choice, sources):
    if choice.quote_id:
        match = next((r for r in source_excerpt_catalog(sources) if r["quote_id"] == choice.quote_id), None)
        if match is None:
            raise ValueError(f"source_quote_id_unknown:{choice.quote_id}")
        if ((choice.block_id and choice.block_id != match["block_id"])
                or (choice.quote and choice.quote != match["quote"])):
            raise ValueError(f"source_quote_choice_conflict:{choice.quote_id}: supplied block_id/quote disagrees with selected range")
        return sources[match["block_id"]], match["quote"], match["start"]
    source = sources.get(choice.block_id)
    if source is None or not choice.quote or choice.quote not in source["full_text"]:
        raise ValueError(f"source_excerpt_mismatch:{choice.block_id}: choose a supplied quote_id or copy a literal source quote")
    return source, choice.quote, source["full_text"].index(choice.quote)
