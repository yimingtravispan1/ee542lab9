import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import jwt
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pwdlib import PasswordHash
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')
SECRET = os.environ['JWT_SECRET']
if len(SECRET) < 32 or SECRET == 'please_change_me_to_a_long_random_value':
    raise RuntimeError('Set JWT_SECRET to a random string of at least 32 characters.')
engine = create_async_engine(os.environ['DATABASE_URL'], pool_pre_ping=True)
sessions = async_sessionmaker(engine, expire_on_commit=False)
passwords = PasswordHash.recommended()
bearer = HTTPBearer()
logger = logging.getLogger('groupchat')
clients: set[WebSocket] = set()
tasks: set[asyncio.Task] = set()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class Message(Base):
    __tablename__ = 'messages'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


@asynccontextmanager
async def lifespan(app):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield
    for task in list(tasks):
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    await engine.dispose()


app = FastAPI(title='EE542 Group Chat', lifespan=lifespan)


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=50, pattern=r'^\S+$')
    password: str = Field(min_length=8, max_length=128)


class NewMessage(BaseModel):
    content: str = Field(min_length=1, max_length=10000)


def token_for(user):
    now = datetime.now(timezone.utc)
    return {'token': jwt.encode({'sub': str(user.id), 'iat': now, 'exp': now + timedelta(minutes=int(os.getenv('JWT_EXPIRE_MINUTES', '43200')))}, SECRET, algorithm='HS256')}


async def user_from_token(token: str):
    try:
        claims = jwt.decode(token, SECRET, algorithms=['HS256'], options={'require': ['sub', 'exp']})
        user_id = int(claims['sub'])
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise HTTPException(401, 'Invalid or expired token')
    async with sessions() as session:
        user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(401, 'User no longer exists')
    return user


async def current_user(auth: HTTPAuthorizationCredentials = Depends(bearer)):
    return await user_from_token(auth.credentials)


@app.post('/api/signup', status_code=201)
async def signup(data: Credentials):
    hashed = await asyncio.to_thread(passwords.hash, data.password)
    async with sessions() as session:
        user = User(username=data.username, password_hash=hashed)
        session.add(user)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(409, 'Username already exists')
    return token_for(user)


@app.post('/api/login')
async def login(data: Credentials):
    async with sessions() as session:
        user = await session.scalar(select(User).where(User.username == data.username))
    if user is None or not await asyncio.to_thread(passwords.verify, data.password, user.password_hash):
        raise HTTPException(401, 'Invalid username or password')
    return token_for(user)


def serialize(message, username):
    return {'id': message.id, 'user_id': message.user_id, 'username': username, 'content': message.content, 'is_bot': message.is_bot, 'created_at': message.created_at.replace(tzinfo=timezone.utc).isoformat()}


@app.get('/api/messages')
async def history(user=Depends(current_user)):
    async with sessions() as session:
        rows = (await session.execute(select(Message, User.username).outerjoin(User, Message.user_id == User.id).order_by(Message.id.desc()).limit(100))).all()
    return {'messages': [serialize(m, 'LLM Bot' if m.is_bot else name) for m, name in reversed(rows)]}


async def broadcast(payload):
    async def send(client):
        try:
            await asyncio.wait_for(client.send_json({'type': 'message', 'message': payload}), timeout=5)
        except Exception:
            clients.discard(client)
    await asyncio.gather(*(send(client) for client in list(clients)))


async def bot_reply(content, recipient):
    try:
        headers = {}
        if os.getenv('LLM_API_KEY'):
            headers['Authorization'] = 'Bearer ' + os.environ['LLM_API_KEY']
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(os.environ['LLM_API_BASE'].rstrip('/') + '/chat/completions', headers=headers, json={'model': os.getenv('LLM_MODEL', 'llama-3-8b-instruct'), 'messages': [{'role': 'system', 'content': 'You are a helpful assistant in a group chat. Always respond in English.'}, {'role': 'user', 'content': content}], 'max_tokens': 512})
            response.raise_for_status()
            answer = response.json()['choices'][0]['message']['content']
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError('LLM returned empty content')
    except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError):
        logger.exception('LLM request failed')
        # Report service failures only to the sender; do not save them as model answers.
        async def send_error(client):
            try:
                await asyncio.wait_for(client.send_json({'type': 'error', 'detail': 'Model service unavailable. Start Llama 3 and check LLM_API_BASE in .env.'}), timeout=5)
            except Exception:
                clients.discard(client)
        await asyncio.gather(*(send_error(c) for c in list(clients) if c.state.user_id == recipient))
        return
    async with sessions() as session:
        message = Message(content=answer, is_bot=True)
        session.add(message)
        await session.commit()
    await broadcast(serialize(message, 'LLM Bot'))


@app.post('/api/messages', status_code=201)
async def post_message(data: NewMessage, user=Depends(current_user)):
    content = data.content.strip()
    if not content:
        raise HTTPException(422, 'Message cannot be blank')
    async with sessions() as session:
        message = Message(user_id=user.id, content=content, is_bot=False)
        session.add(message)
        await session.commit()
    payload = serialize(message, user.username)
    await broadcast(payload)
    if '?' in content or '？' in content:
        task = asyncio.create_task(bot_reply(content, user.id))
        tasks.add(task)
        task.add_done_callback(tasks.discard)
    return payload


@app.websocket('/ws')
async def websocket(websocket: WebSocket):
    await websocket.accept()
    try:
        # Authenticate in the first frame so tokens do not appear in URL logs.
        auth = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        if not isinstance(auth, dict) or not isinstance(auth.get('token'), str):
            raise ValueError('Invalid authentication frame')
        user = await user_from_token(auth['token'])
    except (HTTPException, ValueError, asyncio.TimeoutError, WebSocketDisconnect):
        await websocket.close(code=1008)
        return
    websocket.state.user_id = user.id
    clients.add(websocket)
    await websocket.send_json({'type': 'ready'})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(websocket)


@app.get('/api/health')
async def health():
    async with engine.connect() as connection:
        from sqlalchemy import text
        await connection.execute(text('SELECT 1'))
    return {'status': 'ok', 'database': 'ok'}


app.mount('/', StaticFiles(directory=ROOT / 'frontend', html=True), name='frontend')
