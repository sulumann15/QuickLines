import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

DB_PATH = Path(__file__).parent / "quotes.db"
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quote TEXT NOT NULL,
            author TEXT NOT NULL,
            fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)


async def fetch_random_quote() -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get("https://zenquotes.io/api/random", timeout=5)
        resp.raise_for_status()
        data = resp.json()[0]
        return {"quote": data["q"], "author": data["a"]}


async def fetch_random_fact() -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://uselessfacts.jsph.pl/api/v2/facts/random",
            params={"language": "en"},
            timeout=5,
        )
        resp.raise_for_status()
        return {"fact": " ".join(resp.json()["text"].split())}


def cache_quote(quote: str, author: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO quotes (quote, author) VALUES (?, ?)", (quote, author))
    conn.commit()
    conn.close()


def recent_quotes(limit: int = 5) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT quote, author, fetched_at FROM quotes ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [{"quote": r[0], "author": r[1], "fetched_at": r[2]} for r in rows]


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    history = recent_quotes()
    return templates.TemplateResponse(request, "index.html", {"history": history})


@app.get("/api/quote")
async def get_quote():
    data = await fetch_random_quote()
    cache_quote(data["quote"], data["author"])
    return data


@app.get("/api/fact")
async def get_fact():
    try:
        return await fetch_random_fact()
    except (httpx.HTTPError, KeyError, ValueError):
        raise HTTPException(status_code=502, detail="Could not fetch a fact")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/history")
async def get_history():
    return recent_quotes()
