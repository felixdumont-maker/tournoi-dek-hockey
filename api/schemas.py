import re
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from models import TournamentStatus


# ── Tournament ──
class TournamentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255)
    max_players: int = Field(default=10, ge=2, le=30)
    date_event: Optional[datetime] = None

    @field_validator("slug", mode="before")
    @classmethod
    def normalize_and_validate_slug(cls, value: str) -> str:
        slug = (value or "").strip().lower()
        if not re.fullmatch(r"[a-z0-9-]+", slug):
            raise ValueError("Le slug doit contenir seulement des lettres minuscules, des chiffres et des tirets")
        return slug

class TournamentUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[TournamentStatus] = None
    max_players: Optional[int] = None
    inscriptions_open: Optional[bool] = None
    date_event: Optional[datetime] = None
    surface_one_name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    surface_two_name: Optional[str] = Field(default=None, min_length=1, max_length=80)

class TournamentOut(BaseModel):
    id: int
    name: str
    slug: str
    status: TournamentStatus
    max_players: int
    inscriptions_open: bool
    date_event: Optional[datetime]
    surface_one_name: str
    surface_two_name: str
    created_at: datetime
    class Config:
        from_attributes = True


# ── Division ──
class DivisionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    sort_order: int = 0

class DivisionUpdate(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None

class DivisionOut(BaseModel):
    id: int
    name: str
    sort_order: int
    class Config:
        from_attributes = True


# ── Team ──
class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    seed: int = 0
    captain_email: Optional[str] = None

class TeamUpdate(BaseModel):
    name: Optional[str] = None
    seed: Optional[int] = None
    captain_email: Optional[str] = None

class TeamOut(BaseModel):
    id: int
    name: str
    seed: int
    access_code: Optional[str] = None
    captain_email: Optional[str] = None
    code_sent: bool
    player_count: int = 0
    class Config:
        from_attributes = True


# ── Player ──
class PlayerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    jersey_number: str = Field(min_length=1, max_length=10)
    nbhpa: Optional[str] = None

class PlayerOut(BaseModel):
    id: int
    name: str
    jersey_number: str
    nbhpa: Optional[str]
    class Config:
        from_attributes = True


# ── Match ──
class MatchUpdate(BaseModel):
    score1: Optional[int] = None
    score2: Optional[int] = None
    match_time: Optional[str] = None
    terrain: Optional[str] = None

class MatchOut(BaseModel):
    id: int
    round_number: int
    position: int
    team1_id: Optional[int]
    team1_name: Optional[str] = None
    team2_id: Optional[int]
    team2_name: Optional[str] = None
    score1: Optional[int]
    score2: Optional[int]
    winner_id: Optional[int]
    winner_name: Optional[str] = None
    match_time: Optional[str]
    terrain: Optional[str]
    class Config:
        from_attributes = True


# ── Auth ──
class LoginRequest(BaseModel):
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Bracket generation ──
class GenerateBracketRequest(BaseModel):
    division_id: int


# ── Email ──
class SendCodesRequest(BaseModel):
    team_ids: List[int]


# ── Public views ──
class PublicDivisionOut(BaseModel):
    id: int
    name: str
    teams: List[dict] = []
    matches: List[dict] = []

class PublicTournamentOut(BaseModel):
    id: int
    name: str
    slug: str
    status: str
    inscriptions_open: bool
    max_players: int
    date_event: Optional[datetime]
    surface_one_name: str
    surface_two_name: str
    divisions: List[PublicDivisionOut] = []
