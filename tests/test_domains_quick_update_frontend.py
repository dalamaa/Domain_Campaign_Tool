from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOMAINS_HTML = (ROOT / "app/templates/domains.html").read_text()
DOMAINS_JS = (ROOT / "app/static/js/pages/domains.js").read_text()
BASE_CSS = (ROOT / "app/static/css/base.css").read_text()


def test_quick_update_button_and_accessible_dialog_are_on_domain_campaign_page():
    assert 'id="quick-update-btn"' in DOMAINS_HTML
    assert 'onclick="openQuickUpdateModal()"' in DOMAINS_HTML
    assert 'aria-modal="true"' in DOMAINS_HTML
    assert 'aria-labelledby="quick-update-title"' in DOMAINS_HTML
    assert 'id="quick-update-input"' in DOMAINS_HTML


def test_quick_update_modal_and_preview_have_no_email_used_controls_or_column():
    modal = DOMAINS_HTML.split('id="quick-update-modal"', 1)[1].split(
        '<div\n  id="domain-modal"',
        1,
    )[0]
    assert "Email Used" not in modal
    assert "quick-update-email" not in DOMAINS_HTML
    assert '<th scope="col">Domain</th>' in modal
    assert '<th scope="col">Action</th>' in modal
    assert '<th scope="col">Sequence</th>' in modal
    assert '<th scope="col">Current Price</th>' in modal
    assert '<th scope="col">New Price</th>' in modal
    assert '<th scope="col">Status</th>' in modal


def test_quick_update_open_and_escape_manage_modal_focus():
    open_function = DOMAINS_JS.split("function openQuickUpdateModal()", 1)[1].split("function closeQuickUpdateModal()", 1)[0]
    keydown_function = DOMAINS_JS.split("function handleQuickUpdateModalKeydown(event)", 1)[1].split("function openQuickUpdateModal()", 1)[0]

    assert "modal.hidden = false" in open_function
    assert "document.addEventListener(\"keydown\", handleQuickUpdateModalKeydown)" in open_function
    assert 'getElementById("quick-update-input").focus()' in open_function
    assert 'event.key === "Escape"' in keydown_function
    assert "quickUpdateFocusableElements(modal)" in keydown_function


def test_quick_update_preview_and_back_keep_the_multiline_input():
    assert 'onclick="previewQuickUpdate()"' in DOMAINS_HTML
    assert 'onclick="backToQuickUpdateInput()"' in DOMAINS_HTML
    assert 'getElementById("quick-update-input").focus()' in DOMAINS_JS
    assert 'function backToQuickUpdateInput()' in DOMAINS_JS
    back_function = DOMAINS_JS.split("function backToQuickUpdateInput()", 1)[1].split("function setQuickUpdateBusy", 1)[0]
    assert '.value = ""' not in back_function


def test_blocking_errors_disable_the_final_update_button():
    assert 'confirmButton.disabled = !preview?.can_update || !quickUpdatePreviewToken || quickUpdateBusy;' in DOMAINS_JS
    assert 'id="quick-update-error-summary"' in DOMAINS_HTML
    assert 'aria-describedby="quick-update-input-help quick-update-input-feedback"' in DOMAINS_HTML
    assert 'tr.setAttribute("aria-describedby", errorId)' in DOMAINS_JS


def test_quick_update_success_resets_modal_and_refreshes_existing_table_path():
    assert 'closeQuickUpdateModal();' in DOMAINS_JS
    assert 'await renderDomainTable();' in DOMAINS_JS
    assert 'alert(`${updatedCount} campaign${updatedCount === 1 ? "" : "s"} updated successfully.`);' in DOMAINS_JS


def test_quick_update_modal_is_compact_and_preview_table_can_scroll():
    assert '#quick-update-modal {\n  width: min(94vw, 780px);' in BASE_CSS
    assert '.quick-update-preview-table-wrap' in BASE_CSS
    assert 'overflow: auto;' in BASE_CSS
    assert 'min-width: 680px;' in BASE_CSS


def test_quick_update_uses_authenticated_preview_and_confirmation_endpoints():
    assert 'fetch("/api/campaigns/quick-update/preview"' in DOMAINS_JS
    assert 'fetch("/api/campaigns/quick-update"' in DOMAINS_JS
    preview_function = DOMAINS_JS.split("async function previewQuickUpdate()", 1)[1].split("function backToQuickUpdateInput()", 1)[0]
    assert 'body: JSON.stringify({ input: input.value })' in preview_function
    assert "email_codes" not in preview_function
