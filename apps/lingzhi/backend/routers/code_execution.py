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
from fastapi.concurrency import run_in_threadpool
import subprocess
import tempfile
import time
import re
import os
import sys
import platform
import logging
import shlex
import shutil

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from models import ExecuteCodeRequest, ExecuteCodeResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["code_execution"])

# 支持的语言配置（移除 bash/shell/typescript 以缩小攻击面）
SUPPORTED_LANGUAGES = {
    "python": {"extension": ".py", "timeout": 10},
    "javascript": {"extension": ".js", "timeout": 10},
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
        if dir_path and os.path.exists(dir_path):
            shutil.rmtree(dir_path, ignore_errors=True)
    except Exception:
        pass


def _linux_process_limit(proc_root: str = "/proc") -> int:
    """Reserve 32 additional tasks without counting the host's existing work.

    RLIMIT_NPROC counts all threads owned by the real UID, not just this child.
    A fixed limit of 32 can prevent Node from creating its first internal thread
    on a busy worker even when the submitted snippet starts no workers itself.
    """
    existing = 0
    uid = os.getuid()
    with os.scandir(proc_root) as processes:
        for process in processes:
            if not process.name.isdigit():
                continue
            try:
                if process.stat(follow_symlinks=False).st_uid != uid:
                    continue
                with open(os.path.join(process.path, "status"), encoding="utf-8") as handle:
                    for line in handle:
                        if line.startswith("Threads:"):
                            existing += int(line.split()[1])
                            break
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                # Processes can exit while the snapshot is being collected.
                continue
    return existing + 32


def _build_sandbox_command(base_command: list, file_path: str, language: str) -> list:
    """
    构建带资源限制的沙箱命令。
    Linux 环境下使用 ulimit 限制资源；其他平台仅依赖 timeout。
    """
    if platform.system() != "Linux":
        return base_command + [file_path]

    # Node 24 reserves address space for V8 tables before running any code.
    # Its JS heap is separately capped at 64 MB. Python retains its 256 MB cap.
    virtual_memory_kb = 1048576 if language == "javascript" else 262144
    limits = [
        f"ulimit -v {virtual_memory_kb};",
        "ulimit -f 1024;",      # 文件大小 512KB
        f"ulimit -u {_linux_process_limit()};",  # UID-wide budget above existing tasks
        "ulimit -t 10;",        # CPU 时间 10 秒
    ]

    # Runtime and temporary paths can contain spaces or shell metacharacters.
    # exec also makes subprocess.run's timeout target the runtime itself.
    inner_cmd = shlex.join(base_command + [file_path])
    shell_cmd = " ".join(limits) + " exec " + inner_cmd

    return ["bash", "-c", shell_cmd]


def _runtime_command(language: str) -> list[str]:
    if language == "python":
        return [sys.executable]
    executable = shutil.which("node")
    if not executable:
        raise FileNotFoundError("JavaScript runtime is unavailable")
    # V8's default JIT and background workers reserve more virtual address
    # space than this teaching sandbox permits, even for console.log(). Keep
    # bounded OS limits and run small snippets without JIT or worker pools.
    # Disabling the Wasm trap handler avoids its large address-space reservation.
    return [executable, "--single-threaded", "--jitless", "--disable-wasm-trap-handler",
            "--max-old-space-size=64"]


def _sandbox_environment(temp_dir: str, runtime: str) -> dict[str, str]:
    # Resolve executables before reducing the environment. Never copy the host
    # environment: it can contain model credentials and service access tokens.
    runtime_directory = os.path.dirname(runtime)
    system = platform.system()
    safe_env = {
        "PATH": runtime_directory if system == "Windows" else runtime_directory + os.pathsep + os.defpath,
        "HOME": temp_dir,
        "TMPDIR": temp_dir,
        "TMP": temp_dir,
        "TEMP": temp_dir,
        "LANG": "C.UTF-8",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }
    if system == "Windows":
        # Required by Windows subprocess/runtime DLL resolution. Only these OS
        # paths are inherited; PATH, PYTHONPATH and arbitrary variables are not.
        for name in ("SystemRoot", "WINDIR"):
            if os.environ.get(name):
                safe_env[name] = os.environ[name]
    return safe_env


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

    # A teaching snippet may run until timeout. Keep other requests and SSE
    # heartbeats responsive while the subprocess and temporary files finish.
    return await run_in_threadpool(_execute_code, req.code, language, timeout)


def _execute_code(code: str, language: str, timeout: int) -> ExecuteCodeResponse:
    lang_config = SUPPORTED_LANGUAGES[language]
    start_time = time.perf_counter()
    temp_dir = None

    try:
        # 在独立临时目录中执行，隔离文件系统访问
        temp_dir = tempfile.mkdtemp(prefix="sandbox_")
        file_path = os.path.join(temp_dir, f"code{lang_config['extension']}")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(code)

        # 构建沙箱命令
        runtime = _runtime_command(language)
        cmd = _build_sandbox_command(runtime, file_path, language)

        # 设置受限环境变量（不继承宿主环境）
        safe_env = _sandbox_environment(temp_dir, runtime[0])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=temp_dir,
            env=safe_env,
        )

        execution_time = (time.perf_counter() - start_time) * 1000

        output = _truncate_output(result.stdout)
        error = _truncate_output(result.stderr) if result.stderr else None
        if result.returncode != 0 and not error:
            error = f"执行失败：进程退出码 {result.returncode}"

        return ExecuteCodeResponse(
            success=result.returncode == 0, output=output, error=error,
            execution_time=round(execution_time, 2), language=language
        )

    except subprocess.TimeoutExpired:
        execution_time = (time.perf_counter() - start_time) * 1000
        return ExecuteCodeResponse(
            success=False, output="",
            error=f"执行超时：代码运行超过 {timeout} 秒",
            execution_time=round(execution_time, 2), language=language
        )

    except Exception as e:
        execution_time = (time.perf_counter() - start_time) * 1000
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
