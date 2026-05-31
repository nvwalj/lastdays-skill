from lib.schema import Item, Report


def test_item_to_dict_drops_empty():
    it = Item(
        source="hackernews",
        lang="en",
        title="T",
        url="https://example.com",
        engagement={"points": 10, "comments": 0},
    )
    d = it.to_dict()
    assert d["source"] == "hackernews"
    assert d["engagement"] == {"points": 10}   # zero/None dropped
    assert "author" not in d                    # None dropped
    assert it.engagement_total() == 10.0


def test_report_to_dict():
    r = Report(topic="x", days=7, from_date="2026-05-23", to_date="2026-05-30", generated_at="t")
    r.items_by_source["hackernews"] = [Item(source="hackernews", lang="en", title="T", url="u")]
    d = r.to_dict()
    assert d["counts"] == {"hackernews": 1}
    assert d["window"] == {"days": 7, "from": "2026-05-23", "to": "2026-05-30"}
    assert d["items_by_source"]["hackernews"][0]["title"] == "T"
