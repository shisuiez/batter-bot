import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from bot.config import BOT_TOKEN, ADMINS, OWNER_ID
from bot.db import SessionLocal, User, Hike, Route, HikeParticipant, UserAchievement, Achievement, AdminLog
from sqlalchemy import select
from datetime import datetime, date
from aiogram.utils.markdown import hlink
import aiohttp
from aiogram import filters
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class RegStates(StatesGroup):
    name = State()
    phone = State()
    age = State()

class AddRouteStates(StatesGroup):
    name = State()
    distance = State()
    elevation = State()
    description = State()
    difficulty = State()
    latitude = State()
    longitude = State()

class EditRouteStates(StatesGroup):
    route_id = State()
    name = State()
    distance = State()
    elevation = State()
    description = State()
    difficulty = State()
    latitude = State()
    longitude = State()

class NewHikeStates(StatesGroup):
    route_id = State()
    hike_date = State()

class CompleteHikeStates(StatesGroup):
    hike_id = State()
    completed_ids = State()

class BroadcastStates(StatesGroup):
    text = State()

class EditStatsStates(StatesGroup):
    user_id = State()
    field = State()
    value = State()

def get_rank(hikes_count, total_distance):
    # Примерная логика рангов
    if hikes_count >= 50 or total_distance >= 1000:
        return "Покоритель"
    elif hikes_count >= 20 or total_distance >= 500:
        return "Скаут"
    elif hikes_count >= 10:
        return "Турист"
    elif hikes_count >= 3:
        return "Новичок+"
    else:
        return "Новичок"

ACHIEVEMENTS = [
    {"name": "Первые шаги", "desc": "5 походов", "icon": "🚶", "cond": lambda u, ctx: u.hikes_count >= 5},
    {"name": "Серебряный туризм", "desc": "10 походов", "icon": "🥈", "cond": lambda u, ctx: u.hikes_count >= 10},
    {"name": "Золотой треккер", "desc": "50 походов", "icon": "🥇", "cond": lambda u, ctx: u.hikes_count >= 50},
    {"name": "100 км", "desc": "100 км суммарно", "icon": "🏅", "cond": lambda u, ctx: u.total_distance >= 100},
    {"name": "500 км", "desc": "500 км суммарно", "icon": "🏆", "cond": lambda u, ctx: u.total_distance >= 500},
    {"name": "Высотомер", "desc": "10 000 м набора", "icon": "⛰️", "cond": lambda u, ctx: u.total_elevation >= 10000},
    {"name": "Первый поход", "desc": "Первое участие", "icon": "🚶", "cond": lambda u, ctx: u.hikes_count == 1},
    {"name": "3 подряд", "desc": "3 похода подряд без пропусков", "icon": "🔗", "cond": lambda u, ctx: ctx.get('streak', 0) >= 3},
    {"name": "Сложный маршрут", "desc": "Прохождение сложного маршрута", "icon": "🧗", "cond": lambda u, ctx: ctx.get('hard_route', False)},
    {"name": "Покоритель высот", "desc": "20 000 м набора", "icon": "🏔️", "cond": lambda u, ctx: u.total_elevation >= 20000},
    {"name": "Все маршруты клуба", "desc": "Пройден каждый маршрут", "icon": "🌍", "cond": lambda u, ctx: ctx.get('all_routes', False)},
]

async def check_achievements(session, user, context=None):
    context = context or {}
    res = await session.execute(
        select(Achievement, UserAchievement).join(UserAchievement, Achievement.id == UserAchievement.achievement_id, isouter=True)
        .where(UserAchievement.user_id == user.id)
    )
    got = {a.name for a, ua in res if ua}
    new_ach = []
    for ach in ACHIEVEMENTS:
        if ach["name"] not in got and ach["cond"](user, context):
            res2 = await session.execute(select(Achievement).where(Achievement.name == ach["name"]))
            a = res2.scalar_one_or_none()
            if not a:
                a = Achievement(name=ach["name"], description=ach["desc"], icon=ach["icon"])
                session.add(a)
                await session.commit()
            ua = UserAchievement(user_id=user.id, achievement_id=a.id)
            session.add(ua)
            await session.commit()
            new_ach.append(a)
    return new_ach

async def get_weather_forecast(lat, lon, target_date):
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        f"&daily=temperature_2m_min,temperature_2m_max,precipitation_sum,windspeed_10m_max"
        f"&timezone=auto&start_date={target_date}&end_date={target_date}"
    )
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            daily = data.get("daily", {})
            if not daily or not daily.get("temperature_2m_min"):
                return None
            t_min = daily["temperature_2m_min"][0]
            t_max = daily["temperature_2m_max"][0]
            precip = daily["precipitation_sum"][0]
            wind = daily["windspeed_10m_max"][0]
            return t_min, t_max, precip, wind

