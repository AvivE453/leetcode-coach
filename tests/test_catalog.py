from coach import catalog

TWO_SUM_HTML = """\
<p>You are given an array of integers <code>nums</code>&nbsp;and an integer <code>target</code>.</p>

<p>&nbsp;</p>
<p><strong>Constraints:</strong></p>

<ul>
	<li><code>2 &lt;= nums.length &lt;= 10<sup>4</sup></code></li>
	<li><strong>Only one valid answer exists.</strong></li>
</ul>
"""


def test_clean_html_strips_tags_and_keeps_the_constraints_readable():
    text = catalog._clean_html(TWO_SUM_HTML)

    assert "<code>" not in text and "<li>" not in text and "<strong>" not in text
    assert "2 <= nums.length <= 10^4" in text
    assert "Only one valid answer exists." in text


def test_clean_html_unescapes_entities():
    assert catalog._clean_html("<p>a &lt; b &amp;&amp; b &gt; 0</p>") == "a < b && b > 0"
