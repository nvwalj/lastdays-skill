"""Demand-signal detection: pattern shapes, tool-object requirement, anti-signals."""

from lib.demand import demand_signal, is_demand, DEMAND_THRESHOLD


def _score(t):
    return demand_signal(t)[0]


def _type(t):
    return demand_signal(t)[1]


def test_payment_is_strongest():
    s, t = demand_signal("Honestly I'd pay for an app that auto-files my receipts")
    assert t == "payment" and s >= 0.9
    assert demand_signal("shut up and take my money, build this")[1] == "payment"


def test_payment_requires_purchase_object():
    # "pay to see/fight" is consumption, not product demand -> not payment.
    assert demand_signal("honestly I'd pay to see him in the ring")[1] != "payment"
    assert demand_signal("I'd pay $40 for a tool that does this")[1] == "payment"
    assert demand_signal("I would happily pay for a service like that")[1] == "payment"


def test_payment_recall_purchase_phrasings():
    # reviewer-flagged recall gaps: monthly/premium/purchase phrasings.
    assert demand_signal("I'd pay monthly for a tool that does this")[1] == "payment"
    assert demand_signal("I'd pay a premium for reliable sync")[1] == "payment"
    assert demand_signal("I would purchase a service like that")[1] == "payment"


def test_wish_tool_positive():
    assert _type("is there an app that syncs notes across devices?") == "wish_tool"
    assert _type("someone should build a tool for this") == "wish_tool"
    assert _type("I wish there was a way to automate my standup updates") == "wish_tool"
    assert _score("is there a service that does X") >= DEMAND_THRESHOLD


def test_wish_requires_tool_object_drops_noise():
    # The measured Bluesky noise: "wish" without a tool-like object is NOT demand.
    assert demand_signal("I wish there was a rapture but for assholes") == (0.0, None)
    assert demand_signal("wish everyone a happy donut day") == (0.0, None)
    assert demand_signal("I wish I was back there right now") == (0.0, None)


def test_workaround_detected():
    assert _type("my current workaround is a google sheet with macros") == "workaround"
    assert _type("I built a script to scrape my invoices every month") == "workaround"


def test_selfpromo_with_link_penalized():
    # Advertising your own product (promo language + link) is not an open need.
    ad = "I built a tool for exactly this, check it out at mytool.com"
    assert _score(ad) < DEMAND_THRESHOLD            # workaround base minus promo+link penalty
    # ...but a bare workaround without a link survives.
    assert _score("I built a script to do exactly this") >= DEMAND_THRESHOLD


def test_pain_plus_intensity():
    base = _score("so frustrating to reconcile these by hand")
    amp = _score("wasting hours on this every single time, killing me")
    assert _type("wasting hours on this every single time") == "pain"
    assert amp > base                               # intensity amplifier bumps the score


def test_feature_request():
    assert _type("feature request: please add dark mode") in ("feature_request", "payment")
    assert _type("it would be great if it supported CSV export") == "feature_request"


def test_already_solved_penalized():
    asked = _score("is there an app for X")
    solved = _score("is there an app for X? you can just use Y")
    assert solved < asked                           # already-solved cue subtracts


def test_seeking_signals():
    # Recall gaps the 3-agent review flagged -- implicit demand without a tool noun.
    assert _type("there has to be a better way to manage client invoices") == "seeking"
    assert _type("what do you all use for time tracking these days?") == "seeking"
    assert _type("how do you deal with managing 50 different logins") == "seeking"
    assert is_demand("anyone else struggle with keeping notes in sync across devices")
    assert is_demand("need a way to batch-rename files by date")


def test_seeking_better_way_needs_an_object():
    # "a better way to/of X" is a real ask; a bare colloquial "better way" is noise.
    assert _type("there has to be a better way to manage these invoices") == "seeking"
    assert demand_signal("ugh, there has to be a better way")[1] != "seeking"


def test_no_signal_and_empty():
    assert demand_signal("had a great lunch today, lovely weather") == (0.0, None)
    assert demand_signal("") == (0.0, None)
    assert demand_signal(None) == (0.0, None)


def test_priority_highest_weight_wins():
    # Pain + payment in one text -> payment (the stronger signal) wins.
    s, t = demand_signal("I hate that there's no good option. I'd pay for a tool that fixes it")
    assert t == "payment" and s >= 0.9


def test_is_demand_gate():
    assert is_demand("is there a tool that does X")
    assert not is_demand("just had coffee")
    assert not is_demand("")