async def send_hike_reminders():
    from asyncio import sleep
    while True:
        tomorrow = date.today().toordinal() + 1
        tomorrow_date = date.fromordinal(tomorrow)
        async with SessionLocal() as session:
            q = (
                select(Hike, Route)
                .join(Route, Hike.route_id == Route.id)
                .where(Hike.date == tomorrow_date)
            )
            hikes = await session.execute(q)
            hikes = hikes.all()
            for hike, route in hikes:
                # Получить прогноз
                if route.latitude is not None and route.longitude is not None:
                    weather = await get_weather_forecast(route.latitude, route.longitude, tomorrow_date)
                else:
                    weather = None
                # Получить участников
                q2 = (
                    select(HikeParticipant, User)
                    .join(User, HikeParticipant.user_id == User.id)
                    .where(HikeParticipant.hike_id == hike.id, HikeParticipant.completed == 1)
                )
                participants = await session.execute(q2)
                participants = participants.all()
                for hp, user in participants:
                    if getattr(user, 'notifications_enabled', 1) != 1:
                        continue
                    msg = f"Завтра поход по маршруту '{route.name}'!\n"
                    if weather:
                        t_min, t_max, precip, wind = weather
                        msg += (
                            f"Погода: {t_min:.0f}…{t_max:.0f}°C, осадки: {precip:.1f} мм, ветер: {wind:.0f} м/с.\n"
                        )
                        if t_min < 5:
                            msg += "Рекомендуется тёплая одежда. "
                        if precip > 0:
                            msg += "Возможен дождь — возьмите непромокаемую одежду. "
                    else:
                        msg += "(Не удалось получить прогноз погоды)\n"
                    msg += "Не забудьте снаряжение и хорошее настроение! 🥾"
                    try:
                        await bot.send_message(user.telegram_id, msg)
                    except Exception:
                        pass
        await sleep(60*60*12)  # Проверять каждые 12 часов

async def log_admin_action(session, admin_id, action, details):
    log = AdminLog(admin_id=admin_id, action=action, details=details)
    session.add(log)
    await session.commit()

# Хелпер для удаления сообщений бота в группах
async def delete_later(message: types.Message, delay=15):
    try:
        await asyncio.sleep(delay)
        await message.delete()
    except Exception:
        pass

# Миксин для удаления сообщений после ответа в группах
async def auto_delete_reply(message: types.Message, text, **kwargs):
    reply = await message.answer(text, **kwargs)
    if message.chat.type in ("group", "supergroup"):
        asyncio.create_task(delete_later(reply))

# Приветствие новых участников
@dp.message(F.chat.type.in_(['group', 'supergroup']))
async def welcome_new_members(message: types.Message):
    if message.new_chat_members:
        for user in message.new_chat_members:
            if user.is_bot:
                continue
            await message.reply(f"👋 Добро пожаловать, {user.full_name}!\nЭто бот клуба походов. Для регистрации напиши мне в ЛС /start.")

# Главное меню
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🗺️ Маршруты")],
        [KeyboardButton(text="🚶 Ближайшие походы"), KeyboardButton(text="🏆 Лидеры")],
        [KeyboardButton(text="❓ Помощь")],
    ],
    resize_keyboard=True
)

# Inline-кнопки для профиля и маршрутов
profile_inline = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Посмотреть профиль", callback_data="profile")],
        [InlineKeyboardButton(text="Список маршрутов", callback_data="routes")],
    ]
)

@dp.message(flags={"block": False})
async def catch_unregistered(message: types.Message, state: FSMContext):
    # Не мешаем обработчикам команд
    if message.text and message.text.startswith("/"):
        return
    current_state = await state.get_state()
    if current_state is not None:
        return  # Дай FSM обработать шаг регистрации!
    # Проверяем, зарегистрирован ли пользователь
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = res.scalar_one_or_none()
        if not user:
            await message.answer("Ты еще не зарегистрирован. Напиши /start для регистрации.")
            await state.set_state(RegStates.name)

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    print(f"Получен /start от {message.from_user.id}")
    await message.answer(
        "👋 Привет! Я бот для организации походов. Давай начнем регистрацию или воспользуйся меню внизу!",
        reply_markup=main_menu
    )
    await state.set_state(RegStates.name)

@dp.message(lambda m: m.text == "👤 Профиль")
async def menu_profile(message: types.Message):
    await profile(message)

@dp.message(lambda m: m.text == "🗺️ Маршруты")
async def menu_routes(message: types.Message):
    await routes_list(message)

@dp.message(lambda m: m.text == "🚶 Ближайшие походы")
async def menu_upcoming(message: types.Message):
    await upcoming_hikes(message)

@dp.message(lambda m: m.text == "🏆 Лидеры")
async def menu_leaders(message: types.Message):
    await leaders(message)

@dp.message(lambda m: m.text == "❓ Помощь")
async def menu_help(message: types.Message):
    await help_cmd(message)

