from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.sessions import SessionMiddleware
import pandas as pd
import random
import string
from datetime import date

app = FastAPI()

# Chiave per sessioni (per MVP va bene così)
app.add_middleware(SessionMiddleware, secret_key="supersecretkey")

# Database in RAM (per MVP)
USERS = {}          # email → {"otp": "123456"}
USAGE = {}          # email → {"date": YYYY-MM-DD, "count": X}
DAILY_LIMIT = 10    # limite ricerche per utenti free


# -----------------------------
# HOME → redirect a /login
# -----------------------------
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if request.session.get("email"):
        return RedirectResponse("/app")
    return RedirectResponse("/login")


# -----------------------------
# LOGIN PAGE
# -----------------------------
@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return """
    <html><body style="font-family: Arial; margin: 40px;">
        <h2>Accedi</h2>
        <form action="/send-otp" method="post">
            <p><input type="email" name="email" placeholder="Email" required></p>
            <button type="submit">Invia codice</button>
        </form>
    </body></html>
    """


# -----------------------------
# INVIA OTP
# -----------------------------
@app.post("/send-otp", response_class=HTMLResponse)
async def send_otp(email: str = Form(...)):
    otp = "".join(random.choices(string.digits, k=6))
    USERS[email] = {"otp": otp}

    # Per MVP: mostriamo l’OTP a schermo
    # (in produzione lo invierai via email)
    return f"""
    <html><body style="font-family: Arial; margin: 40px;">
        <h3>Codice inviato a {email}</h3>
        <p><b>Codice OTP (solo per test): {otp}</b></p>
        <form action="/verify-otp" method="post">
            <input type="hidden" name="email" value="{email}">
            <p><input type="text" name="otp" placeholder="Inserisci codice" required></p>
            <button type="submit">Accedi</button>
        </form>
    </body></html>
    """


# -----------------------------
# VERIFICA OTP
# -----------------------------
@app.post("/verify-otp", response_class=HTMLResponse)
async def verify_otp(request: Request, email: str = Form(...), otp: str = Form(...)):
    if email in USERS and USERS[email]["otp"] == otp:
        request.session["email"] = email
        return RedirectResponse("/app", status_code=302)
    return "<h3>Codice errato</h3>"


# -----------------------------
# LOGOUT
# -----------------------------
@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")


# -----------------------------
# PAGINA PRINCIPALE (protetta)
# -----------------------------
@app.get("/app", response_class=HTMLResponse)
async def app_page(request: Request):
    email = request.session.get("email")
    if not email:
        return RedirectResponse("/login")

    # recupero uso giornaliero
    usage = USAGE.get(email, {"date": date.today(), "count": 0})
    count = usage["count"]

    return f"""
    <html><body style="font-family: Arial; margin: 40px;">
        <h2>Benvenuto, {email}</h2>
        <p>Ricerche oggi: <b>{count}/{DAILY_LIMIT}</b></p>
        <a href="/logout">Logout</a>
        <hr>
        <h3>Carica un file e cerca una voce</h3>
        <form action="/search" method="post" enctype="multipart/form-data">
            <p><input type="file" name="file" required></p>
            <p><input type="text" name="query" placeholder="Voce da cercare" required></p>
            <button type="submit">Cerca</button>
        </form>
    </body></html>
    """


# -----------------------------
# FUNZIONE DI RICERCA (super‑veloce)
# -----------------------------
@app.post("/search", response_class=HTMLResponse)
async def search(request: Request, file: UploadFile = File(...), query: str = Form(...)):
    email = request.session.get("email")
    if not email:
        return RedirectResponse("/login")

    # controllo limite giornaliero
    today = date.today()
    usage = USAGE.get(email, {"date": today, "count": 0})

    if usage["date"] != today:
        usage = {"date": today, "count": 0}

    if usage["count"] >= DAILY_LIMIT:
        return "<h3>Hai raggiunto il limite giornaliero di ricerche.</h3>"

    # aggiorno contatore
    usage["count"] += 1
    USAGE[email] = usage

    filename = file.filename.lower()

    try:
        # CSV in streaming
        if filename.endswith(".csv"):
            results = []
            chunksize = 2000
            file.file.seek(0)

            for chunk in pd.read_csv(file.file, chunksize=chunksize, dtype=str):
                chunk = chunk.fillna("").astype(str)
                combined = chunk.agg(" ".join, axis=1)
                mask = combined.str.contains(query, case=False, na=False)
                if mask.any():
                    results.append(chunk[mask])

            if not results:
                return f"<h3>Nessun risultato trovato per: <b>{query}</b></h3>"

            final_df = pd.concat(results, ignore_index=True)
            table_html = final_df.to_html(index=False)

            return f"""
            <h3>Risultati per: <b>{query}</b></h3>
            {table_html}
            <br><a href="/app">Torna indietro</a>
            """

        # XLSX
        elif filename.endswith(".xlsx"):
            file.file.seek(0)
            df = pd.read_excel(file.file, dtype=str)
            df = df.fillna("").astype(str)
            combined = df.agg(" ".join, axis=1)
            mask = combined.str.contains(query, case=False, na=False)
            results = df[mask]

            if results.empty:
                return f"<h3>Nessun risultato trovato per: <b>{query}</b></h3>"

            table_html = results.to_html(index=False)

            return f"""
            <h3>Risultati per: <b>{query}</b></h3>
            {table_html}
            <br><a href="/app">Torna indietro</a>
            """

        else:
            return "<h3>Formato non supportato. Usa CSV o XLSX.</h3>"

    except Exception as e:
        return f"<h3>Errore: {str(e)}</h3>"
