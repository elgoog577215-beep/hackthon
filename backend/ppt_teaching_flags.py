"""Controls new manuscript creation only; never changes an existing task."""
import os


def three_stage_enabled() -> bool:
    return os.environ.get("PPT_THREE_STAGE_ENABLED", "false").strip().lower() in {"true", "1", "yes"}
