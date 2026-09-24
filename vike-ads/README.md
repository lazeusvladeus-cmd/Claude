# Vike Ads: ad creative system

A multi-agent tool for Vike Marketing. It researches current ad creative trends, writes full ad concepts and renders the image asset for each one. You can use it from the command line or from a small local web dashboard.

## The output contract

Every ad concept comes back as **exactly four parts**:

| # | Part | What you do with it |
|---|------|---------------------|
| 1 | **The idea**: one paragraph with the concept, the hook mechanism and a specific audience (demographics, interests and funnel stage) | Read and decide |
| 2 | **On-image text**: the headline and optional subheadline as plain text | Paste it over the image in Adobe Express |
| 3 | **Meta Ads Manager fields**: Primary text, Headline, Description (only if used) and the CTA button | Paste each one into the matching field in Ads Manager |
| 4 | **Generated image**: only the illustrative asset | Place it in Adobe Express |

The image **never** includes the headline, a CTA button or a decorative background gradient. The split between the generated image and the text you add yourself is enforced in several places:
- The ideation schema.
- The validators, which reject design notes, all-caps headlines, CTAs that don't exist in Meta and over-length fields.
- A fixed negative block in every image prompt.
- An optional vision QA pass that checks each render and retries if it fails.

The image uses one of three formats:
- **Dashboard**: a Meta Ads Manager table crop with one data row and one circled stat.
- **Review card**: a white speech-bubble card with a 16px radius, a star rating, an avatar and a quote. It carries no platform branding.
- **DM / iMessage**: an iOS Messages screenshot with the UI text spelled exactly.

## Architecture

```
                 ┌──────────────── Orchestrator ────────────────┐
 "research X" ──►│ Research Agent                                │
 "ad idea for X"►│ Ideation Agent ──► Image Agent (all 4 parts)  │
 "image for X" ─►│ Image Agent only (part 4, stored concept)     │
                 └───────────────────────────────────────────────┘
      shared: config/brand.json · data/ (reports, concepts, images, consents)
```

