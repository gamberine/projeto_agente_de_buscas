"""
PriceBot — API FastAPI
Rotas: /login  /search  /health
"""

import os
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from dotenv import load_dotenv

from src.agent import PriceBotAgent

load_dotenv()

# ─── Config ─────────────────────────────────────────────────────────────────
APP_USER_EMAIL     = os.getenv("APP_USER_EMAIL", "gamberini@gmail.com")
APP_USER_PASS      = os.getenv("APP_USER_PASS",  "passa ai um dois tres quatro")
JWT_SECRET         = os.getenv("JWT_SECRET",     "dev-secret-change-me")
JWT_ALGORITHM      = os.getenv("JWT_ALGORITHM",  "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))
CORS_ORIGINS       = os.getenv("CORS_ORIGINS",   "*").split(",")

# ─── App ────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="PriceBot API",
    description="Buscador Dinâmico de Preços — MVP",
    version="1.0.0-alpha",
)

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

# ─── JWT helpers ────────────────────────────────────────────────────────────
def create_token(email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {"sub": email, "exp": expire, "iat": datetime.now(timezone.utc)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido.")

def get_current_user(creds: HTTPAuthorizationCredentials = Depends(security)) -> str:
    payload = decode_token(creds.credentials)
    return payload["sub"]

# ─── Routes ─────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Sistema"])
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/login", response_model=LoginResponse, tags=["Auth"])
async def login(body: LoginRequest):
    """Autentica o usuário e retorna um JWT."""
    email_ok = body.email.strip().lower() == APP_USER_EMAIL.strip().lower()
    pass_ok  = body.password.strip() == APP_USER_PASS.strip()

    if not (email_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos.",
        )

    token = create_token(body.email)
    return LoginResponse(
        access_token=token,
        expires_in=JWT_EXPIRE_MINUTES * 60,
    )


@app.post("/search", response_model=SearchResponse, tags=["Busca"])
async def search(
    body: SearchRequest,
    current_user: str = Depends(get_current_user),
):
    """Dispara o agente Playwright e retorna os resultados estruturados."""
    if not body.instruction.strip():
        raise HTTPException(status_code=400, detail="Instrução de busca não pode ser vazia.")

    cep_clean = body.cep.replace("-", "").replace(" ", "")
    if len(cep_clean) != 8 or not cep_clean.isdigit():
        raise HTTPException(status_code=400, detail="CEP inválido.")

    if body.platform.lower() not in {"ifood"}:
        raise HTTPException(status_code=400, detail=f"Plataforma '{body.platform}' não suportada.")

    start = asyncio.get_event_loop().time()
    agent = PriceBotAgent()
    raw_results = await agent.search(
        instruction=body.instruction,
        cep=body.cep,
        platform=body.platform,
    )
    duration_ms = int((asyncio.get_event_loop().time() - start) * 1000)

    return SearchResponse(
        status="success",
        query=body.instruction,
        platform=body.platform,
        cep=body.cep,
        results=[SearchResult(**r) for r in raw_results],
        total=len(raw_results),
        duration_ms=duration_ms,
    )
