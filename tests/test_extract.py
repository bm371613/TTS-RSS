from pathlib import Path

from tts_rss.extract import extract_article
from tts_rss.language import detect_language

BODY = " ".join(["The article body has several meaningful sentences about the topic."] * 6)

HTML = f"""<!doctype html>
<html><head><title>Great Article | Some Blog</title>
<meta property="og:title" content="Great Article"></head>
<body>
<nav><a href="/">Home</a> <a href="/about">About</a> <a href="/subscribe">Subscribe</a></nav>
<article>
<h1>Great Article</h1>
<p>{BODY}</p>
<p>A second paragraph continues the argument with more detail and examples.</p>
</article>
<section class="comments"><p>Comment: first! Great post, thanks for sharing.</p></section>
<footer>Copyright 2026 Some Blog. All rights reserved. Privacy policy.</footer>
</body></html>"""


def test_extracts_main_text_without_boilerplate():
    article = extract_article(HTML, url="https://example.com/great")
    assert article.title == "Great Article"
    assert article.text.startswith("The article body")
    assert "\n\nA second paragraph" in article.text
    assert "Subscribe" not in article.text
    assert "Copyright" not in article.text
    assert "first!" not in article.text


FIXTURES = Path(__file__).parent / "fixtures"


def _paragraphs(text: str) -> list[str]:
    return text.split("\n\n")


def test_magazynflary_article():
    html = (FIXTURES / "magazynflary-punkty-krytyczne.html").read_text(encoding="utf-8")
    article = extract_article(html, url="https://magazynflary.pl/2026/09/01/x/")
    assert article.title == "Punkty krytyczne gospodarki cyfrowej: Google"
    assert detect_language(article.text) == "pl"
    paragraphs = _paragraphs(article.text)
    assert paragraphs[0].startswith("Książka Punkty krytyczne Edwarda Fishmana")
    assert paragraphs[-1].endswith("może kiedyś przeczytamy o analogicznym wykorzystaniu Google.")

    # Pull quotes on this site are not repeated in the body, and the paragraph after the
    # first one answers its question, so they must be read, in place.
    quote = next(i for i, p in enumerate(paragraphs) if p.startswith("Zasadne jest pytanie"))
    assert paragraphs[quote].endswith("Czy ta infrastruktura jest bezstronna?")
    assert paragraphs[quote - 1].startswith("Te dwie perspektywy pokazują")
    assert paragraphs[quote + 1].startswith("Śledztwa związane ze sprawami")
    assert any(p.startswith("Jako użytkownicy zostaliśmy tak do tego") for p in paragraphs)

    for boilerplate in [
        "Pisz z nami",  # site banner
        "Zagrożenia współczesności",  # edition link in the byline
        "Korporacje",  # tags
        "Ilustracja",  # image credit
        "Creative Commons",  # license
        "W trosce o dobro wspólne",  # site footer
    ]:
        assert boilerplate not in article.text


def test_pull_quote_repeating_the_body_is_read_once():
    sentence = "A striking sentence that the designer chose to repeat in large type."
    html = f"""<html><head><title>Repeat</title></head><body><article><h1>Repeat</h1>
<p>{BODY}</p>
<aside class="pullquote"><p>{sentence}</p></aside>
<p>Another paragraph of the article. {sentence} And it goes on for a little while.</p>
</article></body></html>"""
    text = extract_article(html).text
    assert text.count("A striking sentence") == 1


def test_xhtml_with_encoding_declaration():
    # The text is already decoded, so declarations of other encodings must not be applied.
    html = '<?xml version="1.0" encoding="iso-8859-2"?>\n' + HTML.replace(
        "<head>", '<head><meta charset="iso-8859-2">'
    ).replace("A second paragraph", "Zażółć gęślą jaźń. A second paragraph")
    article = extract_article(html)
    assert article.title == "Great Article"
    assert "Zażółć gęślą jaźń." in article.text
