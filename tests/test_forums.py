from moodlectl.browser import SIMILAR, html_text, similarity


def test_html_text_keeps_paragraphs_breaks_and_nested_lists():
    html = (
        "<p>Hello <strong>world</strong></p>\r\n<p>a<br>b</p>\r\n"
        "<ul>\r\n<li><p>One</p>\r\n<ul><li>sub</li></ul></li>\r\n<li>Two</li>\r\n</ul>"
    )
    assert html_text(html) == "Hello world\n\na\nb\n- One\n  - sub\n- Two"


def test_similarity_flags_near_duplicate_replies_only():
    said = "Here are the slides for tomorrow's lab"
    assert similarity("Here are **the slides** for tomorrow's  lab!", said) >= SIMILAR
    assert similarity("Exams are postponed to June", said) < SIMILAR
