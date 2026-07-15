"""WebSocket integration tests for the course-generation-optimization spec.

Tests cover:
- WebSocket connection, subscription, and message push flow
- Multi-client concurrent subscription isolation
- Client command handling (skip_node, retry_node, stop_node, custom_instruction, retry_all_failed)
- WebSocket disconnect/reconnect scenarios

Requirements: 1.1, 1.5, 7.4, 16.4
"""
from __future__ import annotations

import asyncio
import json
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from websocket_service import WebSocketService
from models import NodeStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_app(ws_service: WebSocketService | None = None):
    """Create a minimal FastAPI app with the /ws endpoint for testing."""
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from starlette.routing import WebSocketRoute

    svc = ws_service or WebSocketService()

    async def websocket_endpoint(websocket: WebSocket):
        connection_id = await svc.connect(websocket)
        try:
            while True:
                data = await websocket.receive_json()
                await svc.handle_client_command(connection_id, data)
        except WebSocketDisconnect:
            await svc.disconnect(connection_id)
        except Exception:
            await svc.disconnect(connection_id)

    app = FastAPI(routes=[WebSocketRoute("/ws", websocket_endpoint)])

    return app, svc


# ===========================================================================
# 1. Connection, subscription, and message push flow
# ===========================================================================

class TestWebSocketConnectionAndSubscription:
    """Test WebSocket connection, subscription, and message push flow."""

    def test_connect_and_subscribe(self):
        """Client can connect via /ws and subscribe to a course."""
        app, svc = _make_app()
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            # Subscribe to a course
            ws.send_json({"type": "subscribe", "course_id": "course-001"})
            # Connection should be tracked
            assert svc.connection_count >= 1

    def test_subscribe_receives_progress_update(self):
        """Subscribed client receives progress_update messages."""
        app, svc = _make_app()
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "subscribe", "course_id": "course-001"})

            # Push a progress update from the server side
            import threading

            def push():
                import asyncio as _aio
                loop = _aio.new_event_loop()
                loop.run_until_complete(
                    svc.push_progress_update("course-001", {
                        "task_id": "task-1",
                        "course_id": "course-001",
                        "status": "running",
                        "progress": 50,
                        "current_node_name": "1.1 基本概念",
                        "completed_nodes": 3,
                        "total_nodes": 6,
                        "estimated_time_remaining": 30,
                    })
                )
                loop.close()

            t = threading.Thread(target=push)
            t.start()
            t.join(timeout=5)

            msg = ws.receive_json()
            assert msg["type"] == "progress_update"
            assert msg["course_id"] == "course-001"
            assert "payload" in msg
            assert msg["payload"]["task_id"] == "task-1"
            assert msg["payload"]["progress"] == 50
            assert msg["payload"]["completed_nodes"] == 3
            assert msg["payload"]["total_nodes"] == 6

    def test_subscribe_receives_node_completed(self):
        """Subscribed client receives node_completed messages."""
        app, svc = _make_app()
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "subscribe", "course_id": "course-001"})

            import threading, asyncio as _aio

            def push():
                loop = _aio.new_event_loop()
                loop.run_until_complete(
                    svc.push_node_completed("course-001", {
                        "task_id": "task-1",
                        "node_id": "L2-1-1",
                        "node_name": "1.1 基本概念",
                        "generated_chars": 1200,
                    })
                )
                loop.close()

            t = threading.Thread(target=push)
            t.start()
            t.join(timeout=5)

            msg = ws.receive_json()
            assert msg["type"] == "node_completed"
            assert msg["course_id"] == "course-001"
            assert msg["payload"]["node_id"] == "L2-1-1"

    def test_unsubscribe_stops_messages(self):
        """After unsubscribing, client no longer receives messages for that course."""
        app, svc = _make_app()
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "subscribe", "course_id": "course-001"})
            ws.send_json({"type": "unsubscribe", "course_id": "course-001"})

            import threading, asyncio as _aio

            def push():
                loop = _aio.new_event_loop()
                loop.run_until_complete(
                    svc.push_progress_update("course-001", {
                        "task_id": "task-1",
                        "course_id": "course-001",
                        "status": "running",
                        "progress": 50,
                    })
                )
                loop.close()

            t = threading.Thread(target=push)
            t.start()
            t.join(timeout=5)

            # The client should NOT receive any message.
            # We use a short timeout to verify no message arrives.
            import queue
            try:
                # Starlette TestClient websocket doesn't have a timeout param
                # on receive_json, so we rely on the fact that no message was sent.
                # Instead, verify via the service that no subscribers exist.
                pass
            except Exception:
                pass

            # Verify the connection has no subscriptions for course-001
            # We need to find the connection_id; check via service internals
            assert len(svc._course_subscribers.get("course-001", set())) == 0


