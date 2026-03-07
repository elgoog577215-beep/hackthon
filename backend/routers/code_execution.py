# =============================================================================
# 代码执行路由
# 代码沙箱执行、支持语言查询
# =============================================================================

from fastapi import APIRouter, HTTPException
import subprocess
import tempfile
import time
import re
import os
import sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from models import ExecuteCodeRequest, ExecuteCodeResponse

router = APIRouter(prefix="/api", tags=["code_execution"])

# 支持的语言配置
SUPPORTED_LANGUAGES = {
    "python": {"extension": ".py", "command": ["python3"], "timeout": 30},
    "javascript": {"extension": ".js", "command": ["node"], "timeout": 30},
    "typescript": {"extension": ".ts", "command": ["npx", "ts-node"], "timeout": 30},
    "bash": {"extension": ".sh", "command": ["bash"], "timeout": 10},
    "shell": {"extension": ".sh", "command": ["sh"], "timeout": 10},
}

# 安全：禁止的代码模式
FORBIDDEN_PATTERNS = [
    r"import\s+os\s*;.*system",
    r"subprocess\.call",
    r"subprocess\.run",
    r"subprocess\.Popen",
    r"eval\s*\(",
    r"exec\s*\(",
    r"__import__",
    r"open\s*\(.*['\"]\s*[/\\]",
    r"rm\s+-rf\s+/",
    r">\s*/",
    r"dd\s+if=",
]

MAX_OUTPUT_LENGTH = 10000


def _validate_code_security(code: str) -> tuple[bool, str]:
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, code, re.IGNORECASE):
            return False, "Security Error: Code contains potentially dangerous operations"
    return True, ""


def _truncate_output(output: str, max_length: int = MAX_OUTPUT_LENGTH) -> str:
    if len(output) > max_length:
        return output[:max_length] + "\n... (output truncated)"
    return output


def _cleanup_temp_file(file_path: str):
    try:
        if os.path.exists(file_path):
            os.unlink(file_path)
    except OSError:
        pass


@router.post("/execute")
async def execute_code(req: ExecuteCodeRequest):
    language = req.language.lower()

    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language: {language}. Supported: {', '.join(SUPPORTED_LANGUAGES.keys())}"
        )

    lang_config = SUPPORTED_LANGUAGES[language]
    timeout = min(req.timeout, lang_config["timeout"])

    is_safe, error_msg = _validate_code_security(req.code)
    if not is_safe:
        return ExecuteCodeResponse(
            success=False, output="", error=error_msg,
            execution_time=0, language=language
        )

    start_time = time.time()
    temp_file_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode='w', suffix=lang_config["extension"], delete=False
        ) as temp_file:
            temp_file.write(req.code)
            temp_file_path = temp_file.name

        result = subprocess.run(
            lang_config["command"] + [temp_file_path],
            capture_output=True, text=True, timeout=timeout
        )

        execution_time = (time.time() - start_time) * 1000
        _cleanup_temp_file(temp_file_path)
        temp_file_path = None

        output = _truncate_output(result.stdout)
        error = result.stderr if result.stderr else None

        return ExecuteCodeResponse(
            success=result.returncode == 0, output=output, error=error,
            execution_time=round(execution_time, 2), language=language
        )

    except subprocess.TimeoutExpired:
        execution_time = (time.time() - start_time) * 1000
        _cleanup_temp_file(temp_file_path)
        return ExecuteCodeResponse(
            success=False, output="",
            error=f"Execution timeout: Code took longer than {timeout} seconds to execute",
            execution_time=round(execution_time, 2), language=language
        )

    except Exception as e:
        execution_time = (time.time() - start_time) * 1000
        _cleanup_temp_file(temp_file_path)
        return ExecuteCodeResponse(
            success=False, output="",
            error=f"Execution error: {str(e)}",
            execution_time=round(execution_time, 2), language=language
        )


@router.get("/execute/languages")
async def get_supported_languages():
    return {
        "languages": [
            {
                "id": lang_id,
                "name": lang_id.capitalize(),
                "extension": config["extension"],
                "timeout": config["timeout"]
            }
            for lang_id, config in SUPPORTED_LANGUAGES.items()
        ]
    }
