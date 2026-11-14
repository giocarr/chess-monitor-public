import re
from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
import io, shutil
import chess
import chess.pgn
import chess.engine

USERNAME = "giocarr"
API_ROOT = "https://api.chess.com/pub/player"
HEADERS = {"User-Agent": "ChessPerformanceDashboard/1.0 (personal analysis)"}


def find_stockfish():
    candidates = [shutil.which("stockfish"), "/usr/games/stockfish", "/usr/bin/stockfish", "/usr/local/bin/stockfish"]
    for candidate in candidates:
        if candidate and __import__("os").path.isfile(candidate) and __import__("os").access(candidate, __import__("os").X_OK):
            return candidate
    return None

st.set_page_config(page_title="Chess Performance Dashboard", page_icon="♟️", layout="wide")

@st.cache_data(ttl=21600, show_spinner=False)
def load_games(username: str):
    session = requests.Session()
    session.headers.update(HEADERS)
    response = session.get(f"{API_ROOT}/{username}/games/archives", timeout=30)
    response.raise_for_status()
    archives = response.json().get("archives", [])
    games = []
    errors = []
    progress = st.progress(0, text="Recupero archivio Chess.com…")
    for i, url in enumerate(archives):
        try:
            r = session.get(url, timeout=30)
            r.raise_for_status()
            games.extend(r.json().get("games", []))
        except Exception as exc:
            errors.append(f"{url}: {exc}")
        progress.progress((i + 1) / max(1, len(archives)), text=f"Archivio {i+1}/{len(archives)}")
    progress.empty()
    return games, len(archives), errors

