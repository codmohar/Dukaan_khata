import asyncio
from app.agent.fast_engine import try_fast_path

async def run_tests():
    cases = [
        ('Ram ka hua 25 rupees', 'hi'),
        ('Ram ka 25 hua', 'hi'),
        ('ram ka हुआ 25', 'hi'),
        ('Ramesh ge 50 aaythu', 'kn'),
        ('Suresh du 100 aagide', 'kn'),
        ('Aapke hue 15', 'hi'),
        ('Total 50 hua', 'hi'),
        ('50 aaythu', 'kn'),
        ('Ram ka kitna hua', 'hi'),
    ]
    for text, lang in cases:
        res = await try_fast_path('00000000-0000-0000-0000-000000000001', text, lang)
        print(f'=== INPUT: {text} ({lang}) ===')
        print(f'HANDLED: {res.handled}')
        print(f'REPLY: {res.reply}')
        c_ev = [e.get('type') for e in res.events]
        print(f'EVENTS: {c_ev}')

if __name__ == '__main__':
    asyncio.run(run_tests())
