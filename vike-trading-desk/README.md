# Vike Trading Desk

Your personal trading & research app. It runs **on your own PC**, opens **in your browser**, and only you
can see it.

| Tab | What it does | Status |
|---|---|---|
| 📋 Pre-Session Prep | NQ / ES levels, economic events, chart, Context → Location → Confirmation checklist, PDF/PNG export, journal & session review | ✅ Phase 1 |
| 🎓 Learning Roadmap | Your weeks 1-12 learning path with verified links and progress checkboxes | ✅ Phase 2 |
| 📊 Equity Research | SEC fundamentals, tear sheets, DCF, bank metrics, ad KPIs, comparisons | ✅ Phase 3 |
| ✨ Polish | Dark mode by default (switch in ⋮ → Settings → Theme), PDF prep sheet | ✅ Phase 4 |

---

## 1. One-time setup (Windows, about 15 minutes)

### Step 1: Install Python 3.13

Python is the programming language the app is written in. You install it once and never have to look at it.

1. Open <https://www.python.org/downloads/windows/>
2. Find **Python 3.13.16** (or the newest **3.13.x**) and click **Windows installer (64-bit)**.
   *Why not the newest version, 3.15? It came out on 9 Oct 2026, and some data libraries take a few weeks to support
   a brand-new Python. 3.13 is the safe choice.*
3. Run the downloaded file. On the first screen, **tick "Add python.exe to PATH"** (at the bottom), then click
   **Install Now**.
4. When it says *Setup was successful*, click **Close**.

### Step 2: Get the app onto your PC

The easiest way, and the one that makes updates one click later, is **GitHub Desktop**:

1. Download and install GitHub Desktop from <https://desktop.github.com/download/>, then sign in with your GitHub
   account (`lazeusvladeus-cmd`).
2. **File → Clone repository → GitHub.com** tab → choose **`lazeusvladeus-cmd/Claude`** → pick a folder, for example
   `C:\Users\<you>\Trading` → **Clone**.
   *Tip: avoid OneDrive-synced folders (Desktop / Documents are often synced). They make the app slower.*
3. At the top of GitHub Desktop, click **Current branch** and choose **`claude/great-wozniak-m2ap8s`**
   (the app lives on this branch until it's merged into `main`).
4. Open the cloned folder, then the **`vike-trading-desk`** folder inside it.

<details>
<summary>Alternative without GitHub Desktop (ZIP download)</summary>

On github.com open the `Claude` repository, switch the branch (button top-left) to `claude/great-wozniak-m2ap8s`,
click **Code → Download ZIP**, unzip it, and open the `vike-trading-desk` folder. Updating is then manual (see
section 7).
</details>

### Step 3: Start it

**Double-click `start.bat`.**

- **First start:** a black window appears and installs everything it needs (3-10 minutes, only once). Then your
  browser opens the app at <http://localhost:8501>.
- If Windows shows **"Windows protected your PC"**, click **More info → Run anyway**. Windows does this for any file
  that came from the internet.
- **Keep the black window open** while you use the app. Close it to stop the app.
- Later starts take about 10 seconds.
- Tip: right-click `start.bat` → **Send to → Desktop (create shortcut)** for a desktop icon.

---

## 2. Your daily routine (weekdays, before your 15:00 Kyiv shift)

1. **Around 12:00-14:30 Kyiv:** start the app → **📋 Pre-Session Prep → Today's prep**.
2. **Top row:** the session date is picked automatically (you can change it), plus the RTH open time
   (normally 16:30 Kyiv / 09:30 NY) and how long until your prep deadline.
3. **NQ tab, then ES:** read the *Context hints*, the *price ladder* (all levels from highest to lowest, with your
   current price marked ▶ LAST) and the chart. The overnight high/low keeps changing until the 09:30 NY open, so
   before the open it says *"so far"*.
4. **Economic events:** anything high-impact today? Every time is shown in Kyiv **and** NY time.
5. **Context → Location → Confirmation:** fill it in and press **Save plan to journal + create PDF & PNG**. The sheet
   is saved in your journal folder; download or print it if you like.
6. **After the session (or the next morning):** open **📓 Journal & review**, pick the date, see how price traded
   around your levels, write your review, grade your process and attach ATAS screenshots.

**Time zones:** Kyiv is usually **7 hours** ahead of New York. For a few weeks a year it's **6 hours**, because
Europe and the US change their clocks on different dates (in 2026: 8-29 March and 25 October - 1 November). The app
adjusts automatically and tells you when it happens.

---

## 3. The levels on your sheet

| Tag | Meaning |
|---|---|
| **PDH / PDL / PDC** | Prior day high / low / close of the regular session (RTH, 09:30-16:00 NY) |
| **pVWAP** | Prior day's VWAP (volume-weighted average price) at the close |
| **VAH / POC / VAL** | Prior day's value area high, point of control (price with the most volume) and value area low (70% of volume) |
| **ONH / ONL** | Overnight (Globex) high / low: everything traded since yesterday's 16:00 NY close |
| **WkH / WkL** | This week's high / low so far (all hours) |
| **PWH / PWL** | Last week's high / low |
| **nPOC** | **Naked POC**: an older session's POC that price has *never traded back to*. Many order-flow traders watch them as targets |
| **Gap** | Today's open (or, before the open, the last price) minus the prior RTH close |

Colours: **blue** = volume profile levels, **orange** = prior day, **green** = overnight & weekly. Every line also has
a text label, so you never have to rely on colour alone.

---

## 4. Changing settings

Your settings are in **`config.toml`**. It's created automatically on first start (as a copy of
`config.example.toml`). Right-click it → **Open with → Notepad**, change something, save, then press **R** in the
browser tab. Examples:

