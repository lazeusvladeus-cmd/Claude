# Finance Bot — voice-first spending tracker for Telegram

A private Telegram bot that logs your spending from a voice note or a typed
message, keeps the ledger in a Google Sheet, reminds you about upcoming
Google Calendar events, and sends a weekly savings digest with concrete,
personalized advice.

Built for exactly one user (you) — everything is designed around that:
a hard allowlist, no accounts, no multi-tenant anything.

## What it does

- 🎙️ **Voice or text expense logging.** Send a voice note ("fifteen dollars
  for lunch") or just type it. The bot transcribes (Whisper), extracts the
  amount/currency/category (GPT), and asks you to confirm before saving —
  it never silently writes something to your ledger.
- ✏️ **One-tap corrections.** Wrong category or mixed up income/expense?
  Fix it with inline buttons before saving, or `/undo` right after.
- 📊 **Stats, with trend.** `/stats` (7 days) and `/month` (30 days vs. the
  30 days before) — a category breakdown as text plus a pie chart, normalized
  across currencies, with an at-a-glance "up/down vs. last period" line.
- 🎯 **A real, live-adjustable budget.** `/setbudget 1000` any time — no env
  var or redeploy needed. `/budget` shows a progress bar and how much is
  left. Cross 80% or 100% of it and you get pinged **the moment it happens**,
  not buried in next week's digest.
- 💡 **Savings advice.** `/advice` and a weekly digest analyze your spending,
  flag recurring subscriptions you might have forgotten about, and give
  specific suggestions (not "make a budget" — actual numbers).
- 📅 **Calendar reminders.** A message before each upcoming Google Calendar
  event; `/today` lists what's left today.
- 📄 **Google Sheets storage.** Your ledger is a normal spreadsheet you can
  open, filter, and pivot yourself, any time — `/sheet` links straight to it.
- 🧭 **No commands to memorize.** A persistent quick-action keyboard (Stats /
  Advice / Today / Sheet / Help) sits right above the keyboard, and every
  command shows up with a description in Telegram's native `/` menu.

## Architecture, in one paragraph

An `aiogram` (async Telegram bot framework) process polls Telegram for
updates. Every incoming message/callback first passes an allowlist
middleware that hard-rejects anyone whose Telegram user ID isn't yours.
Voice notes go through OpenAI Whisper for transcription; the resulting text
(or anything you type) goes through a GPT call that extracts a structured
transaction as JSON. You confirm via inline buttons, and only then does it
get appended to a Google Sheet (via a service account). A background
scheduler (APScheduler, same process) polls Google Calendar every minute for
upcoming events and fires reminders, and sends a weekly digest built from
your Sheet data plus an LLM call.

No database beyond the Sheet itself, no web server, no separate worker
process — one container, one process, restart-safe.

---

## Setup

Everything below is for you to do when you're back — none of it needed
guessing or fake values, so nothing was skipped or stubbed out.

### 1. Telegram bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram → `/newbot` →
   follow the prompts. You'll get a token like `123456789:AAExxxxxxxxxxxxx`.
2. Message [@userinfobot](https://t.me/userinfobot) to get your own numeric
   Telegram user ID.
3. Put both into `.env` (copy `.env.example` → `.env` first):
   ```
   TELEGRAM_BOT_TOKEN=123456789:AAExxxxxxxxxxxxx
   ALLOWED_TELEGRAM_USER_IDS=your_numeric_id
   ```
   If more than one person should be able to use it (e.g. a partner), add
   both IDs comma-separated. **This is the only thing standing between "my
   private finance bot" and "anyone who finds the bot's username can read my
   spending" — don't skip it, and the bot refuses to start without it.**

### 2. OpenAI API key

1. Create a key at https://platform.openai.com/api-keys.
2. `OPENAI_API_KEY=sk-...` in `.env`.
3. This is the only paid dependency. Whisper transcription + GPT parsing +
   weekly advice for personal-scale usage (a few voice notes a day) runs a
   few dollars a month at most. The bot has a built-in per-minute rate limit
   (`RATE_LIMIT_PER_MINUTE`, default 15) so a bug or accidental spam can't
   run up a surprise bill.

### 3. Google Cloud project (Sheets + Calendar)

1. Go to https://console.cloud.google.com/ → create a new project (any name).
2. **Enable APIs**: in "APIs & Services" → "Library", enable both
   **Google Sheets API** and **Google Calendar API**.
3. **Service account (for Sheets)**:
   - "APIs & Services" → "Credentials" → "Create Credentials" → "Service
     account". Any name is fine. No roles needed at the project level.
   - Open the created service account → "Keys" → "Add Key" → "Create new
     key" → JSON. This downloads a JSON file.
   - Save it as `secrets/service_account.json` in this project.
   - Note the service account's email (looks like
     `something@your-project.iam.gserviceaccount.com`) — you'll need it next.
4. **The spreadsheet**:
   - Create a new blank Google Sheet at https://sheets.new.
   - Share it (top-right "Share" button) with the service account's email
     from above, as **Editor**.
   - Copy the sheet ID from its URL:
     `https://docs.google.com/spreadsheets/d/`**`THIS_PART`**`/edit`
   - `GOOGLE_SHEET_ID=THIS_PART` in `.env`.
   - The bot creates a "Transactions" tab with headers automatically the
     first time it runs — you don't need to set up columns yourself.
5. **OAuth client (for Calendar)** — this one's separate because a service
   account has no access to your personal calendar unless you share it, and
   sharing a whole calendar is more than this needs:
   - "APIs & Services" → "Credentials" → "Create Credentials" → "OAuth
     client ID".
   - If prompted, configure the OAuth consent screen first: choose
     "External", fill in the required fields (app name, your email), and
     add yourself as a **test user**. This is fine to leave in "Testing"
     mode — you're the only user.
   - Application type: **Desktop app**. Create it, then download the JSON.
   - Save it as `secrets/oauth_client.json`.
6. **Run the one-time authorization script** — locally, on a machine with a
   browser (not on a headless server):
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   # fill in .env with everything above before this step
   python scripts/google_oauth_setup.py
   ```
   This opens a browser, you sign in and approve, and it writes
   `secrets/calendar_token.json`. Copy that file to wherever you deploy the
   bot (see below) — it's what lets the bot read your calendar without you
   re-authorizing every time.

### 4. Fill in the rest of `.env`

Open `.env.example` — every variable has a comment explaining it. Key ones
you'll actually want to look at:

- `BASE_CURRENCY` / `TRACKED_CURRENCIES` — set to `USD` and `USD,UAH` (or
  swap the order) to match how you actually spend. Stats and the weekly
  digest are normalized to `BASE_CURRENCY` using daily rates from the
  National Bank of Ukraine's public API (free, no key, and specifically
  reliable for UAH).
- `TIMEZONE` — an IANA name like `Europe/Kyiv`. Controls calendar reminder
  timing and the weekly digest send time.
- `CALENDAR_REMINDER_MINUTES_BEFORE` — default 20.
- `MONTHLY_BUDGET` — an optional starting default; leave blank if you'd
  rather set it from inside the bot with `/setbudget` once it's running
  (that's the normal way to do it day-to-day — no redeploy needed, and it
  overrides this env var once set).

### 5. Run it

**Locally (quickest way to check everything works):**
```bash
pip install -r requirements.txt
python -m app.main
```
Message your bot on Telegram — `/start` should reply immediately.

**Deploy so it's always on** (recommended: [Railway](https://railway.app) —
free/cheap, deploys straight from this repo's `Dockerfile`, no server to
maintain):

1. Push this repo to GitHub (if it isn't already).
2. On Railway: "New Project" → "Deploy from GitHub repo" → pick this repo.
   It detects the `Dockerfile` automatically.
3. In the service's "Variables" tab, add every variable from your `.env`
   (Railway's UI lets you paste a whole `.env` file at once).
4. For the two secret files (`service_account.json`, `oauth_client.json`,
   `calendar_token.json`): Railway supports mounting them as files via
   "Volumes", or simpler for three small JSON files — base64-encode each
   and add a tiny startup step, or use Railway's raw file variables if
   available in your plan. The straightforward path: add a "Volume" mounted
   at `/app/secrets`, then use Railway's shell (or `railway run`) to copy
   the three files in once after first deploy.
5. Deploy. Check the logs for `Bot starting. Allowed users: {...}` — that
   confirms it booted and loaded your allowlist correctly.

(Any other Docker-friendly host — Fly.io, Render, a VPS with
`docker compose up -d` — works the same way: build the image, set the env
vars, mount `secrets/`.)

### 6. Voice input from your iPhone

Send a voice message to the bot the normal Telegram way, and it works
immediately — no setup needed.

For the "double-tap the back of the phone" trigger specifically: iOS's Back
Tap only launches an **iOS Shortcut** — there's no way for Telegram itself
to detect a back-tap, so a short Shortcut is required as the bridge (record
audio → send it to the bot via Telegram's Bot API). You said you'd rather
wire that up yourself, so it's intentionally not included here; the pieces
you'd need are just:
- `https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/sendVoice` (or
  `sendAudio`), called with `chat_id` = your Telegram user ID and the
  recorded clip attached.
- Settings → Accessibility → Touch → Back Tap → Double Tap → your Shortcut.

Ask any time if you'd like the actual step-by-step Shortcut built out later.

### 7. Sharing this with friends

Do this, **not** adding their Telegram IDs to your own bot — an important
distinction. This bot is deliberately single-owner: `ALLOWED_TELEGRAM_USER_IDS`
locks it to whoever you list, and everyone listed shares one Google Sheet.
Adding a friend to *your* bot means their spending lands in *your* spreadsheet,
which is neither what they'd want nor what you'd want.

The right way to share it: each friend deploys their **own copy** — their own
bot (via their own BotFather chat), their own OpenAI key, their own Google
Sheet, their own `.env`. This repo is already built for that (nothing is
hardcoded to you), so it's exactly the steps above, done once per person.
If you want to make that easier, the friendliest thing to hand them is this
repo's link plus this README — everything they need is here.

---

## Commands

| Command | What it does |
|---|---|
| *(voice note)* | Transcribes, parses, asks you to confirm before saving |
| *(any text)* | Same, without the transcription step |
| `/stats` | Spending in the last 7 days, with a chart |
| `/month` | Spending in the last 30 days vs. the 30 days before, with a chart |
| `/advice` | On-demand savings suggestions |
| `/today` | Remaining calendar events today |
| `/budget` | Progress bar + how much of your monthly budget is left |
| `/setbudget <amount>` | Set or change your monthly budget, live |
| `/undo` | Remove the most recent transaction |
| `/sheet` | Link to your Google Sheet ledger |
| `/help` | Command list, inside the bot |

All of the above (except `/setbudget`, `/undo` and `/month`, kept off the
persistent keyboard so it stays to five buttons) are also one tap away on the
bottom quick-action keyboard.

## Repository layout

```
app/
  config.py          settings, loaded + validated once from env vars
  security.py         allowlist middleware + rate limiter
  models.py            ParsedTransaction / Transaction / categories
  formatting.py         shared "render a transaction as a Telegram message" logic
  pending_store.py       short-lived holding area for not-yet-confirmed transactions
  keyboards.py            inline keyboards + the persistent quick-action menu
  scheduler.py             calendar reminders + weekly digest, background jobs
  main.py                   entry point + native command menu registration
  handlers/
    voice.py, text.py         the two entry points into the same parsing pipeline
    commands.py                 slash commands + their quick-action-button twins
    callbacks.py                 confirm / edit / discard / undo / budget-alert logic
  services/
    transcription.py    OpenAI Whisper
    nlp.py                OpenAI GPT: text -> structured transaction, savings advice
    sheets.py               Google Sheets read/write + a Settings key/value tab
    calendar.py               Google Calendar reads
    fx.py                       currency conversion (NBU rates)
    stats.py                      aggregation, trend comparison, chart rendering
    recurring.py                    subscription/recurring-charge detection
    budget.py                         live budget + real-time threshold alerts
    advice.py                           ties stats + recurring + nlp into the digest
scripts/
  google_oauth_setup.py    run once, locally, to authorize Calendar access
tests/                       pytest — parsing validation, stats math, security, storage
```

## Design decisions worth knowing about

**Why a confirmation step instead of auto-saving?** Voice transcription and
LLM parsing are both fallible. An expense tracker that's silently wrong is
worse than a manual one — you'd stop trusting the numbers. One tap to
confirm keeps it fast without that risk.

**Why Google Sheets instead of a "real" database?** You asked for it
specifically (you're already in the Google ecosystem), and it comes with a
free UI, filtering, and pivot tables you'd otherwise have to build. The
tradeoff — it's slower than a real DB and not built for huge datasets — is
a non-issue at personal-finance-tracker scale (thousands of rows, not
millions).

**Why is the budget stored in a Sheet tab instead of a real database?** It
needs to be adjustable at runtime (`/setbudget`) without a redeploy, but this
is still a single-user bot with no other reason to run a database — reusing
the Sheet you already have (a tiny "Settings" tab, same access pattern as the
ledger) gets live-editable state without adding new infrastructure.

**Why alert at 80%/100% specifically, and only once each?** Those are the two
moments that are actually decision-relevant — "you should slow down" and
"you're over" — and re-alerting on every transaction past 100% would just be
noise you'd start ignoring. It resets automatically each calendar month.

**Why is there no bank/card integration?** Not requested, and it's a
fundamentally different trust and security category (linking real
financial-account credentials) than "transcribe what I say I spent." If you
want that later, it's worth its own conversation about which provider and
what access it needs.

## Security notes

- **Allowlist is mandatory.** The bot refuses to start if
  `ALLOWED_TELEGRAM_USER_IDS` is empty — this isn't a "recommended" setting.
- **Secrets never leave your infrastructure.** `.env` and `secrets/` are
  gitignored; logs redact anything that looks like a bot token or OpenAI
  key; error messages sent back to you in Telegram never include stack
  traces or internal details (those go to the server logs only).
- **Spreadsheet formula injection is neutralized.** A voice transcript like
  "equals HYPERLINK evil-link" could otherwise be written as a live formula
  into your Sheet and silently execute when you open it — a known class of
  bug in anything that writes free text into spreadsheets. Any field
  starting with `=`, `+`, `-`, or `@` gets a neutralizing prefix before
  it's written.
- **Cost-abuse guard.** Per-user rate limiting on every OpenAI-backed action,
  plus a hard cap on voice file size, so a bug or a stray message can't turn
  into a runaway bill.
- **Undo is scoped.** `/undo` only ever removes the single most recent row,
  and only if its ID still matches what you were shown — it can't be used to
  delete arbitrary history.

## Running tests

```bash
pip install -r requirements-dev.txt
pytest
```

45 tests cover transaction validation, the formula-injection fix, stats
aggregation and trend comparison, recurring-charge detection, the budget
alert state machine, keyboard/button correctness (including Telegram's
64-byte callback-data limit), the rate limiter, and the pending-confirmation
store.
