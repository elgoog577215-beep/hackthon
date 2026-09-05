import os

from snowflake import SnowflakeGenerator


worker_id = int(os.getenv("WORKER_ID", "1"))  # 工作节点 ID，用于区分不同的工作节点
generator = SnowflakeGenerator(worker_id)


def generate_id() -> str:
    return str(next(generator))
