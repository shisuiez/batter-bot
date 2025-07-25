from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import Integer, String, BigInteger, ForeignKey, Float, Date, Text
from sqlalchemy.orm import relationship
from bot.config import DATABASE_URL
from datetime import date

Base = declarative_base()
engine = create_async_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    phone: Mapped[str] = mapped_column(String(32))
    age: Mapped[int] = mapped_column(Integer)
    total_distance: Mapped[float] = mapped_column(Float, default=0.0)
    total_elevation: Mapped[int] = mapped_column(Integer, default=0)
    hikes_count: Mapped[int] = mapped_column(Integer, default=0)
    rank: Mapped[str] = mapped_column(String(32), default="Новичок")
    notifications_enabled: Mapped[bool] = mapped_column(Integer, default=1)  # 1 - включено, 0 - выключено
    # relationship
    achievements = relationship("UserAchievement", back_populates="user")

class Route(Base):
    __tablename__ = 'routes'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    distance: Mapped[float] = mapped_column(Float)
    elevation: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[str] = mapped_column(String(32))
    latitude: Mapped[float] = mapped_column(Float, nullable=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=True)

class Hike(Base):
    __tablename__ = 'hikes'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    route_id: Mapped[int] = mapped_column(Integer, ForeignKey('routes.id'))
    date: Mapped[Date] = mapped_column(Date)
    participants = relationship("HikeParticipant", back_populates="hike")

class HikeParticipant(Base):
    __tablename__ = 'hike_participants'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hike_id: Mapped[int] = mapped_column(Integer, ForeignKey('hikes.id'))
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'))
    completed: Mapped[bool] = mapped_column(Integer, default=1)  # 1 - дошёл, 0 - нет
    hike = relationship("Hike", back_populates="participants")

class Achievement(Base):
    __tablename__ = 'achievements'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str] = mapped_column(Text)
    icon: Mapped[str] = mapped_column(String(8))

class UserAchievement(Base):
    __tablename__ = 'user_achievements'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'))
    achievement_id: Mapped[int] = mapped_column(Integer, ForeignKey('achievements.id'))
    user = relationship("User", back_populates="achievements")

class AdminLog(Base):
    __tablename__ = 'admin_logs'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(128))
    details: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[Date] = mapped_column(Date, default=date.today) 