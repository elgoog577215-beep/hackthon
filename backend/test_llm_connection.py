import os
import asyncio
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Load env vars
load_dotenv()

api_key = os.getenv("AI_API_KEY")
base_url = os.getenv("AI_API_BASE")
model = os.getenv("AI_MODEL", "Qwen/Qwen3-32B")

print(f"Testing connection to: {base_url}")
print(f"Model: {model}")
print(f"Key: {api_key[:4]}...{api_key[-4:]}")

async def test():
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    extra_body = {
        "enable_thinking": False
    }

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": "9.9和9.11谁大"}
            ],
            stream=True,
            extra_body=extra_body
        )

        print("\nStreaming response:")
        async for chunk in response:
            if chunk.choices:
                delta = chunk.choices[0].delta
                # Try to access reasoning_content safely
                if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                    print(f"[Thinking]: {delta.reasoning_content}", end='', flush=True)
                elif hasattr(delta, 'content') and delta.content:
                    print(delta.content, end='', flush=True)
        print("\n\nDone.")
    except Exception as e:
        print(f"\nError: {e}")

if __name__ == "__main__":
    asyncio.run(test())