def normalize_games(games, username):
    rows = []
    for g in games:
        if not g.get("rated") or g.get("time_class") != "rapid" or g.get("rules") != "chess":
            continue
        white = g.get("white", {})
        black = g.get("black", {})
        is_white = white.get("username", "").lower() == username.lower()
        is_black = black.get("username", "").lower() == username.lower()
        if not (is_white or is_black):
            continue
        me = white if is_white else black
        opponent = black if is_white else white
        result = me.get("result", "")
        if result == "win":
            outcome = "Vittoria"
            score = 1.0
        elif result in ("agreed", "repetition", "stalemate", "insufficient", "50move", "timevsinsufficient"):
            outcome = "Patta"
            score = 0.5
        else:
            outcome = "Sconfitta"
            score = 0.0
        ts = g.get("end_time")
        date = datetime.fromtimestamp(ts, timezone.utc) if ts else None
        eco_url = g.get("eco", "")
        opening = eco_url.rsplit("/", 1)[-1].replace("-", " ") if eco_url else "Non classificata"
        rows.append({
            "date": date, "year": date.year if date else None,
            "month": date.strftime("%Y-%m") if date else None,
            "color": "Bianco" if is_white else "Nero",
            "result": outcome, "score": score,
            "rating": me.get("rating"), "opponent_rating": opponent.get("rating"),
            "opponent": opponent.get("username", "Sconosciuto"),
            "opening": opening, "eco": re.search(r"/([A-E][0-9]{2})", eco_url).group(1) if re.search(r"/([A-E][0-9]{2})", eco_url) else "",
            "url": g.get("url", ""), "pgn": g.get("pgn", ""),
            "accuracy": (g.get("accuracies") or {}).get("white" if is_white else "black"),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("date")
        df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
        df["opponent_rating"] = pd.to_numeric(df["opponent_rating"], errors="coerce")
        df["accuracy"] = pd.to_numeric(df["accuracy"], errors="coerce")
    return df

st.title("♟️ Chess Performance Dashboard")
st.caption("Analisi dello storico Rapid Rated di Chess.com · account giocarr")

with st.spinner("Caricamento partite Rapid Rated da Chess.com…"):
    try:
        games, archive_count, errors = load_games(USERNAME)
        df = normalize_games(games, USERNAME)
    except Exception as exc:
        st.error(f"Non riesco a leggere l'archivio pubblico Chess.com: {exc}")
        st.stop()

if df.empty:
    st.warning("Non risultano partite Rapid Rated nell'archivio restituito da Chess.com.")
    st.stop()

st.caption(f"Ultimo aggiornamento: {datetime.now().strftime('%d/%m/%Y %H:%M')} · {archive_count} archivi mensili consultati")
if errors:
    st.warning(f"Alcuni archivi non sono stati letti ({len(errors)}). I risultati potrebbero essere incompleti.")

min_date, max_date = df["date"].min().date(), df["date"].max().date()
date_range = st.date_input("Periodo di analisi", value=(min_date, max_date), min_value=min_date, max_value=max_date)
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
    view = df[(df["date"].dt.date >= start_date) & (df["date"].dt.date <= end_date)].copy()
else:
    view = df.copy()

if view.empty:
    st.info("Nessuna partita nel periodo selezionato.")
    st.stop()

n = len(view)
wins = int((view["result"] == "Vittoria").sum())
draws = int((view["result"] == "Patta").sum())
losses = int((view["result"] == "Sconfitta").sum())
score_pct = 100 * view["score"].mean()
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Partite", f"{n:,}".replace(",", "."))
c2.metric("Vittorie", f"{wins:,}".replace(",", "."))
c3.metric("Patte", f"{draws:,}".replace(",", "."))
c4.metric("Sconfitte", f"{losses:,}".replace(",", "."))
c5.metric("Punteggio", f"{score_pct:.1f}%")

tab_overview, tab_color, tab_openings, tab_games, tab_engine = st.tabs(["Panoramica", "Bianco e Nero", "Aperture", "Partite", "Analisi Stockfish"])

with tab_overview:
    left, right = st.columns(2)
    monthly = view.dropna(subset=["month"]).groupby("month").agg(games=("score", "size"), score=("score", "mean")).reset_index()
    monthly["score"] *= 100
    with left:
        st.subheader("Partite nel tempo")
        st.plotly_chart(px.bar(monthly, x="month", y="games", labels={"month":"Mese", "games":"Partite"}), use_container_width=True)
    with right:
        st.subheader("Percentuale di punteggio")
        st.plotly_chart(px.line(monthly, x="month", y="score", markers=True, labels={"month":"Mese", "score":"Punteggio %"}), use_container_width=True)
    rating = view.dropna(subset=["rating"])
    if not rating.empty:
        st.subheader("Evoluzione del rating registrato nelle partite")
        st.plotly_chart(px.line(rating, x="date", y="rating", color="color", labels={"date":"Data", "rating":"Rating", "color":"Colore"}), use_container_width=True)
    st.caption("Il rating ricostruito dai PGN è il rating associato a ciascuna partita, non la serie ufficiale completa del profilo.")

with tab_color:
    by_color = view.groupby("color").agg(partite=("score","size"), punteggio=("score","mean"), vittorie=("result", lambda x: (x=="Vittoria").mean())).reset_index()
    by_color["punteggio"] *= 100
    by_color["vittorie"] *= 100
    st.dataframe(by_color.rename(columns={"color":"Colore","partite":"Partite","punteggio":"Punteggio %","vittorie":"Vittorie %"}), hide_index=True, use_container_width=True)
    st.plotly_chart(px.bar(by_color, x="color", y="punteggio", text_auto=".1f", labels={"color":"Colore","punteggio":"Punteggio %"}), use_container_width=True)

with tab_openings:
    min_games = st.slider("Numero minimo di partite per apertura", 1, 30, 5)
    openings = view.groupby(["eco","opening"], dropna=False).agg(partite=("score","size"), punteggio=("score","mean"), accuratezza=("accuracy","mean")).reset_index()
    openings = openings[openings["partite"] >= min_games].sort_values(["punteggio","partite"], ascending=[False,False])
    openings["punteggio"] = (openings["punteggio"]*100).round(1)
    st.dataframe(openings.rename(columns={"eco":"ECO","opening":"Apertura","partite":"Partite","punteggio":"Punteggio %","accuratezza":"Accuratezza media"}), hide_index=True, use_container_width=True)

with tab_games:
    color_filter = st.selectbox("Colore", ["Tutti", "Bianco", "Nero"])
    result_filter = st.selectbox("Esito", ["Tutti", "Vittoria", "Patta", "Sconfitta"])
    listing = view.copy()
    if color_filter != "Tutti":
        listing = listing[listing["color"] == color_filter]
    if result_filter != "Tutti":
        listing = listing[listing["result"] == result_filter]
    listing = listing.sort_values("date", ascending=False)
    st.dataframe(listing[["date","color","result","rating","opponent","opponent_rating","opening","accuracy","url"]].rename(columns={
        "date":"Data","color":"Colore","result":"Esito","rating":"Tuo Elo","opponent":"Avversario","opponent_rating":"Elo avversario","opening":"Apertura","accuracy":"Precisione","url":"Partita"
    }), hide_index=True, use_container_width=True, column_config={"Partita":st.column_config.LinkColumn("Partita")})


@st.cache_data(ttl=604800, show_spinner=False)
def analyze_loss(pgn_text, user_color, depth):
    path = find_stockfish()
    if not path:
        raise RuntimeError("Stockfish non trovato: controlla packages.txt.")
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        raise ValueError("PGN non leggibile.")
    board = game.board()
    white_user = user_color == "Bianco"
    found = []
    engine = chess.engine.SimpleEngine.popen_uci(path)
    try:
        engine.configure({"Threads": 1, "Hash": 128})
        for move in game.mainline_moves():
            is_white = board.turn == chess.WHITE
            if is_white == white_user:
                san = board.san(move)
                number = board.fullmove_number
                before = engine.analyse(board, chess.engine.Limit(depth=depth))
                score_before = before["score"].pov(board.turn).score(mate_score=10000)
                board.push(move)
                after = engine.analyse(board, chess.engine.Limit(depth=depth))
                pov = chess.WHITE if white_user else chess.BLACK
                score_after = after["score"].pov(pov).score(mate_score=10000)
                loss = max(0, score_before - score_after)
                if loss >= 50:
                    kind = "Blunder" if loss >= 250 else ("Errore" if loss >= 100 else "Imprecisione")
                    phase = "Apertura" if number <= 12 else ("Finale" if len(board.piece_map()) <= 12 else "Mediogioco")
                    found.append({"Mossa": str(number) + ("." if white_user else "...") + " " + san,
                                  "Perdita (cp)": int(loss), "Tipo": kind, "Fase": phase})
            else:
                board.push(move)
    finally:
        engine.quit()
    return found

with tab_engine:
    st.subheader("Analisi delle sconfitte con Stockfish")
    st.write("Il motore confronta la posizione prima e dopo ciascuna tua mossa e stima la perdita in centipawn.")
    if not find_stockfish():
        st.error("Stockfish non installato: verifica packages.txt.")
    else:
        lost = view[view["result"] == "Sconfitta"].dropna(subset=["pgn"]).sort_values("date", ascending=False)
        if len(lost) == 0:
            st.info("Nessuna sconfitta con PGN nel periodo selezionato.")
        else:
            count = st.slider("Sconfitte recenti da analizzare", 1, min(20, len(lost)), min(5, len(lost)))
            depth = st.slider("Profondità Stockfish", 8, 16, 10)
            selected = lost.head(count)
            if st.button("Analizza con Stockfish", type="primary"):
                errors, failures = [], []
                progress = st.progress(0)
                for i, (_, row) in enumerate(selected.iterrows()):
                    try:
                        for item in analyze_loss(row["pgn"], row["color"], depth):
                            item.update({"Data": row["date"].strftime("%d/%m/%Y"), "Colore": row["color"],
                                         "Avversario": row["opponent"], "Partita": row["url"]})
                            errors.append(item)
                    except Exception as exc:
                        failures.append(str(exc))
                    progress.progress((i + 1) / len(selected))
                st.session_state["sf_errors"] = pd.DataFrame(errors)
                st.session_state["sf_failures"] = failures
            result = st.session_state.get("sf_errors")
            if result is not None:
                if not result.empty:
                    a, b, c = st.columns(3)
                    a.metric("Errori rilevati", len(result))
                    b.metric("Blunder", int((result["Tipo"] == "Blunder").sum()))
                    c.metric("Perdita media", str(round(result["Perdita (cp)"].mean())) + " cp")
                    st.plotly_chart(px.bar(result.groupby(["Fase", "Tipo"]).size().reset_index(name="Numero"),
                                           x="Fase", y="Numero", color="Tipo", barmode="group"),
                                    use_container_width=True)
                    st.dataframe(result.sort_values("Perdita (cp)", ascending=False),
                                 hide_index=True, use_container_width=True,
                                 column_config={"Partita": st.column_config.LinkColumn("Partita")})
                    st.caption("Soglie indicative: imprecisione 50–99 cp, errore 100–249 cp, blunder da 250 cp. La diagnosi tattica/strategica verrà aggiunta dopo aver validato i risultati.")
                else:
                    st.success("Nessun errore da 50 cp o superiore nelle partite analizzate.")
                for message in st.session_state.get("sf_failures", []):
                    st.warning(message)


st.divider()
st.caption("Analisi Stockfish disponibile sulle sconfitte Rapid selezionate. Le categorie tattiche e strategiche saranno approfondite nelle prossime versioni.")
