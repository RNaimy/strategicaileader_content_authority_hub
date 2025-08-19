from utils.nlp import keyword_frequency, contains_all_keywords, top_keywords


def test_keyword_frequency_counts_words():
    text = "Growth loops drive growth. SEO supports growth."
    keywords = ["growth", "seo", "loops"]
    freq = keyword_frequency(text, keywords)
    assert freq["growth"] == 3
    assert freq["seo"] == 1
    assert freq["loops"] == 1


def test_contains_all_keywords_true_and_false():
    assert contains_all_keywords("Growth loops support SEO.", ["growth", "loops", "seo"]) is True
    assert contains_all_keywords("Growth loops support strategy.", ["growth", "seo"]) is False


def test_top_keywords_orders_desc():
    text = "growth growth seo loops"
    pairs = top_keywords(text, ["growth", "seo", "loops"], top_n=2)
    assert pairs[0][0] == "growth" and pairs[0][1] == 2
    assert len(pairs) == 2


def test_contains_all_keywords_ignores_empty_and_returns_true():
    # No meaningful keywords: should be considered satisfied
    assert contains_all_keywords("anything at all", []) is True
    assert contains_all_keywords("still fine", ["", None, "   "]) is True


def test_keyword_frequency_handles_none_and_empty_keywords():
    # None text and empty/None keywords shouldn't blow up
    freq = keyword_frequency(None, ["growth", None, ""])
    # We only assert the meaningful key; empty/None are normalized away
    assert freq["growth"] == 0


def test_top_keywords_respects_top_n_limit():
    pairs = top_keywords("alpha alpha beta", ["alpha", "beta", "gamma"], top_n=1)
    assert pairs == [("alpha", 2)]
