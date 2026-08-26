"""Local Codex CLI adapter for real-model development and acceptance runs.

The adapter deliberately sits below the course-generation services.  Course
outlines, lesson plans, scripts and slide manuscripts still travel through the
same application contracts and quality gates; only the model transport changes
from an OpenAI-compatible HTTP endpoint to the locally authenticated Codex CLI.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from collections.abc import Callable
from pathlib import Path


logger = logging.getLogger(__name__)


class CodexLocalProviderError(RuntimeError):
    """The local Codex process could not produce a usable model response."""


class CodexLocalProvider:
    """Call ``codex exec`` without exposing its agent surface to course code."""

    def __init__(self) -> None:
        configured_executable = str(
            os.getenv("AI_CODEX_EXECUTABLE") or ""
        ).strip()
        self.executable = (
            configured_executable
            or shutil.which("codex")
            or ""
        )
        self.model = str(os.getenv("AI_CODEX_MODEL") or "").strip()
        self.timeout_seconds = max(
            30.0,
            float(os.getenv("AI_CODEX_TIMEOUT_SECONDS", "600")),
        )
        self.heartbeat_seconds = max(
            1.0,
            float(os.getenv("AI_CODEX_HEARTBEAT_SECONDS", "5")),
        )
        configured_workdir = str(
            os.getenv("AI_CODEX_WORKDIR") or "/tmp"
        ).strip()
        self.workdir = Path(configured_workdir).expanduser()
        self._semaphore = asyncio.Semaphore(
            max(1, int(os.getenv("AI_CODEX_MAX_CONCURRENCY", "4")))
        )

    @property
    def configured(self) -> bool:
        return bool(self.executable and self.workdir.is_dir())

    def _command(self) -> list[str]:
        if not self.configured:
            raise CodexLocalProviderError(
                "local_codex_not_configured"
            )
        command = [
            self.executable,
            "exec",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--color",
            "never",
            "--disable",
            "plugins",
            "--disable",
            "remote_plugin",
            "--disable",
            "apps",
            "--disable",
            "browser_use",
            "--disable",
            "computer_use",
            "--disable",
            "image_generation",
            "--disable",
            "skill_search",
            "--disable",
            "memories",
            "--disable",
            "hooks",
            "--disable",
            "tool_suggest",
            "--disable",
            "shell_tool",
            "-C",
            str(self.workdir),
        ]
        if self.model:
            command.extend(["--model", self.model])
        command.append("-")
        return command

    @staticmethod
    def _compose_prompt(
        *,
        prompt: str,
        system_prompt: str,
        json_mode: bool,
        max_tokens: int | None,
    ) -> str:
        output_contract = [
            "你是灵知课程生产链路内部的模型提供方。",
            "不得读取文件、调用工具、修改环境或补充链路外任务。",
            "只执行下方系统指令与用户请求，并且最终只输出可直接交给调用方的正文，不要解释执行过程。",
        ]
        if json_mode:
            output_contract.append(
                "最终输出必须是单个有效 JSON 值，不要使用 Markdown 代码围栏。"
            )
        if max_tokens is not None:
            output_contract.append(
                f"输出应控制在约 {max_tokens} tokens 以内。"
            )
        return "\n".join([
            *output_contract,
            "",
            "<system_instruction>",
            system_prompt,
            "</system_instruction>",
            "",
            "<user_request>",
            prompt,
            "</user_request>",
        ])

    async def call(
        self,
        *,
        prompt: str,
        system_prompt: str,
        json_mode: bool = False,
        max_tokens: int | None = None,
        on_activity: Callable[[], None] | None = None,
    ) -> str:
        payload = self._compose_prompt(
            prompt=prompt,
            system_prompt=system_prompt,
            json_mode=json_mode,
            max_tokens=max_tokens,
        )
        async with self._semaphore:
            process = await asyncio.create_subprocess_exec(
                *self._command(),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.workdir),
            )
            communicate = asyncio.create_task(
                process.communicate(payload.encode("utf-8"))
            )
            elapsed = 0.0
            try:
                while True:
                    done, _ = await asyncio.wait(
                        {communicate},
                        timeout=self.heartbeat_seconds,
                    )
                    if done:
                        break
                    elapsed += self.heartbeat_seconds
                    if on_activity:
                        on_activity()
                    if elapsed >= self.timeout_seconds:
                        process.terminate()
                        await process.wait()
                        communicate.cancel()
                        try:
                            await communicate
                        except asyncio.CancelledError:
                            pass
                        raise CodexLocalProviderError(
                            "local_codex_timeout"
                        )
                stdout, _stderr = await communicate
            except asyncio.CancelledError:
                process.terminate()
                await process.wait()
                communicate.cancel()
                try:
                    await communicate
                except asyncio.CancelledError:
                    pass
                raise

        output = stdout.decode("utf-8", errors="replace").strip()
        if process.returncode != 0:
            raise CodexLocalProviderError(
                "local_codex_process_failed:"
                f"exit={process.returncode}"
            )
        if not output:
            raise CodexLocalProviderError("local_codex_empty_response")
        logger.info(
            "Local Codex response complete (model=%s, chars=%d)",
            self.model or "codex-default",
            len(output),
        )
        return output
