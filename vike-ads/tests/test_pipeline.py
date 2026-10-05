import re

import pytest

from conftest import FakeBackend, FakeChat, FakeWeb, good_variant, make_orch
from vike_ads.guardrails import NeedsConfirmation, enforce_identity
from vike_ads.images.prompts import build_prompt
from vike_ads.models import PLACEHOLDER_NAME, ImageSpec
from vike_ads.orchestrator import Intent, classify
from vike_ads.render import variant_md


def concepts_payload(*variants):
    return {"concepts": [{"name": "Worst review", "variants": list(variants)}]}


# ---------------------------------------------------------------- routing

@pytest.mark.parametrize("text,intent,subject", [
    ("research fake DM ads for agencies", Intent.RESEARCH, "fake DM ads for agencies"),
    ("Research 1-star review ads", Intent.RESEARCH, "1-star review ads"),
    ("give me an ad idea for dental clinics in Lviv", Intent.IDEA, "an ad idea for dental clinics in Lviv"),
    ("ad ideas for preschools", Intent.IDEA, "ad ideas for preschools"),
    ("generate the image for c-20260924-ab12-B", Intent.IMAGE, "c-20260924-ab12-B"),
    ("just generate the image for the dental one", Intent.IMAGE, "the dental one"),
    ("regenerate image", Intent.IMAGE, ""),
    ("hello", Intent.UNKNOWN, "hello"),
])
def test_classify(text, intent, subject):
    got_intent, got_subject = classify(text)
    assert got_intent is intent
    if intent is not Intent.IDEA:
        assert got_subject == subject


# ---------------------------------------------------------------- 4-part output

def test_idea_returns_exactly_four_parts(brand, store, consents):
    openai = FakeChat("openai", {"senior creative strategist": concepts_payload(
        good_variant("review_card"), good_variant("dashboard"), good_variant("dm_screenshot"))})
    orch = make_orch(brand, store, consents, openai=openai, web=FakeWeb())
    res = orch.handle("give me an ad idea for dental clinics in Lviv")
    assert res.kind == "concepts"
    c = res.concepts[0]
    assert [v.label for v in c.variants] == ["A", "B", "C"]
    for v in c.variants:
        md = variant_md(c, v)
        parts = re.findall(r"^\*\*(\d)\. ", md, flags=re.M)
        assert parts == ["1", "2", "3", "4"]
        assert "Primary text:" in md and "Headline:" in md and "Call to action:" in md
        assert v.image is not None and v.image.backend == "nano-banana"
    # description omitted when unused
    v = c.variants[0].model_copy(deep=True)
    v.meta.description = None
    assert "Description:" not in variant_md(c, v)
    assert any("illustrative" in n for n in res.notes)  # dashboard numbers flagged


def test_invalid_variant_is_repaired_then_accepted(brand, store, consents):
    bad = good_variant("review_card")
    bad["on_image_text"]["headline"] = "OUR WORST REVIEW (Archivo 800, centered)"
    bad["meta"]["cta"] = "Click Here"
    repaired = {"variant": good_variant("review_card")}
    openai = FakeChat("openai", {"senior creative strategist": concepts_payload(bad),
                                 "You fix ad concept JSON": repaired})
    orch = make_orch(brand, store, consents, openai=openai, web=FakeWeb())
    res = orch.idea("dentists", n_variants=1, render_images=False)
    v = res.concepts[0].variants[0]
    assert v.on_image_text.headline == "Our worst review is our best pitch"
    repair_prompt = [u for s, u in openai.calls if "You fix ad concept JSON" in s][0]
    assert "all-caps" in repair_prompt and "Meta CTA" in repair_prompt and "design instructions" in repair_prompt


def test_generic_audience_rejected(brand, store, consents):
    bad = good_variant()
    bad["audience"]["description"] = "Small business owners"
    openai = FakeChat("openai", {"senior creative strategist": concepts_payload(bad),
                                 "You fix ad concept JSON": {"variant": bad}})
    orch = make_orch(brand, store, consents, openai=openai, web=FakeWeb())
    with pytest.raises(RuntimeError):
        orch.idea("anything", n_variants=1, render_images=False)


# ---------------------------------------------------------------- image-only route

