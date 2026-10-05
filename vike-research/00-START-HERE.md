# Vike Marketing — Growth Research: Start Here

**Prepared:** 2026-09-20/21 · **Founder capacity:** ~16 hrs/week (solo) · **Current stage:** pre-first-client, all core assets in place, zero public reviews

---

## Executive Summary

Vike Marketing has real, honest assets: three true client outcomes (Junior School preschool in Lviv got leads within a month; Mary, an author in Israel, sold out her first book batch in 60 days; Alex, a construction startup in Kyiv, got ongoing social media management), three clean no-contract price points ($200/$400/$750) that undercut most Western agency minimums, a live Google Business Profile, a Clutch profile in review, a LinkedIn page, and a founder with strong ads/communication skills and 16 structured hours a week.

The research across all six tasks converges on the same core diagnosis: **Vike's single biggest weakness, repeated in the competitor research, the first-client plan, and the workflow audit alike, is zero public social proof** — no Google reviews, no Clutch reviews, an unindexed site. Every competitor profiled, even the smallest solo operators, has some third-party review presence. Closing that gap is the highest-leverage, lowest-cost move available right now, and it doesn't require new clients — it requires asking the three clients already won.

Second theme: **paid ads are correctly on hold.** The prepared Google Ads campaign (Ireland + Netherlands) should stay paused until conversion tracking actually works (a GTM form-submission event, not just pageviews) — otherwise spend is unmeasurable. Free/cheap organic and direct outreach are the right first-90-day channels, not ads.

