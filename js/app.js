const state = {
  data: null,
  activeLeague: "all",
  activeDate: "all",
};

let topChartInstance = null;
let h2hChartInstance = null;
let totalsChartInstance = null;

init();

async function init() {
  try {
    const res = await fetch("data/games.json", { cache: "no-store" });
    state.data = await res.json();
  } catch (err) {
    document.getElementById("updatedAt").textContent = "Erro ao carregar dados.";
    console.error(err);
    return;
  }

  // data/analises.json guarda análises aprofundadas feitas manualmente (mercados extras,
  // contexto, apostas sugeridas). Não é sobrescrito pelo workflow automático de odds.
  try {
    const analysisRes = await fetch("data/analises.json", { cache: "no-store" });
    if (analysisRes.ok) {
      const analysisData = await analysisRes.json();
      const existingIds = new Set(state.data.games.map((g) => g.id));
      const extra = (analysisData.games || []).filter((g) => !existingIds.has(g.id));
      state.data.games.push(...extra);
    }
  } catch (err) {
    console.warn("Sem análises extras (data/analises.json):", err);
  }

  renderUpdatedAt();
  renderSampleBanner();
  renderDateFilters();
  renderLeagueFilters();
  renderGames();
  renderTopChart();

  document.getElementById("modalClose").addEventListener("click", closeModal);
  document.getElementById("modalOverlay").addEventListener("click", (e) => {
    if (e.target.id === "modalOverlay") closeModal();
  });
}

function renderUpdatedAt() {
  const dt = new Date(state.data.generated_at);
  const formatted = dt.toLocaleString("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "America/Sao_Paulo",
  });
  document.getElementById("updatedAt").textContent = `Atualizado em ${formatted} (horário de Brasília)`;
}

function renderSampleBanner() {
  if (state.data.is_sample) {
    document.getElementById("sampleBanner").hidden = false;
  }
}

function dateKey(isoString) {
  return new Date(isoString).toLocaleDateString("en-CA", { timeZone: "America/Sao_Paulo" });
}

function renderDateFilters() {
  const container = document.getElementById("dateFilters");
  const keys = [...new Set(state.data.games.map((g) => dateKey(g.commence_time)))].sort();

  const buttons = [
    { key: "all", label: "Todos os dias" },
    ...keys.map((key) => {
      const label = new Date(`${key}T12:00:00Z`).toLocaleDateString("pt-BR", {
        weekday: "short",
        day: "2-digit",
        month: "2-digit",
        timeZone: "America/Sao_Paulo",
      });
      return { key, label: label.replace(".", "") };
    }),
  ];

  container.innerHTML = "";
  buttons.forEach((btn) => {
    const el = document.createElement("button");
    el.className = "filter-btn" + (btn.key === state.activeDate ? " active" : "");
    el.textContent = btn.label;
    el.addEventListener("click", () => {
      state.activeDate = btn.key;
      renderDateFilters();
      renderGames();
    });
    container.appendChild(el);
  });
}

function renderLeagueFilters() {
  const container = document.getElementById("leagueFilters");
  const leagueNames = [...new Set(state.data.games.map((g) => g.league_name))];

  const buttons = [{ key: "all", label: "Todos" }, ...leagueNames.map((name) => ({ key: name, label: name }))];

  container.innerHTML = "";
  buttons.forEach((btn) => {
    const el = document.createElement("button");
    el.className = "filter-btn" + (btn.key === state.activeLeague ? " active" : "");
    el.textContent = btn.label;
    el.addEventListener("click", () => {
      state.activeLeague = btn.key;
      renderLeagueFilters();
      renderGames();
    });
    container.appendChild(el);
  });
}

function renderGames() {
  const grid = document.getElementById("gamesGrid");
  grid.innerHTML = "";

  const games = [...state.data.games]
    .filter((g) => state.activeLeague === "all" || g.league_name === state.activeLeague)
    .filter((g) => state.activeDate === "all" || dateKey(g.commence_time) === state.activeDate)
    .sort((a, b) => new Date(a.commence_time) - new Date(b.commence_time));

  if (games.length === 0) {
    grid.innerHTML = `<p style="color:var(--text-dim)">Nenhum jogo encontrado para este filtro.</p>`;
    return;
  }

  games.forEach((game) => grid.appendChild(buildGameCard(game)));
}

