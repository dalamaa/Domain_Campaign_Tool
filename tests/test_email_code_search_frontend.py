from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_email_code_search_tables_keep_identifiers_and_metadata_readable():
    template = (ROOT / "app/templates/email_code_search.html").read_text()
    styles = (ROOT / "app/static/css/email_code_search.css").read_text()

    header = template.split('<thead>', 1)[1].split('</thead>', 1)[0]
    assert header.index('>Domain</th>') < header.index('>State</th>')
    assert header.index('>State</th>') < header.index('>Email Accounts Used</th>')
    assert "Match reasons" not in template
    assert ".email-code-search-table-wrap {" in styles
    assert "overflow-x: auto;" in styles
    assert "min-width: 900px;" in styles
    assert '.email-code-search-table tbody th[scope="row"] {' in styles
    assert "position: static;" in styles
    assert ".email-code-search-table th:nth-child(3)" in styles
    assert "width: 54%;" in styles
    assert "min-width: 26rem;" in styles


def test_email_code_search_form_fills_desktop_row_and_wraps_on_narrow_screens():
    styles = (ROOT / "app/static/css/email_code_search.css").read_text()
    form_rule = styles.split(".email-code-search-form {", 1)[1].split("}", 1)[0]
    field_rule = styles.split(".email-code-search-field {", 1)[1].split("}", 1)[0]
    actions_rule = styles.split(".email-code-search-actions {", 1)[1].split("}", 1)[0]

    assert "display: flex;" in form_rule
    assert "align-items: center;" in form_rule
    assert "flex-wrap: wrap;" in form_rule
    assert "margin-bottom: var(--space-4);" in form_rule
    assert "flex: 1 1 22rem;" in field_rule
    assert "min-width: 0;" in field_rule
    assert "flex: 0 0 auto;" in actions_rule
    assert "align-items: center;" in actions_rule
    assert "@media (max-width: 640px) {\n  .email-code-search-form {\n    align-items: stretch;\n    flex-direction: column;" in styles