# ===========================================================================
# 2. Multi-client concurrent subscription isolation
# ===========================================================================

class TestMultiClientSubscriptionIsolation:
    """Test that messages are only delivered to clients subscribed to the relevant course."""

    def test_two_clients_different_courses(self):
        """Client A subscribes to course-001, Client B to course-002.
        Messages for course-001 only go to Client A."""
        app, svc = _make_app()
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws_a:
            ws_a.send_json({"type": "subscribe", "course_id": "course-001"})

            with client.websocket_connect("/ws") as ws_b:
                ws_b.send_json({"type": "subscribe", "course_id": "course-002"})

                import threading, asyncio as _aio

                def push():
                    loop = _aio.new_event_loop()
                    loop.run_until_complete(
                        svc.push_progress_update("course-001", {
                            "task_id": "task-1",
                            "course_id": "course-001",
                            "status": "running",
                            "progress": 75,
                        })
                    )
                    loop.close()

                t = threading.Thread(target=push)
                t.start()
                t.join(timeout=5)

                # Client A should receive the message
                msg_a = ws_a.receive_json()
                assert msg_a["type"] == "progress_update"
                assert msg_a["course_id"] == "course-001"

                # Client B should NOT receive anything for course-001
                # Verify via service that course-002 subscribers don't include course-001 messages
                subs_002 = svc._course_subscribers.get("course-002", set())
                subs_001 = svc._course_subscribers.get("course-001", set())
                assert subs_001.isdisjoint(subs_002)

    def test_two_clients_same_course(self):
        """Both clients subscribe to the same course and both receive messages."""
        app, svc = _make_app()
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws_a:
            ws_a.send_json({"type": "subscribe", "course_id": "course-001"})

            with client.websocket_connect("/ws") as ws_b:
                ws_b.send_json({"type": "subscribe", "course_id": "course-001"})

                import threading, asyncio as _aio

                def push():
                    loop = _aio.new_event_loop()
                    loop.run_until_complete(
                        svc.push_node_completed("course-001", {
                            "task_id": "task-1",
                            "node_id": "L2-1-1",
                            "node_name": "1.1 基本概念",
                            "generated_chars": 800,
                        })
                    )
                    loop.close()

                t = threading.Thread(target=push)
                t.start()
                t.join(timeout=5)

                msg_a = ws_a.receive_json()
                msg_b = ws_b.receive_json()

                assert msg_a["type"] == "node_completed"
                assert msg_b["type"] == "node_completed"
                assert msg_a["payload"]["node_id"] == "L2-1-1"
                assert msg_b["payload"]["node_id"] == "L2-1-1"

    def test_client_subscribes_multiple_courses(self):
        """A single client can subscribe to multiple courses and receive messages for both."""
        app, svc = _make_app()
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "subscribe", "course_id": "course-001"})
            ws.send_json({"type": "subscribe", "course_id": "course-002"})

            import threading, asyncio as _aio

            def push():
                loop = _aio.new_event_loop()
                loop.run_until_complete(
                    svc.push_progress_update("course-002", {
                        "task_id": "task-2",
                        "course_id": "course-002",
                        "status": "running",
                        "progress": 25,
                    })
                )
                loop.close()

            t = threading.Thread(target=push)
            t.start()
            t.join(timeout=5)

            msg = ws.receive_json()
            assert msg["type"] == "progress_update"
            assert msg["course_id"] == "course-002"


# ===========================================================================
# 3. Client command handling
# ===========================================================================

