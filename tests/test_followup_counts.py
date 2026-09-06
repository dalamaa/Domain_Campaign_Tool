from pathlib import Path


def test_followup_accordion_counts_are_bound_to_api_results(client):
    html = client.get("/").get_data(as_text=True)
    script = Path("app/static/js/pages/dashboard.js").read_text()

    assert 'First Follow-ups (<span id="first-followup-count">0</span>)' in html
    assert 'Normal Follow-ups (<span id="normal-followup-count">0</span>)' in html
    assert "function getFollowupResultCount(data)" in script
    assert "if (Number.isInteger(data.count)) return data.count;" in script
    assert "(data.due || []).length + (data.past_due || []).length" in script
    assert 'document.getElementById("first-followup-count")' in script
    assert 'document.getElementById("normal-followup-count")' in script
    assert script.count("count.textContent = getFollowupResultCount(data);") == 2


def test_existing_dashboard_counts_remain_separate(client):
    html = client.get("/").get_data(as_text=True)

    assert 'id="resting-suggestions-count"' in html
    assert 'id="expiring-soon-count"' in html
    assert 'id="first-followup-count"' in html
    assert 'id="normal-followup-count"' in html