function buildGameCard(game) {
  const card = document.createElement("div");
  card.className = "game-card";
  card.addEventListener("click", () => openModal(game));

  const dt = new Date(game.commence_time);
  const formatted = dt.toLocaleString("pt-BR", {
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "America/Sao_Paulo",
  });

  const favorite = topOutcome(game.markets.h2h);

  card.innerHTML = `
    <span class="league-tag">${game.league_name}</span>
    ${game.featured_analysis ? '<span class="analysis-tag">🔎 Análise completa</span>' : ""}
    <div class="teams">
      <div class="team">
        <div class="avatar">${initials(game.home_team)}</div>
        <span>${game.home_team}</span>
      </div>
      <span class="vs">vs</span>
      <div class="team">
        <div class="avatar">${initials(game.away_team)}</div>
        <span>${game.away_team}</span>
      </div>
    </div>
    <div class="datetime">${formatted} (BRT)${liveBadgeHtml(game.live)}</div>
    <div class="favorite">Favorito: ${favorite.name} · ${favorite.implied_pct.toFixed(0)}%</div>
  `;
  return card;
}

function liveBadgeHtml(live) {
  if (!live) return "";
  if (live.status === "inprogress") {
    return `<span class="live-badge inprogress">AO VIVO ${live.home_score}-${live.away_score}</span>`;
  }
  if (live.status === "finished") {
    return `<span class="live-badge finished">Final ${live.home_score}-${live.away_score}</span>`;
  }
  return "";
}

function initials(name) {
  return name
    .split(" ")
    .filter((w) => w.length > 2 || w === name.split(" ")[0])
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
}

function topOutcome(outcomes) {
  return [...outcomes].sort((a, b) => b.implied_pct - a.implied_pct)[0];
}

function openModal(game) {
  document.getElementById("modalTitle").textContent = `${game.home_team} vs ${game.away_team}`;
  const dt = new Date(game.commence_time);
  const formatted = dt.toLocaleString("pt-BR", {
    dateStyle: "full",
    timeStyle: "short",
    timeZone: "America/Sao_Paulo",
  });
  document.getElementById("modalMeta").textContent = `${game.league_name} · ${formatted} (Brasília) · ${game.bookmaker_count || "—"} casas consultadas`;

  const roundVenue = [game.round, game.venue].filter(Boolean).join(" · ");
  if (roundVenue) {
    document.getElementById("modalMeta").textContent += ` · ${roundVenue}`;
  }

  fillOddsTable("h2hTable", game.markets.h2h);
  fillOddsTable("totalsTable", game.markets.totals);

  renderDonut("h2hChart", game.markets.h2h, (o) => h2hChartInstance, (c) => (h2hChartInstance = c));
  renderDonut("totalsChart", game.markets.totals, (o) => totalsChartInstance, (c) => (totalsChartInstance = c));

  renderOptionalMarket("handicapSection", "handicapTable", game.markets.handicap);
  renderOptionalMarket("bttsSection", "bttsTable", game.markets.btts);
  renderOptionalMarket("cornersSection", "cornersTable", game.markets.corners);
  renderCards(game.markets.cards);
  renderSuggested(game);
  renderNotes(game);

  renderLineups(game);
  renderStats(game);

  document.getElementById("modalOverlay").hidden = false;
}

function closeModal() {
  document.getElementById("modalOverlay").hidden = true;
}

function fillOddsTable(tableId, outcomes) {
  const table = document.getElementById(tableId);
  const sorted = [...outcomes].sort((a, b) => b.implied_pct - a.implied_pct);
  table.innerHTML = sorted
    .map(
      (o, i) => `
      <tr class="${i === 0 ? "top-pick" : ""}">
        <td>${o.name}</td>
        <td>odd ${o.avg_price.toFixed(2)}</td>
        <td>${o.implied_pct.toFixed(1)}%</td>
      </tr>`
    )
    .join("");
}

function renderDonut(canvasId, outcomes, getInstance, setInstance) {
  const ctx = document.getElementById(canvasId);
  const existing = getInstance();
  if (existing) existing.destroy();

  const sorted = [...outcomes].sort((a, b) => b.implied_pct - a.implied_pct);
  const chart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: sorted.map((o) => `${o.name} (${o.implied_pct.toFixed(0)}%)`),
      datasets: [
        {
          data: sorted.map((o) => o.implied_pct),
          backgroundColor: ["#22c55e", "#3b82f6", "#f59e0b", "#ef4444"],
          borderColor: "#16223a",
          borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom", labels: { color: "#e8edf7", boxWidth: 12, font: { size: 11 } } },
      },
    },
  });
  setInstance(chart);
}

