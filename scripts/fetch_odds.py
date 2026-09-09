"""Busca jogos e odds na The Odds API e gera data/games.json para o site estático.

Uso: ODDS_API_KEY=xxxx python scripts/fetch_odds.py

Orçamento de créditos (plano free = 500/mês): 5 ligas x 3 mercados (h2h, totals,
btts) x 1 região = 15 créditos por execução. Rodando 1x/dia = ~450/mês, com folga
pra reruns manuais. Handicap/escanteios/cartões não entram aqui — a The Odds API
não cobre escanteios/cartões em nenhum plano, e handicap ficou de fora pra caber
no orçamento com 5 ligas (ele ainda pode ser adicionado manualmente via
data/analises.json, como no exemplo Santos x Atlético-MG).

Ajuste LEAGUES/REGIONS/MARKETS abaixo conforme seu plano — cada liga ou mercado
a mais multiplica o custo por execução.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import sofascore

API_BASE = "https://api.the-odds-api.com/v4/sports"
REGION = "eu"
MARKETS = "h2h,totals"
ODDS_FORMAT = "decimal"

# sport_key (The Odds API) -> nome exibido no site
LEAGUES = {
    "soccer_brazil_campeonato": "Brasileirão Série A",
    "soccer_conmebol_copa_libertadores": "Libertadores",
    "soccer_conmebol_copa_sudamericana": "Copa Sul-Americana",
    "soccer_epl": "Premier League",
    "soccer_uefa_champs_league": "Champions League",
}

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "games.json")
HISTORY_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "history.json")
HISTORY_MAX_ENTRIES = 14


def fetch_league(sport_key: str, api_key: str):
    url = (
        f"{API_BASE}/{sport_key}/odds/"
        f"?apiKey={api_key}&regions={REGION}&markets={MARKETS}"
        f"&oddsFormat={ODDS_FORMAT}&dateFormat=iso"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "gol-de-ia/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            remaining = resp.headers.get("x-requests-remaining")
            if remaining is not None:
                print(f"  créditos restantes: {remaining}")
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        print(f"  [aviso] {sport_key} falhou ({e.code}): {body[:300]}", file=sys.stderr)
        return None
    except urllib.error.URLError as e:
        print(f"  [aviso] {sport_key} falhou (rede): {e}", file=sys.stderr)
        return None


def implied_probabilities(outcomes_prices):
    """Recebe lista de odds decimais e devolve % implícita normalizada (remove a margem)."""
    inverses = [1 / p for p in outcomes_prices if p and p > 0]
    total = sum(inverses)
    if total == 0:
        return [0 for _ in outcomes_prices]
    return [round((1 / p) / total * 100, 1) if p and p > 0 else 0 for p in outcomes_prices]


def average_prices_by_outcome(bookmakers, market_key):
    """Agrega odds de todos os bookmakers para um mercado, tirando a média por outcome (name+point)."""
    sums = {}
    counts = {}
    for bm in bookmakers:
        market = next((m for m in bm.get("markets", []) if m.get("key") == market_key), None)
        if not market:
            continue
        for outcome in market.get("outcomes", []):
            key = (outcome.get("name"), outcome.get("point"))
            price = outcome.get("price")
            if not price:
                continue
            sums[key] = sums.get(key, 0) + price
            counts[key] = counts.get(key, 0) + 1
    return {key: sums[key] / counts[key] for key in sums}


def build_h2h(event, home_team, away_team):
    avg = average_prices_by_outcome(event.get("bookmakers", []), "h2h")
    if not avg:
        return []
    names = list(avg.keys())
    prices = [avg[k] for k in names]
    pcts = implied_probabilities(prices)

    def outcome_type(name):
        if name == home_team:
            return "home"
        if name == away_team:
            return "away"
        return "draw"

    result = []
    for (name, _point), price, pct in zip(names, prices, pcts):
        result.append(
            {
                "name": "Empate" if outcome_type(name) == "draw" else name,
                "type": outcome_type(name),
                "avg_price": round(price, 2),
                "implied_pct": pct,
            }
        )
    return result


def build_totals(event):
    avg = average_prices_by_outcome(event.get("bookmakers", []), "totals")
    if not avg:
        return []
    names = list(avg.keys())
    prices = [avg[k] for k in names]
    pcts = implied_probabilities(prices)

    result = []
    for (name, point), price, pct in zip(names, prices, pcts):
        label_pt = "Mais de" if name.lower().startswith("over") else "Menos de"
        result.append(
            {
                "name": f"{label_pt} {point} gols" if point is not None else name,
                "type": "over" if name.lower().startswith("over") else "under",
                "point": point,
                "avg_price": round(price, 2),
                "implied_pct": pct,
            }
        )
    return result


def build_btts(event):
    avg = average_prices_by_outcome(event.get("bookmakers", []), "btts")
    if not avg:
        return []
    names = list(avg.keys())
    prices = [avg[k] for k in names]
    pcts = implied_probabilities(prices)

    result = []
    for (name, _point), price, pct in zip(names, prices, pcts):
        is_yes = name.strip().lower() == "yes"
        result.append(
            {
                "name": "Ambas marcam — Sim" if is_yes else "Ambas marcam — Não",
                "type": "yes" if is_yes else "no",
                "avg_price": round(price, 2),
                "implied_pct": pct,
            }
        )
    return result


def update_history(games):
    """Acrescenta a % implícita do favorito de hoje ao histórico de cada jogo (data/history.json).
    Best-effort: se o arquivo não existir ainda, começa do zero."""
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            history = json.load(f).get("matches", {})
    except (FileNotFoundError, json.JSONDecodeError):
        history = {}

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for game in games:
        h2h = game.get("markets", {}).get("h2h", [])
        if not h2h:
            continue
        favorite = max(h2h, key=lambda o: o["implied_pct"])
        entries = history.setdefault(game["id"], [])
        entries[:] = [e for e in entries if e["date"] != today]
        entries.append({"date": today, "pct": favorite["implied_pct"]})
        entries.sort(key=lambda e: e["date"])
        del entries[:-HISTORY_MAX_ENTRIES]

    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump({"matches": history}, f, ensure_ascii=False, indent=2)


def main():
    api_key = os.environ.get("ODDS_API_KEY")
    if not api_key:
        print("ERRO: defina a variável de ambiente ODDS_API_KEY", file=sys.stderr)
        sys.exit(1)

    games = []
    for sport_key, league_name in LEAGUES.items():
        print(f"Buscando {league_name} ({sport_key})...")
        events = fetch_league(sport_key, api_key)
        if not events:
            continue

        for event in events:
            home_team = event.get("home_team")
            away_team = event.get("away_team")
            h2h = build_h2h(event, home_team, away_team)
            totals = build_totals(event)
            btts = build_btts(event)
            if not h2h and not totals:
                continue

            games.append(
                {
                    "id": event.get("id"),
                    "league_key": sport_key,
                    "league_name": league_name,
                    "commence_time": event.get("commence_time"),
                    "home_team": home_team,
                    "away_team": away_team,
                    "bookmaker_count": len(event.get("bookmakers", [])),
                    "markets": {"h2h": h2h, "totals": totals, "btts": btts},
                }
            )

        time.sleep(1)  # não martelar a API

    print(f"\nEnriquecendo {len(games)} jogos com dados do SofaScore (placar/escalações/estatísticas)...")
    games = [sofascore.enrich_game(g) for g in games]

    update_history(games)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "is_sample": False,
        "region": REGION,
        "leagues": [{"key": k, "name": v} for k, v in LEAGUES.items()],
        "games": games,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nOK: {len(games)} jogos salvos em {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
