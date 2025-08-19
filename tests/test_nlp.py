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
