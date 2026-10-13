from tts_rss.chunking import split_text


def test_short_text_is_one_chunk():
    assert split_text("Hello.\n\nWorld.", 100) == ["Hello.\n\nWorld."]


def test_paragraphs_are_packed_up_to_limit():
    text = "\n\n".join(["a" * 40] * 5)
    chunks = split_text(text, 100)
    assert all(len(c) <= 100 for c in chunks)
    assert chunks[0] == "a" * 40 + "\n\n" + "a" * 40
    assert len(chunks) == 3


def test_long_paragraph_splits_on_sentences():
    paragraph = " ".join(f"Sentence number {i}." for i in range(50))
    chunks = split_text(paragraph, 120)
    assert all(len(c) <= 120 for c in chunks)
    assert all(c.endswith(".") for c in chunks)
    assert "\n\n" not in "".join(chunks)
    assert " ".join(chunks) == paragraph


def test_very_long_sentence_splits_on_words():
    sentence = " ".join(["word"] * 100)
    chunks = split_text(sentence, 50)
    assert all(len(c) <= 50 for c in chunks)
    assert " ".join(chunks) == sentence


def test_no_text_is_lost():
    text = "First paragraph here.\n\n\n  Second   one, with spaces.  \n\nThird."
    chunks = split_text(text, 30)
    assert all(len(c) <= 30 for c in chunks)
    joined = " ".join(" ".join(chunks).split())
    assert joined == "First paragraph here. Second one, with spaces. Third."