@dp.callback_query(lambda c: c.data == "profile")
async def cb_profile(callback: types.CallbackQuery):
    await profile(callback.message)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "routes")
async def cb_routes(callback: types.CallbackQuery):
    await routes_list(callback.message)
    await callback.answer()

@dp.message(RegStates.name)
async def reg_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(types.KeyboardButton(text="Поделиться контактом", request_contact=True))
    await message.answer(
        "Отправь свой номер телефона (или нажми кнопку)", reply_markup=kb
    )
    await state.set_state(RegStates.phone)

@dp.message(RegStates.phone, F.contact)
async def reg_phone_contact(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number
    await state.update_data(phone=phone)
    await message.answer("Сколько тебе лет?", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(RegStates.age)

@dp.message(RegStates.phone)
async def reg_phone_text(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    if not phone.replace('+', '').replace('-', '').isdigit():
        await message.answer("Пожалуйста, введите корректный номер телефона или воспользуйтесь кнопкой.")
        return
    await state.update_data(phone=phone)
    await message.answer("Сколько тебе лет?", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(RegStates.age)

@dp.message(RegStates.age)
async def reg_age(message: types.Message, state: FSMContext):
    age_text = message.text.strip()
    if not age_text.isdigit() or not (6 <= int(age_text) <= 100):
        await message.answer("Пожалуйста, введите возраст числом (6-100).")
        return
    await state.update_data(age=int(age_text))
    data = await state.get_data()
    # Сохраняем пользователя в БД
    async with SessionLocal() as session:
        # Проверяем, не зарегистрирован ли уже
        res = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = res.scalar_one_or_none()
        if user:
            await message.answer("Ты уже зарегистрирован!")
        else:
            user = User(
                telegram_id=message.from_user.id,
                name=data["name"],
                phone=data["phone"],
                age=data["age"]
            )
            session.add(user)
            await session.commit()
            await message.answer("Регистрация завершена! Добро пожаловать в клуб походов! 🥾")
    await state.clear()

# Пример форматирования профиля
@dp.message(Command("profile"))
async def profile(message: types.Message):
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = res.scalar_one_or_none()
        if not user:
            await message.answer("Ты еще не зарегистрирован. Напиши /start для регистрации.", reply_markup=main_menu)
            return
        ach_res = await session.execute(
            select(Achievement).join(UserAchievement).where(UserAchievement.user_id == user.id)
        )
        achievements = ach_res.scalars().all()
        ach_text = "\n".join([f"{a.icon} <b>{a.name}</b>" for a in achievements]) if achievements else "—"
        text = (
            f"<b>👤 Профиль</b>\n"
            f"<b>Имя:</b> {user.name}\n"
            f"<b>Телефон:</b> {user.phone}\n"
            f"<b>Возраст:</b> {user.age}\n"
            f"\n"
            f"<b>🏅 Ранг:</b> {user.rank}\n"
            f"<b>📈 Статистика:</b>\n"
            f"  • <b>Километраж:</b> {user.total_distance:.1f} км\n"
            f"  • <b>Набор высоты:</b> {user.total_elevation} м\n"
            f"  • <b>Походов:</b> {user.hikes_count}\n"
            f"\n"
            f"<b>🎖 Достижения:</b>\n{ach_text}"
        )
        await message.answer(text, parse_mode="HTML", reply_markup=profile_inline)

@dp.message(Command("history"))
async def history(message: types.Message):
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = res.scalar_one_or_none()
        if not user:
            await message.answer("Ты еще не зарегистрирован. Напиши /start для регистрации.")
            return
        # Получаем все походы пользователя
        q = (
            select(Hike, Route)
            .join(HikeParticipant, HikeParticipant.hike_id == Hike.id)
            .join(Route, Hike.route_id == Route.id)
            .where(HikeParticipant.user_id == user.id)
            .order_by(Hike.date.desc())
        )
        hikes = await session.execute(q)
        hikes = hikes.all()
        if not hikes:
            await message.answer("У тебя пока нет завершённых походов.")
            return
        lines = []
        for hike, route in hikes:
            lines.append(f"{hike.date:%d.%m.%Y} — {route.name} ({route.distance} км, {route.elevation} м)")
        await message.answer("\n".join(lines))

@dp.message(Command("routes"))
async def routes_list(message: types.Message):
    async with SessionLocal() as session:
        res = await session.execute(select(Route))
        routes = res.scalars().all()
        if not routes:
            await message.answer("Маршрутов пока нет.")
            return
        lines = [f"{r.id}. {r.name} — {r.distance} км, {r.elevation} м, сложность: {r.difficulty}" for r in routes]
        await auto_delete_reply(message, "\n".join(lines))

@dp.message(Command("add_route"))
async def add_route_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        await message.answer("⛔️ Только администраторы могут добавлять маршруты.")
        return
    await message.answer("Введите название маршрута:")
    await state.set_state(AddRouteStates.name)

@dp.message(AddRouteStates.name)
async def add_route_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("Протяжённость маршрута (км):")
    await state.set_state(AddRouteStates.distance)

@dp.message(AddRouteStates.distance)
async def add_route_distance(message: types.Message, state: FSMContext):
    try:
        distance = float(message.text.replace(',', '.'))
        if distance <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите число (км), например: 12.5")
        return
    await state.update_data(distance=distance)
    await message.answer("Суммарный набор высоты (м):")
    await state.set_state(AddRouteStates.elevation)

@dp.message(AddRouteStates.elevation)
async def add_route_elevation(message: types.Message, state: FSMContext):
    try:
        elevation = int(message.text)
        if elevation < 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите целое число (метры), например: 800")
        return
    await state.update_data(elevation=elevation)
    await message.answer("Краткое описание маршрута:")
    await state.set_state(AddRouteStates.description)

@dp.message(AddRouteStates.description)
async def add_route_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await message.answer("Сложность маршрута (например: лёгкая, средняя, сложная):")
    await state.set_state(AddRouteStates.difficulty)

@dp.message(AddRouteStates.difficulty)
async def add_route_difficulty(message: types.Message, state: FSMContext):
    await state.update_data(difficulty=message.text.strip())
    await message.answer("Координаты старта (широта, например: 42.876):")
    await state.set_state(AddRouteStates.latitude)

@dp.message(AddRouteStates.latitude)
async def add_route_latitude(message: types.Message, state: FSMContext):
    try:
        lat = float(message.text.replace(',', '.'))
    except ValueError:
        await message.answer("Введите число, например: 42.876")
        return
    await state.update_data(latitude=lat)
    await message.answer("Координаты старта (долгота, например: 74.605):")
    await state.set_state(AddRouteStates.longitude)

@dp.message(AddRouteStates.longitude)
async def add_route_longitude(message: types.Message, state: FSMContext):
    try:
        lon = float(message.text.replace(',', '.'))
    except ValueError:
        await message.answer("Введите число, например: 74.605")
        return
    await state.update_data(longitude=lon)
    data = await state.get_data()
    async with SessionLocal() as session:
        route = Route(
            name=data["name"],
            distance=data["distance"],
            elevation=data["elevation"],
            description=data["description"],
            difficulty=data["difficulty"],
            latitude=data["latitude"],
            longitude=lon
        )
        session.add(route)
        await session.commit()
        await message.answer(f"Маршрут '{route.name}' успешно добавлен!")
        await log_admin_action(session, message.from_user.id, "add_route", f"{route.name} ({route.distance} км, {route.elevation} м)")
    await state.clear()

@dp.message(Command("edit_route"))
async def edit_route_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        await message.answer("⛔️ Только администраторы могут редактировать маршруты.")
        return
    await message.answer("Введите ID маршрута для редактирования (посмотреть ID можно через /routes):")
    await state.set_state(EditRouteStates.route_id)

@dp.message(EditRouteStates.route_id)
async def edit_route_id(message: types.Message, state: FSMContext):
    try:
        route_id = int(message.text)
    except ValueError:
        await message.answer("Введите числовой ID маршрута.")
        return
    async with SessionLocal() as session:
        route = await session.get(Route, route_id)
        if not route:
            await message.answer("Маршрут с таким ID не найден.")
            await state.clear()
            return
        await state.update_data(route_id=route_id)
        await state.update_data(name=route.name, distance=route.distance, elevation=route.elevation,
                               description=route.description, difficulty=route.difficulty,
                               latitude=route.latitude, longitude=route.longitude)
    await message.answer(
        "Оставьте поле пустым, если не хотите менять значение.\n\nНовое название маршрута:")
    await state.set_state(EditRouteStates.name)

@dp.message(EditRouteStates.name)
async def edit_route_name(message: types.Message, state: FSMContext):
    if message.text.strip():
        await state.update_data(name=message.text.strip())
    await message.answer("Новая протяжённость маршрута (км):")
    await state.set_state(EditRouteStates.distance)

@dp.message(EditRouteStates.distance)
async def edit_route_distance(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text:
        try:
            distance = float(text.replace(',', '.'))
            if distance <= 0:
                raise ValueError
            await state.update_data(distance=distance)
        except ValueError:
            await message.answer("Введите число (км), например: 12.5 или оставьте поле пустым.")
            return
    await message.answer("Новый суммарный набор высоты (м):")
    await state.set_state(EditRouteStates.elevation)

@dp.message(EditRouteStates.elevation)
async def edit_route_elevation(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text:
        try:
            elevation = int(text)
            if elevation < 0:
                raise ValueError
            await state.update_data(elevation=elevation)
        except ValueError:
            await message.answer("Введите целое число (метры), например: 800 или оставьте поле пустым.")
            return
    await message.answer("Новое описание маршрута:")
    await state.set_state(EditRouteStates.description)

@dp.message(EditRouteStates.description)
async def edit_route_description(message: types.Message, state: FSMContext):
    if message.text.strip():
        await state.update_data(description=message.text.strip())
    await message.answer("Новая сложность маршрута:")
    await state.set_state(EditRouteStates.difficulty)

@dp.message(EditRouteStates.difficulty)
async def edit_route_difficulty(message: types.Message, state: FSMContext):
    if message.text.strip():
        await state.update_data(difficulty=message.text.strip())
    await message.answer("Новая широта (latitude):")
    await state.set_state(EditRouteStates.latitude)

@dp.message(EditRouteStates.latitude)
async def edit_route_latitude(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text:
        try:
            lat = float(text.replace(',', '.'))
            await state.update_data(latitude=lat)
        except ValueError:
            await message.answer("Введите число, например: 42.876 или оставьте поле пустым.")
            return
    await message.answer("Новая долгота (longitude):")
    await state.set_state(EditRouteStates.longitude)

@dp.message(EditRouteStates.longitude)
async def edit_route_longitude(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text:
        try:
            lon = float(text.replace(',', '.'))
            await state.update_data(longitude=lon)
        except ValueError:
            await message.answer("Введите число, например: 74.605 или оставьте поле пустым.")
            return
    data = await state.get_data()
    async with SessionLocal() as session:
        route = await session.get(Route, data["route_id"])
        if not route:
            await message.answer("Ошибка: маршрут не найден.")
            await state.clear()
            return
        route.name = data["name"]
        route.distance = data["distance"]
        route.elevation = data["elevation"]
        route.description = data["description"]
        route.difficulty = data["difficulty"]
        route.latitude = data["latitude"]
        route.longitude = data["longitude"]
        await session.commit()
        await message.answer(f"Маршрут '{route.name}' успешно обновлён!")
        await log_admin_action(session, message.from_user.id, "edit_route", f"{route.name} (ID {route.id})")
    await state.clear()

@dp.message(Command("new_hike"))
async def new_hike_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        await message.answer("⛔️ Только администраторы могут планировать походы.")
        return
    async with SessionLocal() as session:
        res = await session.execute(select(Route))
        routes = res.scalars().all()
        if not routes:
            await message.answer("Нет маршрутов для планирования. Добавьте маршрут через /add_route.")
            return
        lines = [f"{r.id}. {r.name} — {r.distance} км, {r.elevation} м" for r in routes]
        await message.answer("Выберите маршрут (введите ID):\n" + "\n".join(lines))
    await state.set_state(NewHikeStates.route_id)

@dp.message(NewHikeStates.route_id)
async def new_hike_route(message: types.Message, state: FSMContext):
    try:
        route_id = int(message.text)
    except ValueError:
        await message.answer("Введите числовой ID маршрута.")
        return
    async with SessionLocal() as session:
        route = await session.get(Route, route_id)
        if not route:
            await message.answer("Маршрут с таким ID не найден. Попробуйте снова.")
            return
        await state.update_data(route_id=route_id)
    await message.answer("Введите дату похода в формате ДД.ММ.ГГГГ (например, 25.08.2024):")
    await state.set_state(NewHikeStates.hike_date)

@dp.message(NewHikeStates.hike_date)
async def new_hike_date(message: types.Message, state: FSMContext):
    try:
        hike_date = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
        if hike_date < date.today():
            raise ValueError
    except ValueError:
        await message.answer("Введите корректную дату в формате ДД.ММ.ГГГГ (и не в прошлом)")
        return
    data = await state.get_data()
    async with SessionLocal() as session:
        hike = Hike(route_id=data["route_id"], date=hike_date)
        session.add(hike)
        await session.commit()
        await message.answer(f"Поход успешно запланирован на {hike_date:%d.%m.%Y}!")
        await log_admin_action(session, message.from_user.id, "new_hike", f"{hike.id}: {route.name} на {hike_date}")
    await state.clear()

@dp.message(Command("upcoming"))
async def upcoming_hikes(message: types.Message):
    async with SessionLocal() as session:
        q = (
            select(Hike, Route)
            .join(Route, Hike.route_id == Route.id)
            .where(Hike.date >= date.today())
            .order_by(Hike.date.asc())
        )
        hikes = await session.execute(q)
        hikes = hikes.all()
        if not hikes:
            await message.answer("Ближайших походов пока нет.")
            return
        lines = []
        for hike, route in hikes:
            lines.append(f"{hike.date:%d.%m.%Y} — {route.name} ({route.distance} км, {route.elevation} м)")
        await auto_delete_reply(message, "\n".join(lines))

@dp.message(Command("join"))
async def join_info(message: types.Message):
    await message.answer(
        "Чтобы записаться на поход, свяжитесь с администратором (оплата и запись происходят через ЛС).\n" \
        "Список админов: /admins"
    )

@dp.message(Command("admins"))
async def admins_list(message: types.Message):
    # Здесь можно вручную прописать username админов или хранить их в БД
    # Пример: ADMINS_USERNAMES = {123456789: 'admin1', 987654321: 'admin2'}
    ADMINS_USERNAMES = {
        123456789: 'admin1',
        987654321: 'admin2',
        # ...
    }
    lines = []
    for admin_id in ADMINS:
        username = ADMINS_USERNAMES.get(admin_id)
        if username:
            lines.append(hlink(f"@{username}", f"https://t.me/{username}"))
        else:
            lines.append(f"ID: {admin_id}")
    await message.answer("Администраторы для связи:\n" + "\n".join(lines), parse_mode="HTML")

@dp.message(Command("notify_off"))
async def notify_off(message: types.Message):
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = res.scalar_one_or_none()
        if not user:
            await message.answer("Сначала зарегистрируйтесь через /start.")
            return
        user.notifications_enabled = 0
        await session.commit()
        await message.answer("🔕 Вы успешно отписались от напоминаний и рассылок. Чтобы снова получать уведомления, используйте /notify_on.")

@dp.message(Command("notify_on"))
async def notify_on(message: types.Message):
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = res.scalar_one_or_none()
        if not user:
            await message.answer("Сначала зарегистрируйтесь через /start.")
            return
        user.notifications_enabled = 1
        await session.commit()
        await message.answer("🔔 Вы снова будете получать напоминания и рассылки.")

class AddParticipantStates(StatesGroup):
    hike_id = State()
    user_id = State()

@dp.message(Command("add_participant"))
async def add_participant_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        await message.answer("⛔️ Только администраторы могут добавлять участников.")
        return
    async with SessionLocal() as session:
        q = (
            select(Hike, Route)
            .join(Route, Hike.route_id == Route.id)
            .where(Hike.date >= date.today())
            .order_by(Hike.date.asc())
        )
        hikes = await session.execute(q)
        hikes = hikes.all()
        if not hikes:
            await message.answer("Нет запланированных походов.")
            return
        lines = [f"{hike.id}. {hike.date:%d.%m.%Y} — {route.name}" for hike, route in hikes]
        await message.answer("Выберите поход (введите ID):\n" + "\n".join(lines))
    await state.set_state(AddParticipantStates.hike_id)

@dp.message(AddParticipantStates.hike_id)
async def add_participant_hike(message: types.Message, state: FSMContext):
    try:
        hike_id = int(message.text)
    except ValueError:
        await message.answer("Введите числовой ID похода.")
        return
    async with SessionLocal() as session:
        hike = await session.get(Hike, hike_id)
        if not hike:
            await message.answer("Поход с таким ID не найден.")
            return
        await state.update_data(hike_id=hike_id)
    await message.answer("Введите Telegram ID пользователя (узнать можно через /profile или /users):")
    await state.set_state(AddParticipantStates.user_id)

@dp.message(AddParticipantStates.user_id)
async def add_participant_user(message: types.Message, state: FSMContext):
    try:
        user_id = int(message.text)
    except ValueError:
        await message.answer("Введите числовой Telegram ID пользователя.")
        return
    data = await state.get_data()
    async with SessionLocal() as session:
        # Проверяем, есть ли такой пользователь
        res = await session.execute(select(User).where(User.telegram_id == user_id))
        user = res.scalar_one_or_none()
        if not user:
            await message.answer("Пользователь с таким Telegram ID не найден.")
            return
        # Проверяем, не добавлен ли уже
        res2 = await session.execute(
            select(HikeParticipant).where(
                HikeParticipant.hike_id == data["hike_id"],
                HikeParticipant.user_id == user.id
            )
        )
        exists = res2.scalar_one_or_none()
        if exists:
            await message.answer("Этот пользователь уже добавлен в участники этого похода.")
            return
        hp = HikeParticipant(hike_id=data["hike_id"], user_id=user.id)
        session.add(hp)
        await session.commit()
        await message.answer(f"Пользователь {user.name} успешно добавлен в участники похода!")
    await state.clear()

@dp.message(Command("complete_hike"))
async def complete_hike_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        await message.answer("⛔️ Только администраторы могут завершать походы.")
        return
    async with SessionLocal() as session:
        q = (
            select(Hike, Route)
            .join(Route, Hike.route_id == Route.id)
            .where(Hike.date <= date.today())
            .order_by(Hike.date.desc())
        )
        hikes = await session.execute(q)
        hikes = hikes.all()
        if not hikes:
            await message.answer("Нет завершённых походов.")
            return
        lines = [f"{hike.id}. {hike.date:%d.%m.%Y} — {route.name}" for hike, route in hikes]
        await message.answer("Выберите поход для завершения (введите ID):\n" + "\n".join(lines))
    await state.set_state(CompleteHikeStates.hike_id)

@dp.message(CompleteHikeStates.hike_id)
async def complete_hike_id(message: types.Message, state: FSMContext):
    try:
        hike_id = int(message.text)
    except ValueError:
        await message.answer("Введите числовой ID похода.")
        return
    async with SessionLocal() as session:
        hike = await session.get(Hike, hike_id)
        if not hike:
            await message.answer("Поход с таким ID не найден.")
            return
        # Получаем участников
        q = (
            select(HikeParticipant, User)
            .join(User, HikeParticipant.user_id == User.id)
            .where(HikeParticipant.hike_id == hike_id)
        )
        participants = await session.execute(q)
        participants = participants.all()
        if not participants:
            await message.answer("В этом походе нет участников.")
            return
        lines = [f"{user.id} ({user.telegram_id}) — {user.name}" for hp, user in participants]
        await message.answer(
            "Участники похода:\n" + "\n".join(lines) +
            "\n\nВведите ID пользователей (через запятую), которые дошли до конца:"
        )
    await state.update_data(hike_id=hike_id)
    await state.set_state(CompleteHikeStates.completed_ids)

@dp.message(CompleteHikeStates.completed_ids)
async def complete_hike_done(message: types.Message, state: FSMContext):
    ids_text = message.text.replace(' ', '')
    try:
        ids = [int(x) for x in ids_text.split(',') if x]
    except ValueError:
        await message.answer("Введите ID пользователей через запятую, например: 1,2,3")
        return
    data = await state.get_data()
    hike_id = data["hike_id"]
    async with SessionLocal() as session:
        # Получаем поход и маршрут
        hike = await session.get(Hike, hike_id)
        route = await session.get(Route, hike.route_id)
        # Получаем всех участников
        q = (
            select(HikeParticipant, User)
            .join(User, HikeParticipant.user_id == User.id)
            .where(HikeParticipant.hike_id == hike_id)
        )
        participants = await session.execute(q)
        participants = participants.all()
        # Обновляем статус дошедших
        for hp, user in participants:
            if user.id in ids:
                hp.completed = 1
                # Обновляем статистику
                user.total_distance += route.distance
                user.total_elevation += route.elevation
                user.hikes_count += 1
                user.rank = get_rank(user.hikes_count, user.total_distance)
                # В complete_hike_done перед вызовом check_achievements собираю context:
                # streak (походы подряд)
                qstreak = (
                    select(HikeParticipant, Hike)
                    .join(Hike, HikeParticipant.hike_id == Hike.id)
                    .where(HikeParticipant.user_id == user.id, HikeParticipant.completed == 1)
                    .order_by(Hike.date.desc())
                    .limit(3)
                )
                streak_hikes = await session.execute(qstreak)
                streak_hikes = streak_hikes.all()
                streak = 1
                if len(streak_hikes) == 3:
                    dates = [hike.date for hp, hike in streak_hikes]
                    if (dates[0] - dates[1]).days == (dates[1] - dates[2]).days == 1:
                        streak = 3
                # hard_route
                hard_route = route.difficulty.lower() == "сложная"
                # all_routes
                qall = await session.execute(select(Route.id))
                all_route_ids = {r[0] for r in qall}
                quser = await session.execute(
                    select(Hike.route_id)
                    .join(HikeParticipant, HikeParticipant.hike_id == Hike.id)
                    .where(HikeParticipant.user_id == user.id, HikeParticipant.completed == 1)
                )
                user_route_ids = {r[0] for r in quser}
                all_routes = all_route_ids and all_route_ids.issubset(user_route_ids)
                context = {"streak": streak, "hard_route": hard_route, "all_routes": all_routes}
                new_ach = await check_achievements(session, user, context)
                await session.commit()
                # Уведомление
                try:
                    msg = f"Поздравляем! Вы прошли поход '{route.name}' ({route.distance} км, {route.elevation} м).\n"
                    msg += f"Ваш новый километраж: {user.total_distance:.1f} км, походов: {user.hikes_count}, ранг: {user.rank}."
                    if new_ach:
                        msg += "\n\n🎉 Новые достижения: " + ", ".join(f"{a.icon} {a.name}" for a in new_ach)
                    await bot.send_message(user.telegram_id, msg)
                except Exception:
                    pass
            else:
                hp.completed = 0
        await session.commit()
        await message.answer("Статистика обновлена, участники уведомлены!")
        await log_admin_action(session, message.from_user.id, "complete_hike", f"hike_id={hike_id}, completed={ids}")
    await state.clear()

@dp.message(Command("leaders"))
async def leaders(message: types.Message):
    async with SessionLocal() as session:
        q = (
            select(User)
            .order_by(User.total_distance.desc(), User.hikes_count.desc())
            .limit(10)
        )
        users = await session.execute(q)
        users = users.scalars().all()
        if not users:
            await message.answer("Нет данных для лидерборда.")
            return
        lines = [
            f"{i+1}. {u.name} — {u.total_distance:.1f} км, {u.hikes_count} походов, ранг: {u.rank}"
            for i, u in enumerate(users)
        ]
        await auto_delete_reply(message, "🏆 Топ-10 участников:\n" + "\n".join(lines))

@dp.message(Command("broadcast"))
async def broadcast_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        await message.answer("⛔️ Только администраторы могут делать рассылку.")
        return
    await message.answer("Введите текст объявления для рассылки всем пользователям:")
    await state.set_state(BroadcastStates.text)

@dp.message(BroadcastStates.text)
async def broadcast_send(message: types.Message, state: FSMContext):
    text = message.text.strip()
    async with SessionLocal() as session:
        res = await session.execute(select(User))
        users = res.scalars().all()
        count = 0
        for user in users:
            if getattr(user, 'notifications_enabled', 1) != 1:
                continue
            try:
                await bot.send_message(user.telegram_id, f"📢 Объявление:\n{text}")
                count += 1
            except Exception:
                pass
    await message.answer(f"Рассылка завершена. Сообщение отправлено {count} пользователям.")
    await state.clear()
    await log_admin_action(session, message.from_user.id, "broadcast", text)

@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    text = (
        "🤖 <b>Бот для организации походов</b>\n\n"
        "<b>Основные команды:</b>\n"
        "/start — регистрация\n"
        "/profile — мой профиль и статистика\n"
        "/history — история походов\n"
        "/routes — список маршрутов\n"
        "/upcoming — ближайшие походы\n"
        "/join — как записаться на поход\n"
        "/leaders — топ-10 участников\n"
        "/admins — список админов для связи\n"
        "\n<b>Для админов:</b>\n"
        "/add_route — добавить маршрут\n"
        "/edit_route — редактировать маршрут\n"
        "/new_hike — запланировать поход\n"
        "/add_participant — добавить участника в поход\n"
        "/complete_hike — завершить поход\n"
        "/broadcast — рассылка объявления всем\n"
        "\n<b>Погода и напоминания</b> — бот сам напомнит участникам о походе и погоде за сутки до события.\n"
    )
    await auto_delete_reply(message, text, parse_mode="HTML")

@dp.message(Command("edit_stats"))
async def edit_stats_start(message: types.Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔️ Только владелец бота может редактировать статистику.")
        return
    await message.answer("Введите Telegram ID пользователя для редактирования:")
    await state.set_state(EditStatsStates.user_id)

@dp.message(EditStatsStates.user_id)
async def edit_stats_user(message: types.Message, state: FSMContext):
    try:
        user_id = int(message.text)
    except ValueError:
        await message.answer("Введите числовой Telegram ID пользователя.")
        return
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.telegram_id == user_id))
        user = res.scalar_one_or_none()
        if not user:
            await message.answer("Пользователь не найден.")
            await state.clear()
            return
        await state.update_data(user_id=user_id)
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Километры"), KeyboardButton(text="Высота")],
            [KeyboardButton(text="Походы"), KeyboardButton(text="Ранг")],
            [KeyboardButton(text="Отмена")],
        ], resize_keyboard=True, one_time_keyboard=True
    )
    await message.answer("Что редактировать?", reply_markup=kb)
    await state.set_state(EditStatsStates.field)

@dp.message(EditStatsStates.field)
async def edit_stats_field(message: types.Message, state: FSMContext):
    field = message.text.lower()
    if field not in ["километры", "высота", "походы", "ранг", "отмена"]:
        await message.answer("Выберите действие из меню.")
        return
    if field == "отмена":
        await message.answer("Редактирование отменено.", reply_markup=main_menu)
        await state.clear()
        return
    await state.update_data(field=field)
    await message.answer("Введите новое значение:", reply_markup=main_menu)
    await state.set_state(EditStatsStates.value)

@dp.message(EditStatsStates.value)
async def edit_stats_value(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data["user_id"]
    field = data["field"]
    value = message.text.strip()
    async with SessionLocal() as session:
        res = await session.execute(select(User).where(User.telegram_id == user_id))
        user = res.scalar_one_or_none()
        if not user:
            await message.answer("Пользователь не найден.")
            await state.clear()
            return
        if field == "километры":
            try:
                user.total_distance = float(value)
            except ValueError:
                await message.answer("Введите число.")
                return
        elif field == "высота":
            try:
                user.total_elevation = int(value)
            except ValueError:
                await message.answer("Введите целое число.")
                return
        elif field == "походы":
            try:
                user.hikes_count = int(value)
            except ValueError:
                await message.answer("Введите целое число.")
                return
        elif field == "ранг":
            user.rank = value
        await session.commit()
        await message.answer(f"✅ Значение обновлено!", reply_markup=main_menu)
    await state.clear()

async def main():
    print("Polling запускается!")
    import asyncio
    asyncio.create_task(send_hike_reminders())
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main()) 