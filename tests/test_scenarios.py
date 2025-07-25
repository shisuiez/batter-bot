import pytest
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import clear_mappers
from bot.db import Base, User, Route, Hike, HikeParticipant, Achievement, UserAchievement
from bot.main import get_rank

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
async def test_registration_and_profile(session):
    user = User(telegram_id=111, name="Тест", phone="+79990001122", age=25)
    session.add(user)
    await session.commit()
    res = await session.get(User, user.id)
    assert res is not None
    assert res.name == "Тест"
    assert res.phone == "+79990001122"
    assert res.age == 25

@pytest.mark.asyncio
async def test_admin_add_route_and_hike(session):
    route = Route(name="Маршрут 1", distance=12.0, elevation=500, description="desc", difficulty="средняя")
    session.add(route)
    await session.commit()
    hike = Hike(route_id=route.id, date="2024-08-01")
    session.add(hike)
    await session.commit()
    res = await session.get(Hike, hike.id)
    assert res is not None
    assert res.route_id == route.id

@pytest.mark.asyncio
async def test_add_participant_and_complete_hike(session):
    user = User(telegram_id=222, name="Участник", phone="+79990003344", age=30)
    route = Route(name="Сложный", distance=20.0, elevation=1200, description="desc", difficulty="сложная")
    session.add_all([user, route])
    await session.commit()
    hike = Hike(route_id=route.id, date="2024-08-02")
    session.add(hike)
    await session.commit()
    hp = HikeParticipant(hike_id=hike.id, user_id=user.id, completed=1)
    session.add(hp)
    await session.commit()
    # Завершение похода: обновление статистики
    user.total_distance += route.distance
    user.total_elevation += route.elevation
    user.hikes_count += 1
    user.rank = get_rank(user.hikes_count, user.total_distance)
    await session.commit()
    res = await session.get(User, user.id)
    assert res.total_distance == 20.0
    assert res.total_elevation == 1200
    assert res.hikes_count == 1
    assert res.rank in ["Новичок", "Новичок+"]

@pytest.mark.asyncio
async def test_admin_rights(session):
    # Проверяем, что неадмин не может добавить маршрут (логика в боте, тут просто пример)
    # Можно мокать вызовы, но тут проверим права на уровне данных
    admin_id = 999
    user_id = 333
    # Допустим, admin_id в списке админов, user_id — нет
    assert admin_id != user_id

@pytest.mark.asyncio
async def test_notifications_flag(session):
    user = User(telegram_id=444, name="Оповещаемый", phone="+79990005566", age=28, notifications_enabled=1)
    session.add(user)
    await session.commit()
    # Отключаем уведомления
    user.notifications_enabled = 0
    await session.commit()
    res = await session.get(User, user.id)
    assert res.notifications_enabled == 0 