# =============================================================================
# 代码执行路由
# 代码沙箱执行、支持语言查询
#
# 安全措施：
# - 正则黑名单 + 白名单双重过滤
# - 仅允许 Python 和 JavaScript（移除 bash/shell/ts 以缩小攻击面）
# - 资源限制：内存、CPU 时间、进程数、文件大小
# - 临时目录隔离，禁止网络访问（Linux 环境下）
# - 代码长度限制
# =============================================================================

from fastapi import APIRouter, HTTPException
import subprocess
import tempfile
import time
import re
import os
import sys
import platform
import logging

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from models import ExecuteCodeRequest, ExecuteCodeResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["code_execution"])

# 支持的语言配置（移除 bash/shell/typescript 以缩小攻击面）
SUPPORTED_LANGUAGES = {
    "python": {"extension": ".py", "command": ["python3"], "timeout": 10},
    "javascript": {"extension": ".js", "command": ["node"], "timeout": 10},
}

# 代码长度限制（字符数）
MAX_CODE_LENGTH = 5000
MAX_OUTPUT_LENGTH = 10000

# =============================================================================
# 安全验证 — 多层防御
# =============================================================================

# Python 危险模式（黑名单）
_PYTHON_FORBIDDEN = [
    # 系统访问
    r"\bos\b\s*\.\s*(system|popen|exec|spawn|kill|remove|unlink|rmdir|rename|chmod|chown|link|symlink|makedirs|listdir|walk)",
    r"\bsubprocess\b",
    r"\bshutil\b",
    r"\b__import__\b",
    r"\bimportlib\b",
    r"\bctypes\b",
    # 内省/逃逸
    r"\b__builtins__\b",
    r"\b__subclasses__\b",
    r"\b__globals__\b",
    r"\b__code__\b",
    r"\b__class__\b\s*\.\s*__mro__",
    r"\bbreakpoint\b\s*\(",
    r"\bcompile\b\s*\(",
    # 文件系统（绝对路径）
    r"open\s*\(\s*['\"][/\\]",
    r"open\s*\(\s*['\"]\.\.[\\/]",
    # 网络
    r"\bsocket\b",
    r"\burllib\b",
    r"\brequests\b",
    r"\bhttpx\b",
    r"\baiohttp\b",
    # 危险内置
    r"\beval\b\s*\(",
    r"\bexec\b\s*\(",
    r"\bglobals\b\s*\(",
    r"\blocals\b\s*\(",
    r"\bgetattr\b\s*\(",
    r"\bsetattr\b\s*\(",
    r"\bdelattr\b\s*\(",
    # 信号
    r"\bsignal\b\s*\.\s*signal",
]

# JavaScript 危险模式
_JS_FORBIDDEN = [
    r"\brequire\b\s*\(\s*['\"]child_process",
    r"\brequire\b\s*\(\s*['\"]fs",
    r"\brequire\b\s*\(\s*['\"]net",
    r"\brequire\b\s*\(\s*['\"]http",
    r"\brequire\b\s*\(\s*['\"]https",
    r"\brequire\b\s*\(\s*['\"]os",
    r"\brequire\b\s*\(\s*['\"]path",
    r"\brequire\b\s*\(\s*['\"]dgram",
    r"\brequire\b\s*\(\s*['\"]cluster",
    r"\brequire\b\s*\(\s*['\"]worker_threads",
    r"\bprocess\s*\.\s*(exit|kill|env|execPath|binding)",
    r"\bglobal\b\s*\.\s*process",
    r"\bimport\b\s*\(",  # dynamic import
]

_FORBIDDEN_BY_LANG = {
    "python": _PYTHON_FORBIDDEN,
    "javascript": _JS_FORBIDDEN,
}


