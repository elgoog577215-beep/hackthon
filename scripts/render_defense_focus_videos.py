"""Render the final defense videos with deliberate 1.8x-1.9x focus moves.

The source recordings remain untouched.  The output is normalized to 1440x810,
30 fps, H.264, no audio, and uses eased focus windows around the actions and
results that need to remain readable on a projected screen.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
FFMPEG_FALLBACK = Path(r"C:\ffmpeg-8.0.1-essentials_build\bin\ffmpeg.exe")


@dataclass(frozen=True)
class FocusWindow:
    start: float
    end: float
    zoom: float
    center_x: int
    center_y: int
    transition: float = 0.55


@dataclass(frozen=True)
class VideoSpec:
    source: Path
    output: Path
    focuses: tuple[FocusWindow, ...]


def _number(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _zoom_window(window: FocusWindow) -> str:
    start = _number(window.start)
    ramp_end = _number(window.start + window.transition)
    ramp_down = _number(window.end - window.transition)
    end = _number(window.end)
    transition = _number(window.transition)
    gain = _number(window.zoom - 1)
    peak = _number(window.zoom)
    return (
        f"if(between(in_time,{start},{ramp_end}),"
        f"1+{gain}*(in_time-{start})/{transition},"
        f"if(between(in_time,{ramp_end},{ramp_down}),{peak},"
        f"1+{gain}*({end}-in_time)/{transition}))"
    )


def _zoom_expression(focuses: tuple[FocusWindow, ...]) -> str:
    expression = "1"
    for window in reversed(focuses):
        expression = (
            f"if(between(in_time,{_number(window.start)},"
            f"{_number(window.end)}),{_zoom_window(window)},{expression})"
        )
    return expression


def _position_expression(
    focuses: tuple[FocusWindow, ...],
    axis: str,
) -> str:
    source_dimension = "iw" if axis == "x" else "ih"
    center_default = f"{source_dimension}/2-{source_dimension}/zoom/2"
    expression = center_default
    for window in reversed(focuses):
        center = window.center_x if axis == "x" else window.center_y
        focused = (
            f"min(max({center}-{source_dimension}/zoom/2,0),"
            f"{source_dimension}-{source_dimension}/zoom)"
        )
        expression = (
            f"if(between(in_time,{_number(window.start)},"
            f"{_number(window.end)}),{focused},{expression})"
        )
    return expression


def _find_ffmpeg() -> str:
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    if FFMPEG_FALLBACK.exists():
        return str(FFMPEG_FALLBACK)
    raise FileNotFoundError("ffmpeg was not found in PATH or the bundled fallback path")


def render(spec: VideoSpec, ffmpeg: str) -> None:
    if not spec.source.exists():
        raise FileNotFoundError(f"source video not found: {spec.source}")
    spec.output.parent.mkdir(parents=True, exist_ok=True)
    zoom = _zoom_expression(spec.focuses)
    x = _position_expression(spec.focuses, "x")
    y = _position_expression(spec.focuses, "y")
    video_filter = (
        f"zoompan=z='{zoom}':x='{x}':y='{y}':"
        "d=1:s=1440x810:fps=30,format=yuv420p"
    )
    command = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-i",
        str(spec.source),
        "-vf",
        video_filter,
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-movflags",
        "+faststart",
        str(spec.output),
    ]
    print(f"Rendering {spec.output.name} from {spec.source.name}", flush=True)
    subprocess.run(command, check=True, cwd=ROOT)


def main() -> int:
    ffmpeg = _find_ffmpeg()
    specs = (
        VideoSpec(
            source=ROOT / "recordings" / "qizhi_structured_same_source_browser_60s.mp4",
            output=ROOT / "demo_videos" / "final_defense_video1_structured_same_source_2x.mp4",
            focuses=(
                FocusWindow(4.5, 11.5, 1.9, 1650, 710),
                FocusWindow(49.0, 60.0, 1.8, 1000, 505),
            ),
        ),
        VideoSpec(
            source=ROOT / "recordings" / "qizhi_personalized_growth_browser_60s.mp4",
            output=ROOT / "demo_videos" / "final_defense_video2_personalized_growth_2x.mp4",
            focuses=(
                FocusWindow(3.0, 20.0, 1.85, 1450, 520),
                FocusWindow(27.0, 43.0, 1.85, 1450, 625),
                FocusWindow(50.0, 60.0, 1.8, 1160, 510),
            ),
        ),
    )
    for spec in specs:
        render(spec, ffmpeg)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        print(f"render failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
