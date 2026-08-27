from app.services import budget


def _reset_budget_module_state():
    """The alert tracker is module-level state (by design — see budget.py); tests
    need a clean slate so one test's alerts don't leak into the next."""
    budget._alerted_month_key = None
    budget._alerted_threshold_index = -1


def test_no_alert_below_first_threshold():
    _reset_budget_module_state()
    assert budget.check_threshold_alert("2026-08", used_fraction=0.5) is None


def test_alert_fires_once_when_crossing_80_percent():
    _reset_budget_module_state()
    assert budget.check_threshold_alert("2026-08", used_fraction=0.85) is not None
    # Same threshold, still under 100%: should not fire again
    assert budget.check_threshold_alert("2026-08", used_fraction=0.9) is None


def test_alert_fires_again_when_crossing_100_percent():
    _reset_budget_module_state()
    budget.check_threshold_alert("2026-08", used_fraction=0.85)  # crosses 80%
    alert = budget.check_threshold_alert("2026-08", used_fraction=1.05)  # crosses 100%
    assert alert is not None
    assert "over" in alert.lower()


def test_alert_state_resets_on_new_month():
    _reset_budget_module_state()
    budget.check_threshold_alert("2026-08", used_fraction=1.1)  # crosses both thresholds
    # New month: even a high fraction should fire fresh, not be suppressed by August's state
    alert = budget.check_threshold_alert("2026-09", used_fraction=0.85)
    assert alert is not None


def test_no_alert_if_fraction_never_reaches_threshold():
    _reset_budget_module_state()
    for frac in (0.1, 0.3, 0.5, 0.7, 0.79):
        assert budget.check_threshold_alert("2026-08", used_fraction=frac) is None
