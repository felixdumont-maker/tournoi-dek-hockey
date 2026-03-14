import os
import math
import secrets
import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, joinedload
from jose import jwt, JWTError
from dotenv import load_dotenv

load_dotenv()

from models import (
    init_db, get_db, Tournament, Division, Team, Player, Match,
    TournamentStatus
)
from schemas import (
    TournamentCreate, TournamentUpdate, TournamentOut,
    DivisionCreate, DivisionUpdate, DivisionOut,
    TeamCreate, TeamUpdate, TeamOut,
    PlayerCreate, PlayerOut,
    MatchUpdate, MatchOut,
    LoginRequest, TokenOut,
    GenerateBracketRequest, SendCodesRequest,
    PublicTournamentOut, PublicDivisionOut
)

# ═══════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
BASE_URL = os.getenv("BASE_URL", "https://tournoi.cocktailmedia.ca")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24


# ═══════════════════════════════════════════════════════
# LIFESPAN
# ═══════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="Tournoi Dek Hockey API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════
def create_token(data: dict):
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode({**data, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalide")


def get_admin_token(authorization: str = Query(None, alias="token")):
    """Extract token from query param or could be extended for header."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Non autorisé")
    return verify_token(authorization)


@app.post("/api/auth/login", response_model=TokenOut)
def login(req: LoginRequest):
    if req.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Mot de passe incorrect")
    token = create_token({"sub": "admin", "role": "admin"})
    return {"access_token": token}


# ═══════════════════════════════════════════════════════
# TOURNAMENTS (ADMIN)
# ═══════════════════════════════════════════════════════
@app.get("/api/admin/tournaments", response_model=List[TournamentOut])
def list_tournaments(db: Session = Depends(get_db), auth=Depends(get_admin_token)):
    return db.query(Tournament).order_by(Tournament.created_at.desc()).all()


@app.post("/api/admin/tournaments", response_model=TournamentOut)
def create_tournament(data: TournamentCreate, db: Session = Depends(get_db), auth=Depends(get_admin_token)):
    if db.query(Tournament).filter(Tournament.slug == data.slug).first():
        raise HTTPException(400, "Ce slug existe déjà")
    t = Tournament(**data.model_dump())
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@app.get("/api/admin/tournaments/{tid}", response_model=TournamentOut)
def get_tournament(tid: int, db: Session = Depends(get_db), auth=Depends(get_admin_token)):
    t = db.query(Tournament).get(tid)
    if not t:
        raise HTTPException(404, "Tournoi introuvable")
    return t


@app.patch("/api/admin/tournaments/{tid}", response_model=TournamentOut)
def update_tournament(tid: int, data: TournamentUpdate, db: Session = Depends(get_db), auth=Depends(get_admin_token)):
    t = db.query(Tournament).get(tid)
    if not t:
        raise HTTPException(404, "Tournoi introuvable")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(t, k, v)
    db.commit()
    db.refresh(t)
    return t


@app.delete("/api/admin/tournaments/{tid}")
def delete_tournament(tid: int, db: Session = Depends(get_db), auth=Depends(get_admin_token)):
    t = db.query(Tournament).get(tid)
    if not t:
        raise HTTPException(404)
    db.delete(t)
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════
# DIVISIONS (ADMIN)
# ═══════════════════════════════════════════════════════
@app.get("/api/admin/tournaments/{tid}/divisions")
def list_divisions(tid: int, db: Session = Depends(get_db), auth=Depends(get_admin_token)):
    divs = db.query(Division).filter(Division.tournament_id == tid).order_by(Division.sort_order).all()
    result = []
    for d in divs:
        teams = db.query(Team).filter(Team.division_id == d.id).order_by(Team.seed).all()
        result.append({
            "id": d.id, "name": d.name, "sort_order": d.sort_order,
            "teams": [
                {
                    "id": t.id, "name": t.name, "seed": t.seed,
                    "access_code": t.access_code, "captain_email": t.captain_email,
                    "code_sent": t.code_sent,
                    "player_count": len(t.players)
                } for t in teams
            ]
        })
    return result


@app.post("/api/admin/tournaments/{tid}/divisions")
def create_division(tid: int, data: DivisionCreate, db: Session = Depends(get_db), auth=Depends(get_admin_token)):
    d = Division(tournament_id=tid, **data.model_dump())
    db.add(d)
    db.commit()
    db.refresh(d)
    return {"id": d.id, "name": d.name, "sort_order": d.sort_order}


@app.patch("/api/admin/divisions/{did}")
def update_division(did: int, data: DivisionUpdate, db: Session = Depends(get_db), auth=Depends(get_admin_token)):
    d = db.query(Division).get(did)
    if not d:
        raise HTTPException(404)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(d, k, v)
    db.commit()
    return {"ok": True}


@app.delete("/api/admin/divisions/{did}")
def delete_division(did: int, db: Session = Depends(get_db), auth=Depends(get_admin_token)):
    d = db.query(Division).get(did)
    if not d:
        raise HTTPException(404)
    db.delete(d)
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════
# TEAMS (ADMIN)
# ═══════════════════════════════════════════════════════
@app.post("/api/admin/divisions/{did}/teams")
def create_team(did: int, data: TeamCreate, db: Session = Depends(get_db), auth=Depends(get_admin_token)):
    t = Team(division_id=did, **data.model_dump())
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"id": t.id, "name": t.name, "seed": t.seed}


@app.patch("/api/admin/teams/{team_id}")
def update_team(team_id: int, data: TeamUpdate, db: Session = Depends(get_db), auth=Depends(get_admin_token)):
    t = db.query(Team).get(team_id)
    if not t:
        raise HTTPException(404)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(t, k, v)
    db.commit()
    return {"ok": True}


@app.delete("/api/admin/teams/{team_id}")
def delete_team(team_id: int, db: Session = Depends(get_db), auth=Depends(get_admin_token)):
    t = db.query(Team).get(team_id)
    if not t:
        raise HTTPException(404)
    db.delete(t)
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════
# ACCESS CODES (ADMIN)
# ═══════════════════════════════════════════════════════
@app.post("/api/admin/tournaments/{tid}/generate-codes")
def generate_codes(tid: int, db: Session = Depends(get_db), auth=Depends(get_admin_token)):
    divs = db.query(Division).filter(Division.tournament_id == tid).all()
    count = 0
    for d in divs:
        teams = db.query(Team).filter(Team.division_id == d.id).all()
        for t in teams:
            if not t.access_code:
                t.access_code = secrets.token_urlsafe(6).upper()[:8]
                count += 1
    db.commit()
    return {"generated": count}


@app.post("/api/admin/teams/{team_id}/regenerate-code")
def regenerate_code(team_id: int, db: Session = Depends(get_db), auth=Depends(get_admin_token)):
    t = db.query(Team).get(team_id)
    if not t:
        raise HTTPException(404)
    t.access_code = secrets.token_urlsafe(6).upper()[:8]
    t.code_sent = False
    db.commit()
    return {"code": t.access_code}


# ═══════════════════════════════════════════════════════
# EMAIL (ADMIN)
# ═══════════════════════════════════════════════════════
@app.post("/api/admin/send-codes")
async def send_codes(req: SendCodesRequest, db: Session = Depends(get_db), auth=Depends(get_admin_token)):
    import aiosmtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASSWORD", "")
    from_name = os.getenv("SMTP_FROM_NAME", "Tournoi Dek Hockey")
    from_email = os.getenv("SMTP_FROM_EMAIL", smtp_user)

    if not smtp_host or not smtp_user:
        raise HTTPException(400, "SMTP non configuré")

    sent = 0
    errors = []

    for team_id in req.team_ids:
        team = db.query(Team).options(joinedload(Team.division)).get(team_id)
        if not team or not team.access_code or not team.captain_email:
            errors.append(f"Team {team_id}: manque code ou email")
            continue

        tournament = db.query(Tournament).get(team.division.tournament_id)
        link = f"{BASE_URL}/inscription?code={team.access_code}"

        html_body = f"""
        <div style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:2rem;">
            <h2 style="color:#c5a55a;">{tournament.name if tournament else 'Tournoi'}</h2>
            <p>Bonjour capitaine de <strong>{team.name}</strong>,</p>
            <p>Voici ton lien d'inscription pour inscrire les joueurs de ton équipe dans la division <strong>{team.division.name}</strong> :</p>
            <p style="margin:1.5rem 0;">
                <a href="{link}" style="background:#c5a55a;color:#fff;padding:0.75rem 1.5rem;border-radius:8px;text-decoration:none;font-weight:bold;">
                    Inscrire mon équipe
                </a>
            </p>
            <p style="font-size:0.85rem;color:#888;">Ou copie ce lien : {link}</p>
            <hr style="border:none;border-top:1px solid #eee;margin:2rem 0;">
            <p style="font-size:0.8rem;color:#aaa;">Cocktail Media — Tournois</p>
        </div>
        """

        msg = MIMEMultipart("alternative")
        msg["From"] = f"{from_name} <{from_email}>"
        msg["To"] = team.captain_email
        msg["Subject"] = f"Inscription — {tournament.name if tournament else 'Tournoi'} — {team.name}"
        msg.attach(MIMEText(html_body, "html"))

        try:
            await aiosmtplib.send(
                msg,
                hostname=smtp_host,
                port=smtp_port,
                username=smtp_user,
                password=smtp_pass,
                start_tls=True,
            )
            team.code_sent = True
            sent += 1
        except Exception as e:
            errors.append(f"{team.name}: {str(e)}")

    db.commit()
    return {"sent": sent, "errors": errors}


# ═══════════════════════════════════════════════════════
# BRACKETS (ADMIN)
# ═══════════════════════════════════════════════════════
@app.post("/api/admin/divisions/{did}/generate-bracket")
def generate_bracket(did: int, db: Session = Depends(get_db), auth=Depends(get_admin_token)):
    div = db.query(Division).get(did)
    if not div:
        raise HTTPException(404)

    teams = db.query(Team).filter(Team.division_id == did).order_by(Team.seed).all()
    if len(teams) < 2:
        raise HTTPException(400, f"'{div.name}' a besoin d'au moins 2 équipes")

    # Clear existing matches
    db.query(Match).filter(Match.division_id == did).delete()
    db.flush()

    n = len(teams)
    bracket_size = 2 ** math.ceil(math.log2(n))
    total_rounds = int(math.log2(bracket_size))

    # Seed teams
    seeding_order = _get_seeding(bracket_size)
    seeded = [None] * bracket_size
    for i, team in enumerate(teams):
        seeded[seeding_order[i]] = team

    # Create all matches
    all_matches = {}

    # Round 1
    for i in range(bracket_size // 2):
        m = Match(
            division_id=did,
            round_number=1,
            position=i,
            team1_id=seeded[i * 2].id if seeded[i * 2] else None,
            team2_id=seeded[i * 2 + 1].id if seeded[i * 2 + 1] else None,
        )
        # Auto-advance byes
        if seeded[i * 2] and not seeded[i * 2 + 1]:
            m.winner_id = seeded[i * 2].id
        elif not seeded[i * 2] and seeded[i * 2 + 1]:
            m.winner_id = seeded[i * 2 + 1].id

        db.add(m)
        db.flush()
        all_matches[(1, i)] = m

    # Subsequent rounds
    for r in range(2, total_rounds + 1):
        matches_in_round = bracket_size // (2 ** r)
        for i in range(matches_in_round):
            m = Match(division_id=did, round_number=r, position=i)
            db.add(m)
            db.flush()
            all_matches[(r, i)] = m

    # Link matches (next_match_id, next_match_slot)
    for r in range(1, total_rounds):
        matches_in_round = bracket_size // (2 ** r)
        for i in range(matches_in_round):
            m = all_matches[(r, i)]
            next_pos = i // 2
            next_slot = 1 if i % 2 == 0 else 2
            next_match = all_matches.get((r + 1, next_pos))
            if next_match:
                m.next_match_id = next_match.id
                m.next_match_slot = next_slot

    # Propagate byes
    for r in range(1, total_rounds + 1):
        matches_in_round = bracket_size // (2 ** r)
        for i in range(matches_in_round):
            m = all_matches[(r, i)]
            if m.winner_id and m.next_match_id:
                next_m = db.query(Match).get(m.next_match_id)
                if next_m:
                    if m.next_match_slot == 1:
                        next_m.team1_id = m.winner_id
                    else:
                        next_m.team2_id = m.winner_id
                    # Check if this creates another bye
                    if next_m.team1_id and not next_m.team2_id:
                        next_m.winner_id = next_m.team1_id
                    elif next_m.team2_id and not next_m.team1_id:
                        next_m.winner_id = next_m.team2_id

    db.commit()
    return {"ok": True, "rounds": total_rounds, "matches": len(all_matches)}


def _get_seeding(size):
    if size == 1:
        return [0]
    half = _get_seeding(size // 2)
    result = []
    for pos in half:
        result.append(pos * 2)
        result.append(pos * 2 + 1)
    return result


# ═══════════════════════════════════════════════════════
# MATCHES (ADMIN — score updates)
# ═══════════════════════════════════════════════════════
@app.get("/api/admin/divisions/{did}/matches")
def get_matches(did: int, db: Session = Depends(get_db), auth=Depends(get_admin_token)):
    matches = db.query(Match).filter(Match.division_id == did).order_by(Match.round_number, Match.position).all()
    return [_match_to_dict(m, db) for m in matches]


@app.patch("/api/admin/matches/{mid}")
def update_match(mid: int, data: MatchUpdate, db: Session = Depends(get_db), auth=Depends(get_admin_token)):
    m = db.query(Match).get(mid)
    if not m:
        raise HTTPException(404)

    if data.match_time is not None:
        m.match_time = data.match_time
    if data.terrain is not None:
        m.terrain = data.terrain

    if data.score1 is not None:
        m.score1 = data.score1
    if data.score2 is not None:
        m.score2 = data.score2

    # Determine winner
    old_winner = m.winner_id
    if m.score1 is not None and m.score2 is not None and m.score1 != m.score2:
        m.winner_id = m.team1_id if m.score1 > m.score2 else m.team2_id
    else:
        m.winner_id = None

    # Advance or clear downstream
    if m.winner_id != old_winner:
        _clear_downstream(db, m)
        if m.winner_id and m.next_match_id:
            next_m = db.query(Match).get(m.next_match_id)
            if next_m:
                if m.next_match_slot == 1:
                    next_m.team1_id = m.winner_id
                else:
                    next_m.team2_id = m.winner_id

    db.commit()

    # Broadcast via WebSocket
    asyncio.create_task(_broadcast_update(m.division_id, db))

    return _match_to_dict(m, db)


def _clear_downstream(db: Session, match: Match):
    if not match.next_match_id:
        return
    next_m = db.query(Match).get(match.next_match_id)
    if not next_m:
        return
    if match.next_match_slot == 1:
        next_m.team1_id = None
    else:
        next_m.team2_id = None
    next_m.score1 = None
    next_m.score2 = None
    next_m.winner_id = None
    _clear_downstream(db, next_m)


def _match_to_dict(m: Match, db: Session):
    t1 = db.query(Team).get(m.team1_id) if m.team1_id else None
    t2 = db.query(Team).get(m.team2_id) if m.team2_id else None
    w = db.query(Team).get(m.winner_id) if m.winner_id else None
    return {
        "id": m.id,
        "round_number": m.round_number,
        "position": m.position,
        "team1_id": m.team1_id,
        "team1_name": t1.name if t1 else None,
        "team2_id": m.team2_id,
        "team2_name": t2.name if t2 else None,
        "score1": m.score1,
        "score2": m.score2,
        "winner_id": m.winner_id,
        "winner_name": w.name if w else None,
        "match_time": m.match_time,
        "terrain": m.terrain,
    }


# ═══════════════════════════════════════════════════════
# PLAYERS (ADMIN VIEW)
# ═══════════════════════════════════════════════════════
@app.get("/api/admin/teams/{team_id}/players", response_model=List[PlayerOut])
def list_players_admin(team_id: int, db: Session = Depends(get_db), auth=Depends(get_admin_token)):
    return db.query(Player).filter(Player.team_id == team_id).all()


@app.delete("/api/admin/players/{pid}")
def delete_player_admin(pid: int, db: Session = Depends(get_db), auth=Depends(get_admin_token)):
    p = db.query(Player).get(pid)
    if not p:
        raise HTTPException(404)
    db.delete(p)
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════
# PUBLIC — INSCRIPTION (code-protected)
# ═══════════════════════════════════════════════════════
@app.get("/api/inscription/{code}")
def get_inscription_info(code: str, db: Session = Depends(get_db)):
    team = db.query(Team).filter(Team.access_code == code).first()
    if not team:
        raise HTTPException(404, "Code invalide")

    div = db.query(Division).get(team.division_id)
    tournament = db.query(Tournament).get(div.tournament_id) if div else None

    if tournament and not tournament.inscriptions_open:
        raise HTTPException(403, "Inscriptions fermées")

    players = db.query(Player).filter(Player.team_id == team.id).all()

    return {
        "tournament_name": tournament.name if tournament else "",
        "division_name": div.name if div else "",
        "team_id": team.id,
        "team_name": team.name,
        "max_players": tournament.max_players if tournament else 10,
        "players": [{"id": p.id, "name": p.name, "jersey_number": p.jersey_number, "nbhpa": p.nbhpa} for p in players]
    }


@app.post("/api/inscription/{code}/players")
def add_player_inscription(code: str, data: PlayerCreate, db: Session = Depends(get_db)):
    team = db.query(Team).filter(Team.access_code == code).first()
    if not team:
        raise HTTPException(404, "Code invalide")

    div = db.query(Division).get(team.division_id)
    tournament = db.query(Tournament).get(div.tournament_id) if div else None

    if tournament and not tournament.inscriptions_open:
        raise HTTPException(403, "Inscriptions fermées")

    current_count = db.query(Player).filter(Player.team_id == team.id).count()
    max_p = tournament.max_players if tournament else 10
    if current_count >= max_p:
        raise HTTPException(400, "Alignement complet")

    # Check duplicate jersey
    existing = db.query(Player).filter(
        Player.team_id == team.id, Player.jersey_number == data.jersey_number
    ).first()
    if existing:
        raise HTTPException(400, "Ce numéro de chandail est déjà pris")

    p = Player(team_id=team.id, **data.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"id": p.id, "name": p.name, "jersey_number": p.jersey_number, "nbhpa": p.nbhpa}


@app.delete("/api/inscription/{code}/players/{pid}")
def remove_player_inscription(code: str, pid: int, db: Session = Depends(get_db)):
    team = db.query(Team).filter(Team.access_code == code).first()
    if not team:
        raise HTTPException(404)
    p = db.query(Player).filter(Player.id == pid, Player.team_id == team.id).first()
    if not p:
        raise HTTPException(404)
    db.delete(p)
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════
# PUBLIC — TOURNAMENT DATA (read-only)
# ═══════════════════════════════════════════════════════
@app.get("/api/public/tournaments")
def list_public_tournaments(db: Session = Depends(get_db)):
    tournaments = db.query(Tournament).filter(
        Tournament.status.in_([TournamentStatus.ACTIVE, TournamentStatus.ARCHIVED])
    ).order_by(Tournament.date_event.desc()).all()
    return [{
        "id": t.id, "name": t.name, "slug": t.slug, "status": t.status.value, "date_event": t.date_event,
        "surface_one_name": t.surface_one_name, "surface_two_name": t.surface_two_name
    } for t in tournaments]


@app.get("/api/public/tournaments/{slug}")
def get_public_tournament(slug: str, db: Session = Depends(get_db)):
    t = db.query(Tournament).filter(Tournament.slug == slug).first()
    if not t or t.status == TournamentStatus.DRAFT:
        raise HTTPException(404, "Tournoi introuvable")

    divisions = db.query(Division).filter(Division.tournament_id == t.id).order_by(Division.sort_order).all()
    result = {
        "id": t.id, "name": t.name, "slug": t.slug, "status": t.status.value,
        "max_players": t.max_players, "inscriptions_open": t.inscriptions_open,
        "date_event": t.date_event,
        "surface_one_name": t.surface_one_name,
        "surface_two_name": t.surface_two_name,
        "divisions": []
    }

    for d in divisions:
        teams = db.query(Team).filter(Team.division_id == d.id).order_by(Team.seed).all()
        matches = db.query(Match).filter(Match.division_id == d.id).order_by(Match.round_number, Match.position).all()

        result["divisions"].append({
            "id": d.id, "name": d.name,
            "teams": [{"id": te.id, "name": te.name, "seed": te.seed} for te in teams],
            "matches": [_match_to_dict(m, db) for m in matches]
        })

    return result


# ═══════════════════════════════════════════════════════
# WEBSOCKET — LIVE SCORES
# ═══════════════════════════════════════════════════════
class ConnectionManager:
    def __init__(self):
        self.active: dict[str, list[WebSocket]] = {}  # slug -> [websockets]

    async def connect(self, slug: str, ws: WebSocket):
        await ws.accept()
        if slug not in self.active:
            self.active[slug] = []
        self.active[slug].append(ws)

    def disconnect(self, slug: str, ws: WebSocket):
        if slug in self.active:
            self.active[slug] = [w for w in self.active[slug] if w != ws]

    async def broadcast(self, slug: str, data: dict):
        if slug not in self.active:
            return
        dead = []
        for ws in self.active[slug]:
            try:
                await ws.send_json(data)
            except:
                dead.append(ws)
        for ws in dead:
            self.active[slug] = [w for w in self.active[slug] if w != ws]


manager = ConnectionManager()


@app.websocket("/ws/{slug}")
async def websocket_endpoint(websocket: WebSocket, slug: str):
    await manager.connect(slug, websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep connection alive
    except WebSocketDisconnect:
        manager.disconnect(slug, websocket)


async def _broadcast_update(division_id: int, db: Session):
    """Broadcast match updates to all connected clients for the tournament."""
    div = db.query(Division).get(division_id)
    if not div:
        return
    tournament = db.query(Tournament).get(div.tournament_id)
    if not tournament:
        return

    matches = db.query(Match).filter(Match.division_id == division_id).order_by(Match.round_number, Match.position).all()
    data = {
        "type": "match_update",
        "division_id": division_id,
        "division_name": div.name,
        "matches": [_match_to_dict(m, db) for m in matches]
    }
    await manager.broadcast(tournament.slug, data)


# ═══════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════
@app.get("/api/health")
def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