class TestClientCommandHandling:
    """Test that client commands are properly received and forwarded to the command handler."""

    def test_skip_node_command(self):
        """skip_node command is forwarded to the command handler."""
        handler = AsyncMock()
        svc = WebSocketService(command_handler=handler)
        app, _ = _make_app(svc)
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "subscribe", "course_id": "course-001"})
            ws.send_json({
                "type": "skip_node",
                "course_id": "course-001",
                "node_id": "L2-1-1",
            })

        # The handler should have been called with skip_node
        handler.assert_called()
        call_args = handler.call_args
        assert call_args[0][0] == "skip_node"
        assert call_args[0][1]["course_id"] == "course-001"
        assert call_args[0][1]["node_id"] == "L2-1-1"

    def test_retry_node_command(self):
        """retry_node command is forwarded to the command handler."""
        handler = AsyncMock()
        svc = WebSocketService(command_handler=handler)
        app, _ = _make_app(svc)
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "subscribe", "course_id": "course-001"})
            ws.send_json({
                "type": "retry_node",
                "course_id": "course-001",
                "node_id": "L2-1-2",
            })

        handler.assert_called()
        call_args = handler.call_args
        assert call_args[0][0] == "retry_node"
        assert call_args[0][1]["node_id"] == "L2-1-2"

    def test_stop_node_command(self):
        """stop_node command is forwarded to the command handler."""
        handler = AsyncMock()
        svc = WebSocketService(command_handler=handler)
        app, _ = _make_app(svc)
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({
                "type": "stop_node",
                "course_id": "course-001",
                "node_id": "L2-1-1",
            })

        handler.assert_called()
        assert handler.call_args[0][0] == "stop_node"

    def test_custom_instruction_command(self):
        """custom_instruction command is forwarded with payload."""
        handler = AsyncMock()
        svc = WebSocketService(command_handler=handler)
        app, _ = _make_app(svc)
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({
                "type": "custom_instruction",
                "course_id": "course-001",
                "node_id": "L2-1-1",
                "payload": {"instruction": "请增加更多代码示例"},
            })

        handler.assert_called()
        call_args = handler.call_args
        assert call_args[0][0] == "custom_instruction"
        assert call_args[0][1]["payload"]["instruction"] == "请增加更多代码示例"

    def test_retry_all_failed_command(self):
        """retry_all_failed command is forwarded to the command handler."""
        handler = AsyncMock()
        svc = WebSocketService(command_handler=handler)
        app, _ = _make_app(svc)
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({
                "type": "retry_all_failed",
                "course_id": "course-001",
            })

        handler.assert_called()
        assert handler.call_args[0][0] == "retry_all_failed"
        assert handler.call_args[0][1]["course_id"] == "course-001"

    def test_unknown_command_ignored(self):
        """Unknown command types are silently ignored (no crash)."""
        handler = AsyncMock()
        svc = WebSocketService(command_handler=handler)
        app, _ = _make_app(svc)
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({
                "type": "invalid_command",
                "course_id": "course-001",
            })

        # Handler should NOT be called for unknown commands
        handler.assert_not_called()

    def test_command_without_handler_does_not_crash(self):
        """Sending a task command when no handler is set does not crash."""
        svc = WebSocketService()  # No command_handler
        app, _ = _make_app(svc)
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({
                "type": "skip_node",
                "course_id": "course-001",
                "node_id": "L2-1-1",
            })
        # Should not raise


# ===========================================================================
# 4. WebSocket disconnect/reconnect scenarios
# ===========================================================================

class TestWebSocketDisconnectReconnect:
    """Test WebSocket disconnect and reconnect behavior."""

    def test_disconnect_cleans_up_subscriptions(self):
        """When a client disconnects, its subscriptions are cleaned up."""
        app, svc = _make_app()
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "subscribe", "course_id": "course-001"})
            # Force a round-trip to ensure subscribe is processed
            import threading, asyncio as _aio

            def push():
                loop = _aio.new_event_loop()
                loop.run_until_complete(
                    svc.push_progress_update("course-001", {
                        "task_id": "t", "course_id": "course-001",
                        "status": "running", "progress": 1,
                    })
                )
                loop.close()

            t = threading.Thread(target=push)
            t.start()
            t.join(timeout=5)
            # Receiving the message proves subscription was active
            msg = ws.receive_json()
            assert msg["type"] == "progress_update"

        # After disconnect, subscriptions should be cleaned
        assert len(svc._course_subscribers.get("course-001", set())) == 0

    def test_disconnect_decrements_connection_count(self):
        """Connection count decreases after disconnect."""
        app, svc = _make_app()
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            assert svc.connection_count >= 1

        assert svc.connection_count == 0

    def test_reconnect_can_resubscribe(self):
        """After disconnect and reconnect, client can subscribe again."""
        app, svc = _make_app()
        client = TestClient(app)

        # First connection
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "subscribe", "course_id": "course-001"})
        assert svc.connection_count == 0

        # Reconnect and verify subscription works by receiving a message
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "subscribe", "course_id": "course-001"})

            import threading, asyncio as _aio

            def push():
                loop = _aio.new_event_loop()
                loop.run_until_complete(
                    svc.push_progress_update("course-001", {
                        "task_id": "t", "course_id": "course-001",
                        "status": "running", "progress": 10,
                    })
                )
                loop.close()

            t = threading.Thread(target=push)
            t.start()
            t.join(timeout=5)

            msg = ws.receive_json()
            assert msg["type"] == "progress_update"
            assert svc.connection_count >= 1

    def test_reconnect_receives_messages_after_resubscribe(self):
        """After reconnecting and resubscribing, client receives messages again."""
        app, svc = _make_app()
        client = TestClient(app)

        # First connection and disconnect
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "subscribe", "course_id": "course-001"})

        # Reconnect
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "subscribe", "course_id": "course-001"})

            import threading, asyncio as _aio

            def push():
                loop = _aio.new_event_loop()
                loop.run_until_complete(
                    svc.push_progress_update("course-001", {
                        "task_id": "task-1",
                        "course_id": "course-001",
                        "status": "running",
                        "progress": 80,
                    })
                )
                loop.close()

            t = threading.Thread(target=push)
            t.start()
            t.join(timeout=5)

            msg = ws.receive_json()
            assert msg["type"] == "progress_update"
            assert msg["payload"]["progress"] == 80

    def test_multiple_disconnect_reconnect_cycles(self):
        """Multiple disconnect/reconnect cycles work correctly."""
        app, svc = _make_app()
        client = TestClient(app)

        for i in range(3):
            with client.websocket_connect("/ws") as ws:
                ws.send_json({"type": "subscribe", "course_id": f"course-{i}"})
                assert svc.connection_count >= 1

            # After each disconnect
            assert len(svc._course_subscribers.get(f"course-{i}", set())) == 0

        assert svc.connection_count == 0


