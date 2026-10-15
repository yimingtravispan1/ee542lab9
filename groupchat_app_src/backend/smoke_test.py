r"""Integration checks against the running app and its real MySQL database.

Run with .venv\Scripts\python.exe smoke_test.py. Test records are removed.
Use --expect-model to check real model inference instead of model unavailability.
"""
import asyncio
import argparse
import json
import secrets
from urllib.parse import urlsplit, urlunsplit

import httpx
import websockets
from sqlalchemy import delete, select

from app import Message, User, engine, sessions


async def main(expect_model=False, base_url='http://127.0.0.1:8000'):
    suffix = secrets.token_hex(5)
    credentials = [{'username': f'smoke_{suffix}_{i}', 'password': secrets.token_urlsafe(16)} for i in range(2)]
    ids = []
    bot_content = None
    try:
        site = urlsplit(base_url)
        ws_url = urlunsplit(('wss' if site.scheme == 'https' else 'ws', site.netloc, '/ws', '', ''))
        async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
            assert (await client.get('/api/health')).json()['database'] == 'ok'
            assert 'Group Chat' in (await client.get('/')).text
            assert (await client.get('/api/messages')).status_code in (401, 403)
            tokens = []
            for data in credentials:
                response = await client.post('/api/signup', json=data)
                assert response.status_code == 201, response.text
                tokens.append(response.json()['token'])
            assert (await client.post('/api/signup', json=credentials[0])).status_code == 409
            assert (await client.post('/api/login', json=credentials[0])).status_code == 200
            assert (await client.post('/api/login', json={**credentials[0], 'password': 'wrong-password'})).status_code == 401
            headers = {'Authorization': 'Bearer ' + tokens[0]}
            assert (await client.post('/api/messages', headers=headers, json={'content': '   '})).status_code == 422
            async with websockets.connect(ws_url) as first, websockets.connect(ws_url) as second:
                for socket, token in zip((first, second), tokens):
                    await socket.send(json.dumps({'token': token}))
                    assert json.loads(await asyncio.wait_for(socket.recv(), 5))['type'] == 'ready'
                content = f'Hello from smoke test {suffix}'
                response = await client.post('/api/messages', headers=headers, json={'content': content})
                assert response.status_code == 201, response.text
                ids.append(response.json()['id'])
                for socket in (first, second):
                    event = json.loads(await asyncio.wait_for(socket.recv(), 5))
                    assert event['message']['content'] == content
                history = (await client.get('/api/messages', headers=headers)).json()['messages']
                assert any(m['id'] == ids[0] for m in history)
                response = await client.post('/api/messages', headers=headers, json={'content': 'What is 2 + 2? Reply with only the number.' if expect_model else f'Model connection test {suffix}?'})
                assert response.status_code == 201, response.text
                ids.append(response.json()['id'])
                for socket in (first, second):
                    assert json.loads(await asyncio.wait_for(socket.recv(), 5))['type'] == 'message'
                if expect_model:
                    answer = json.loads(await asyncio.wait_for(first.recv(), 180))
                    assert answer['type'] == 'message', answer
                    bot = answer['message']
                    assert bot['is_bot'] is True and '4' in bot['content'], answer
                    ids.append(bot['id'])
                    bot_content = bot['content']
                    other = json.loads(await asyncio.wait_for(second.recv(), 5))
                    assert other['message']['id'] == bot['id']
                    history = (await client.get('/api/messages', headers=headers)).json()['messages']
                    assert any(m['id'] == bot['id'] and m['is_bot'] and m['content'] == bot_content for m in history)
                else:
                    error = json.loads(await asyncio.wait_for(first.recv(), 15))
                    assert error['type'] == 'error' and 'unavailable' in error['detail']
            async with sessions() as session:
                user = await session.scalar(select(User).where(User.username == credentials[0]['username']))
                assert user.password_hash.startswith('$argon2')
                assert await session.get(Message, ids[0]) is not None
        print('PASS: health, static frontend, signup, login, duplicate/invalid input, JWT protection, two-client WebSocket broadcast, MySQL persistence, and Argon2 hashing.')
        if expect_model:
            print('PASS: real Llama inference, bot broadcast to both clients, and saved bot response in message history.')
            print('Model response to 2 + 2: ' + bot_content)
        else:
            print('PASS: unavailable-model error. Real inference was not tested.')
    finally:
        async with sessions() as session:
            if ids:
                await session.execute(delete(Message).where(Message.id.in_(ids)))
            await session.execute(delete(User).where(User.username.in_([x['username'] for x in credentials])))
            await session.commit()
        await engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--expect-model', action='store_true')
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    asyncio.run(main(args.expect_model, args.base_url))
