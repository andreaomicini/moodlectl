import pytest

from moodlectl.browser import SIMILAR, html_text, similarity
from moodlectl.cli import forum_ref
from moodlectl.errors import moodlectlError


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


def test_forum_ref_accepts_ids_and_pasted_urls():
    site = "https://virtuale.unibo.it/mod/forum/"
    assert forum_ref("42", "discussion") == 42
    assert forum_ref(site + "view.php?id=2037611", "forum") == 2037611
    assert forum_ref(site + "discuss.php?d=230424#p315396", "discussion") == 230424
    with pytest.raises(moodlectlError, match="discussions list 2037611"):
        forum_ref(site + "view.php?id=2037611", "discussion")  # a forum, not a discussion
    with pytest.raises(moodlectlError):
        forum_ref(site + "post.php?reply=1", "forum")
