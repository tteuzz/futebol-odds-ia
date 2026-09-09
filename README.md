# Gol de IA

Site estático que mostra os jogos das principais ligas de futebol (Brasileirão, Libertadores,
Copa Sul-Americana, Premier League, Champions League) com as odds das casas de apostas
convertidas em **probabilidade implícita (%)** — 1X2, gols e BTTS (ambas marcam) automáticos,
handicap/escanteios/cartões nas análises manuais —, histórico diário da odd, gráficos de
"apostas mais prováveis do dia" e, quando disponível, placar ao vivo/escalações/estatísticas via
SofaScore.

⚠️ **Isto é uma ferramenta informativa, não uma recomendação de aposta.** As porcentagens são
probabilidades implícitas nas odds do mercado, não previsões garantidas. Aposte com responsabilidade.

## Como funciona

1. Um workflow do GitHub Actions (`.github/workflows/update-odds.yml`) roda todo dia às 08:00
   (horário de Brasília) e executa `scripts/fetch_odds.py`.
2. Esse script busca jogos e odds na [The Odds API](https://the-odds-api.com/) para cada liga
   configurada, calcula a probabilidade implícita de cada resultado e tenta enriquecer cada jogo
   com placar ao vivo/escalações/estatísticas do SofaScore (best-effort — se bloquear, o site
   continua funcionando só com as odds).
3. O resultado é salvo em `data/games.json`, que é commitado automaticamente no repositório.
4. O GitHub Pages serve os arquivos estáticos (`index.html`, `css/`, `js/`) que leem esse JSON.

## Configuração (uma vez só)

### 1. Criar a chave da The Odds API

1. Crie uma conta grátis em https://the-odds-api.com/ (plano free = 500 créditos/mês).
2. Copie sua API key.

### 2. Adicionar a chave como secret do repositório

No GitHub: **Settings → Secrets and variables → Actions → New repository secret**
- Nome: `ODDS_API_KEY`
- Valor: sua chave copiada acima

### 3. Ativar o GitHub Pages

**Settings → Pages → Source: Deploy from a branch → Branch: `main` / pasta `/ (root)`** → Save.

O site ficará disponível em `https://SEU-USUARIO.github.io/NOME-DO-REPO/` (leva alguns minutos
para publicar pela primeira vez).

### 4. Gerar os dados reais pela primeira vez

Vá em **Actions → Atualizar Odds → Run workflow** e rode manualmente. Depois disso ele roda
sozinho todo dia. Você também pode rodar manualmente sempre que quiser forçar uma atualização.

## Ajustando as ligas

Edite o dicionário `LEAGUES` em `scripts/fetch_odds.py` — a chave é o `sport_key` da The Odds API
e o valor é o nome exibido no site. Lista completa de ligas disponíveis:
https://the-odds-api.com/sports-odds-data/sports-apis.html

⚠️ Cada liga consultada gasta créditos (mercados × regiões). Com 5 ligas, `h2h` + `totals` + `btts`
e região `eu`, uma atualização por dia consome ~450 dos 500 créditos gratuitos do mês (15
créditos/execução). Adicionar liga ou mercado sem estourar a cota:
- +1 liga = +3 créditos/execução (~90/mês)
- +1 mercado (ex: `spreads` pra handicap) = +5 créditos/execução (~150/mês)

Se quiser mais ligas/mercados do que cabe, ajuste o `cron` no workflow (ex: a cada 2 dias) ou
migre pra um plano pago da The Odds API.

### Escanteios e cartões

A The Odds API **não oferece** esses mercados em nenhum plano — por isso eles só aparecem nas
análises manuais (`data/analises.json`). A alternativa mais barata encontrada até agora é a
[5DollarFootballAPI](https://5dollarfootballapi.com/) (plano Pro, US$5/mês, inclui corner/card
lines do Bet365) — não foi integrada ainda porque é um serviço pequeno e não verificado.

## Rodando localmente

```bash
$env:ODDS_API_KEY = "sua-chave-aqui"
python scripts/fetch_odds.py
```

Depois abra `index.html` num navegador (ou sirva a pasta com qualquer servidor estático) para
conferir o resultado antes de commitar.

## Sobre o SofaScore

O enriquecimento com placar ao vivo/escalações/estatísticas usa endpoints não-oficiais e não
documentados do SofaScore. Esse uso é apenas pessoal/não-comercial. O SofaScore costuma bloquear
requisições vindas de IPs de datacenter (como os runners do GitHub Actions) — se isso acontecer,
o script detecta o bloqueio, registra um aviso no log da Action e segue normalmente sem esses
dados extras (as odds nunca são afetadas). Se quiser esses dados de forma mais confiável, rode
`scripts/fetch_odds.py` localmente (do seu próprio IP) e faça commit/push manual.
