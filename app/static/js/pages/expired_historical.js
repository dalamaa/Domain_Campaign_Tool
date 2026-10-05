(() => {
  "use strict";

  const state = {
    expired: [],
    historical: [],
    retentionDays: 60,
    autoArchiveDays: 90,
    selectedDomainIds: new Set(),
  };

  const byId = (id) => document.getElementById(id);

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function formatDate(value) {
    if (!value) return "—";
    return new Date(`${value}T00:00:00`).toLocaleDateString();
  }

  function formatDateTime(value) {
    if (!value) return "—";
    return new Date(value).toLocaleDateString();
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Unable to complete the request.");
    return data;
  }

  function filteredRows(rows, inputId) {
    const search = byId(inputId).value.trim().toLowerCase();
    return rows.filter((row) => !search || row.domain_name.toLowerCase().includes(search));
  }

  function updateArchiveButton() {
    const button = byId("archive-eligible-button");
    const selected = [...state.selectedDomainIds].filter((id) =>
      state.expired.some((row) => row.domain_id === id),
    );
    state.selectedDomainIds = new Set(selected);
    const eligibleCount = state.expired.filter((row) => row.eligible).length;
    button.disabled = eligibleCount === 0;
    button.textContent = selected.length
      ? `Archive Selected (${selected.length})`
      : "Move Eligible to Historical";
  }

  function archiveStatusMarkup(row) {
    if (!row.eligible) {
      return '<span title="Manual archive is available after the retention threshold.">Not yet eligible</span>';
    }
    if (row.days_until_auto_archive > 0) {
      return `<span>Eligible</span><small>Auto in ${row.days_until_auto_archive}d</small>`;
    }
    return '<span class="expired-historical-auto" title="Automatic archival is due on the next scheduler run.">Auto pending</span>';
  }

  function renderExpiredDomains() {
    const rows = filteredRows(state.expired, "expired-domain-search");
    byId("expired-domain-count").textContent = `${rows.length} domain${rows.length === 1 ? "" : "s"}`;
    byId("expired-domain-empty").hidden = rows.length !== 0;
    byId("expired-domain-table-body").innerHTML = rows.map((row) => `
      <tr>
        <td><input type="checkbox" data-expired-domain-id="${row.domain_id}" aria-label="Select ${escapeHtml(row.domain_name)} for Historical" title="${row.eligible ? "Select for manual archive" : "Not yet eligible for manual archive"}" ${row.eligible ? "" : "disabled"} ${state.selectedDomainIds.has(row.domain_id) ? "checked" : ""} /></td>
        <td>${escapeHtml(row.domain_name)}</td>
        <td>${escapeHtml(formatDate(row.expiry_date))}</td>
        <td>${row.days_expired ?? "—"}d</td>
        <td>${archiveStatusMarkup(row)}</td>
        <td>${escapeHtml(formatDate(row.last_contact_date))}</td>
        <td>${row.sequence == null ? "—" : `S${row.sequence}`}</td>
        <td>${escapeHtml(row.email_used || "—")}</td>
        <td>${row.last_price == null ? "—" : `$${row.last_price}`}</td>
      </tr>`).join("");
    updateArchiveButton();
  }

  function renderHistoricalDomains() {
    const rows = filteredRows(state.historical, "historical-domain-search");
    byId("historical-domain-count").textContent = `${rows.length} domain${rows.length === 1 ? "" : "s"}`;
    byId("historical-domain-empty").hidden = rows.length !== 0;
    byId("historical-domain-table-body").innerHTML = rows.map((row) => `
      <tr>
        <td>${escapeHtml(row.domain_name)}</td>
        <td>${escapeHtml(formatDate(row.expiry_date))}</td>
        <td>${escapeHtml(row.last_email_used || "—")}</td>
        <td>${escapeHtml(formatDateTime(row.retired_at))}</td>
      </tr>`).join("");
  }

  async function loadExpiredHistorical() {
    try {
      const data = await fetchJson("/api/expired-historical");
      state.expired = data.expired || [];
      state.historical = data.historical || [];
      state.retentionDays = data.retention_days;
      state.autoArchiveDays = data.auto_archive_days;
      byId("expired-retention-note").textContent =
        `Manual archive after ${state.retentionDays} days; automatic archive after ${state.autoArchiveDays} days.`;
      renderExpiredDomains();
      renderHistoricalDomains();
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  async function archiveEligible() {
    const selected = [...state.selectedDomainIds];
    const message = selected.length
      ? `Move ${selected.length} selected domain${selected.length === 1 ? "" : "s"} to Historical?`
      : "Move all eligible domains to Historical?";
    if (!window.confirm(message)) return;
    try {
      const result = await fetchJson("/api/expired-historical/archive", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(selected.length ? { domain_ids: selected } : {}),
      });
      state.selectedDomainIds.clear();
      showToast(`${result.archived_count} domain${result.archived_count === 1 ? "" : "s"} moved to Historical.`);
      await loadExpiredHistorical();
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  function bindEvents() {
    byId("archive-eligible-button").addEventListener("click", archiveEligible);
    byId("refresh-expired-historical-button").addEventListener("click", loadExpiredHistorical);
    byId("expired-domain-search").addEventListener("input", renderExpiredDomains);
    byId("historical-domain-search").addEventListener("input", renderHistoricalDomains);
    byId("expired-domain-table-body").addEventListener("change", (event) => {
      const checkbox = event.target.closest("[data-expired-domain-id]");
      if (!checkbox) return;
      const id = Number(checkbox.dataset.expiredDomainId);
      if (checkbox.checked) state.selectedDomainIds.add(id);
      else state.selectedDomainIds.delete(id);
      updateArchiveButton();
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    bindEvents();
    loadExpiredHistorical();
  });
})();
