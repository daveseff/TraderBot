# AI Paper Trader

Experimental paper-trading stock bot for Alpaca paper accounts only. It uses simple momentum and liquidity scoring, enforces conservative risk limits, journals every decision to SQLite, and can generate a markdown performance report after a two-week experiment.

The bot can discover symbols dynamically from Alpaca screeners and optionally use either OpenAI or a local Ollama model to rank the strongest candidates from structured market metrics instead of relying on a hardcoded ticker list.

## Safety constraints

- Paper trading only
- Refuses to run unless `ALPACA_PAPER=true`
- Uses `TradingClient(..., paper=True)`
- No margin
- No shorting
- Max 3 open positions
- Max `$30` notional per position by default
- Max daily loss `5%` by default
- Adds simulated slippage of `0.1%` per trade
- Logs all skipped trades and reasons

Note: Alpaca paper accounts may still report a margin multiplier. This bot does not reject that account state by itself; instead it enforces no-margin behavior by sizing buys against cash-only buying power.

## Project layout

```text
ai-paper-trader/
  Dockerfile
  docker-compose.yml
  requirements.txt
  .env.example
  README.md
  bot/
    __init__.py
    config.py
    broker_alpaca.py
    market_data.py
    strategy.py
    risk.py
    journal.py
    report.py
    main.py
  tests/
    test_risk.py
    test_strategy.py
```

## Setup

1. Create an Alpaca paper account at <https://alpaca.markets/>.
2. In the Alpaca dashboard, create paper trading API keys.
3. Choose an AI provider for the ranking layer:
   OpenAI, or a local Ollama instance.
4. Copy the environment template:

```bash
cp .env.example .env
```

5. Edit `.env` and set your paper API key and secret.

To use dynamic AI-driven research, leave `UNIVERSE` blank or remove it. The bot will discover liquid candidates from Alpaca's market screeners, then:

- filter out low-price and low-liquidity names
- score the survivors with momentum and volatility metrics
- optionally ask the configured OpenAI model to rank the final candidate set

If AI research is disabled or the configured provider is unavailable, the bot still uses dynamic discovery and falls back to rule-based ranking only.

## AI provider configuration

Use OpenAI:

```env
AI_PROVIDER=openai
OPENAI_API_KEY=your_openai_key
OPENAI_MODEL=gpt-4o-mini
AI_RESEARCH_ENABLED=true
```

Use Ollama:

```env
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=llama3.1
AI_RESEARCH_ENABLED=true
```

Notes for Ollama:

- `host.docker.internal` is mapped in `docker-compose.yml` so the container can reach your host's Ollama daemon.
- On Linux, this requires a recent Docker version with `host-gateway` support.
- The bot uses Ollama's native `/api/chat` endpoint and requests JSON output.
- If the local model is unavailable or returns invalid JSON, the bot falls back to rule-based ranking.

## Run with Docker

Build the image:

```bash
docker compose build
```

Run a scan without placing orders:

```bash
docker compose run --rm trader python -m bot.main scan
```

Run the trading cycle:

```bash
docker compose run --rm trader python -m bot.main trade
```

Run continuously in a long-lived loop:

```bash
docker compose up -d
docker compose logs -f trader
```

Generate a markdown report:

```bash
docker compose run --rm trader python -m bot.main report
```

Generate a postmortem review report with skip patterns and losing-trade context:

```bash
docker compose run --rm trader python -m bot.main review
```

Close all paper positions:

```bash
docker compose run --rm trader python -m bot.main close-all
```

## Local development

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
ruff check .
```

## Data and reports

- SQLite database defaults to `/app/data/trader.db`
- Markdown reports default to `/app/data/reports`
- Docker mounts local `./data` into the container so journals and reports persist
- Default container mode is `python -m bot.main daemon`
- `RUN_INTERVAL_SECONDS` controls how often a trade cycle runs
- `MARKET_OPEN_ONLY=true` skips cycles while the market is closed

## Suggested two-week experiment

Run the daemon for 2 weeks, then run `report` to review:

- Starting capital vs ending equity
- Estimated slippage costs
- Trade count and win/loss count
- Best and worst trade
- Decision log summary

## Scheduling later

You can either keep the daemon container running or schedule the one-shot trading command later with cron or systemd.

Example cron entry for weekdays:

```cron
30 13 * * 1-5 cd /home/dave/git/TraderBot/ai-paper-trader && docker compose run --rm trader python -m bot.main trade
```

Example systemd service and timer can wrap the same Docker command if you want more structured logging and restart behavior.

## Warning

This project is hard-coded for paper trading workflows and should never be pointed at a live account.
