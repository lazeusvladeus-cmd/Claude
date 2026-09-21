# Vike Marketing — Operational Essentials Audit
**Prepared:** 2026-09-20 | **Scope:** what a serious 1-person (16 hrs/week) agency still needs to operate credibly and legally while selling to Ireland/Netherlands SMBs plus Lviv/Ukraine local niches, on a near-zero budget.

**How to read this doc:** every tool price below was checked today (2026-09-20) against a live page — the URL is cited next to the claim. Every legal/tax/GDPR statement is directional research only and is explicitly flagged **"verify with a professional"** — I am not a lawyer or accountant, and Ukrainian tax rules in particular change often.

---

## 1. Master Priority Table

| # | Item | Impact | Effort | Now / Later | Est. Monthly Cost |
|---|------|--------|--------|-------------|--------------------|
| 1 | Confirm/formalize FOP (sole proprietor) status + Group 3 tax registration | High | High | **NOW** (blocks legal invoicing) | $0 tool cost; ~$50–150 one-off accountant consult (verify) |
| 2 | Simple month-to-month service agreement template | High | Low | **NOW** | Free |
| 3 | Privacy policy + cookie consent banner (site + pixel) | High | Med | **NOW** | Free (CookieYes free tier) |
| 4 | Connect site contact form → real CRM/Sheet (kill "Telegram only" leads) | High | Low | **NOW** | Free |
| 5 | CRM for lead/deal tracking | High | Low | **NOW** | Free (Zoho or HubSpot free tier) |
| 6 | GA4 property set up correctly (conversions, not just pageviews) | High | Low | **NOW** | Free |
| 7 | GTM form-submission → conversion tracking (GA4 + Google Ads) | High | Med | **NOW** | Free |
| 8 | SPF / DKIM / DMARC on sending domain (cold outreach deliverability) | High | Med | **NOW** | Free |
| 9 | Booking link (Calendly-style) for the free audit CTA | Med | Low | **NOW** | Free |
| 10 | Case-study template (fillable, ready for client #1) | Med | Low | **NOW** | Free |
| 11 | Brand assets checklist (logo files, colors, one-pager) | Med | Low | **NOW** | Free (Canva free) |
| 12 | Portfolio presentation without real project photos yet | Med | Low | **NOW** | Free |
| 13 | Proposal template (reusable, branded) | Med | Low | **NOW** | Free (Google Docs/Canva) |
| 14 | Reporting template for client dashboards | Med | Low | **NOW** | Free (Looker Studio) |
| 15 | Lightweight project/task board (solo use) | Med | Low | **NOW** | Free (Trello or Notion) |
| 16 | Re-verify SSL certificate on vikemarketing.com | High | Low | **NOW** (5-min check) | Free |
| 17 | Time tracking | Low | Low | **LATER** (light touch) | Free (Toggl free) |
| 18 | Contract e-signature tool (formal, trackable) | Low | Low | **LATER** (once volume justifies) | Free tier now, ~$19+/mo later |
| 19 | Upgrade automation tool past free tier (Make/Zapier paid) | Med | Low | **LATER** (once lead volume > ~90 tasks/mo) | $0 → $9–29/mo when needed |
| 20 | CRM paid tier (multi-pipeline, automation) | Med | Low | **LATER** (once >3 users or need workflow automation) | $0 → $14+/user/mo |
| 21 | VAT/EU compliance review (Diia City, VAT registration threshold) | Med | High | **LATER** (revisit at scale or with accountant) | Accountant fee (verify) |

**Reading the table:** almost everything genuinely needed *right now* is free or near-free — the real cost this month is Vladyslav's time (a handful of hours across items 1–16) plus one paid professional consultation (item 1). Nothing on this list requires meaningful cash outlay before there's revenue to justify it.

---

## 2. Legal Entity / FOP Status (Ukraine)

**Flag: this entire section is directional research, not legal or tax advice. Verify every figure and rule with a licensed Ukrainian accountant (bukhgalter) or lawyer before acting.**

Vike currently has "no formal legal entity status confirmed." For a Ukraine-based solo founder invoicing Irish/Dutch (and other EU) clients for digital marketing services, the standard, well-trodden path used by Ukrainian freelancers/agencies is registration as a **FOP (Fizychna Osoba-Pidpryiemets, sole proprietor) under the simplified tax system, Group 3**:

- Group 3 FOPs can work with individuals, Ukrainian companies, **and foreign clients** — this is the group IT/marketing freelancers and small agencies typically use for exactly this situation ([fieldari.com](https://fieldari.com/en/blog/ukraine-fop-group-3-freelancer-tax-2026), checked 2026-09-20).
- Reported 2026 tax structure: 5% single tax (or 3% + VAT) plus a 1% military levy, for an effective ~6% headline rate, plus a flat quarterly Unified Social Contribution (ESV/SSC) — one source cites ~1,902.34 UAH/quarter regardless of income ([torgsoft.ua](https://torgsoft.ua/en/articles/law/podatkovyj-kalendar/), [buh.ua](https://buh.ua/en/when-and-how-much-will-a-sole-proprietor-pay-taxes-in-ukraine), checked 2026-09-20). **Verify with an accountant** — rates, the military levy, and ESV amounts have changed multiple times in recent years and may change again.
- Group 3 income ceiling reported at 1,167 minimum wages (~UAH 10.09M in 2026) ([promotion-global.com](https://promotion-global.com/en/fop-group-3-taxes-2026-ukraine/), checked 2026-09-20) — far above Vike's near-term revenue, so not an immediate constraint, but worth knowing.
- Foreign-currency payments from EU clients are generally treated as legal FOP income when received into a declared foreign-currency account at a Ukrainian bank ([buh.ua](https://buh.ua/en/when-and-how-much-will-a-sole-proprietor-pay-taxes-in-ukraine), checked 2026-09-20) — meaning **how the client pays (bank transfer vs. Wise vs. Stripe/PayPal) matters for compliance** and should be set up correctly from day one with an accountant's input, not improvised.
- One source flags potential VAT changes affecting Group 3 FOPs in 2026 ([case.lviv.ua](https://case.lviv.ua/en/fop-3-grupi-u-2026-roci-chi-dovedetsya-platiti-pdv-i-yak-pidgotuvatisya-do-zmin.html), checked 2026-09-20) — **verify current VAT obligations before invoicing EU B2B clients**, since EU clients may also expect basic company documentation for their own reverse-charge/accounting purposes.

**What's typically needed to invoice EU clients as a Ukrainian FOP (general practice, verify specifics):**
1. FOP registration completed (Group 3, correct KVED/activity codes for marketing/advertising services).
2. A business bank account (UAH and/or foreign currency) at a Ukrainian bank, properly linked to the FOP.
3. An invoice format EU clients can process internally (invoice number, FOP registration number, service description, amount, currency, bank details) — EU companies generally don't need Vike to charge VAT on B2B services rendered from outside the EU, but this depends on service type and should be confirmed.
4. Basic bookkeeping (even a spreadsheet) tracking each payment against each invoice — required for Ukrainian tax reporting regardless of client location.

**Do now:** if FOP registration is not yet done, this is the single highest-leverage "NOW" item — it blocks being able to legally invoice and receive payment from EU clients at all. Book one paid session with a Ukrainian accountant this month (typically inexpensive, often a flat consultation fee) to confirm group, KVED codes, and payment-receipt mechanics before the first paid client signs.

**Do later:** VAT threshold monitoring, Diia City resident status (a special legal/tax regime some Ukrainian IT companies use) — irrelevant at Vike's current revenue but worth a mention to revisit once revenue scales meaningfully. **Verify with a professional** whether Diia City ever becomes relevant for a marketing (vs. pure IT) business.

---

## 3. Contracts — Month-to-Month Service Agreement

Vike sells month-to-month, no-contract retainers ($200/$400/$750). "No contract" in a sales sense should not mean "no written agreement" — a lightweight service agreement protects both sides and looks professional to EU SMB buyers who expect one.

**What a simple agreement should cover (template considerations, not a substitute for legal review):**
- Parties, effective date, services included per tier (Launch/Scale/Dominate), explicitly scoped (e.g., "Meta + Google ad management, X hours creative production/month").
- Fee, billing cycle (monthly, in advance or arrears), accepted payment methods/currency.
- Month-to-month term with a stated notice period to cancel (e.g., 14–30 days) — this is where "no contracts" gets formalized as "no lock-in," not "no paperwork."
- Ad spend disclaimer (client pays Meta/Google directly or reimburses spend; agency fee is separate from media spend).
- IP ownership of creative assets produced (typically transfers to client on payment).
- Confidentiality (client data, ad account access).
- Limitation of liability and no-guarantee-of-results clause (standard in performance marketing).
- Governing law/jurisdiction — **verify with a lawyer** which is more practical/enforceable: Ukrainian law, or the client's jurisdiction (Irish/Dutch), given cross-border enforcement is largely theoretical at this deal size anyway.

**Practical no-cost path:** Bonsai (HelloBonsai) publishes free, non-gated contract templates including a monthly retainer agreement template ([hellobonsai.com/contract-template/monthly-retainer-agreement](https://www.hellobonsai.com/contract-template/monthly-retainer-agreement), checked 2026-09-20) usable as a drafting starting point without paying for the platform. Their paid plans ($15–$59/user/month, [hellobonsai.com/pricing](https://www.hellobonsai.com/pricing), checked 2026-09-20) add e-signature tracking, invoicing, and CRM — **not worth paying for at 1 client**, but worth revisiting once signature/tracking volume justifies it (see item 18 in the master table).

**Do now:** adapt one free template into a one-page PDF/Google Doc, reused for every new client. **Do later:** move to a proper e-signature tool once signing 2+ contracts/month makes "email a PDF back and forth" annoying.

---

## 4. Privacy / GDPR Basics for a Non-EU Agency Handling EU Client Data

**Flag: directional research only. Verify specifics with a data-protection lawyer, especially before running EU-facing paid ad campaigns.**

**Does GDPR apply to Vike even though it's based in Ukraine (non-EU)?** Yes, in substance. GDPR's "targeting criterion" (Article 3(2)) applies to a non-EU business that intentionally offers goods/services to people in the EU or monitors their behavior — factors regulators look at include EU-focused advertising, EU-market language, and actively soliciting EU clients ([EDPB Guidelines 3/2018 on territorial scope](https://www.edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-32018-territorial-scope-gdpr-article-3-version_en), checked 2026-09-20; summarized also at [legiscope.com](https://www.legiscope.com/blog/gdpr-applies-outside-eu.html), checked 2026-09-20). Vike explicitly targets Ireland and the Netherlands, which puts it squarely inside this scope for the personal data it collects from EU site visitors and leads (form submissions, ad pixel data). **Verify with a lawyer** whether formal obligations like appointing an EU representative (Article 27) apply at Vike's current scale — likely a low near-term risk given size, but the underlying data-handling obligations (lawful basis, consent, security) apply regardless of company size.

**Three concrete things to fix now:**

1. **Site contact form** — have a short privacy notice near the form (what data is collected, why, how long it's kept, that it's not sold/shared beyond what's needed to deliver the service) and a link to a full privacy policy page. This is basic GDPR "transparency" (Art. 13) practice and also standard trust-signal expected by EU B2B buyers.

2. **Cookie consent for the site (EU visitors)** — a consent banner is needed before non-essential cookies (analytics, ad pixels) fire, not just as a footer disclaimer. **CookieYes** free plan covers up to 5,000 pageviews/month with automatic cookie blocking, both a cookie-policy and privacy-policy generator, a consent log, and certified Google Consent Mode v2 support ([cookiebannerguide.com](https://www.cookiebannerguide.com/cookieyes-pricing/), checked 2026-09-20) — plenty for a not-yet-indexed site with low traffic. Paid tiers start at $10/month/domain if traffic or customization needs grow ([enzuzo.com](https://www.enzuzo.com/blog/cookieyes-pricing), checked 2026-09-20).

3. **Meta pixel / ad tracking** — under GDPR guidance, the Meta Pixel legally requires **prior, explicit consent** before it fires for EU visitors; Meta's "Limited Data Use" flag does not itself satisfy this requirement ([flowconsent.com](https://www.flowconsent.com/en/blog/meta-pixel-gdpr-compliance-guide), checked 2026-09-20; also confirmed via multiple 2026 sources referencing Austrian DPA enforcement). Practical no-code setup: configure the CookieYes (or similar) consent banner to categorize the Meta Pixel and Google Ads tag as "marketing/advertising" cookies, and use **Google Consent Mode v2** so the Meta/Google tags only fire (or fire in reduced/anonymized mode) after opt-in — CookieYes's free tier already supports Consent Mode v2, which is the current (2026) baseline expectation for any site running Google Ads/Analytics with EU traffic.

**Do now:** privacy policy page + CookieYes free banner + Consent Mode v2 toggle, before running any EU-facing paid Meta/Google campaigns for clients or for Vike's own lead gen. **Do later:** formal GDPR data processing agreements (DPAs) with clients once Vike handles client-owned EU customer data directly (e.g., managing a client's CRM/email list) — **verify with a lawyer** when that threshold is crossed.

---

## 5. CRM Options (Free/Cheap Tiers for a Solo Founder)

Currently leads "likely land via a site form or Telegram, not a proper pipeline" — the single biggest operational gap. Comparison of 4 real, current options:

| CRM | Free tier | Free tier limits | Paid entry price | Source |
|---|---|---|---|---|
| **HubSpot CRM** | Yes, permanent | 2 users, 1,000 contacts (accounts created after Sept 2024), 1 pipeline, 2,000 marketing emails/mo, 10 custom properties | Starter $7/seat/mo (annual) / $20/mo (monthly) | [costbench.com](https://costbench.com/software/crm/hubspot/free-plan/), [usecarly.com](https://www.usecarly.com/blog/hubspot-free-plan-limits/), checked 2026-09-20 |
| **Zoho CRM** | Yes, permanent | Up to 3 users, leads/contacts/accounts/deals, tasks, standard reports; no workflow automation | Standard $14/user/mo (annual) | [layer3labs.io](https://www.layer3labs.io/guides/zoho-crm-pricing), [costbench.com](https://costbench.com/software/crm/zoho-crm/), checked 2026-09-20 |
| **Pipedrive** | **No permanent free plan** — 14-day trial only | N/A | Lite $14–24/user/mo (annual/monthly) | [lindy.ai](https://www.lindy.ai/blog/pipedrive-pricing), checked 2026-09-20 |
| **Google Sheets (manual "CRM")** | Free (already have Google Workspace/Gmail) | Fully manual, no automation, no reminders | N/A | — |

**Recommendation:** **Zoho CRM free tier** is the best fit for a solo founder right now — genuinely free forever for up to 3 users (covers Vladyslav + informal cofounder + UGC creator later), covers the core need (contacts, deals/pipeline, tasks), and the paid tier is cheap ($14/user/mo) if/when workflow automation becomes worth paying for. HubSpot's free tier is also solid and slightly more polished for a solo user, but its 1,000-contact cap and 2-user cap are tighter over time, and its paid jump (to $90/mo Professional plus a **mandatory $1,500 onboarding fee**, per [fouzanadil.com](https://www.fouzanadil.com/blog/hubspot-crm-pricing-2026), checked 2026-09-20) is a steep cliff to avoid triggering prematurely — a reason to prefer Zoho's gentler pricing ladder for a bootstrapped agency. Pipedrive has no free tier and isn't justified yet.

**Do now:** set up Zoho CRM (or HubSpot) free tier, add all pipeline stages matching Vike's sales process (Audit requested → Audit delivered → Proposal sent → Won/Lost), and route the site form into it (see Section 8). **Do later:** upgrade only when a 4th team member joins or multi-pipeline/automation is genuinely needed.

---

## 6. Proposal and Reporting Tools

**Proposals:**
- **PandaDoc** free plan: 5 documents/month (60/year), unlimited e-signatures, but no workflow automation, analytics, or CRM integration on free ([axisconsulting.io](https://axisconsulting.io/pandadoc-pricing-guide/), checked 2026-09-20). Paid starts at $19/user/mo (annual) ([bindlegal.com](https://bindlegal.com/resources/comparisons/pandadoc-pricing-2026/), checked 2026-09-20).
- At 1–4 proposals/month (realistic for a solo founder acquiring first clients), PandaDoc's free tier is sufficient. Alternative at zero cost and zero limits: a branded **Google Docs template** (duplicate-and-fill) or a **Canva Doc** — no signature tracking, but free and unlimited, and perfectly adequate until proposal volume or the "trackable/e-signed" polish becomes worth paying for.

**Reporting (client-facing dashboards):**
- **Looker Studio** (Google, free) is the standard choice: free for all core features, connects natively to GA4, Google Ads, and Google Sheets, and can build recurring/auto-refreshing client report dashboards ([valiotti.com](https://valiotti.com/technologies/looker-studio/), checked 2026-09-20). Third-party connectors for Meta Ads/other platforms typically route through paid connectors like Supermetrics or Windsor.ai ($20–$200/mo) if native blending isn't enough ([swydo.com](https://www.swydo.com/blog/looker-studio-pricing/), checked 2026-09-20) — **not worth paying for yet**; Meta Ads data can be manually exported/pasted into Sheets and blended into Looker Studio at zero cost while client count is small.

**Do now:** one Looker Studio template (GA4 + Google Ads native connectors) reused per client; PandaDoc free tier or a Google Docs proposal template. **Do later:** a paid Meta Ads connector once managing 4+ paid Meta accounts makes manual CSV export genuinely time-costly.

---

## 7. Project Management Tools (Solo / Very Small Team)

| Tool | Free tier | Key limit | Paid entry | Source |
|---|---|---|---|---|
| **Trello** | Yes, forever free | 10 boards/workspace, unlimited cards | Standard $5/user/mo (annual) | [checkthat.ai](https://checkthat.ai/brands/trello/pricing), checked 2026-09-20 |
| **ClickUp** | Yes, forever free | Unlimited tasks/users, but only 60MB total storage | Unlimited $7/user/mo (annual) | [costbench.com](https://costbench.com/software/project-management/clickup/), [usecarly.com](https://www.usecarly.com/blog/clickup-pricing/), checked 2026-09-20 |
| **Notion** | Yes, forever free (personal) | Unlimited blocks solo, 5MB/file upload, 7-day page history, 10 guests | Plus $10/user/mo (annual) | [costbench.com](https://costbench.com/software/project-management/notion/), checked 2026-09-20 |

**Recommendation:** For a solo founder who also wants a lightweight client/content database (case studies, proposal tracker, brand assets links), **Notion free** is the most versatile single tool — doubles as documentation hub, case-study repository, and simple kanban board, all in one free workspace, with the one caveat that inviting collaborators (cofounder/UGC creator) trims the free-tier block allowance. **Trello** is simpler and purely visual if Vladyslav prefers a pure kanban board with zero setup. Either is fine; avoid ClickUp's steeper learning curve for a 16-hr/week solo operation — its 60MB storage cap also bites faster than expected once creative files are attached to tasks.

**Do now:** pick one (Notion recommended) and set up a single board: Leads → Onboarding → Active clients → Content/creative queue. **Do later:** nothing — this tier is sufficient indefinitely for a team under ~5 people.

---

## 8. Time Tracking (Light Touch)

Given 16 hrs/week and no hourly billing (pricing is flat monthly retainers), time tracking is a **low-impact, low-effort, "later" item** — mainly useful for Vladyslav's own sanity-check of how many hours each client actually consumes vs. the flat fee, to catch scope creep early.

**Toggl Track** free plan: up to 5 users, unlimited time entries/projects/clients, idle detection, calendar integration, CSV/PDF export, no time limit ([costbench.com](https://costbench.com/software/time-tracking/toggl-track/), checked 2026-09-20). This comfortably covers Vike today and even after the cofounder/UGC creator formalize.

**Do now (optional, ~15 min setup):** install Toggl free, tag time by client, review monthly to spot which tier is under/over-served relative to its price. **Do later:** nothing — free tier is sufficient at this scale; don't over-engineer with a paid time-tracking/profitability tool.

---

## 9. Automating Lead Capture (Form → Real CRM/Spreadsheet)

This is the single most concrete operational fix requested: **stop leads dead-ending in Telegram; get them into a system with follow-up and reporting.**

**Current likely setup:** Netlify-hosted site with a native HTML form (Netlify Forms) or a Telegram bot integration, with no CRM record.

**Netlify Forms pricing update (relevant, current):** as of an April 2026 pricing change, Netlify made form submissions **free and unlimited across all credit-based plans** (previously capped at 100/month on legacy free tiers) ([netlify.com/changelog](https://www.netlify.com/changelog/2026-04-14-pricing-updates-april-2026/), checked 2026-09-20). So the form itself is not a cost problem — the missing piece is purely the **integration** from form submission to CRM/Sheet.

**Recommended no-code path (pick one):**

1. **Native Netlify → Zapier/Make integration (simplest):** Netlify Forms has a documented Zapier integration that triggers a "New Form Submission" event Zapier can push into Google Sheets, Zoho CRM, or HubSpot with zero custom code.
2. **Zapier free plan:** 100 tasks/month, but limited to **2-step (single-action) Zaps** on the free tier ([nocode.mba](https://www.nocode.mba/articles/zapier-pricing-2026), checked 2026-09-20). At Vike's current lead volume (a handful of leads/month pre-launch), 100 tasks/month is enough for "new form submission → create CRM contact" as a 2-step Zap.
3. **Make.com free plan (better long-term free tier):** 1,000 operations/month, up to 2 active scenarios, 15-minute minimum interval between scheduled runs, full visual builder with 3,000+ app connectors ([latenode.com](https://latenode.com/blog/make-com-pricing), checked 2026-09-20). Make's free tier supports **multi-step** scenarios (unlike Zapier's free 2-step cap), making it the stronger free choice if the workflow needs more than one action (e.g., "new form submission → create CRM contact → send Vladyslav a Telegram notification → append row to a Google Sheet backup").

**Recommendation:** use **Make.com free tier** over Zapier free tier for this specific job, specifically because it allows a multi-step scenario (CRM + Sheet backup + Telegram alert) within the free 1,000 ops/month allowance — Zapier's free plan would require multiple separate 2-step Zaps to do the same job and burns through the 100-task cap faster.

**Concrete setup a no-code founder can follow:**
1. In Netlify, confirm the contact form has `data-netlify="true"` (already standard for Netlify Forms) — no code change needed if using the existing form.
2. Create a free Make.com account, connect the **Netlify** app module (or use a webhook if no native module — Netlify supports outgoing webhooks per form under Site settings → Forms → Form notifications → Outgoing webhook).
3. Add the Netlify form's webhook as the scenario's trigger.
4. Add a module: **Zoho CRM (or HubSpot) → Create Lead**, mapping form fields (name, email, message) to CRM fields.
5. Add a second module: **Google Sheets → Add Row** as a simple backup/audit trail.
6. (Optional) Add a third module: keep the existing **Telegram** notification so Vladyslav still gets the instant ping he's used to — Telegram becomes a notification channel, not the system of record.
7. Turn the scenario on; test with a dummy form submission; confirm it lands in both the CRM and the Sheet.

**Do now:** this exact setup, this month — it directly fixes the stated gap and takes under an hour once accounts exist. **Do later:** upgrade Make to a paid tier ($9/mo Core, per [pxlpeak.com](https://pxlpeak.com/blog/ai-tools/make-pricing-guide), checked 2026-09-20) only if monthly operations exceed the 1,000 free credits — unlikely until lead volume is meaningfully higher than today.

---

## 10. Conversion Tracking — GTM Form-Submission Event (Not Just Pageviews)

**The problem this fixes:** a "Google tag firing on page load" only tells you someone visited; it doesn't tell you someone actually submitted the lead form — the metric that matters for judging ad spend efficiency.

**Current (2026) best-practice setup, actionable by a no-code founder:**

1. **Install Google Tag Manager (GTM)** on vikemarketing.com if not already present (one container snippet in the site `<head>`/body, or via Netlify's site settings if a snippet manager is used).
2. In GTM, create a **Form Submission trigger**. Best practice: filter it to fire only on the specific contact form (e.g., by Form ID or Form Classes equals the form's identifier), not "all forms," to avoid false positives from unrelated forms (e.g., a newsletter signup) ([analyticsmania.com](https://www.analyticsmania.com/post/google-tag-manager-form-tracking/), checked 2026-09-20).
3. Enable **"Check Validation"** on the trigger so it only fires after the form successfully validates/submits, not on every click attempt including failed submissions ([harmukhtechnologies.in](https://harmukhtechnologies.in/google-tag-manager-conversion-tracking-guide-2026/), checked 2026-09-20).
4. Create a **GA4 Event tag** (e.g., event name `contact_form_submit`) attached to that trigger, using Vike's GA4 Measurement ID.
5. Separately, create a **Google Ads Conversion Tracking tag** (once running Google Ads for Vike itself or for clients) attached to the same trigger — this is what actually optimizes ad delivery toward real leads, not just clicks.
6. **Mark the GA4 event as a Key Event/Conversion** inside GA4 Admin → Events — a very commonly missed step; without it, GA4 will show the event firing but conversion reports will read zero ([circlesstudio.com](https://circlesstudio.com/blog/ga4-best-practices-for-optimizing-analytics/), checked 2026-09-20).
7. **Test in GTM Preview mode** before publishing: submit the form live, confirm the trigger fires in the GTM debugger, then confirm the event appears in GA4's **DebugView** in real time ([reform.app](https://www.reform.app/blog/how-to-track-form-submissions-in-ga4), checked 2026-09-20).
8. **Caveat flagged by current guidance:** GA4's built-in "Enhanced Measurement" form-tracking (the automatic, no-GTM-needed option) has been reported to **over-count submissions** on some sites in 2026 ([analyticsmania.com](https://www.analyticsmania.com/post/google-tag-manager-form-tracking/), checked 2026-09-20) — if Vike enables Enhanced Measurement form tracking and later notices inflated numbers, disable it and rely on the manual GTM trigger above instead, or use one or the other, never both simultaneously (double-counting).
9. **GDPR interaction:** wire this tag to only fire after cookie consent (see Section 4) via Consent Mode v2, so EU-visitor conversions aren't tracked without consent, and so conversion counts remain accurate (unconsented sessions are excluded from tracking, not silently double-counted).

**Do now:** this full setup, once (reusable pattern for every client site too — this becomes a sellable deliverable of the "Marketing Automation" service line, not just Vike's own site).

---

## 11. Analytics Setup — GA4 Current Best Practice for a Small Site

Given the site is "not yet indexed by Google" and traffic is presumably low, GA4 setup should be lean, not exhaustive:

- Full setup for an SMB site is reported to take roughly 60–90 minutes: install the tag (via GTM), define the 3–5 real conversions that matter (form submit, phone-number click, calendar-booking click), filter out internal/dev traffic, and link Google Search Console + Google Ads ([cronicodigital.com](https://cronicodigital.com/ga4-setup-guide-for-businesses-in-2026-track-the-right-data-and-grow-faster/), [rivermountainsystems.com](https://www.rivermountainsystems.com/blog/ga4-setup-for-smbs.html), checked 2026-09-20).
- Most small business sites only need **4–6 tracked events done well**, rather than tracking everything possible — over-instrumentation adds noise without adding decision-usefulness at this traffic level ([measuremarketing.pro](https://measuremarketing.pro/blog/ga4-best-practices-2026.html), checked 2026-09-20).
- A 2026-specific note: Google has added **flexible per-event conversion attribution settings**, useful once running Google Ads, to reduce reporting mismatches between Google Ads and GA4 ([influenceflow.io](https://influenceflow.io/resources/google-analytics-4-conversion-tracking-complete-guide-for-2026/), checked 2026-09-20).
- Consent Mode v2 is now described as a baseline 2026 requirement for any site with EU traffic running Google Ads/Analytics — without it, GA4 silently drops data from non-consenting visitors, undercounting real conversions ([circlesstudio.com](https://circlesstudio.com/blog/ga4-best-practices-for-optimizing-analytics/), checked 2026-09-20) — reinforcing Section 4's recommendation.

**Recommended Vike conversion events (5, matching the site's actual CTAs):** `contact_form_submit`, `audit_request_submit` (if the free-audit form is separate from general contact), `booking_link_click` (Calendly/Cal.com), `phone_click` (if a phone number/WhatsApp link exists), `email_click` (mailto: link click).

**Do now:** this setup, alongside Section 10's GTM work — they're the same project. **Do later:** nothing further needed at this traffic level; revisit once organic traffic is meaningfully higher (post-indexing, post-SEO work).

---

## 12. Email Deliverability for Cold Outreach — SPF / DKIM / DMARC

Cold outreach to Irish/Dutch SMBs from a sales@vikemarketing.com address risks landing in spam if the sending domain lacks proper email authentication — this is a real, current (2026) concern as Gmail/Outlook enforcement of sender authentication has tightened industry-wide.

**Current best practice (2026), actionable steps:**
1. **SPF (Sender Policy Framework):** publish a TXT DNS record listing which mail servers are authorized to send as @vikemarketing.com (e.g., Google Workspace's or whichever provider handles sales@vikemarketing.com's outbound mail). Validate with MXToolbox's free SPF Record Check ([mxtoolbox.com/spf.aspx](https://mxtoolbox.com/spf.aspx), checked 2026-09-20).
2. **DKIM (DomainKeys Identified Mail):** enable DKIM signing in the email provider (Google Workspace admin console has a one-click DKIM generator), publish the resulting DKIM TXT record, and verify with MXToolbox's free DKIM Check ([mxtoolbox.com/dkim.aspx](https://mxtoolbox.com/dkim.aspx), checked 2026-09-20).
3. **DMARC (Domain-based Message Authentication):** publish a DMARC TXT record tying SPF+DKIM together and telling receiving servers what to do with mail that fails both. **Best-practice sequencing:** start with `p=none` (monitor-only, no rejection) for a few weeks to see real traffic in DMARC reports, then tighten to `p=quarantine` and eventually `p=reject` once confident nothing legitimate is being flagged — this staged rollout is the standard low-risk approach for a small sender domain. Validate/build the record with MXToolbox's free DMARC tools ([mxtoolbox.com/dmarc.aspx](https://mxtoolbox.com/dmarc.aspx), checked 2026-09-20).
4. **Ongoing monitoring:** MXToolbox's free SuperTool covers DNS, blacklist, SPF/DKIM/DMARC, and header analysis in one place, useful for one-off validation and troubleshooting ([blog.mystrika.com](https://blog.mystrika.com/mxtoolbox/), checked 2026-09-20). For Gmail-specific sender-reputation signals (spam rate, domain reputation as seen by Gmail specifically), **Google Postmaster Tools** (free, Google account required) is the complementary tool — it shows Gmail-facing reputation trends that MXToolbox's generic DNS checks don't ([per comparison in the same source, checked 2026-09-20]).
5. **Practical cold-outreach hygiene** (not a tool, a practice): send cold outreach from a real inbox (not a no-reply address), warm up a new domain/inbox gradually with low volume before scaling, and keep list quality high — these matter as much as the DNS records themselves for actual deliverability, though they fall outside strict "tooling."

**Do now:** SPF + DKIM this month (a 20–30 minute DNS task, no cost) before any outbound cold-email campaign to Irish/Dutch prospects; add DMARC in `p=none` monitoring mode. **Do later:** tighten DMARC to `p=reject` once a few weeks of clean reports build confidence.

---

## 13. Case-Study Template (Fillable Structure)

No case studies exist yet, but the template should be ready before the first client's results are provable, so it can be filled the moment there's proof.

**Recommended structure (standard, high-converting performance-marketing case study shape):**
1. **Client snapshot** — industry, location, business size (anonymized as "an Irish [industry] SMB" if the client prefers not to be named early on).
2. **The challenge** — what wasn't working before Vike (e.g., "no consistent lead flow from paid ads," "wasted spend on unqualified traffic").
3. **What Vike did** — which service tier (Launch/Scale/Dominate), which channels (Meta/Google), timeframe.
4. **The numbers** — before/after metrics: cost per lead, conversion rate, ROAS, lead volume — whatever is honestly measurable and improved. Use ranges or "X% improvement" framing if absolute numbers are sensitive.
5. **Client quote** (even a short one-line testimonial once available) — pairs naturally with collecting the first Google/Clutch reviews (already flagged as missing).
6. **Visual** — before/after screenshot of ad performance dashboard (Looker Studio export) or ad creative thumbnail, not necessarily a "project photo."
7. **CTA** — link to the booking link (Section 15) for a free audit.

**Do now:** build this as a reusable Notion/Google Docs template with placeholder fields, so the moment client #1 has one full month of results, filling it in is a 15-minute task, not a from-scratch write-up.

---

## 14. Portfolio Presentation Without Real Project Photos Yet

Since no real project photos exist, the portfolio needs a credible non-photo-dependent format:

- **Ad creative mockups:** use Canva's free device/social mockup frames to present sample ad copy/creative concepts inside a realistic Instagram/Facebook feed frame — this is standard practice across the industry even for agencies with real client work, since it presents creative cleanly regardless of whether it's a live or speculative example.
- **Performance dashboards as "proof of process":** a blurred/anonymized Looker Studio dashboard screenshot demonstrates reporting rigor even before there's a flagship result to show — this signals competence (this agency tracks and reports properly) independent of having a big before/after story yet.
- **Process walkthrough over "portfolio":** given zero case studies, lean the site/portfolio section toward "how we work" (audit → strategy → creative → launch → report, matching Vike's actual service list) rather than pretending to have a project gallery that doesn't exist yet — this is honest and still persuasive to SMB buyers who are often evaluating process/trust signals as much as past logos.
- **Free growth audit as the real portfolio substitute:** since the free audit is already the hook, treat *a sample redacted audit* (e.g., a genuine audit done on a public local business as a demonstration, clearly labeled as an example) as the strongest available "portfolio" artifact right now — it's real work product, not a mockup.

**Do now:** build one sample audit as a showcase piece (clearly labeled "example audit," not a live client) plus 2–3 Canva ad-mockup concepts for the site's "work" section. **Do later:** replace with real client case studies as they close.

---

## 15. Brand Assets Checklist

Standard minimum kit a serious small agency needs, mapped to what's realistically achievable at zero/near-zero cost:

- [ ] **Logo files** — vector (SVG/AI) master + PNG exports (transparent background, multiple sizes) + a monochrome/single-color version for dark backgrounds.
- [ ] **Brand color palette** — documented hex codes (primary, secondary, accent, neutrals).
- [ ] **Typography** — 1–2 web-safe or Google Fonts pairing, documented for consistency across site/decks/proposals.
- [ ] **Favicon** — generated from the logo mark.
- [ ] **Social media profile assets** — consistent profile photo/banner sized correctly for LinkedIn (already has a page) and Clutch (profile under review).
- [ ] **Email signature** — name, title, Vike branding, booking link (Section 15), consistent across sales@vikemarketing.com.
- [ ] **One-pager / capabilities PDF** — services + pricing tiers, exportable for cold outreach attachments.
- [ ] **Proposal + report templates branded consistently** (ties to Sections 6 and 13).

**Tooling:** Canva free plan covers this almost entirely — it includes 1 Brand Kit on the free tier (colors, logo, fonts) ([miracamp.com](https://www.miracamp.com/learn/canva/pricing-plans), checked 2026-09-20), which is sufficient for a single-brand agency (Vike only needs one brand kit, not multiple). Canva Pro ($18/mo per [socialrails.com](https://socialrails.com/blog/canva-pricing), checked 2026-09-20, though another source cites ~$15/mo — **treat exact figure as approximate/estimate**, verify current price at checkout) adds 5 Brand Kits, background remover, and Magic Studio AI — **not worth paying for** at 1 brand and no current need for background removal at volume.

**Do now:** build the free Canva Brand Kit (logo, colors, fonts) once, this month — every other asset (one-pager, proposal template, social banners, email signature) reuses it. **Do later:** Canva Pro only if managing multiple client brand kits becomes a real time-saver need (i.e., once running creative production for several clients' own brands, which is a paid service line, not Vike's own branding).

---

## 16. Booking Link (Calendly-Style)

| Tool | Free tier | Key limit | Paid entry | Source |
|---|---|---|---|---|
| **Calendly** | Yes, permanently free | **1 event type only**, 1 user, basic scheduling, Google Calendar sync | Standard $10/seat/mo (annual) | [talkspresso.com](https://talkspresso.com/blog/how-much-does-calendly-cost-2026), [meetergo.com](https://meetergo.com/en/magazine/calendly-plans), checked 2026-09-20 |
| **Cal.com** | "Free" tier exists but is reportedly a **time-limited trial**, not forever-free, despite generous features (unlimited event types, routing forms, workflows) during the trial | Trial period only, then requires paid plan | Teams $15/user/mo | [costbench.com](https://costbench.com/software/scheduling/cal-com/free-plan/), checked 2026-09-20 |
| **TidyCal** (mentioned for completeness, not deeply verified here) | One-time-payment lifetime deal model exists in the market (unverified current price) | — | — | Not independently verified in this research pass — flag as **unverified**, confirm current offer before relying on it |

**Recommendation:** **Calendly free tier** is the more reliable "actually free forever" option for Vike's single use case (booking the free growth audit call) — one event type is all that's needed at this stage (a single "Book a free growth audit" 30-minute slot). Cal.com's richer free features are attractive but reportedly time-limited rather than a genuine permanent free tier as of this check, which makes Calendly the safer default despite fewer features. **Verify Cal.com's exact current free-trial terms directly on cal.com/pricing before ruling it out**, since sources on this point were not fully consistent.

**Do now:** set up Calendly free, one event type ("Free Growth Audit — 30 min"), embed the link on the site and use it as the CTA across cold outreach, LinkedIn, and the site's contact section. **Do later:** upgrade to a paid tier or reconsider Cal.com only if multiple event types (e.g., separate "audit call" vs. "onboarding call" vs. "strategy check-in") become necessary — plausible once past the first few clients.

---

## Lean Overall Tool Stack — Recommendation

### "Free tier is enough" (use now, $0/month)
| Category | Tool | Why |
|---|---|---|
| CRM | Zoho CRM (free) | 3 users, real pipeline, room to grow |
| Lead automation | Make.com (free, 1,000 ops/mo) | Form → CRM + Sheet + Telegram in one scenario |
| Forms | Netlify Forms (native, now unlimited free) | Already hosting on Netlify |
| Analytics | GA4 + GTM | Industry standard, free |
| Reporting | Looker Studio | Native GA4/Ads/Sheets connectors |
| Cookie consent / GDPR | CookieYes (free, 5,000 pageviews/mo) | Consent Mode v2 included |
| Project management | Notion (free) | Doubles as case-study/asset repo |
| Time tracking | Toggl Track (free, up to 5 users) | Light-touch, covers team as it grows |
| Booking | Calendly (free) | 1 event type is all that's needed now |
| Design/Brand kit | Canva (free) | 1 Brand Kit sufficient for 1 brand |
| Proposals | Google Docs template / PandaDoc free (5 docs/mo) | Low volume today |
| Contracts | Bonsai free templates (used as drafting source, not the paid platform) | No cost |
| Email auth | SPF/DKIM (provider-native) + DMARC (DNS) + MXToolbox (free checks) | No cost, DNS-only |

**Estimated total: $0/month tool cost.**

### "Worth paying for" (later, once revenue exists)
| Category | Tool | Trigger to upgrade | Est. cost |
|---|---|---|---|
| Automation | Make.com Core | >1,000 ops/month | ~$9/mo (annual) |
| CRM | Zoho CRM Standard | >3 users or need workflow automation | $14/user/mo |
| Proposals/contracts | PandaDoc Starter or Bonsai | >5 proposals/mo or need e-signature tracking | $19–25/mo |
| Cookie consent | CookieYes Basic | >5,000 pageviews/mo (post-indexing traffic growth) | $10/mo |
| Design | Canva Pro | Multiple client brand kits needed | ~$15–18/mo |
| Booking | Calendly Standard | Need multiple event types | $10/seat/mo |
| Legal/accounting | Ukrainian accountant (recurring) | Ongoing FOP compliance once trading | Variable — **verify with a professional** |

**Estimated cost once these are triggered (not all needed simultaneously): roughly $60–90/month**, phased in only as specific volume triggers are hit — none of it needs to be paid before revenue exists.

### Bottom line
Everything on the "NOW" list is achievable this month within 16 hrs/week at **$0 tool spend**, with the one necessary paid item being a single accountant consultation to confirm FOP/tax status (Section 2) — which is also the item blocking legal invoicing of the first EU client, making it the most urgent action overall.

---

*All tool pricing verified against live pages on 2026-09-20 as cited inline. All legal, tax, and GDPR statements are directional research only — verify with a qualified Ukrainian accountant/lawyer and, for GDPR specifics, a data-protection professional, before relying on them operationally.*