- **Research Agent** (`vike_ads/agents/research.py`) covers five themes: 1-star review ads, fake DM/iMessage ads, dashboard and before/after screenshots, anti-ad/pattern-interrupt formats, and the shift to authenticity over polish.
  - Sources: Google Custom Search (or OpenAI web search if that isn't set), the Meta Ad Library API, and page excerpts. Each report also includes Ad Library links to browse by hand.
  - Every finding has to cite sources from the evidence pack. Findings that cite nothing are dropped.
- **Ideation Agent** (`agents/ideation.py`) takes the verified findings and the brand context and produces concepts with several variants each (default 3, spread across the formats).
  - Every variant is checked against its schema, the identity guardrail, the format validators and claim verification.
  - A variant that fails gets one repair pass. If it still fails, it is dropped and never shown.
- **Image Agent** (`agents/image.py`) builds its prompt directly from the stored, agreed concept and makes no call to a copy model, so it can't invent new copy.
  - It uses **Nano Banana (Gemini API)** first and falls back to **fal.ai**.
  - Optional style references are read from `references/<format>/`.
- **Orchestrator** (`orchestrator.py`) routes requests using regex rules first and the OpenAI classifier as a fallback.
  - "Generate the image for X" accepts a variant ID, a concept ID, "the latest" or a fuzzy description.
  - If nothing matches, it asks which concept you meant, or tells you to run an idea request first. It never invents a new concept.

### DeepSeek rule
DeepSeek output is never shown as verified on DeepSeek's word alone (`verification.py`):
- **Research:** every finding DeepSeek writes goes to an **OpenAI judge along with a fresh web search**. If it's confirmed it is marked `cross_checked`. If not, it goes under **"Unverified leads"**, is clearly labelled, and is never passed to ideation.
- **Ideation:** DeepSeek writes one extra "challenger" variant per concept. OpenAI independently pulls out every claim in it (the variant's own list isn't trusted), and each claim is cross-checked. Anything unsupported is removed in the repair pass, or the whole variant is dropped.
- DeepSeek can never act as the judge. The code refuses to set that up.

### Identity guardrail (`guardrails.py`, can't be switched off)
- Review cards and DMs default to **`[Client Name]` and a silhouette avatar**, which you fill in yourself. Any name or photo-real face suggested by the model is replaced.
- A **photo-realistic, named likeness** is only possible when *you* ask for one (`--photoreal "Name"`) **and** that name is in the consent registry.
  - If it isn't registered, the system **asks first**. To confirm, you type `yes, real client with consent`.
  - One more check runs just before any prompt is sent to an image backend.
- No setting or environment variable turns this off.

## Setup

```bash
cd vike-ads
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in keys
python -m vike_ads doctor   # shows which integrations are live
```

**Keys** (all read from environment variables; see `.env.example`):
- **OpenAI**: *required* for ideation, verification and image QA. Set `OPENAI_MODEL` to the model you want (default `gpt-5`).
- **Gemini / Nano Banana** (primary images):
  1. Create a key at <https://aistudio.google.com/apikey>.
  2. Its Google Cloud project needs the **Generative Language API** enabled and **billing** set up, because image models aren't on the free tier.
  3. The default model is `gemini-3-pro-image-preview` (Nano Banana Pro), which renders UI text best. `gemini-2.5-flash-image` is cheaper.
  4. For Vertex AI instead, set `GOOGLE_IMAGE_BACKEND=vertex` and `VERTEX_PROJECT`, and run `gcloud auth login`.
- **fal.ai** (secondary images): `FAL_KEY`. The default model is `fal-ai/nano-banana-pro`, and it switches to `/edit` automatically when reference images are attached.
- **DeepSeek** (optional): `DEEPSEEK_API_KEY`.
- **Google Custom Search** (optional): `GOOGLE_CSE_API_KEY` and `GOOGLE_CSE_ID`. Google has closed this API to new customers, so without it the system uses OpenAI web search.
- **Meta Ad Library API** (optional): `META_AD_LIBRARY_TOKEN`, which needs an identity-verified developer account. Commercial ads are only returned for EU-reached ads, so the default countries are `IE,NL`. The token is removed from every stored URL.

**Reference images:** save your three reference ads' assets as PNG/JPG in `references/dashboard/`, `references/review_card/` and `references/dm_screenshot/`. They are sent as *style references* only. They're gitignored, so client material never gets committed.

## Usage

```bash
# free text, routed by the orchestrator
python -m vike_ads "research fake DM ads for agencies"
python -m vike_ads "give me an ad idea for dental clinics in Lviv that boost their own posts"
python -m vike_ads "generate the image for c-20260924-ab12-B"
python -m vike_ads "generate the image for the dental one"      # fuzzy match to a stored concept

# explicit commands
python -m vike_ads research "preschools" --themes one_star_review,fake_dm
python -m vike_ads idea "Irish accountants, cold audience" --variants 4 --format review_card,dm_screenshot
python -m vike_ads idea "..." --no-images      # parts 1-3 now, render later
python -m vike_ads image c-20260924-ab12 --backend fal      # every variant of a concept
python -m vike_ads image c-20260924-ab12-A --photoreal "Mary"   # asks for consent first
python -m vike_ads list | show <id> | latest-research
python -m vike_ads consent add "Mary" | consent list

# dashboard (local only, no auth)
python -m vike_ads serve                     # http://127.0.0.1:8765
python -m vike_ads serve --with-scheduler    # plus the weekly research refresh
```

**Weekly research refresh:** run `python -m vike_ads schedule` as a long-running process. It runs every `WEEKLY_RESEARCH_DAY` at `WEEKLY_RESEARCH_HOUR` in your `TIMEZONE`. You can use cron instead:
```
0 8 * * 1  cd /path/to/vike-ads && .venv/bin/python -m vike_ads research >> data/weekly.log 2>&1
```
New ideas always use the most recent report.

Notes go to stderr and are kept separate from the 4-part output. They cover things like "dashboard numbers are illustrative, so swap in real account data" and QA warnings.

## Brand context
`config/brand.json` holds the palette, typography and component rules, plus the agency facts every agent uses. That includes the offer facts, the proof points and the names of real clients, which are never used as display names. Agency claims in the copy may only come from `offer_facts` and `proof_points`, so keep those accurate.

## Tests
```bash
pip install -r requirements-dev.txt && python -m pytest
```
The tests use fake LLM, search and image backends plus mocked HTTP. They cover:
- the 4-part rendering
- the repair and drop behaviour
- routing
- the image-only path reusing a stored concept without calling a copy model
- the fallback to fal.ai
- the identity guardrail and consent flow
- DeepSeek cross-checking
- request payloads for Gemini, fal.ai, OpenAI and the Meta Ad Library
- the dashboard API