def test_image_only_reuses_stored_concept_without_llm(brand, store, consents):
    openai = FakeChat("openai", {"senior creative strategist": concepts_payload(good_variant("dm_screenshot"))})
    orch = make_orch(brand, store, consents, openai=openai, web=FakeWeb())
    c = orch.idea("dentists", n_variants=1, render_images=False).concepts[0]
    calls_before = len(openai.calls)
    backend = FakeBackend("nano-banana")
    orch.image_agent.router.backends = [backend]

    res = orch.handle(f"generate the image for {c.variants[0].id}")
    assert res.kind == "image"
    assert len(openai.calls) == calls_before  # no copywriting model involved
    assert "**1." not in res.markdown and "**4. Generated image**" in res.markdown
    assert "that would be us" in backend.prompts[0]  # agreed DM copy reused verbatim
    assert "Our worst review" not in backend.prompts[0]  # on-image headline is NOT baked in
    assert store.get_concept(c.id).variants[0].image is not None

    # fuzzy / "latest" references resolve to the same stored concept
    assert orch.handle("generate the image for the latest").kind == "image"


def test_image_for_unknown_concept_does_not_invent(brand, store, consents):
    orch = make_orch(brand, store, consents)
    res = orch.image("a brand new gym concept")
    assert res.kind == "error" and "No agreed concept" in res.markdown


def test_router_falls_back_to_fal(brand, store, consents):
    openai = FakeChat("openai", {"senior creative strategist": concepts_payload(good_variant())})
    primary, secondary = FakeBackend("nano-banana", ok=False), FakeBackend("fal")
    orch = make_orch(brand, store, consents, openai=openai, web=FakeWeb(), backends=[primary, secondary])
    c = orch.idea("dentists", n_variants=1).concepts[0]
    assert primary.prompts and c.variants[0].image.backend == "fal"


# ---------------------------------------------------------------- image prompt rules

@pytest.mark.parametrize("fmt", ["dashboard", "review_card", "dm_screenshot"])
def test_prompt_forbids_composited_ad(brand, fmt):
    spec = ImageSpec.model_validate({**good_variant(fmt)["image_spec"], "aspect_ratio": "4:3"})
    p = build_prompt(spec, brand)
    assert "Do NOT add any headline" in p
    assert "call-to-action button" in p
    assert "No gradient" in p
    assert "#F5F4FB" in p


# ---------------------------------------------------------------- guardrail

def test_model_supplied_names_and_faces_are_replaced(brand, store, consents):
    v = good_variant()
    v["image_spec"]["review"]["identity"] = {"display_name": "Sarah Kowalski", "avatar": "photoreal"}
    openai = FakeChat("openai", {"senior creative strategist": concepts_payload(v)})
    orch = make_orch(brand, store, consents, openai=openai, web=FakeWeb())
    backend = FakeBackend("nano-banana")
    orch.image_agent.router.backends = [backend]
    c = orch.idea("dentists", n_variants=1).concepts[0]
    ident = c.variants[0].image_spec.review.identity
    assert ident.display_name == PLACEHOLDER_NAME and ident.avatar == "silhouette"
    assert "Sarah" not in backend.prompts[0] and "silhouette" in backend.prompts[0]


def test_photoreal_request_asks_first_then_allows_after_consent(brand, store, consents):
    openai = FakeChat("openai", {"senior creative strategist": concepts_payload(good_variant())})
    orch = make_orch(brand, store, consents, openai=openai, web=FakeWeb())
    c = orch.idea("dentists", n_variants=1, render_images=False).concepts[0]
    vid = c.variants[0].id

    res = orch.image(vid, photoreal_name="Mary")
    assert res.kind == "question" and res.pending_name == "Mary" and "consent" in res.question
    assert store.get_concept(c.id).variants[0].image is None  # nothing generated

    consents.confirm("Mary", confirmed_by="test")
    res = orch.image(vid, photoreal_name="Mary")
    assert res.kind == "image"
    ident = store.get_concept(c.id).variants[0].image_spec.review.identity
    assert ident.display_name == "Mary" and ident.avatar == "photoreal" and ident.consent_ref


