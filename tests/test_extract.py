from tts_rss.extract import extract_article

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
