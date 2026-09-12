import asyncio
import json
import os
import secrets
import sqlite3
import string
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import AnyHttpUrl, BaseModel


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


@app.post("/api/links", status_code=201)
async def create_link(payload: LinkRequest, request: Request) -> dict:
    check_create_link_rate_limit(request)
    async with links_lock:
        links = await read_links()
        code = create_code()
        while code in links:
            code = create_code()
        links[code] = {
            "url": str(payload.url),
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "clicks": 0,
        }
        await write_links(links)

    base_url = PUBLIC_URL or str(request.base_url).rstrip("/")
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