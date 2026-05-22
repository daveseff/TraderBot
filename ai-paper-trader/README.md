# AI Paper Trader

Experimental paper-trading stock bot for Alpaca paper accounts only. It uses simple momentum and liquidity scoring, enforces conservative risk limits, journals every decision to SQLite, and can generate a markdown performance report after a two-week experiment.

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
3. Copy the environment template:

```bash
cp .env.example .env
```

4. Edit `.env` and set your paper API key and secret.

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

Generate a markdown report:

```bash
docker compose run --rm trader python -m bot.main report
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

## Suggested two-week experiment

Run `trade` once per market day for 2 weeks, then run `report` to review:

- Starting capital vs ending equity
- Estimated slippage costs
- Trade count and win/loss count
- Best and worst trade
- Decision log summary

## Scheduling later

You can schedule the trading command later with cron or systemd.

Example cron entry for weekdays:

```cron
30 13 * * 1-5 cd /home/dave/git/TraderBot/ai-paper-trader && docker compose run --rm trader python -m bot.main trade
```

Example systemd service and timer can wrap the same Docker command if you want more structured logging and restart behavior.

## Warning

This project is hard-coded for paper trading workflows and should never be pointed at a live account.