# ===========================================================================
# 5. Message structure validation
# ===========================================================================

class TestMessageStructure:
    """Test that pushed messages contain all required fields."""

    def test_progress_update_message_structure(self):
        """progress_update messages contain type, course_id, task_id, payload."""
        app, svc = _make_app()
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "subscribe", "course_id": "course-001"})

            import threading, asyncio as _aio

            def push():
                loop = _aio.new_event_loop()
                loop.run_until_complete(
                    svc.push_progress_update("course-001", {
                        "task_id": "task-1",
                        "course_id": "course-001",
                        "status": "running",
                        "progress": 50,
                        "current_node_name": "1.1 基本概念",
                        "completed_nodes": 3,
                        "total_nodes": 6,
                        "estimated_time_remaining": 30,
                    })
                )
                loop.close()

            t = threading.Thread(target=push)
            t.start()
            t.join(timeout=5)

            msg = ws.receive_json()
            # Validate required top-level fields
            assert "type" in msg
            assert "course_id" in msg
            assert "task_id" in msg
            assert "payload" in msg
            # Validate payload fields per Requirement 1.6
            payload = msg["payload"]
            assert "task_id" in payload
            assert "status" in payload
            assert "progress" in payload
            assert "current_node_name" in payload
            assert "completed_nodes" in payload
            assert "total_nodes" in payload

    def test_stream_chunk_message_structure(self):
        """stream_chunk messages contain node_id and chunk in payload."""
        app, svc = _make_app()
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "subscribe", "course_id": "course-001"})

            import threading, asyncio as _aio

            def push():
                loop = _aio.new_event_loop()
                loop.run_until_complete(
                    svc.push_stream_chunk("course-001", "L2-1-1", "Hello ")
                )
                loop.close()

            t = threading.Thread(target=push)
            t.start()
            t.join(timeout=5)

            msg = ws.receive_json()
            assert msg["type"] == "stream_chunk"
            assert msg["payload"]["node_id"] == "L2-1-1"
            assert msg["payload"]["chunk"] == "Hello "

    def test_task_error_message_structure(self):
        """task_error messages contain error details in payload."""
        app, svc = _make_app()
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "subscribe", "course_id": "course-001"})

            import threading, asyncio as _aio

            def push():
                loop = _aio.new_event_loop()
                loop.run_until_complete(
                    svc.push_error("course-001", {
                        "task_id": "task-1",
                        "node_id": "L2-1-1",
                        "error": "LLM API timeout",
                    })
                )
                loop.close()

            t = threading.Thread(target=push)
            t.start()
            t.join(timeout=5)

            msg = ws.receive_json()
            assert msg["type"] == "task_error"
            assert msg["course_id"] == "course-001"
            assert "error" in msg["payload"]

    def test_failure_report_message_structure(self):
        """failure_report messages contain failed_nodes list."""
        app, svc = _make_app()
        client = TestClient(app)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "subscribe", "course_id": "course-001"})

            import threading, asyncio as _aio

            def push():
                loop = _aio.new_event_loop()
                loop.run_until_complete(
                    svc.push_failure_report("course-001", {
                        "task_id": "task-1",
                        "course_id": "course-001",
                        "failed_nodes": [
                            {"node_id": "L2-1-1", "node_name": "1.1", "error": "timeout", "retry_count": 2},
                        ],
                        "total_failed": 1,
                    })
                )
                loop.close()

            t = threading.Thread(target=push)
            t.start()
            t.join(timeout=5)

            msg = ws.receive_json()
            assert msg["type"] == "failure_report"
            assert msg["payload"]["total_failed"] == 1
            assert len(msg["payload"]["failed_nodes"]) == 1