Third theme: **local Ukraine niches (preschools, dental clinics) are the realistic near-term wedge**, not Ireland/Netherlands — despite Ireland/NL being the larger long-term prize (Irish SMEs spend €600–3,000/mo on digital marketing on average, well above Vike's $750 ceiling). Local prospects get a same-category case study (Junior School), a shared language, and in-person meetings — advantages no foreign competitor can match. Ireland/NL should run as a slower-burning parallel channel from week 3 onward, converting better once local case studies exist.

Fourth theme: a handful of **quiet operational blockers** need clearing before any of this scales cleanly — SSL status on vikemarketing.com, the Google Business Profile address (a business centre Vike doesn't actually occupy — should be hidden in favor of a service area), FOP/tax registration status (needed to legally invoice EU clients), and the site form still routing to Telegram instead of a real CRM.

None of this requires spending money. Nearly everything on the "do now" list across every file is free or near-free — the real cost is founder hours plus one paid accountant consultation.

---

## Top 10 Highest-Impact Actions This Week

1. **Ask Junior School, Mary, and Alex for a Google review and a Clutch review.** This is the single most-repeated finding across the research (competitor gap analysis + first-client plan): every comparable agency has reviews, Vike has none. Use the review-request template in `03-templates.md`. Zero cost, highest leverage available.
2. **Re-verify the SSL certificate on vikemarketing.com** (Netlify → Domain management → HTTPS). A 5-minute check that blocks trust and conversions if broken. (`05-workflow-and-essentials.md` §16)
3. **Hide the Google Business Profile's business-centre street address and finalize the service-area setup.** A misleading address risks suspension; this was already identified as unresolved from prior work.
4. **Book one paid consultation with a Ukrainian accountant to confirm FOP (sole proprietor) status and Group 3 tax registration.** This blocks legally invoicing EU clients and is the one item on the entire audit worth spending money on now. (`05-workflow-and-essentials.md` §2)
5. **Connect the site contact form to a real CRM or spreadsheet — stop relying on Telegram alone.** Free with Netlify Forms + Zapier/Make free tier or a native integration. (`05-workflow-and-essentials.md` §9)
6. **Set up GTM form-submission conversion tracking + a correctly configured GA4 property**, before any future ad spend (Google Ads stays paused until this exists). (`05-workflow-and-essentials.md` §10–11)
7. **Finish the Clutch profile, confirm The Manifest auto-syncs, optimize the LinkedIn Company Page, and submit to GoodFirms.** These are the four Priority-1 listing actions already in motion or free to complete this week. (`01-listing-platforms.md`, Priority 1 section)
8. **Set up SPF/DKIM/DMARC on the sending domain now**, so cold email to Ireland/Netherlands prospects can start warmed-up in week 3 rather than landing in spam. (`05-workflow-and-essentials.md` §12, `04-first-client-plan.md` §2.1)
9. **Start ICP #1 outreach: Lviv preschools and child development centers.** Google Maps prospecting + Instagram DM + in-person visits, leading with the Junior School case study — the single strongest sales sentence Vike has right now. (`04-first-client-plan.md` §1, §2.4)
10. **Submit vikemarketing.com to Google Search Console and request indexing.** The site currently returns zero results on `site:vikemarketing.com` — it isn't discoverable yet. (`06-growth-and-seo.md`, technical SEO checklist)

---

## All Research Files

| File | Contents |
|---|---|
| [`01-listing-platforms.md`](./01-listing-platforms.md) | 22 real, active 2026 platforms (directories, communities, marketplaces) ranked by priority, each with a filled-in Vike listing, signup steps, and ban/penalty risk flags. |
| [`01-copy-paste-texts.md`](./01-copy-paste-texts.md) | Every ready-to-paste listing text from file 01, collected in one place by platform. |
| [`02-competitors.md`](./02-competitors.md) | 13 real European agencies profiled (Ireland, Ukraine, Estonia, Netherlands, Germany, Poland, UK) — pricing, positioning, SEO/social signals, case-study format — plus a "what to copy / what to beat" summary. |
| [`03-client-lifecycle.md`](./03-client-lifecycle.md) | Best-practice client lifecycle: proposal → onboarding → kickoff → reporting → invoicing (Stripe/Wise/PayPal + VAT/reverse-charge basics for a Ukraine seller billing EU clients) → churn prevention → offboarding. Legal/tax points flagged "verify with a professional." |
| [`03-templates.md`](./03-templates.md) | Ready-to-use templates: welcome email, onboarding questionnaire, kickoff agenda, monthly report outline, invoice wording, review-request message, upsell messages — all adapted to Vike's three plans. |
| [`04-first-client-plan.md`](./04-first-client-plan.md) | Realistic 30/60/90-day plan for the first client and the first 10: ranked ICPs, channel-by-channel outreach playbook with templates, the free growth audit spec, pilot/case-study strategy, and a week-by-week KPI checklist. |
| [`05-workflow-and-essentials.md`](./05-workflow-and-essentials.md) | Operational gap audit: legal/FOP status, contracts, GDPR, CRM, conversion tracking, email deliverability, case-study template, and a lean $0/month tool stack ranked by impact × effort, now vs. later. |
| [`06-growth-and-seo.md`](./06-growth-and-seo.md) | Keyword research, page-by-page SEO recommendations, 3-month content calendar, local SEO, backlink plan, technical SEO checklist, the "Vike" brand-collision analysis, and a social media strategy with 12 ready post ideas. |
| [`06-roadmap-12-months.md`](./06-roadmap-12-months.md) | Quarter-by-quarter 12-month roadmap from first client to premium positioning, with honest milestones and a cross-quarter tracking table. |

---

## A Note on the "Vike" Name

Research confirmed a real brand collision: `vike.dev` (an active open-source Vite framework, ~25–31K weekly npm downloads) dominates bare "Vike" search results, alongside VIKE Beauty, Vike Bike, and a couple of spelling-adjacent marketing agencies (Vik SEO, VikoMarketing). Recommendation: never target the bare keyword "Vike" — always pair with "Marketing" and a geography qualifier, use Organization schema markup with `sameAs` links to LinkedIn/GBP/Clutch, and don't rename now (it would erase existing GBP/Clutch/testimonial equity). A formal EUIPO trademark search is still a separate open action, not covered here. Full detail in `06-growth-and-seo.md`.

---

## Everything Not Yet Verified

Every file marks unverified claims explicitly and cites real sources with URLs. Three categories need direct, hands-on follow-up before being relied on operationally:
- **Legal/tax specifics** (FOP status, VAT reverse-charge wording, Stripe/Wise/PayPal current Ukraine eligibility) — verify with a Ukrainian accountant.
- **Live technical SEO** — the actual vikemarketing.com site could not be fetched from this research environment (network egress was blocked to that domain); the SEO recommendations are current best practice pending a real on-site audit.
- **Search volumes/traffic estimates** — every keyword/traffic figure without a cited tool is explicitly marked "(estimate)."
