import asyncio  # Biblioteca para programação assíncrona (permite que execute várias coisas ao mesmo tempo sem travar)
import os # Permite interagir com o sistema operacional, como acessar variáveis de ambiente e manipular arquivos
import secrets # Serve para criar códigos aleatórios curtos como os da url encurtada
import sqlite3 # Biblioteca padrão do python para trabalhar com sqlite3
import string # Dá o alfabeto base para criação dos códigos encurtados
import time # Biblioteca para medir o tempo e controlar o ratelimit de requisições
from collections import defaultdict, deque # Para criar dicionários que já têm valor padrão & deque é uma fila de dados, ótima para controlar requisições em sequência.
# Isso é usado para controlar o rate limit por IP.
from datetime import datetime, timezone # Usado para gerar data e hora e a segunda importação é de uma biblioteca é para colocar a data em formato UTC
from pathlib import Path # Serve para trabalhar com caminhos de arquivos
#import json # Serve para trabalhar com json

from fastapi import FastAPI, HTTPException, Request # Importa o fastAPI, lançar erros http, e o request tras informações da requisição, como IP do cliente
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse # serve um arquivo como resposta HTTP, JSONResponse = retorna JSON manualmente, com status customizado.
#RedirectResponse = redireciona o navegador para outra URL.

from fastapi.staticfiles import StaticFiles # Permite servir arquivos estáticos, como CSS, JS e imagens.
from pydantic import AnyHttpUrl, BaseModel # O base model cria modelos de dados válidos, e o Anyhttpurl garante que a URL enviada seja válida


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LINKS_DB = DATA_DIR / "links.sqlite3"
LEGACY_LINKS_FILE = DATA_DIR / "links.json"
PUBLIC_URL = os.getenv("PUBLIC_URL", "").rstrip("/")
CODE_ALPHABET = string.ascii_letters + string.digits
CREATE_LINK_LIMIT = 10
CREATE_LINK_WINDOW_SECONDS = 60
create_link_requests: dict[str, deque[float]] = defaultdict(deque)
links_lock = asyncio.Lock()

app = FastAPI(title="Encurtalink", description="Encurtador de links simples")


class LinkRequest(BaseModel):
    url: AnyHttpUrl


def initialize_database() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(LINKS_DB) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS links (
                code TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                created_at TEXT NOT NULL,
                clicks INTEGER NOT NULL DEFAULT 0
            )
            """
        )
"""
Função para ler os dados legados (Não tem mais uso)

        link_count = connection.execute("SELECT COUNT(*) FROM links").fetchone()[0]
        if link_count == 0 and LEGACY_LINKS_FILE.exists():
            legacy_links = json.loads(LEGACY_LINKS_FILE.read_text(encoding="utf-8"))
            connection.executemany(
                "INSERT OR IGNORE INTO links (code, url, created_at, clicks) VALUES (?, ?, ?, ?)",
                [
                    (code, link["url"], link["createdAt"], link.get("clicks", 0))
                    for code, link in legacy_links.items()
                ],
            )
"""

async def read_links() -> dict:
    def read_from_database() -> dict:
        with sqlite3.connect(LINKS_DB) as connection:
            rows = connection.execute(
                "SELECT code, url, created_at, clicks FROM links"
            ).fetchall()
        return {
            code: {"url": url, "createdAt": created_at, "clicks": clicks}
            for code, url, created_at, clicks in rows
        }

    return await asyncio.to_thread(read_from_database)


async def write_links(links: dict) -> None:
    def write_to_database() -> None:
        with sqlite3.connect(LINKS_DB) as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO links (code, url, created_at, clicks)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (code, link["url"], link["createdAt"], link["clicks"])
                    for code, link in links.items()
                ],
            )

    await asyncio.to_thread(write_to_database)


initialize_database()


def create_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(7))


def check_create_link_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    request_times = create_link_requests[client_ip]

    while request_times and now - request_times[0] >= CREATE_LINK_WINDOW_SECONDS:
        request_times.popleft()

    if len(request_times) >= CREATE_LINK_LIMIT:
        retry_after = max(
            1, int(CREATE_LINK_WINDOW_SECONDS - (now - request_times[0]))
        )
        raise HTTPException(
            status_code=429,
            detail="Limite de criação de links atingido. Tente novamente em breve.",
            headers={"Retry-After": str(retry_after)},
        )

    request_times.append(now)


@app.get("/", include_in_schema=False)
async def homepage() -> FileResponse:
    return FileResponse(BASE_DIR / "public" / "index.html")


@app.post("/api/links", status_code=201, response_model=None)
async def create_link(payload: LinkRequest, request: Request) -> dict | JSONResponse:
    check_create_link_rate_limit(request)
    async with links_lock:
        links = await read_links()
        requested_url = str(payload.url)
        existing_link = next(
            ((code, link) for code, link in links.items() if link["url"] == requested_url),
            None,
        )
        base_url = PUBLIC_URL or str(request.base_url).rstrip("/")

        if existing_link is not None:
            code, _ = existing_link
            return JSONResponse(
                status_code=200,
                content={
                    "code": code,
                    "shortUrl": f"{base_url}/{code}",
                    "existing": True,
                    "message": "Link já existente",
                },
            )

        code = create_code()
        while code in links:
            code = create_code()
        links[code] = {
            "url": requested_url,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "clicks": 0,
        }
        await write_links(links)

    return {"code": code, "shortUrl": f"{base_url}/{code}"}


@app.get("/{code}")
async def redirect_link(code: str) -> RedirectResponse:
    async with links_lock:
        links = await read_links()
        link = links.get(code)
        if link is None:
            raise HTTPException(status_code=404, detail="Link não encontrado.")
        link["clicks"] += 1
        await write_links(links)
    return RedirectResponse(link["url"], status_code=307)


app.mount("/static", StaticFiles(directory=BASE_DIR / "public"), name="static")