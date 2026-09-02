"""
Restaurant Menu QR Platform (MVP)
Bid project: Restaurant Menu QR Platform

Owner uploads a menu (image/PDF or simple items) -> public page + QR code.

Run:
  pip install -r requirements.txt
  uvicorn app:app --reload --port 8080
Open http://127.0.0.1:8080
"""

from __future__ import annotations

import io
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import qrcode
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
UPLOADS = DATA / "uploads"
DB = DATA / "menus.db"
PUBLIC_BASE = "http://127.0.0.1:8080"

DATA.mkdir(exist_ok=True)
UPLOADS.mkdir(exist_ok=True)

app = FastAPI(title="Restaurant QR Menu MVP")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS)), name="uploads")


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS restaurants (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS menu_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                restaurant_id TEXT NOT NULL,
                name TEXT NOT NULL,
                price TEXT DEFAULT '',
                description TEXT DEFAULT '',
                FOREIGN KEY(restaurant_id) REFERENCES restaurants(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS menu_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                restaurant_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                stored_as TEXT NOT NULL,
                FOREIGN KEY(restaurant_id) REFERENCES restaurants(id)
            )
            """
        )


@app.on_event("startup")
def on_startup() -> None:
    init_db()


HOME_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>QR Menu</title>
  <style>
    :root { --ink:#1a1f16; --accent:#2f6f4e; --bg:#f4efe6; --card:#fffdf8; }
    * { box-sizing: border-box; }
    body { margin:0; font-family: Georgia, "Times New Roman", serif; background:
      radial-gradient(circle at 10% 10%, #fff8e8, transparent 40%),
      radial-gradient(circle at 90% 0%, #e6f0ea, transparent 35%),
      var(--bg); color: var(--ink); }
    main { max-width: 720px; margin: 0 auto; padding: 48px 20px 80px; }
    h1 { font-size: clamp(2rem, 5vw, 3rem); margin: 0 0 8px; letter-spacing: -0.02em; }
    p.lead { color:#4a5148; margin:0 0 28px; }
    form { background: var(--card); padding: 24px; border: 1px solid #ddd4c4; }
    label { display:block; margin: 14px 0 6px; font-size: 0.95rem; }
    input, textarea { width:100%; padding:10px 12px; border:1px solid #cfc5b4; background:#fff; font: inherit; }
    button { margin-top: 18px; background: var(--accent); color:white; border:0; padding:12px 18px; font: inherit; cursor:pointer; }
    .hint { font-size: 0.85rem; color:#6a7166; }
  </style>
</head>
<body>
<main>
  <h1>QR Menu</h1>
  <p class="lead">Create a public restaurant menu and a scan-ready QR code in one step.</p>
  <form action="/create" method="post" enctype="multipart/form-data">
    <label>Restaurant name</label>
    <input name="name" required placeholder="e.g. Green Bowl Café"/>

    <label>Menu items <span class="hint">(one per line: Name | Price | Description)</span></label>
    <textarea name="items" rows="8" placeholder="Avocado Toast | 8.50 | Sourdough, chili oil
Latte | 4.00 | Oat milk available"></textarea>

    <label>Or upload menu file (image / PDF)</label>
    <input type="file" name="file" accept=".png,.jpg,.jpeg,.webp,.pdf"/>

    <button type="submit">Generate QR menu</button>
  </form>
</main>
</body>
</html>
"""


OWNER_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{name} — Owner</title>
  <style>
    body {{ font-family: Georgia, serif; background:#f4efe6; margin:0; color:#1a1f16; }}
    main {{ max-width:720px; margin:0 auto; padding:40px 20px; }}
    a {{ color:#2f6f4e; }}
    .box {{ background:#fffdf8; border:1px solid #ddd4c4; padding:20px; margin:16px 0; }}
    img.qr {{ width:220px; height:220px; background:white; }}
    code {{ background:#eee8dc; padding:2px 6px; }}
  </style>
</head>
<body>
<main>
  <h1>{name}</h1>
  <div class="box">
    <p>Public menu URL:<br><a href="{public}" target="_blank">{public}</a></p>
    <p>QR image: <a href="/r/{rid}/qr.png">download PNG</a></p>
    <p><img class="qr" src="/r/{rid}/qr.png" alt="QR"/></p>
    <p class="hint">Share the QR at tables. Guests open the public page — no app install.</p>
  </div>
  <p><a href="/">Create another</a></p>
</main>
</body>
</html>
"""


PUBLIC_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{name} Menu</title>
  <style>
    body {{ margin:0; font-family: "Segoe UI", sans-serif; background:#111; color:#f7f3ea; }}
    header {{ padding:28px 20px 8px; text-align:center; }}
    h1 {{ margin:0; font-weight:600; letter-spacing:0.02em; }}
    .wrap {{ max-width:640px; margin:0 auto; padding:12px 16px 60px; }}
    .item {{ border-bottom:1px solid #2a2a2a; padding:14px 0; display:flex; justify-content:space-between; gap:12px; }}
    .name {{ font-size:1.05rem; }}
    .desc {{ color:#b8b0a2; font-size:0.9rem; margin-top:4px; }}
    .price {{ white-space:nowrap; color:#d8c39a; }}
    .file {{ margin-top:20px; }}
    .file img, .file embed {{ width:100%; border-radius:8px; background:#222; }}
    .empty {{ color:#999; text-align:center; padding:40px 0; }}
  </style>
</head>
<body>
<header><h1>{name}</h1></header>
<div class="wrap">
  {items_html}
  {files_html}
</div>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def home():
    return HOME_HTML


def parse_items(raw: str) -> list[tuple[str, str, str]]:
    rows = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        name = parts[0]
        price = parts[1] if len(parts) > 1 else ""
        desc = parts[2] if len(parts) > 2 else ""
        rows.append((name, price, desc))
    return rows


@app.post("/create")
async def create(
    name: str = Form(...),
    items: str = Form(""),
    file: UploadFile | None = File(None),
):
    name = name.strip()
    if not name:
        raise HTTPException(400, "Name required")

    rid = secrets.token_urlsafe(8)
    now = datetime.now(timezone.utc).isoformat()
    parsed = parse_items(items)

    with db() as conn:
        conn.execute(
            "INSERT INTO restaurants(id, name, created_at) VALUES (?,?,?)",
            (rid, name, now),
        )
        for n, p, d in parsed:
            conn.execute(
                "INSERT INTO menu_items(restaurant_id, name, price, description) VALUES (?,?,?,?)",
                (rid, n, p, d),
            )
        if file and file.filename:
            ext = Path(file.filename).suffix.lower()
            if ext not in {".png", ".jpg", ".jpeg", ".webp", ".pdf"}:
                raise HTTPException(400, "Unsupported file type")
            stored = f"{rid}_{secrets.token_hex(4)}{ext}"
            dest = UPLOADS / stored
            dest.write_bytes(await file.read())
            conn.execute(
                "INSERT INTO menu_files(restaurant_id, filename, stored_as) VALUES (?,?,?)",
                (rid, file.filename, stored),
            )
        conn.commit()

    return RedirectResponse(f"/owner/{rid}", status_code=303)


@app.get("/owner/{rid}", response_class=HTMLResponse)
def owner(rid: str):
    with db() as conn:
        row = conn.execute("SELECT * FROM restaurants WHERE id=?", (rid,)).fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    public = f"{PUBLIC_BASE}/m/{rid}"
    return OWNER_HTML.format(name=row["name"], public=public, rid=rid)


@app.get("/m/{rid}", response_class=HTMLResponse)
def public_menu(rid: str):
    with db() as conn:
        rest = conn.execute("SELECT * FROM restaurants WHERE id=?", (rid,)).fetchone()
        if not rest:
            raise HTTPException(404, "Not found")
        items = conn.execute(
            "SELECT * FROM menu_items WHERE restaurant_id=? ORDER BY id", (rid,)
        ).fetchall()
        files = conn.execute(
            "SELECT * FROM menu_files WHERE restaurant_id=? ORDER BY id", (rid,)
        ).fetchall()

    if items:
        items_html = "".join(
            f'<div class="item"><div><div class="name">{i["name"]}</div>'
            f'<div class="desc">{i["description"]}</div></div>'
            f'<div class="price">{i["price"]}</div></div>'
            for i in items
        )
    else:
        items_html = '<p class="empty">Menu coming soon.</p>' if not files else ""

    files_html = ""
    for f in files:
        url = f"/uploads/{f['stored_as']}"
        if f["stored_as"].lower().endswith(".pdf"):
            files_html += f'<div class="file"><embed src="{url}" type="application/pdf" height="640"/></div>'
        else:
            files_html += f'<div class="file"><img src="{url}" alt="menu"/></div>'

    return PUBLIC_HTML.format(name=rest["name"], items_html=items_html, files_html=files_html)


@app.get("/r/{rid}/qr.png")
def qr_png(rid: str):
    with db() as conn:
        rest = conn.execute("SELECT id FROM restaurants WHERE id=?", (rid,)).fetchone()
    if not rest:
        raise HTTPException(404, "Not found")
    url = f"{PUBLIC_BASE}/m/{rid}"
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


@app.get("/api/health")
def health():
    return {"status": "ok", "menus_db": str(DB)}
