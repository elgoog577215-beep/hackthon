"""WebSocket 服务，管理连接和消息推送，替代旧的 ConnectionManager。

支持按 courseId 订阅/取消订阅，仅向订阅了对应课程的客户端推送事件。
处理客户端命令（skip_node、retry_node、custom_instruction、stop_node、retry_all_failed）
并委托给注入的 command_handler 回调执行。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Literal, TypedDict

from fastapi import WebSocket

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Message protocol types
# ---------------------------------------------------------------------------

class WSMessage(TypedDict, total=False):
    """服务端 -> 客户端 消息协议"""
    type: Literal[
        "progress_update",
        "node_completed",
        "stream_chunk",
        "task_completed",
        "task_error",
        "failure_report",
    ]
    task_id: str
    course_id: str
    payload: dict


class WSCommand(TypedDict, total=False):
    """客户端 -> 服务端 命令协议"""
    type: Literal[
        "subscribe",
        "unsubscribe",
        "skip_node",
        "retry_node",
        "stop_node",
        "custom_instruction",
        "retry_all_failed",
    ]
    course_id: str
    node_id: str | None
    payload: dict | None


# Type alias for the command handler callback (injected, e.g. TaskManager methods)
CommandHandler = Callable[[str, dict], Awaitable[None]]


# ---------------------------------------------------------------------------
# WebSocketService
# ---------------------------------------------------------------------------

class WebSocketService:
    """WebSocket 服务，管理连接和消息推送。

    * 每个连接分配唯一 ``connection_id``（UUID）。
    * 支持按 ``course_id`` 订阅/取消订阅。
    * 推送方法仅发送给订阅了对应 ``course_id`` 的客户端。
    * ``handle_client_command`` 将命令委托给注入的 ``command_handler``。
    """

    def __init__(self, command_handler: CommandHandler | None = None) -> None:
        # connection_id -> WebSocket
        self._connections: dict[str, WebSocket] = {}
        # connection_id -> set of subscribed course_ids
        self._subscriptions: dict[str, set[str]] = {}
        # course_id -> set of connection_ids subscribed to it
        self._course_subscribers: dict[str, set[str]] = {}
        # Lock for thread-safe mutation of connection/subscription state
        self._lock: asyncio.Lock = asyncio.Lock()
        # Injected callback for handling task-level commands
        self._command_handler: CommandHandler | None = command_handler

    # ------------------------------------------------------------------
    # Command handler injection
    # ------------------------------------------------------------------

    def set_command_handler(self, handler: CommandHandler) -> None:
        """Set or replace the command handler callback."""
        self._command_handler = handler

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(
        self,
        websocket: WebSocket,
        course_id: str | None = None,
    ) -> str:
        """Accept a WebSocket connection and return a unique ``connection_id``.

        If *course_id* is provided the connection is automatically subscribed.
        """
        await websocket.accept()
        connection_id = str(uuid.uuid4())

        async with self._lock:
            self._connections[connection_id] = websocket
            self._subscriptions[connection_id] = set()

        if course_id is not None:
            await self.subscribe(connection_id, course_id)

        logger.info(
            "WebSocket connected: %s (course=%s). Total: %d",
            connection_id,
            course_id,
            len(self._connections),
        )
        return connection_id

    async def disconnect(self, connection_id: str) -> None:
        """Disconnect and clean up all subscriptions for *connection_id*."""
        async with self._lock:
            subscribed_courses = self._subscriptions.pop(connection_id, set())
            for cid in subscribed_courses:
                subs = self._course_subscribers.get(cid)
                if subs is not None:
                    subs.discard(connection_id)
                    if not subs:
                        del self._course_subscribers[cid]
            self._connections.pop(connection_id, None)

        logger.info(
            "WebSocket disconnected: %s. Total: %d",
            connection_id,
            len(self._connections),
        )

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    async def subscribe(self, connection_id: str, course_id: str) -> None:
        """Subscribe *connection_id* to updates for *course_id*."""
        async with self._lock:
            subs = self._subscriptions.get(connection_id)
            if subs is None:
                logger.warning("subscribe: unknown connection %s", connection_id)
                return
            subs.add(course_id)
            self._course_subscribers.setdefault(course_id, set()).add(connection_id)

        logger.debug("Connection %s subscribed to course %s", connection_id, course_id)

    async def unsubscribe(self, connection_id: str, course_id: str) -> None:
        """Unsubscribe *connection_id* from *course_id*."""
        async with self._lock:
            subs = self._subscriptions.get(connection_id)
            if subs is not None:
                subs.discard(course_id)
            course_subs = self._course_subscribers.get(course_id)
            if course_subs is not None:
                course_subs.discard(connection_id)
                if not course_subs:
                    del self._course_subscribers[course_id]

        logger.debug("Connection %s unsubscribed from course %s", connection_id, course_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_subscribers(self, course_id: str) -> list[tuple[str, WebSocket]]:
        """Return a snapshot of (connection_id, websocket) pairs subscribed to *course_id*."""
        async with self._lock:
            conn_ids = list(self._course_subscribers.get(course_id, set()))
            return [
                (cid, self._connections[cid])
                for cid in conn_ids
                if cid in self._connections
            ]

    async def _send_to_subscribers(self, course_id: str, message: dict[str, Any]) -> None:
        """Send *message* to all clients subscribed to *course_id*.

        Silently removes connections that have been closed.
        """
        subscribers = await self._get_subscribers(course_id)
        disconnected: list[str] = []

        for conn_id, ws in subscribers:
            try:
                await ws.send_json(message)
            except Exception:
                logger.warning("Failed to send to %s, marking as disconnected", conn_id)
                disconnected.append(conn_id)

        for conn_id in disconnected:
            await self.disconnect(conn_id)

    # ------------------------------------------------------------------
    # Push methods (server -> client)
    # ------------------------------------------------------------------

    async def push_node_completed(self, course_id: str, node_data: dict[str, Any]) -> None:
        """Push a ``node_completed`` event to subscribers of *course_id*."""
        message: WSMessage = {
            "type": "node_completed",
            "course_id": course_id,
            "task_id": node_data.get("task_id", ""),
            "payload": node_data,
        }
        await self._send_to_subscribers(course_id, message)

    async def push_progress_update(self, course_id: str, progress: dict[str, Any]) -> None:
        """Push a ``progress_update`` event to subscribers of *course_id*.

        *progress* should contain: task_id, status, progress, current_node_name,
        completed_nodes, total_nodes, estimated_time_remaining.
        """
        message: WSMessage = {
            "type": "progress_update",
            "course_id": course_id,
            "task_id": progress.get("task_id", ""),
            "payload": progress,
        }
        await self._send_to_subscribers(course_id, message)

    async def push_stream_chunk(
        self,
        course_id: str,
        node_id: str,
        chunk: str,
    ) -> None:
        """Push a ``stream_chunk`` event to subscribers of *course_id*."""
        message: WSMessage = {
            "type": "stream_chunk",
            "course_id": course_id,
            "task_id": "",
            "payload": {
                "node_id": node_id,
                "chunk": chunk,
            },
        }
        await self._send_to_subscribers(course_id, message)

    async def push_error(self, course_id: str, error: dict[str, Any]) -> None:
        """Push a ``task_error`` event to subscribers of *course_id*."""
        message: WSMessage = {
            "type": "task_error",
            "course_id": course_id,
            "task_id": error.get("task_id", ""),
            "payload": error,
        }
        await self._send_to_subscribers(course_id, message)

    async def push_task_completed(self, course_id: str, payload: dict[str, Any]) -> None:
        """Push a ``task_completed`` event to subscribers of *course_id*."""
        message: WSMessage = {
            "type": "task_completed",
            "course_id": course_id,
            "task_id": payload.get("task_id", ""),
            "payload": payload,
        }
        await self._send_to_subscribers(course_id, message)

    async def push_failure_report(self, course_id: str, report: dict[str, Any]) -> None:
        """Push a ``failure_report`` event to subscribers of *course_id*."""
        message: WSMessage = {
            "type": "failure_report",
            "course_id": course_id,
            "task_id": report.get("task_id", ""),
            "payload": report,
        }
        await self._send_to_subscribers(course_id, message)

    # ------------------------------------------------------------------
    # Client command handling
    # ------------------------------------------------------------------

    async def handle_client_command(self, connection_id: str, command: dict[str, Any]) -> None:
        """Process a command received from the client.

        Subscription commands (``subscribe`` / ``unsubscribe``) are handled
        directly.  Task-level commands (``skip_node``, ``retry_node``,
        ``custom_instruction``, ``stop_node``, ``retry_all_failed``) are
        delegated to the injected *command_handler* callback.
        """
        cmd_type: str = command.get("type", "")
        course_id: str = command.get("course_id", "")
        node_id: str | None = command.get("node_id")
        payload: dict[str, Any] | None = command.get("payload")

        # --- Subscription commands handled locally ---
        if cmd_type == "subscribe":
            if course_id:
                await self.subscribe(connection_id, course_id)
            return

        if cmd_type == "unsubscribe":
            if course_id:
                await self.unsubscribe(connection_id, course_id)
            return

        # --- Task-level commands delegated to command_handler ---
        valid_commands = {
            "skip_node",
            "retry_node",
            "custom_instruction",
            "stop_node",
            "retry_all_failed",
        }

        if cmd_type not in valid_commands:
            logger.warning("Unknown command type: %s from %s", cmd_type, connection_id)
            return

        if self._command_handler is None:
            logger.error(
                "No command_handler set; cannot process command %s from %s",
                cmd_type,
                connection_id,
            )
            return

        try:
            await self._command_handler(cmd_type, {
                "course_id": course_id,
                "node_id": node_id,
                "payload": payload,
            })
        except Exception:
            logger.exception(
                "Error handling command %s from %s",
                cmd_type,
                connection_id,
            )

    # ------------------------------------------------------------------
    # Broadcast (all connections, regardless of subscription)
    # ------------------------------------------------------------------

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send *message* to every connected client (no subscription filter)."""
        async with self._lock:
            items = list(self._connections.items())

        disconnected: list[str] = []
        for conn_id, ws in items:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(conn_id)

        for conn_id in disconnected:
            await self.disconnect(conn_id)

    # ------------------------------------------------------------------
    # Utility / introspection
    # ------------------------------------------------------------------

    @property
    def connection_count(self) -> int:
        """Number of active connections."""
        return len(self._connections)

    def get_subscribed_courses(self, connection_id: str) -> set[str]:
        """Return the set of course_ids a connection is subscribed to."""
        return set(self._subscriptions.get(connection_id, set()))