def test_guardrail_cannot_be_bypassed_by_spec(consents):
    spec = ImageSpec.model_validate({**good_variant()["image_spec"], "aspect_ratio": "4:3"})
    spec.review.identity.avatar = "photoreal"
    spec.review.identity.display_name = "Alex"
    out = enforce_identity(spec, consents)
    assert out.review.identity.display_name == PLACEHOLDER_NAME
    assert out.review.identity.avatar == "silhouette"
    with pytest.raises(NeedsConfirmation):
        enforce_identity(spec, consents, requested_photoreal_name="Alex")
    with pytest.raises(ValueError):
        consents.confirm("[Client Name]")


# ---------------------------------------------------------------- DeepSeek cross-checking

def test_deepseek_research_findings_need_second_source(brand, store, consents):
    synth = lambda findings: (lambda s, u: {"findings": findings})  # noqa: E731
    openai = FakeChat("openai", {
        "research analyst": synth([{"trend": "Lo-fi wins", "summary": "Lo-fi static ads are rising.",
                                    "source_ids": ["S1"], "formats": ["review_card"]}]),
        "strict fact-checker": lambda s, u: (
            {"supported": True, "note": "ok", "supporting_urls": ["https://example.com/trend"]}
            if "1-star" in u.split("EVIDENCE")[0] else {"supported": False, "note": "no evidence", "supporting_urls": []}),
    })
    deepseek = FakeChat("deepseek", {"research analyst": synth([
        {"trend": "1-star review ads", "summary": "1-star review ads are up.", "source_ids": ["S1"]},
        {"trend": "Made-up stat", "summary": "CTR triples with emoji.", "source_ids": ["S1"]},
        {"trend": "Hallucinated source", "summary": "x", "source_ids": ["S99"]},
    ])})
    orch = make_orch(brand, store, consents, openai=openai, deepseek=deepseek, web=FakeWeb())
    rep = orch.research("agencies").report
    by_trend = {f.trend: f for f in rep.findings}
    assert by_trend["Lo-fi wins"].verification == "sourced"
    assert by_trend["1-star review ads"].verification == "cross_checked"
    assert "Made-up stat" not in by_trend
    assert [f.trend for f in rep.unverified_leads] == ["Made-up stat"]
    assert "Hallucinated source" not in by_trend  # sourceless findings are dropped outright
    md = orch.research("agencies").markdown
    assert "Unverified leads (DeepSeek-only — NOT verified" in md


def test_unverified_leads_never_reach_ideation(brand, store, consents):
    from vike_ads.models import Finding, ResearchReport, Source
    rep = ResearchReport(id="r-1", topic="t", sources=[Source(id="S1", url="https://e.com")],
                         findings=[Finding(trend="Real trend", summary="s", source_ids=["S1"])],
                         unverified_leads=[Finding(trend="SECRET_UNVERIFIED", summary="s", verification="unverified")])
    store.save_report(rep)
    openai = FakeChat("openai", {"senior creative strategist": concepts_payload(good_variant())})
    orch = make_orch(brand, store, consents, openai=openai, web=FakeWeb())
    orch.idea("x", n_variants=1, render_images=False)
    prompt = openai.calls[0][1]
    assert "Real trend" in prompt and "SECRET_UNVERIFIED" not in prompt


def test_deepseek_variant_with_unverifiable_claim_is_dropped(brand, store, consents):
    ds_variant = good_variant("dm_screenshot")
    ds_variant["meta"]["primary_text"] = "Agencies using DMs see 312% more leads."
    openai = FakeChat("openai", {
        "senior creative strategist": concepts_payload(good_variant()),
        "List every factual": {"claims": ["Agencies using DMs see 312% more leads"]},
        "strict fact-checker": {"supported": False, "note": "no source", "supporting_urls": []},
        "You fix ad concept JSON": {"variant": ds_variant},  # repair fails to remove the claim
    })
    deepseek = FakeChat("deepseek", {"senior creative strategist": concepts_payload(ds_variant)})
    orch = make_orch(brand, store, consents, openai=openai, deepseek=deepseek, web=FakeWeb())
    c = orch.idea("x", n_variants=1, render_images=False).concepts[0]
    assert [v.origin for v in c.variants] == ["openai"]
    assert all("312%" not in v.meta.primary_text for v in c.variants)


def test_deepseek_cannot_judge_itself():
    from vike_ads.verification import CrossChecker
    with pytest.raises(ValueError):
        CrossChecker(FakeChat("deepseek", {}), None)
