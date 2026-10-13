from tts_rss.language import detect_language


def test_polish():
    text = "To jest artykuł o tym, że nie wszystko się udało, ale było warto spróbować."
    assert detect_language(text) == "pl"


def test_english():
    text = "This is an article about the fact that not everything worked, but it was worth it."
    assert detect_language(text) == "en"


def test_english_with_polish_names_is_english():
    text = (
        "The interview with Łukasz Żółkiewski and Małgorzata Wąsik was held in Łódź, "
        "and it covered the history of the city and its industry."
    )
    assert detect_language(text) == "en"


def test_short_text_falls_back_to_diacritics():
    assert detect_language("Zażółć gęślą jaźń") == "pl"
    assert detect_language("Hello world") == "en"
