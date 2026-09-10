#!/usr/bin/env python3
"""Read-only production process/log diagnostics; never print credentials or prompts."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path


def main() -> None:
    pid = subprocess.check_output(
        ["systemctl", "show", "lingzhi", "--property=MainPID", "--value"], text=True
    ).strip()
    result: dict = {"service_running": pid.isdigit() and int(pid) > 0}
    try:
        raw = Path(f"/proc/{int(pid)}/environ").read_bytes()
        live = dict(part.decode(errors="replace").split("=", 1) for part in raw.split(b"\0") if b"=" in part)
        result["configuration_matches_saved"] = {
            key: live.get(key, "") == os.getenv(key, "")
            for key in ("AI_API_BASE", "AI_API_KEY", "AI_MODEL", "AI_MODEL_FAST", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
        }
        result["live_numeric_settings"] = {
            key: value for key, value in live.items()
            if key.startswith("AI_") and re.fullmatch(r"[0-9.]+", value)
        }
        result["live_proxy_present"] = {
            key: bool(live.get(key)) for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")
        }
    except (OSError, ValueError) as error:
        result["process_inspection_error"] = type(error).__name__
    # Only whitelisted diagnostic fragments are emitted. Course text, URLs,
    # addresses, headers and arbitrary exception messages never leave the host.
    patterns = [
        r"(?:httpx|httpcore|openai)\.(?:[A-Za-z]*Error|[A-Za-z]*Timeout)",
        r"(?:ConnectTimeout|ReadTimeout|PoolTimeout|WriteTimeout|APIConnectionError|APITimeoutError)",
        r"Request timed out\.", r"All connection attempts failed", r"Connection refused",
        r"Network is unreachable", r"Name or service not known", r"Temporary failure in name resolution",
        r"Too many open files", r"Event loop is closed", r"Cannot assign requested address",
        r"Whole-course scan batch=\d+ part=\d+ failed",
        r"AI model transient failure \d+/\d+", r"AI model circuit opened",
        r"HTTP/[12](?:\.\d)? [45]\d\d [A-Za-z ]+",
    ]
    journal = subprocess.run(
        ["journalctl", "-u", "lingzhi", "--since", "45 minutes ago", "-n", "12000", "--no-pager", "-o", "json"],
        capture_output=True, text=True, timeout=30,
    )
    events = []
    for line in journal.stdout.splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        message = str(item.get("MESSAGE") or "")
        matches = list(dict.fromkeys(match for pattern in patterns for match in re.findall(pattern, message)))
        if matches:
            events.append({"timestamp_us": item.get("__REALTIME_TIMESTAMP"), "signals": matches})
    result["journal_returncode"] = journal.returncode
    result["events"] = events[-180:]
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
