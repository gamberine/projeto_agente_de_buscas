"""
PriceBot — API FastAPI
Rotas: GET /health  POST /login  POST /search  GET /history
"""

import os, json, asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from dotenv import load_dotenv

from src.agent import PriceBotAgent

load_dotenv()

# ─── Config ─────────────────────────────────────────────────────────────────
APP_USER_EMAIL     = os.getenv("APP_USER_EMAIL", "gamberine@gmail.com")
APP_USER_PASS      = os.getenv("APP_USER_PASS",  "1234")
JWT_SECRET         = os.getenv("JWT_SECRET",     "dev-secret-change-me")
JWT_ALGORITHM      = os.getenv("JWT_ALGORITHM",  "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))
CORS_ORIGINS       = os.getenv("CORS_ORIGINS",   "*").split(",")
DATA_DIR           = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# ─── App ────────────────────────────────────────────────────────────────────
app = FastAPI(title="PriceBot API", version="1.0.0-alpha")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# ─── Schemas ────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

class SearchRequest(BaseModel):
    instruction: str
    cep: str
    platform: str = "ifood"

class SearchResult(BaseModel):
    product: str
    establishment: str
    price: str
    delivery_fee: str
    estimated_time: str
    platform: str
    searched_at: str

class SearchResponse(BaseModel):
    status: str
    query: str
    platform: str
    cep: str
    results: list[SearchResult]
    total: int
    duration_ms: int

# ─── JWT ────────────────────────────────────────────────────────────────────
def create_token(email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": email, "exp": expire, "iat": datetime.now(timezone.utc)},
        JWT_SECRET, algorithm=JWT_ALGORITHM,
    )

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expirado.")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Token inválido.")

def get_current_user(creds: HTTPAuthorizationCredentials = Depends(security)) -> str:
    return decode_token(creds.credentials)["sub"]

# ─── Routes ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    email_ok = body.email.strip().lower() == APP_USER_EMAIL.strip().lower()
    pass_ok  = body.password.strip() == APP_USER_PASS.strip()
    if not (email_ok and pass_ok):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou senha incorretos.")
    return LoginResponse(
        access_token=create_token(body.email),
        expires_in=JWT_EXPIRE_MINUTES * 60,
    )


@app.post("/search", response_model=SearchResponse)
async def search(
    body: SearchRequest,
    current_user: str = Depends(get_current_user),
):
    if not body.instruction.strip():
        raise HTTPException(400, "Instrução de busca não pode ser vazia.")

    cep_clean = body.cep.replace("-", "").replace(" ", "")
    if len(cep_clean) != 8 or not cep_clean.isdigit():
        raise HTTPException(400, "CEP inválido.")

    if body.platform.lower() not in {"ifood"}:
        raise HTTPException(400, f"Plataforma '{body.platform}' não suportada.")

    start = asyncio.get_event_loop().time()
    agent = PriceBotAgent()
    raw   = await agent.search(
        instruction=body.instruction,
        cep=body.cep,
        platform=body.platform,
    )
    duration_ms = int((asyncio.get_event_loop().time() - start) * 1000)

    results = [SearchResult(**r) for r in raw]

    # Salva histórico em data/
    record = {
        "ts":          datetime.now(timezone.utc).isoformat(),
        "user":        current_user,
        "instruction": body.instruction,
        "cep":         body.cep,
        "platform":    body.platform,
        "total":       len(results),
        "duration_ms": duration_ms,
        "results":     [r.model_dump() for r in results],
    }
    hist_file = DATA_DIR / "history.json"
    history   = []
    if hist_file.exists():
        try:
            history = json.loads(hist_file.read_text())
        except Exception:
            history = []
    history.insert(0, record)
    hist_file.write_text(json.dumps(history[:200], ensure_ascii=False, indent=2))

    return SearchResponse(
        status="success",
        query=body.instruction,
        platform=body.platform,
        cep=body.cep,
        results=results,
        total=len(results),
        duration_ms=duration_ms,
    )


@app.get("/history")
async def get_history(current_user: str = Depends(get_current_user)):
    hist_file = DATA_DIR / "history.json"
    if not hist_file.exists():
        return {"history": []}
    try:
        return {"history": json.loads(hist_file.read_text())}
    except Exception:
        return {"history": []}