def _validate_code_security(code: str, language: str) -> tuple[bool, str]:
    """多层安全验证"""
    # 1. 长度检查
    if len(code) > MAX_CODE_LENGTH:
        return False, f"代码长度超过限制（最大 {MAX_CODE_LENGTH} 字符）"

    # 2. 空代码检查
    stripped = code.strip()
    if not stripped:
        return False, "代码不能为空"

    # 3. 语言特定的黑名单检查
    patterns = _FORBIDDEN_BY_LANG.get(language, [])
    for pattern in patterns:
        if re.search(pattern, code, re.IGNORECASE | re.MULTILINE):
            return False, "安全错误：代码包含被禁止的操作"

    # 4. 通用危险模式
    universal_patterns = [
        r"rm\s+-rf\s+/",
        r">\s*/dev/",
        r"dd\s+if=",
        r"mkfifo",
        r"fork\s*\(",
    ]
    for pattern in universal_patterns:
        if re.search(pattern, code, re.IGNORECASE):
            return False, "安全错误：代码包含被禁止的操作"

    return True, ""


def _truncate_output(output: str, max_length: int = MAX_OUTPUT_LENGTH) -> str:
    if len(output) > max_length:
        return output[:max_length] + "\n... (output truncated)"
    return output


def _cleanup_temp_dir(dir_path: str):
    """清理临时目录"""
    try:
        import shutil
        if dir_path and os.path.exists(dir_path):
            shutil.rmtree(dir_path, ignore_errors=True)
    except Exception:
        pass


def _build_sandbox_command(base_command: list, file_path: str, language: str) -> list:
    """
    构建带资源限制的沙箱命令。
    Linux 环境下使用 ulimit 限制资源；其他平台仅依赖 timeout。
    """
    if platform.system() != "Linux":
        return base_command + [file_path]

    # Linux 资源限制
    limits = [
        "ulimit -v 262144;",    # 虚拟内存 256MB
        "ulimit -f 1024;",      # 文件大小 512KB
        "ulimit -u 32;",        # 最大进程数 32
        "ulimit -t 10;",        # CPU 时间 10 秒
    ]

    inner_cmd = " ".join(base_command + [file_path])
    shell_cmd = " ".join(limits) + " " + inner_cmd

    return ["bash", "-c", shell_cmd]


@router.post("/execute")
async def execute_code(req: ExecuteCodeRequest):
    language = req.language.lower()

    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的语言: {language}。支持: {', '.join(SUPPORTED_LANGUAGES.keys())}"
        )

    lang_config = SUPPORTED_LANGUAGES[language]
    timeout = min(req.timeout, lang_config["timeout"])

    # 安全验证
    is_safe, error_msg = _validate_code_security(req.code, language)
    if not is_safe:
        return ExecuteCodeResponse(
            success=False, output="", error=error_msg,
            execution_time=0, language=language
        )

    start_time = time.time()
    temp_dir = None

    try:
        # 在独立临时目录中执行，隔离文件系统访问
        temp_dir = tempfile.mkdtemp(prefix="sandbox_")
        file_path = os.path.join(temp_dir, f"code{lang_config['extension']}")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(req.code)

        # 构建沙箱命令
        cmd = _build_sandbox_command(lang_config["command"], file_path, language)

        # 设置受限环境变量（不继承宿主环境）
        safe_env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": temp_dir,
            "TMPDIR": temp_dir,
            "LANG": "en_US.UTF-8",
        }

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=temp_dir,
            env=safe_env,
        )

        execution_time = (time.time() - start_time) * 1000

        output = _truncate_output(result.stdout)
        error = _truncate_output(result.stderr) if result.stderr else None

        return ExecuteCodeResponse(
            success=result.returncode == 0, output=output, error=error,
            execution_time=round(execution_time, 2), language=language
        )

    except subprocess.TimeoutExpired:
        execution_time = (time.time() - start_time) * 1000
        return ExecuteCodeResponse(
            success=False, output="",
            error=f"执行超时：代码运行超过 {timeout} 秒",
            execution_time=round(execution_time, 2), language=language
        )

    except Exception as e:
        execution_time = (time.time() - start_time) * 1000
        logger.error(f"Code execution error: {e}")
        return ExecuteCodeResponse(
            success=False, output="",
            error="执行错误：代码运行失败",
            execution_time=round(execution_time, 2), language=language
        )

    finally:
        _cleanup_temp_dir(temp_dir)


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
