import asyncio
from app.agent.fast_engine import try_fast_path, _extract_name_tokens

async def main():
    cases = [
        'रोबिन के खाते में ₹15 लिखो',
        'Robin ke khate mein 15 likho',
        'robinudar 15 likho',
        'robinudhar 15 udhar',
        'रमेश के खाते में ₹50 लिखो',
        'सुरेश के खाते में ₹200 लिखो',
    ]
    for text in cases:
        tokens = _extract_name_tokens(text)
        res = await try_fast_path('00000000-0000-0000-0000-000000000001', text, 'hi')
        print(f"=== INPUT: {text} ===")
        print(f"NAME TOKENS: {tokens}")
        print(f"HANDLED: {res.handled}")
        print(f"REPLY: {res.reply}")
        c_names = [e.get('customer') for e in res.events if e.get('customer')]
        print(f"CUSTOMER SAVED: {c_names}")

if __name__ == '__main__':
    asyncio.run(main())

