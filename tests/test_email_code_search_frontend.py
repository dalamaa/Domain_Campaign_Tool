from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_email_code_search_tables_keep_identifiers_and_metadata_readable():
    template = (ROOT / "app/templates/email_code_search.html").read_text()
    styles = (ROOT / "app/static/css/email_code_search.css").read_text()

    assert 'class="email-code-match-meta"' in template
    assert ".email-code-search-table-wrap {" in styles
    assert "overflow-x: auto;" in styles
    assert "min-width: 760px;" in styles
    assert '.email-code-search-table tbody th[scope="row"] {' in styles
    assert "position: static;" in styles
    assert ".email-code-match-meta > span {" in styles
    assert "white-space: nowrap;" in styles
