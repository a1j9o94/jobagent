# app/queue_manager.py
import json
import logging
import os
import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

import redis
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    JOB_APPLICATION = "job_application"
    UPDATE_JOB_STATUS = "update_job_status"
    APPROVAL_REQUEST = "approval_request"
    SEND_NOTIFICATION = "send_notification"


@dataclass
class QueueTask:
    id: str
    type: TaskType
    payload: Dict[str, Any]
    retries: int = 0
    created_at: str = None
    priority: int = 0

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow().isoformat()


class JobApplicationTaskPayload(BaseModel):
    job_id: int
    job_url: str
    company: str
    title: str
    user_data: Dict[str, Any]
    credentials: Optional[Dict[str, str]] = None
    custom_answers: Optional[Dict[str, Any]] = None
    application_id: int


class UpdateJobStatusTaskPayload(BaseModel):
    job_id: int
    application_id: int
    status: str  # 'applied', 'failed', 'waiting_approval', 'needs_user_info'
    notes: Optional[str] = None
    error_message: Optional[str] = None
    screenshot_url: Optional[str] = None
    submitted_at: Optional[str] = None


class ApprovalRequestTaskPayload(BaseModel):
    job_id: int
    application_id: int
    question: str
    current_state: Optional[str] = None
    screenshot_url: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class QueueManager:
    """Manages Redis queues for task communication between Python and Node.js services."""

    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.redis_client = redis.from_url(
            self.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True
        )
        logger.info(f"Initialized QueueManager with Redis URL: {self.redis_url}")

    def _get_queue_key(self, task_type: TaskType) -> str:
        """Generate the Redis key for a task type queue."""
        return f"tasks:{task_type.value}"

    def _get_result_key(self, task_id: str) -> str:
        """Generate the Redis key for task results."""
        return f"task_results:{task_id}"

    def publish_task(
        self, 
        task_type: TaskType, 
        payload: Dict[str, Any], 
        priority: int = 0
    ) -> str:
        """Publish a task to the specified queue."""
        try:
            task_id = f"{task_type.value}_{int(datetime.utcnow().timestamp())}_{uuid.uuid4().hex[:8]}"
            
            task = QueueTask(
                id=task_id,
                type=task_type,
                payload=payload,
                priority=priority
            )

            queue_key = self._get_queue_key(task_type)
            task_json = json.dumps({
                "id": task.id,
                "type": task.type.value,
                "payload": task.payload,
                "retries": task.retries,
                "created_at": task.created_at,
                "priority": task.priority
            })

            # Use RPUSH to add to the end of the queue (FIFO)
            self.redis_client.rpush(queue_key, task_json)
            
            logger.info(f"Published task {task_id} to {task_type.value} queue")
            return task_id

        except Exception as e:
            logger.error(f"Failed to publish task to {task_type.value}: {e}")
            raise

    def consume_task(self, task_type: TaskType, timeout: int = 0) -> Optional[QueueTask]:
        """Consume a task from the specified queue."""
        try:
            queue_key = self._get_queue_key(task_type)
            
            if timeout > 0:
                # Blocking pop with timeout
                result = self.redis_client.blpop(queue_key, timeout=timeout)
                if result:
                    _, task_json = result
                else:
                    return None
            else:
                # Non-blocking pop
                task_json = self.redis_client.lpop(queue_key)
                if not task_json:
                    return None

            task_data = json.loads(task_json)
            
            task = QueueTask(
                id=task_data["id"],
                type=TaskType(task_data["type"]),
                payload=task_data["payload"],
                retries=task_data.get("retries", 0),
                created_at=task_data.get("created_at"),
                priority=task_data.get("priority", 0)
            )
            
            logger.info(f"Consumed task {task.id} from {task_type.value} queue")
            return task

        except Exception as e:
            logger.error(f"Failed to consume task from {task_type.value}: {e}")
            return None

    def get_queue_length(self, task_type: TaskType) -> int:
        """Get the number of tasks in a queue."""
        try:
            queue_key = self._get_queue_key(task_type)
            return self.redis_client.llen(queue_key)
        except Exception as e:
            logger.error(f"Failed to get queue length for {task_type.value}: {e}")
            return 0

    def get_queue_stats(self) -> Dict[str, int]:
        """Get statistics for all queues."""
        stats = {}
        for task_type in TaskType:
            stats[task_type.value] = self.get_queue_length(task_type)
        return stats

    def health_check(self) -> bool:
        """Check if Redis connection is healthy."""
        try:
            self.redis_client.ping()
            return True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False

    def publish_job_application_task(
        self,
        job_id: int,
        application_id: int,
        job_url: str,
        company: str,
        title: str,
        user_data: Dict[str, Any],
        credentials: Optional[Dict[str, str]] = None,
        custom_answers: Optional[Dict[str, Any]] = None
    ) -> str:
        """Convenience method to publish a job application task."""
        payload = JobApplicationTaskPayload(
            job_id=job_id,
            application_id=application_id,
            job_url=job_url,
            company=company,
            title=title,
            user_data=user_data,
            credentials=credentials,
            custom_answers=custom_answers
        ).dict()

        return self.publish_task(TaskType.JOB_APPLICATION, payload)

    def publish_approval_request(
        self,
        job_id: int,
        application_id: int,
        question: str,
        current_state: Optional[str] = None,
        screenshot_url: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Convenience method to publish an approval request."""
        payload = ApprovalRequestTaskPayload(
            job_id=job_id,
            application_id=application_id,
            question=question,
            current_state=current_state,
            screenshot_url=screenshot_url,
            context=context
        ).dict()

        return self.publish_task(TaskType.APPROVAL_REQUEST, payload)

    def close(self):
        """Close the Redis connection."""
        if self.redis_client:
            self.redis_client.close()
            logger.info("Redis connection closed")


# Global instance
queue_manager = QueueManager() 