| You want to... | Change this |
|---|---|
| Hide ES | in `[instruments.ES]` set `enabled = false` |
| Also see medium-impact events | `impact_levels = ["High", "Medium"]` |
| Show 5 sessions on the chart | `sessions_to_show = 5` |
| Bigger candles | `bar_minutes = 15` |
| Keep the journal somewhere else | `folder = "C:/Users/You/Documents/TradingJournal"` (use forward slashes `/`) |
| Change your risk defaults | the `[risk]` section |

If you make a typo, the app tells you which line to fix.

---

## 5. Where your files are

| Path | What |
|---|---|
| `journal/2026-10-15/` | that day's `prep.json` (levels, plan, review), `sheet.pdf`, `sheet_NQ.png`, `sheet_ES.png`, `screenshots/` |
| `data/economic_events_manual.csv` | events you added yourself |
| `data/cache/` | downloaded prices (safe to delete) |
| `config.toml` | your settings |

None of these are uploaded to GitHub. **Back up your journal folder yourself**: copy it to Google Drive now and then,
or set the journal `folder` to a synced folder.

---

## 6. About the data (the honest version)

### Prices: Yahoo Finance via `yfinance` (free)

Good enough for daily prep levels, but know the limits:

- **Unofficial.** yfinance reads Yahoo's website data. Yahoo sometimes rate-limits it or changes things; then the
  library needs an update (double-click **`update.bat`**).
- **Delayed.** CME futures on Yahoo are delayed (usually 10+ minutes). Fine for prep, never for live entries: ATAS is
  your live data.
- **Short intraday history.** 1-minute bars only for about the last 8 days, 5-minute bars for about 60 days,
  hourly for about 2 years. The app saves everything it downloads, so your own 1-minute history grows if you open it
  daily.
- **Bars, not trades.** No bid/ask, no delta, no footprint. The volume profile spreads each bar's volume over its
  range, so VAH / VAL / POC are close to ATAS (usually within a few ticks) but not identical. **Always confirm levels
  on your ATAS chart.**
- **Continuous contract.** `NQ=F` / `ES=F` are Yahoo's front-month series. In rollover weeks (March, June,
  September, December) they may show a different contract than your ATAS chart; the app warns you then.
- **Holidays.** On US holidays the CME often has a shortened session, and the app counts it as "the prior day".
  Double-check levels on the day after a holiday.

### Economic calendar: free ForexFactory weekly feed

Free and widely used, but unofficial: it covers one week at a time and blocks you if you download too often (the
app downloads at most every 4 hours and keeps a copy). For important days, cross-check the official calendars (links
inside the app: Fed FOMC, BLS for CPI/NFP, BEA for GDP/PCE). You can always add events yourself in the app.

### Paid data for coded backtesting (weeks 8-12): recommendation only, nothing bought

