import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "effective_requirements.py"


def _effective(path: Path) -> list[str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.splitlines()


def test_environment_markers_do_not_create_a_false_dependency_change(
    tmp_path: Path,
) -> None:
    previous = tmp_path / "previous.txt"
    current = tmp_path / "current.txt"
    previous.write_text("rapidocr-onnxruntime>=1.3,<2.0\n")
    current.write_text(
        "rapidocr-onnxruntime>=1.3,<2.0; python_version < '3.13'\n"
        "rapidocr>=3.0,<4.0; python_version >= '3.13'\n"
    )

    if sys.version_info < (3, 13):
        assert _effective(previous) == _effective(current)
    else:
        assert _effective(previous) != _effective(current)


def test_real_dependency_change_remains_visible(tmp_path: Path) -> None:
    previous = tmp_path / "previous.txt"
    current = tmp_path / "current.txt"
    previous.write_text("openai>=1.12,<2.0\n")
    current.write_text("openai>=1.13,<2.0\n")

    assert _effective(previous) != _effective(current)


def test_unsupported_requirement_option_fails_closed(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("-r other-requirements.txt\n")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(requirements)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "unsupported requirements option" in result.stderr
