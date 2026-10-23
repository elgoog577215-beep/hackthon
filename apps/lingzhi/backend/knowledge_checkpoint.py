"""Await durable checkpoints while retaining compatibility with synchronous callers."""
import inspect


async def checkpoint(save, **updates):
    result=save(**updates)
    if inspect.isawaitable(result):
        return await result
    return result
