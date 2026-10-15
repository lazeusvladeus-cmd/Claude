import datetime as dt

import pandas as pd

from desk.econ_calendar import events_for_day, feed_covers, get_events, load_manual, parse_feed, save_manual

NY = "America/New_York"

# Excerpt of the real ForexFactory weekly feed (week of 11 Oct 2026)
FEED = [
    {"title": "Bank Holiday", "country": "USD", "date": "2026-10-12T07:00:00-04:00", "impact": "Holiday", "forecast": "", "previous": ""},
    {"title": "Core CPI m/m", "country": "USD", "date": "2026-10-14T08:30:00-04:00", "impact": "High", "forecast": "0.2%", "previous": "0.3%"},
    {"title": "CPI m/m", "country": "USD", "date": "2026-10-14T08:30:00-04:00", "impact": "High", "forecast": "0.6%", "previous": "0.4%"},
    {"title": "CB Leading Index m/m", "country": "GBP", "date": "2026-10-14T09:30:00-04:00", "impact": "Low", "forecast": "", "previous": "-0.1%"},
    {"title": "Beige Book", "country": "USD", "date": "2026-10-14T14:00:00-04:00", "impact": "Low", "forecast": "", "previous": ""},
    {"title": "Employment Change", "country": "AUD", "date": "2026-10-14T20:30:00-04:00", "impact": "High", "forecast": "19.6K", "previous": "39.5K"},
    {"title": "Retail Sales m/m", "country": "USD", "date": "2026-10-15T08:30:00-04:00", "impact": "High", "forecast": "0.3%", "previous": "1.2%"},
]


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code = status
        self.payload = payload

    def json(self):
        if isinstance(self.payload, str):
            raise ValueError("not json")
        return self.payload


def test_usd_high_impact_grouped_by_time():
    feed = parse_feed(FEED, NY)
    table, problems = events_for_day(feed, load_manual("missing.csv"), dt.date(2026, 10, 14), NY)
    assert problems == []
    assert len(table) == 1  # AUD (other country) and low-impact events filtered out
    row = table.iloc[0]
    assert row["time"] == pd.Timestamp("2026-10-14 08:30", tz=NY)
    assert row["events"] == "Core CPI m/m · CPI m/m"
    assert "forecast 0.6%" in row["details"] and row["impact"] == "High"


def test_holidays_always_show_and_medium_is_optional():
    feed = parse_feed(FEED, NY)
    table, _ = events_for_day(feed, load_manual("missing.csv"), dt.date(2026, 10, 12), NY)
    assert table.iloc[0]["all_day"] and "Bank Holiday" in table.iloc[0]["events"]
    table, _ = events_for_day(feed, load_manual("missing.csv"), dt.date(2026, 10, 14), NY, impacts=("High", "Low"))
    assert "Beige Book" in " ".join(table["events"])


def test_feed_week_coverage():
    feed = parse_feed(FEED, NY)
    assert feed_covers(feed, dt.date(2026, 10, 11))  # Sunday starts the ForexFactory week
    assert feed_covers(feed, dt.date(2026, 10, 17))
    assert not feed_covers(feed, dt.date(2026, 10, 19))


def test_manual_events_merge_and_validate(tmp_path):
    csv = tmp_path / "manual.csv"
    manual = pd.DataFrame(
        [
            {"date": "2026-10-14", "time_ny": "08:30", "event": "CPI (my note)", "impact": "high", "notes": "hot print?"},
            {"date": "2026-10-14", "time_ny": "", "event": "Earnings season", "impact": "", "notes": ""},
            {"date": "14.10.2026", "time_ny": "10:00", "event": "Bad date", "impact": "High", "notes": ""},
            {"date": "2026-10-14", "time_ny": "2pm", "event": "Bad time", "impact": "High", "notes": ""},
        ]
    )
    save_manual(manual, csv)
    table, problems = events_for_day(parse_feed(FEED, NY), load_manual(csv), dt.date(2026, 10, 14), NY)
    assert len(problems) == 2
    assert table.iloc[0]["all_day"] and table.iloc[0]["events"] == "Earnings season"
    cpi = table[table["time"] == pd.Timestamp("2026-10-14 08:30", tz=NY)].iloc[0]
    assert "CPI (my note)" in cpi["events"] and cpi["source"] == "ForexFactory + manual"


def test_feed_is_cached_and_rate_limit_falls_back(tmp_path):
    calls = []
    now = pd.Timestamp("2026-10-14 06:00", tz=NY)

    def ok(url):
        calls.append(url)
        return FakeResponse(200, FEED)

    first = get_events(dt.date(2026, 10, 14), tmp_path, tmp_path / "m.csv", NY, now, http_get=ok)
    assert first.feed_ok and len(first.table) == 1 and len(calls) == 1
    get_events(dt.date(2026, 10, 14), tmp_path, tmp_path / "m.csv", NY, now + pd.Timedelta(hours=1), http_get=ok)
    assert len(calls) == 1  # saved copy reused, no second download

    def refused(url):
        return FakeResponse(200, "<html>Request Denied</html>")

    later = get_events(dt.date(2026, 10, 14), tmp_path, tmp_path / "m.csv", NY, now + pd.Timedelta(hours=6), http_get=refused)
    assert later.feed_ok and "saved copy" in later.notes[0]


def test_next_week_feed_used_for_monday_prep(tmp_path):
    next_week = [{"title": "ISM Manufacturing PMI", "country": "USD", "date": "2026-10-19T10:00:00-04:00", "impact": "High", "forecast": "", "previous": ""}]

    def fake(url):
        return FakeResponse(200, next_week if "nextweek" in url else FEED)

    result = get_events(dt.date(2026, 10, 19), tmp_path, tmp_path / "m.csv", NY, pd.Timestamp("2026-10-17 10:00", tz=NY), http_get=fake)
    assert result.feed_ok and result.table.iloc[0]["events"] == "ISM Manufacturing PMI"


def test_unpublished_week_explains_manual_entry(tmp_path):
    def fake(url):
        return FakeResponse(404, None) if "nextweek" in url else FakeResponse(200, FEED)

    result = get_events(dt.date(2026, 10, 19), tmp_path, tmp_path / "m.csv", NY, pd.Timestamp("2026-10-17 10:00", tz=NY), http_get=fake)
    assert not result.feed_ok and result.table.empty
    assert any("manually" in n for n in result.notes)