**Cheapest reliable: [Databento](https://databento.com/pricing), pay-as-you-go.** Official CME Globex data back to
2010: 1-minute bars plus tick-by-tick trades that record which side was the aggressor, so you can rebuild real delta
and footprint for an order-flow strategy. Historical data needs no subscription: you pay per GB, and new accounts get
**$125 of free credit** (expires after 6 months). Databento's own example: the free credit covers about 16 months
of ES tick-by-tick trades, and 1-minute bars are far smaller. Their estimator shows the exact price before you
download.

**Alternative: [FirstRate Data](https://firstratedata.com/i/futures/NQ)**: a one-time **$199.95** for NQ 1-minute
bars back to 2008 (simple CSV files, continuous and individual contracts, bars only, no order flow), plus $99.95/year
if you want updates.

*Prices checked on 15 Oct 2026. I have not signed you up for anything.*

---

## 7. Updating the app (after each phase)

**GitHub Desktop:** open it → **Fetch origin** → **Pull origin**. Then double-click `start.bat` as usual (it installs
any new libraries by itself). Your `config.toml`, journal and events are never touched by updates.

**ZIP users:** download the new ZIP, unzip it to a new folder, then copy `config.toml`, the `journal` folder and
`data/economic_events_manual.csv` from your old folder into the new one.

---

## 8. If something goes wrong

| Problem | Fix |
|---|---|
| *Python was not found* | Do step 1 again and tick **Add python.exe to PATH**. Restart the PC if it still fails. |
| *Yahoo is limiting requests* | Wait 5-10 minutes, then press **Refresh data**. Don't hammer the button. |
| Downloads fail although they worked before | Double-click **`update.bat`** (updates yfinance), then `start.bat`. |
| Levels differ from ATAS by a few ticks | Expected (see section 6). |
| Levels differ from ATAS by a lot | Rollover week? Or check that your ATAS session is 09:30-16:00 NY for RTH. |
| The browser didn't open | Open <http://localhost:8501> yourself. |
| *Port 8501 is in use* | The app is probably already running in another black window. |
| The app says the settings file needs a fix | It names the line. Fix it in Notepad, save, press R. |
| Anything else is broken | Delete the `.venv` folder and double-click `start.bat` (a fresh install). |

---

## 9. For the curious: what's inside

```
vike-trading-desk/
├── start.bat / update.bat     one-click start / update the libraries
├── app.py                     the app (3 tabs)
├── config.example.toml        settings template → your config.toml
├── requirements.txt           libraries the app needs
├── desk/                      the code
│   ├── levels.py              prior day, overnight, value area, weekly, naked POCs, gap
│   ├── profile.py             volume profile (POC / VAH / VAL)
│   ├── market_data.py         Yahoo download + local copy
│   ├── econ_calendar.py       free feed + your manual events
│   ├── charts.py              interactive chart
│   ├── sheet_export.py        PDF / PNG sheet
│   ├── journal.py             journal folder
│   ├── timeutil.py            Kyiv / New York clocks, trade dates, contract months
│   └── ui_prep.py             the Pre-Session Prep tab
└── tests/                     automatic checks (made-up prices, never shown in the app)
```

Running the checks (optional): `.venv\Scripts\python -m pip install pytest` then `.venv\Scripts\python -m pytest`.

---

## 10. Equity Research tab (Tab 2)

1. **First time:** the tab asks for your **name and email**. The SEC requires this for its free data API; it's sent
   only to sec.gov and saved in `data/sec_contact.txt` (or set `sec_user_agent` in `config.toml`).
2. Pick a company from your coverage list (`[coverage]` in `config.toml`: quality / banks / ad_driven) or type any
   US ticker.
3. **Tear sheet:** 10 years of revenue, margins, FCF, ROIC, debt, cash, share count (from 10-K XBRL data), TTM figures
   (last fiscal year + this year-to-date - last year-to-date) and multiples (P/E, EV/EBIT, FCF yield) with Yahoo prices.
4. **Valuation:** DCF sliders (growth, target margin, discount rate, terminal growth + advanced), a sensitivity
   chart (which assumption matters most), a discount-rate × terminal-growth table, and a **reverse DCF** (growth priced
   in). Banks get **justified P/B = (ROE - g) / (r - g)** instead, because a DCF doesn't fit banks.
5. **Banks** show P/B, P/TBV, ROE, ROTCE, efficiency ratio, NII / average assets (approximate NIM), loan growth,
   provisions and net charge-offs. CET1 is taken from the SEC data when the bank tags it; otherwise type the reported
   figure (and NIM) from the 10-K into the boxes under the table.
6. **KPIs:** a tracker for ad metrics (ad revenue, daily active users/people, ARPU/ARPP, ad impressions growth,
   price per ad growth). These live in earnings releases, not in SEC data - type them in from Meta's IR site. The
   tear sheet also reads **advertising revenue** and segment revenue from the latest 10-K when available.
7. **Notes:** thesis, risks, catalysts, valuation notes - saved per company in `data/research/`.
8. **Compare:** 2-3 companies side by side (table + revenue and ROE charts).

Honest limits: XBRL tags differ between companies, so a few fields can be empty for some companies (shown as "-").
Always check key numbers against the 10-K.

## 11. Learning Roadmap tab (Tab 3)

- 12 trading modules + 5 equity modules, each with what to learn, why it matters for your Context → Location →
  Confirmation strategy, a practical exercise and 2-4 resource links (all checked on 15 Oct 2026).
- Set the date your week 1 starts; the tab shows what to study this week and the full week 1-12 plan.
- Tick links, exercises and modules as you go, and write notes - saved in `data/learning_progress.json`.
- Add your own links in the tab, or edit `learning/my_links.csv` with Excel/Notepad. Module texts are in
  `learning/roadmap.toml`.
