import json
import os
import uuid
import time
import threading
import asyncio
from datetime import datetime
from typing import Dict, List, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TASKS_FILE = "tasks.json"

class TaskManager:
    def __init__(self, storage_module, ai_service_module):
        self.storage = storage_module
        self.ai_service = ai_service_module
        self.tasks: Dict[str, Dict] = {}
        self.lock = threading.Lock()
        self.worker_thread = None
        self.running = False
        self.load_tasks()

    def load_tasks(self):
        if os.path.exists(TASKS_FILE):
            try:
                with open(TASKS_FILE, "r") as f:
                    self.tasks = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load tasks: {e}")
                self.tasks = {}

    def save_tasks(self):
        with self.lock:
            try:
                with open(TASKS_FILE, "w") as f:
                    json.dump(self.tasks, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Failed to save tasks: {e}")

    def create_task(self, course_id: str, task_type: str = "auto_generate") -> str:
        task_id = str(uuid.uuid4())
        task = {
            "id": task_id,
            "course_id": course_id,
            "type": task_type,
            "status": "pending",
            "progress": 0,
            "total": 0,
            "current_node_name": "",
            "message": "Waiting to start...",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "error": None
        }
        self.tasks[task_id] = task
        self.save_tasks()
        return task_id

    def get_task(self, task_id: str) -> Optional[Dict]:
        return self.tasks.get(task_id)

    def get_tasks_by_course(self, course_id: str) -> List[Dict]:
        return [t for t in self.tasks.values() if t["course_id"] == course_id]

    def pause_task(self, task_id: str):
        if task_id in self.tasks:
            if self.tasks[task_id]["status"] in ["pending", "running"]:
                self.tasks[task_id]["status"] = "paused"
                self.tasks[task_id]["message"] = "Paused by user"
                self.save_tasks()

    def resume_task(self, task_id: str):
        if task_id in self.tasks:
            if self.tasks[task_id]["status"] == "paused":
                self.tasks[task_id]["status"] = "pending"
                self.tasks[task_id]["message"] = "Resuming..."
                self.save_tasks()

    def delete_task(self, task_id: str):
        if task_id in self.tasks:
            del self.tasks[task_id]
            self.save_tasks()

    def start_worker(self):
        if not self.running:
            self.running = True
            self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.worker_thread.start()
            logger.info("Task worker started")

    def stop_worker(self):
        self.running = False
        if self.worker_thread:
            self.worker_thread.join()

    def _worker_loop(self):
        # Create a new event loop for async calls in this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        while self.running:
            # Find a pending task
            # We prioritize running tasks first, then pending
            active_task_id = None
            
            with self.lock:
                # First check if any task is 'running' (maybe interrupted by restart)
                # Or 'pending'
                candidates = [
                    tid for tid, t in self.tasks.items() 
                    if t["status"] in ["pending", "running"]
                ]
                if candidates:
                    # Pick the first one for now (FIFO)
                    # Ideally we might want round-robin or priority, but simple is fine
                    active_task_id = candidates[0]
            
            if active_task_id:
                try:
                    loop.run_until_complete(self._process_task(active_task_id))
                except Exception as e:
                    logger.error(f"Error processing task {active_task_id}: {e}")
                    with self.lock:
                        self.tasks[active_task_id]["status"] = "failed"
                        self.tasks[active_task_id]["error"] = str(e)
                        self.save_tasks()
                
                # Sleep a bit to prevent tight loop if no work is actually done or after a step
                time.sleep(1) 
            else:
                # No tasks, sleep longer
                time.sleep(2)

    async def _process_task(self, task_id: str):
        task = self.tasks.get(task_id)
        if not task or task["status"] == "paused":
            return

        course_id = task["course_id"]
        
        # Mark as running
        if task["status"] != "running":
            task["status"] = "running"
            self.save_tasks()

        # Load Course
        course_data = self.storage.load_course(course_id)
        if not course_data:
            task["status"] = "failed"
            task["error"] = "Course not found"
            self.save_tasks()
            return

        # --- LOGIC: Identify Next Step ---
        # Strategy: Depth-First Traversal
        # 1. Find Level 1 nodes.
        # 2. For each Level 1 node:
        #    a. If no children -> Generate Subnodes (Level 2).
        #    b. If children -> Check each child (Level 2).
        #       i. If content empty -> Generate Content.
        
        nodes = course_data.get("nodes", [])
        
        # Build hierarchy
        l1_nodes = [n for n in nodes if n.get("node_level", 1) == 1]
        # Sort by some index if available? For now assume array order is correct.
        
        next_action = None # (type, node)
        
        total_steps = len(l1_nodes) # Crude approximation: L1 count
        completed_steps = 0
        
        for l1 in l1_nodes:
            # Check if it has children
            children = [n for n in nodes if n.get("parent_node_id") == l1["node_id"]]
            
            if not children:
                # Needs subnodes
                next_action = ("subnodes", l1)
                break
            
            # Check children content
            l2_incomplete = [c for c in children if not c.get("node_content")]
            if l2_incomplete:
                # Needs content
                next_action = ("content", l2_incomplete[0])
                break
            
            completed_steps += 1

        # Update progress (rough estimate)
        # Better progress: Count all potential L2 nodes? 
        # Let's keep it simple: progress is just for UI feedback.
        
        if not next_action:
            # All done!
            task["status"] = "completed"
            task["progress"] = 100
            task["message"] = "All steps completed"
            task["updated_at"] = datetime.now().isoformat()
            self.save_tasks()
            return

        action_type, target_node = next_action
        
        # Check pause again before starting expensive operation
        if self.tasks[task_id]["status"] == "paused":
            return

        # Execute Action
        try:
            task["message"] = f"Processing {target_node.get('node_name')} ({action_type})..."
            task["current_node_name"] = target_node.get("node_name")
            self.save_tasks()
            
            if action_type == "subnodes":
                # Generate Subnodes
                # We need context
                parent_context = target_node.get("node_content", "")
                course_outline = "" # Construct if needed, similar to main.py
                
                # Construct simple outline
                for i, node in enumerate(l1_nodes):
                    course_outline += f"{i+1}. {node.get('node_name', '')}\n"

                new_nodes = await self.ai_service.generate_sub_nodes(
                    target_node["node_name"], 
                    target_node["node_level"], 
                    target_node["node_id"], 
                    course_data.get("course_name", ""),
                    parent_context,
                    course_outline
                )
                
                # Save to course
                if "nodes" not in course_data:
                    course_data["nodes"] = []
                course_data["nodes"].extend(new_nodes)
                self.storage.save_course(course_id, course_data)
                
            elif action_type == "content":
                # Generate Content
                # Need context
                # Find siblings for context
                siblings = [n for n in nodes if n.get("parent_node_id") == target_node.get("parent_node_id")]
                # Find previous sibling
                prev_context = ""
                try:
                    idx = next(i for i, n in enumerate(siblings) if n["node_id"] == target_node["node_id"])
                    if idx > 0:
                        prev_node = siblings[idx-1]
                        prev_context = f"Previous section ({prev_node['node_name']}): {prev_node.get('node_content', '')[-300:]}"
                except StopIteration:
                    pass
                
                # Course context (L1 nodes)
                course_context = "\n".join([f"- {n['node_name']}" for n in l1_nodes])

                content = await self.ai_service.redefine_content(
                    target_node["node_name"],
                    "", # user_requirement
                    "", # original_content
                    course_context,
                    prev_context
                )
                
                # Save
                target_node["node_content"] = content
                target_node["node_type"] = "custom" # Mark as generated
                
                # Update node in the list (reference modification might not work if dict was copied, but usually works for mutable objs in list)
                # But to be safe, find index and replace
                for i, n in enumerate(course_data["nodes"]):
                    if n["node_id"] == target_node["node_id"]:
                        course_data["nodes"][i] = target_node
                        break
                
                self.storage.save_course(course_id, course_data)

            # Update task timestamp
            task["updated_at"] = datetime.now().isoformat()
            self.save_tasks()

        except Exception as e:
            logger.error(f"Task execution failed: {e}")
            # Don't fail the whole task immediately? 
            # Maybe retry count? For now, fail.
            task["status"] = "failed"
            task["error"] = str(e)
            self.save_tasks()