function renderOptionalMarket(sectionId, tableId, outcomes) {
  const section = document.getElementById(sectionId);
  if (!outcomes || outcomes.length === 0) {
    section.hidden = true;
    return;
  }
  section.hidden = false;
  fillOddsTable(tableId, outcomes);
}

function renderCards(outcomes) {
  const section = document.getElementById("cardsSection");
  if (!outcomes || outcomes.length === 0) {
    section.hidden = true;
    return;
  }
  section.hidden = false;
  fillOddsTable("cardsTable", outcomes);
  const hasModerateConfidence = outcomes.some((o) => o.confidence && o.confidence !== "alta");
  document.getElementById("cardsHint").textContent = hasModerateConfidence
    ? "⚠️ Sem linha consolidada das casas de apostas para este mercado — estimativa qualitativa, confiança moderada."
    : "";
}

function renderSuggested(game) {
  const section = document.getElementById("suggestedSection");
  const bets = game.suggested_bets;
  if (!bets || bets.length === 0) {
    section.hidden = true;
    return;
  }
  section.hidden = false;
  document.getElementById("suggestedTable").innerHTML = bets
    .map((b) => `<tr><td>${b.label}</td><td>${b.pct}</td></tr>`)
    .join("");
  const parlayEl = document.getElementById("parlayHint");
  parlayEl.textContent = game.suggested_parlay ? `🧾 Múltipla sugerida: ${game.suggested_parlay}` : "";
}

function renderNotes(game) {
  const section = document.getElementById("notesSection");
  const notes = game.notes;
  if (!notes || notes.length === 0) {
    section.hidden = true;
    return;
  }
  section.hidden = false;
  document.getElementById("notesList").innerHTML = notes.map((n) => `<li>${n}</li>`).join("");
}

function renderLineups(game) {
  const section = document.getElementById("lineupsSection");
  const body = document.getElementById("lineupsBody");
  const lineups = game.lineups;

  if (!lineups || (!lineups.home.length && !lineups.away.length)) {
    section.hidden = true;
    return;
  }

  section.hidden = false;
  const note = lineups.confirmed ? "" : `<p class="hint">Escalação provável (ainda não confirmada).</p>`;
  body.innerHTML = `
    ${note}
    <div class="side">
      <h5>${game.home_team}</h5>
      <ol>${lineups.home.map((p) => `<li>${p}</li>`).join("")}</ol>
    </div>
    <div class="side">
      <h5>${game.away_team}</h5>
      <ol>${lineups.away.map((p) => `<li>${p}</li>`).join("")}</ol>
    </div>
  `;
}

const STAT_NAMES_PT = {
  "Ball possession": "Posse de bola",
  "Total shots": "Finalizações",
  "Shots on target": "Finalizações no gol",
  "Corner kicks": "Escanteios",
  "Fouls": "Faltas",
};

function renderStats(game) {
  const section = document.getElementById("statsSection");
  const table = document.getElementById("statsTable");
  const stats = game.stats;

  if (!stats || stats.length === 0) {
    section.hidden = true;
    return;
  }

  section.hidden = false;
  table.innerHTML = stats
    .map(
      (s) => `
      <tr>
        <td>${s.home}</td>
        <td>${STAT_NAMES_PT[s.name] || s.name}</td>
        <td>${s.away}</td>
      </tr>`
    )
    .join("");
}

function renderTopChart() {
  const rows = [];
  state.data.games.forEach((game) => {
    Object.entries(game.markets).forEach(([marketKey, outcomes]) => {
      outcomes.forEach((o) => {
        if (marketKey === "h2h" && o.type === "draw") return;
        rows.push({
          label: `${o.name} — ${game.home_team} x ${game.away_team}`,
          pct: o.implied_pct,
        });
      });
    });
  });

  rows.sort((a, b) => b.pct - a.pct);
  const top = rows.slice(0, 8);

  const ctx = document.getElementById("topChart");
  if (topChartInstance) topChartInstance.destroy();
  topChartInstance = new Chart(ctx, {
    type: "bar",
    data: {
      labels: top.map((r) => r.label),
      datasets: [
        {
          label: "Probabilidade implícita (%)",
          data: top.map((r) => r.pct),
          backgroundColor: "#22c55e",
          borderRadius: 6,
        },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { min: 0, max: 100, ticks: { color: "#93a2c2" }, grid: { color: "#223252" } },
        y: { ticks: { color: "#e8edf7", font: { size: 11 } }, grid: { display: false } },
      },
      plugins: { legend: { display: false } },
    },
  });
}
