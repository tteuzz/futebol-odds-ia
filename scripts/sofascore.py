"""Enriquecimento opcional com dados do SofaScore (API não-oficial, não documentada).

Usa apenas para: placar ao vivo/status, escalações e estatísticas básicas.
As odds continuam vindo exclusivamente da The Odds API (fetch_odds.py).

Atenção: o SofaScore costuma bloquear (403) requisições vindas de IPs de
datacenter/nuvem, incluindo os runners do GitHub Actions. Por isso todo o
código aqui é best-effort: qualquer falha é ignorada e o jogo simplesmente
fica sem esses dados extras, sem quebrar o resto do site.
"""

import difflib
import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

API_BASE = "https://api.sofascore.com/api/v1"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json",
}
STAT_WHITELIST = {"Ball possession", "Total shots", "Shots on target", "Corner kicks", "Fouls"}

_schedule_cache = {}
_blocked = False  # vira True se detectarmos bloqueio (403) para parar de tentar


def _get(path):
    global _blocked
    if _blocked:
        return None
    url = f"{API_BASE}{path}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            _blocked = True
            print(f"  [sofascore] bloqueado ({e.code}) neste IP — pulando enriquecimento pelo resto da execução")
        return None
    except Exception as e:  # noqa: BLE001 - best-effort, nunca deve derrubar o fetch principal
        print(f"  [sofascore] falha em {path}: {e}")
        return None


def _normalize(name: str) -> str:
    name = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    name = name.lower()
    name = re.sub(r"\b(fc|cf|sc|ac|ec|afc|cd|se|ca)\b", "", name)
    name = re.sub(r"[^a-z0-9 ]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def _scheduled_events(date_str: str):
    if date_str in _schedule_cache:
        return _schedule_cache[date_str]
    data = _get(f"/sport/football/scheduled-events/{date_str}")
    events = (data or {}).get("events", [])
    _schedule_cache[date_str] = events
    time.sleep(0.3)
    return events


def find_event_id(home_team: str, away_team: str, commence_iso: str):
    if _blocked:
        return None
    try:
        commence_dt = datetime.fromisoformat(commence_iso.replace("Z", "+00:00"))
    except ValueError:
        return None

    candidates = []
    for delta in (-1, 0, 1):
        d = (commence_dt + timedelta(days=delta)).strftime("%Y-%m-%d")
        candidates.extend(_scheduled_events(d))

    best, best_score = None, 0.0
    for ev in candidates:
        h = ev.get("homeTeam", {}).get("name", "")
        a = ev.get("awayTeam", {}).get("name", "")
        ts = ev.get("startTimestamp")
        if ts:
            ev_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            if abs((ev_dt - commence_dt).total_seconds()) > 12 * 3600:
                continue
        score = _similarity(home_team, h) + _similarity(away_team, a)
        if score > best_score:
            best_score, best = score, ev

    if best and best_score >= 1.3:
        return best.get("id")
    return None


def get_live_status(event_id):
    data = _get(f"/event/{event_id}")
    ev = (data or {}).get("event")
    if not ev:
        return None
    status = ev.get("status", {})
    return {
        "status": status.get("type"),  # notstarted | inprogress | finished
        "description": status.get("description"),
        "home_score": (ev.get("homeScore") or {}).get("current"),
        "away_score": (ev.get("awayScore") or {}).get("current"),
    }


def get_lineups(event_id):
    data = _get(f"/event/{event_id}/lineups")
    if not data:
        return None

    def starters(side):
        players = (data.get(side) or {}).get("players", [])
        names = [p["player"]["name"] for p in players if not p.get("substitute") and p.get("player", {}).get("name")]
        return names[:11]

    return {
        "confirmed": bool(data.get("confirmed")),
        "home": starters("home"),
        "away": starters("away"),
    }


def get_key_stats(event_id):
    data = _get(f"/event/{event_id}/statistics")
    stats_periods = (data or {}).get("statistics", [])
    period = next((p for p in stats_periods if p.get("period") == "ALL"), None) or (stats_periods[0] if stats_periods else None)
    if not period:
        return None

    result = []
    for group in period.get("groups", []):
        for item in group.get("statisticsItems", []):
            if item.get("name") in STAT_WHITELIST:
                result.append({"name": item.get("name"), "home": item.get("home"), "away": item.get("away")})
    return result or None


def enrich_game(game: dict):
    """Tenta adicionar live/lineups/stats ao dict do jogo. Nunca lança exceção."""
    try:
        event_id = find_event_id(game["home_team"], game["away_team"], game["commence_time"])
        if not event_id:
            return game

        live = get_live_status(event_id)
        if live:
            game["live"] = live

        lineups = get_lineups(event_id)
        if lineups and (lineups["home"] or lineups["away"]):
            game["lineups"] = lineups

        if live and live.get("status") in ("inprogress", "finished"):
            stats = get_key_stats(event_id)
            if stats:
                game["stats"] = stats

        time.sleep(0.3)
    except Exception as e:  # noqa: BLE001
        print(f"  [sofascore] erro inesperado enriquecendo {game.get('home_team')}: {e}")
    return game
