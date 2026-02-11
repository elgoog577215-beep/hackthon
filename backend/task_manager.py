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

    def get_all_tasks(self, limit: int = 100) -> List[Dict]:
        # Define status priority (lower value = higher priority)
        status_priority = {
            "running": 0,
            "pending": 1,
            "paused": 2,
            "failed": 3,
            "completed": 4
        }
        
        tasks_list = list(self.tasks.values())
        
        # 1. Sort by updated_at DESC (newest first)
        tasks_list.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        
        # 2. Sort by priority ASC (Running > Pending > Paused > Failed > Completed)
        # Python's sort is stable, so it preserves the relative time order within each group
        tasks_list.sort(key=lambda x: status_priority.get(x.get("status", ""), 5))
        
        return tasks_list[:limit]

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

    def clear_failed_tasks(self):
        with self.lock:
            initial_count = len(self.tasks)
            self.tasks = {tid: t for tid, t in self.tasks.items() if t.get("status") != "failed"}
            if len(self.tasks) < initial_count:
                self.save_tasks()
            return initial_count - len(self.tasks)

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
        
        # Run the async manager
        loop.run_until_complete(self._async_manager())

    async def _async_manager(self):
        MAX_CONCURRENT = 5  # Increased concurrency
        # Map task_id -> Task (Future)
        running_tasks = {} 
        
        logger.info(f"Async worker manager started. Max concurrent: {MAX_CONCURRENT}")

        while self.running:
            # 1. Cleanup finished tasks
            # Check statuses of running tasks
            done_ids = []
            for tid, task in running_tasks.items():
                if task.done():
                    done_ids.append(tid)
                    # Handle exceptions
                    try:
                        await task
                    except Exception as e:
                        logger.error(f"Task {tid} raised exception: {e}")
                        with self.lock:
                            if tid in self.tasks:
                                self.tasks[tid]["status"] = "failed"
                                self.tasks[tid]["error"] = str(e)
                                self.save_tasks()
            
            for tid in done_ids:
                del running_tasks[tid]

            # 2. Fill slots
            free_slots = MAX_CONCURRENT - len(running_tasks)
            if free_slots > 0:
                with self.lock:
                    # Find candidates not already running
                    # We look for pending OR running (which means "ready to run next step")
                    candidates = [
                        (tid, t) for tid, t in self.tasks.items() 
                        if t["status"] in ["pending", "running"] 
                        and tid not in running_tasks
                        and t.get("status") != "paused"
                    ]
                    
                    # Sort by updated_at ASC (Oldest updated first -> Round Robin / FIFO)
                    candidates.sort(key=lambda x: x[1].get("updated_at", ""))
                    
                    for i in range(min(free_slots, len(candidates))):
                        tid = candidates[i][0]
                        # Launch task
                        future = asyncio.create_task(self._process_task(tid))
                        running_tasks[tid] = future
                        logger.info(f"Started task chunk: {tid}")
            
            await asyncio.sleep(0.1)  # Faster polling

    async def _process_task(self, task_id: str):
        task = self.tasks.get(task_id)
        if not task or task["status"] == "paused":
            return

        course_id = task["course_id"]
        
        # Mark as running
        if task["status"] != "running":
            task["status"] = "running"
            self.save_tasks()

        # Load Course (Initial check)
        course_data = self.storage.load_course(course_id)
        if not course_data:
            task["status"] = "failed"
            task["error"] = "Course not found"
            self.save_tasks()
            return

        # --- LOGIC: Identify Next Step (Batching) ---
        nodes = course_data.get("nodes", [])
        l1_nodes = [n for n in nodes if n.get("node_level", 1) == 1]
        
        actions = [] # List of (type, node)
        BATCH_SIZE = 3 # Process up to 3 items in parallel
        
        total_steps = len(l1_nodes)
        completed_steps = 0
        
        # Get difficulty from course data, default to medium
        difficulty = course_data.get("difficulty", "medium").lower()
        
        # Helper to check if content is "full" (not just summary)
        def is_content_complete(node):
            content = node.get("node_content", "")
            return len(content) > 300

        for l1 in l1_nodes:
            children = [n for n in nodes if n.get("parent_node_id") == l1["node_id"]]
            
            # Determine if we should generate subnodes
            # If difficulty is beginner/basic, we treat L1 as leaf nodes and skip subnodes
            should_have_subnodes = (difficulty not in ["beginner", "basic"])

            if should_have_subnodes and not children:
                # Needs subnodes
                actions.append(("subnodes", l1))
                if len(actions) >= BATCH_SIZE:
                    break
            else:
                # If has children, check if they need content
                # Only check content if we aren't already full of subnode tasks
                if len(actions) < BATCH_SIZE:
                    if children:
                        l2_incomplete = [
                            c for c in children 
                            if not is_content_complete(c)
                        ]
                        for child in l2_incomplete:
                            actions.append(("content", child))
                            if len(actions) >= BATCH_SIZE:
                                break
                    elif not should_have_subnodes:
                        # No children and shouldn't have them -> L1 content needed
                        if not is_content_complete(l1):
                            actions.append(("content", l1))
                            if len(actions) >= BATCH_SIZE:
                                break
            
            if len(actions) >= BATCH_SIZE:
                break
            
            # Count completion
            has_children = len(children) > 0
            if has_children:
                if all(is_content_complete(c) for c in children):
                    completed_steps += 1
            elif not should_have_subnodes:
                 if is_content_complete(l1):
                     completed_steps += 1

        if not actions:
            # All done!
            task["status"] = "completed"
            task["progress"] = 100
            task["message"] = "All steps completed"
            task["updated_at"] = datetime.now().isoformat()
            self.save_tasks()
            return

        # Check pause again
        if self.tasks[task_id]["status"] == "paused":
            return

        # Execute Actions in Parallel
        try:
            # Construct detailed message
            msg_parts = []
            for action_type, target_node in actions:
                node_name = target_node.get("node_name", "Unknown")
                # Truncate very long node names
                if len(node_name) > 15:
                    node_name = node_name[:12] + "..."
                    
                if action_type == "subnodes":
                    msg_parts.append(f"大纲: {node_name}")
                elif action_type == "content":
                    msg_parts.append(f"正文: {node_name}")
            
            task["message"] = " | ".join(msg_parts)
            # If still too long, truncate the whole message
            if len(task["message"]) > 60:
                task["message"] = task["message"][:57] + "..."
            
            # Update progress based on estimate
            task["progress"] = min(95, int((completed_steps) / total_steps * 100))
            task["updated_at"] = datetime.now().isoformat()
            self.save_tasks()
            
            # Prepare coroutines
            coroutines = []
            for action_type, target_node in actions:
                if action_type == "subnodes":
                    # Context building
                    parent_context = target_node.get("node_content", "")
                    course_outline = ""
                    for i, node in enumerate(l1_nodes):
                        course_outline += f"{i+1}. {node.get('node_name', '')}\n"
                    
                    coro = self.ai_service.generate_sub_nodes(
                        target_node["node_name"], 
                        target_node["node_level"], 
                        target_node["node_id"], 
                        course_data.get("course_name", ""),
                        parent_context,
                        course_outline
                    )
                    coroutines.append(("subnodes", target_node["node_id"], coro))
                    
                elif action_type == "content":
                    difficulty = course_data.get("difficulty", "expert")
                    style = course_data.get("style", "academic")
                    coro = self.ai_service.generate_node_content(
                        target_node["node_name"],
                        target_node.get("node_context", ""),
                        target_node["node_id"],
                        course_data.get("course_name", ""),
                        difficulty=difficulty,
                        style=style
                    )
                    coroutines.append(("content", target_node["node_id"], coro))
            
            # Run parallel
            results = await asyncio.gather(*[c[2] for c in coroutines], return_exceptions=True)
            
            # --- CRITICAL SECTION: RE-LOAD AND PATCH ---
            # Re-load fresh data to avoid overwriting user edits
            fresh_data = self.storage.load_course(course_id)
            if not fresh_data:
                logger.error(f"Course {course_id} disappeared during generation")
                return
                
            fresh_nodes = fresh_data.get("nodes", [])
            modified = False
            
            for i, result in enumerate(results):
                action_type, node_id, _ = coroutines[i]
                
                if isinstance(result, Exception):
                    logger.error(f"Error processing {node_id}: {result}")
                    continue
                
                if action_type == "subnodes":
                    # result is list of new nodes
                    # Check if they were already added (rare race)
                    # Just append
                    fresh_nodes.extend(result)
                    modified = True
                    
                elif action_type == "content":
                    # result is content string
                    # Find node in fresh_nodes
                    for n in fresh_nodes:
                        if n["node_id"] == node_id:
                            n["node_content"] = result
                            modified = True
                            break
            
            if modified:
                fresh_data["nodes"] = fresh_nodes
                self.storage.save_course(course_id, fresh_data)
                
        except Exception as e:
            logger.error(f"Error in task batch: {e}")
            task["error"] = str(e)
            # Retry next time
