import httpx
import asyncio
from app.config import settings

models = [
    "gemini-3.1-flash-lite",
    "gemini-3.1-flash-lite-preview",
    "gemini-3-flash-preview",
    "gemini-3.5-flash-lite",
    "gemini-flash-latest",
]

async def check():
    async with httpx.AsyncClient(timeout=4.0) as client:
        for m in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={settings.gemini_api_key}"
            try:
                r = await client.post(url, json={"contents": [{"parts": [{"text": "hi"}]}]})
                print(f"{m:30}: {r.status_code} | {r.text[:80]}")
            except Exception as e:
                print(f"{m:30}: {e}")

if __name__ == "__main__":
    asyncio.run(check())

