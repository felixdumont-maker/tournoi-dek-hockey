from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Enum as SAEnum,
    create_engine, event, text
)
from sqlalchemy.orm import relationship, declarative_base, sessionmaker
from datetime import datetime, timezone
import enum
import os

DATABASE_URL = (
    f"mysql+pymysql://{os.getenv('DB_USER','tournoi')}:{os.getenv('DB_PASSWORD','')}"
    f"@{os.getenv('DB_HOST','mariadb')}:{os.getenv('DB_PORT','3306')}"
    f"/{os.getenv('DB_NAME','tournoi')}?charset=utf8mb4"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def now_utc():
    return datetime.now(timezone.utc)


class TournamentStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class Tournament(Base):
    __tablename__ = "tournaments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False)
    status = Column(SAEnum(TournamentStatus), default=TournamentStatus.DRAFT)
    max_players = Column(Integer, default=10)
    inscriptions_open = Column(Boolean, default=False)
    date_event = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=now_utc)
    updated_at = Column(DateTime, default=now_utc, onupdate=now_utc)
    surface_one_name = Column(String(80), nullable=False, default="Surface 1 - Shawinigan")
    surface_two_name = Column(String(80), nullable=False, default="Surface 2 - Shawinigan")

    divisions = relationship("Division", back_populates="tournament", cascade="all, delete-orphan")


class Division(Base):
    __tablename__ = "divisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    sort_order = Column(Integer, default=0)

    tournament = relationship("Tournament", back_populates="divisions")
    teams = relationship("Team", back_populates="division", cascade="all, delete-orphan")
    matches = relationship("Match", back_populates="division", cascade="all, delete-orphan")


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, autoincrement=True)
    division_id = Column(Integer, ForeignKey("divisions.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    seed = Column(Integer, default=0)
    access_code = Column(String(16), unique=True, nullable=True)
    captain_email = Column(String(255), nullable=True)
    code_sent = Column(Boolean, default=False)

    division = relationship("Division", back_populates="teams")
    players = relationship("Player", back_populates="team", cascade="all, delete-orphan")


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    jersey_number = Column(String(10), nullable=False)
    nbhpa = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=now_utc)

    team = relationship("Team", back_populates="players")


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    division_id = Column(Integer, ForeignKey("divisions.id", ondelete="CASCADE"), nullable=False)
    round_number = Column(Integer, nullable=False)
    position = Column(Integer, nullable=False)  # Position within the round
    team1_id = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    team2_id = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    score1 = Column(Integer, nullable=True)
    score2 = Column(Integer, nullable=True)
    winner_id = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    match_time = Column(String(10), nullable=True)  # "14:30"
    terrain = Column(String(50), nullable=True)
    next_match_id = Column(Integer, ForeignKey("matches.id", ondelete="SET NULL"), nullable=True)
    next_match_slot = Column(Integer, nullable=True)  # 1 or 2 (team1 or team2 of next match)

    division = relationship("Division", back_populates="matches")
    team1 = relationship("Team", foreign_keys=[team1_id])
    team2 = relationship("Team", foreign_keys=[team2_id])
    winner = relationship("Team", foreign_keys=[winner_id])


def init_db():
    Base.metadata.create_all(bind=engine)
    # Progressive migration for existing deployments
    with engine.begin() as conn:
        for sql in [
            "ALTER TABLE tournaments ADD COLUMN surface_one_name VARCHAR(80) NOT NULL DEFAULT 'Surface 1 - Shawinigan'",
            "ALTER TABLE tournaments ADD COLUMN surface_two_name VARCHAR(80) NOT NULL DEFAULT 'Surface 2 - Shawinigan'",
        ]:
            try:
                conn.execute(text(sql))
            except Exception:
                # Column probably already exists
                pass
