import pytest
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import clear_mappers
from bot.db import Base, User, Route, Achievement, UserAchievement

DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="function")
async def session():
    engine = create_async_engine(DATABASE_URL, echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()
    clear_mappers()

@pytest.mark.asyncio
async def test_user_registration(session):
    user = User(telegram_id=123, name="Тест", phone="+79990001122", age=25)
    session.add(user)
    await session.commit()
    res = await session.get(User, user.id)
    assert res is not None
    assert res.name == "Тест"

@pytest.mark.asyncio
async def test_add_route(session):
    route = Route(name="Пик", distance=10.5, elevation=800, description="Тестовый маршрут", difficulty="средняя")
    session.add(route)
    await session.commit()
    res = await session.get(Route, route.id)
    assert res is not None
    assert res.name == "Пик"

@pytest.mark.asyncio
async def test_achievement(session):
    user = User(telegram_id=456, name="Достиженец", phone="+79990002233", age=30, hikes_count=5)
    ach = Achievement(name="Первые шаги", description="5 походов", icon="🥉")
    session.add_all([user, ach])
    await session.commit()
    ua = UserAchievement(user_id=user.id, achievement_id=ach.id)
    session.add(ua)
    await session.commit()
    res = await session.get(UserAchievement, ua.id)
    assert res is not None
    assert res.user_id == user.id
    assert res.achievement_id == ach.id 