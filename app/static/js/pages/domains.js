// 1. domains.js
let selectedDomains = new Set();
let searchTerm = "";
let currentSort = { key: "daysSince", direction: "asc" };
let domains = [];
let allEmailAccounts = [];
const emailPickerStates = new Map();
let editActionLoadRequestId = 0;
let businessToday = null;
let businessTodayIso = "";
let domainTableRenderRequestId = 0;
let selectedExportInProgress = false;
let bulkImportFiles = {
  campaignHistory: null,
  emailUsage: null,
};
let bulkImportConflictSelections = {};
const bulkImportState = {
  matching: null,
};

async function fetchBusinessInfo() {
  const res = await fetch("/api/settings/business-info");
  const data = await res.json();
  return data;
}

async function fetchDomains() {
  const res = await fetch(`/api/domains?t=${Date.now()}`);
  const data = await res.json();
  return data;
}

function updateSearch(val) {
  searchTerm = val.trim().toLowerCase();
  renderDomainTable();
}

function sortTable(key) {
  if (currentSort.key === key) {
    currentSort.direction = currentSort.direction === "asc" ? "desc" : "asc";
  } else {
    currentSort.key = key;
    currentSort.direction = "asc";
  }

  applyCurrentSort();
  renderDomainTable();
}

function applyCurrentSort() {
  const { key, direction } = currentSort;
  const today = businessToday || new Date();

  domains.sort((a, b) => {
    let valA, valB;

    // Helper to calculate days since
    const getDaysSince = (contactDate) => {
      if (!contactDate) return Infinity; // N/A to the end
      const date = new Date(contactDate);
      return Math.floor((today - date) / (1000 * 60 * 60 * 24));
    };

    // Helper to calculate days left
    const getDaysLeft = (expiryDate) => {
      if (!expiryDate) return -Infinity;
      const date = new Date(expiryDate);
      return Math.floor((date - today) / (1000 * 60 * 60 * 24));
    };

    if (key === "daysSince") {
      valA = getDaysSince(a.lastContact);
      valB = getDaysSince(b.lastContact);
    } else if (key === "daysLeft") {
      valA = getDaysLeft(a.expiry);
      valB = getDaysLeft(b.expiry);
    } else if (["expiry", "lastContact", "createdAt"].includes(key)) {
      valA = a[key] ? new Date(a[key]) : new Date(0);
      valB = b[key] ? new Date(b[key]) : new Date(0);
    } else if (key === "price" || key === "seq") {
      valA = Number(a[key] || 0);
      valB = Number(b[key] || 0);
    } else {
      valA = (a[key] || "").toString().toLowerCase();
      valB = (b[key] || "").toString().toLowerCase();
    }

    if (valA < valB) return direction === "asc" ? -1 : 1;
    if (valA > valB) return direction === "asc" ? 1 : -1;
    return 0;
  });
}

// 2. Fix sorting and table persistence in domains.js
// 2. Fix the renderDomainTable in domains.js
async function renderDomainTable() {
  const requestId = ++domainTableRenderRequestId;
  const businessInfo = await fetchBusinessInfo();
  const fetchedDomains = await fetchDomains();
  // Fetch email accounts for validation
  const accRes = await fetch("/api/email-accounts");
  const fetchedEmailAccounts = await accRes.json();
  if (requestId !== domainTableRenderRequestId) return;

  businessTodayIso = businessInfo.business_today || "";
  businessToday = new Date(businessInfo.business_today);
  domains = fetchedDomains;
  allEmailAccounts = fetchedEmailAccounts;
  reconcileSelectedDomains(domains);

  // Apply current sort
  if (currentSort.key) {
    applyCurrentSort();
  }

  const body = document.getElementById("domain-table-body");
  if (!body) return;

  // Filter by search
  const filtered = domains.filter(
    (c) => c.domain && c.domain.toLowerCase().includes(searchTerm),
  );
  const countEl = document.getElementById("domain-count");
  if (countEl)
    countEl.textContent = `${filtered.length} of ${domains.length} domains`;

  updateSelectAllState(filtered);
  updateDomainActionBar();

  body.innerHTML = filtered
    .map((c) => {
      const expiryDate = c.expiry ? new Date(c.expiry) : null;
      const lastContactDate = c.lastContact ? new Date(c.lastContact) : null;

      const daysLeft = expiryDate
        ? Math.floor((expiryDate - businessToday) / (1000 * 60 * 60 * 24))
        : "N/A";
      const daysSince = lastContactDate
        ? Math.floor((businessToday - lastContactDate) / (1000 * 60 * 60 * 24))
        : "N/A";
      // Ensure we use the property 'latestEmails' returned by the API
      return `
        <tr data-domain-id="${c.id}" class="${selectedDomains.has(c.id) ? "selected" : ""}">
            <td><input type="checkbox" ${selectedDomains.has(c.id) ? "checked" : ""} onchange="toggleDomainSelection(${c.id})"></td>
            <td onclick="openHistoryModal(${c.id}, '${c.domain}')" style="cursor:pointer; text-decoration: underline;">${c.domain}</td>
            <td>${c.createdAt ? c.createdAt.slice(0, 10) : "N/A"}</td>
            <td>${c.expiry || "N/A"}</td>
            <td>${daysLeft} days</td>
            <td>${c.status || "Dormant"}</td>
            <td>${c.price ? `$${c.price}` : "N/A"}</td>
            <td>${daysSince} days</td>
            <td>${c.hasValues ? c.seq : "Not started"}</td>
            <td>${c.lastAction || "N/A"}</td>
            <td>${c.latestEmails || "N/A"}</td>
        </tr>`;
    })
    .join("");
}

async function openHistoryModal(id, domainName) {
  const modal = document.getElementById("history-modal");
  const body = document.getElementById("history-table-body");
  document.getElementById("history-modal-domain").textContent =
    `History: ${domainName}`;

  const res = await fetch(`/api/domains/${id}/history`);
  const data = await res.json();

  body.innerHTML = data
    .map(
      (h) => `
    <tr>
      <td>${formatActionDateDisplay(h.date)}</td>
      <td>${h.action}</td>
      <td>${h.price_before !== null ? `$${h.price_before} → ` : ""}$${h.price_after}</td>
      <td>${h.notes || ""}</td>
    </tr>
  `,
    )
    .join("");

  modal.style.display = "block";
}

function closeHistoryModal() {
  document.getElementById("history-modal").style.display = "none";
}

function formatDateInputValue(value) {
  if (!value) return "";
  if (value instanceof Date) {
    if (Number.isNaN(value.getTime())) return "";
    const pad = (part) => String(part).padStart(2, "0");
    return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`;
  }

  const match = String(value).match(/^\d{4}-\d{2}-\d{2}/);
  return match ? match[0] : "";
}

function formatActionDateDisplay(value) {
  const dateValue = formatDateInputValue(value);
  if (!dateValue) return "Unknown";
  const [year, month, day] = dateValue.split("-");
  return `${month}/${day}/${year}`;
}

function toggleDomainSelection(id) {
  if (selectedDomains.has(id)) selectedDomains.delete(id);
  else selectedDomains.add(id);
  updateDomainActionBar();
  renderDomainTable();
}

function reconcileSelectedDomains(authoritativeDomains) {
  const validIds = new Set(authoritativeDomains.map((domain) => String(domain.id)));
  for (const selectedId of selectedDomains) {
    if (!validIds.has(String(selectedId))) selectedDomains.delete(selectedId);
  }
}

function clearAllDomainSelections(masterCheckbox, updateActionBar = true) {
  selectedDomains.clear();
  if (masterCheckbox) {
    masterCheckbox.checked = false;
    masterCheckbox.indeterminate = false;
  }
  if (updateActionBar) updateDomainActionBar();
}

function updateSelectAllState(filtered) {
  const selectAll = document.getElementById("select-all-checkbox");
  if (!selectAll) return;

  const selectedCount = filtered.filter((c) => selectedDomains.has(c.id)).length;
  selectAll.checked = filtered.length > 0 && selectedCount === filtered.length;
  selectAll.indeterminate = selectedCount > 0 && selectedCount < filtered.length;
}

function updateRenderedSelectionState(filtered) {
  const body = document.getElementById("domain-table-body");
  if (body && body.querySelectorAll) {
    const selectedIds = new Set(Array.from(selectedDomains, (id) => String(id)));
    body.querySelectorAll("tr[data-domain-id]").forEach((row) => {
      const selected = selectedIds.has(row.dataset.domainId);
      row.classList.toggle("selected", selected);
      const checkbox = row.querySelector('input[type="checkbox"]');
      if (checkbox) checkbox.checked = selected;
    });
  }
  updateSelectAllState(filtered);
  updateDomainActionBar();
}

function toggleSelectAll(masterCheckbox) {
  const filtered = domains.filter(
    (c) => c.domain && c.domain.toLowerCase().includes(searchTerm),
  );

  if (masterCheckbox.checked) {
    filtered.forEach((c) => selectedDomains.add(c.id));
  } else {
    clearAllDomainSelections(masterCheckbox, false);
  }
  updateRenderedSelectionState(filtered);
}

// 1. Update updateDomainActionBar in domains.js
function updateDomainActionBar() {
  const count = selectedDomains.size;
  const editBtn = document.getElementById("edit-btn");
  const delBtn = document.getElementById("delete-btn");
  const bulkEditBtn = document.getElementById("bulk-edit-btn");
  const actionBtn = document.getElementById("action-btn");
  const exportSelectedBtn = document.getElementById("export-selected-btn");
  const resetBtn = document.getElementById("reset-campaign-btn");

  // Edit button: enabled exactly 1 record selected
  if (editBtn) editBtn.disabled = count !== 1;

  // Bulk Edit button: enabled 2 or more records selected
  if (bulkEditBtn) bulkEditBtn.disabled = count < 2;

  // Action button: enabled exactly 1 record selected
  if (actionBtn) actionBtn.disabled = count !== 1;
  if (exportSelectedBtn && !selectedExportInProgress) {
    exportSelectedBtn.disabled = count === 0;
  }
  if (resetBtn) resetBtn.disabled = count !== 1;

  // Delete button: enabled if anything is selected
  if (delBtn) delBtn.disabled = count === 0;
}

function selectedExportFilename(response) {
  const contentDisposition = response.headers?.get?.("Content-Disposition") || "";
  const match = contentDisposition.match(/filename="?([^";]+)"?/i);
  return match
    ? match[1]
    : `domain-campaign-selected-${businessTodayIso || formatDateInputValue(new Date())}.csv`;
}

async function exportSelectedDomains() {
  if (selectedExportInProgress || selectedDomains.size === 0) return;

  const exportButton = document.getElementById("export-selected-btn");
  selectedExportInProgress = true;
  if (exportButton) {
    exportButton.disabled = true;
    exportButton.textContent = "Exporting…";
  }

  try {
    const response = await fetch("/api/domains/export-selected", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // Set iteration preserves selection order, including hidden selections.
      body: JSON.stringify({ domain_ids: Array.from(selectedDomains) }),
    });
    if (!response.ok) {
      const result = await response.json().catch(() => ({}));
      throw new Error(result.error || "Unable to export selected domains.");
    }

    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = selectedExportFilename(response);
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(objectUrl);
  } catch (error) {
    alert(error.message || "Unable to export selected domains.");
  } finally {
    selectedExportInProgress = false;
    if (exportButton) exportButton.textContent = "Export Selected";
    updateDomainActionBar();
  }
}

function selectedDomainRecord() {
  const id = Array.from(selectedDomains)[0];
  return domains.find((domain) => domain.id == id) || null;
}

function campaignIdForDomainRecord(record) {
  return record && record.campaign_id != null ? record.campaign_id : null;
}

async function resetSelectedCampaign() {
  if (selectedDomains.size !== 1) return;
  const record = selectedDomainRecord();
  const campaignId = campaignIdForDomainRecord(record);
  if (!record || campaignId == null) {
    alert("This domain has no campaign to reset.");
    return;
  }

  const confirmed = confirm(
    `Reset campaign for ${record.domain}?\n\n` +
      "This permanently removes the current campaign's:\n" +
      "- history\n- associated email accounts\n" +
      "- sequence/price/contact state\n- reservations\n\n" +
      "The Domain itself, expiry date, and domain-level data will remain.",
  );
  if (!confirmed) return;

  const typed = prompt(`Type ${record.domain} to confirm the campaign reset:`);
  if (typed === null || typed.trim().toLowerCase() !== record.domain.trim().toLowerCase()) {
    alert("Campaign reset cancelled. The domain name did not match.");
    return;
  }

  const response = await fetch(`/api/campaigns/${campaignId}/reset`, { method: "POST" });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    alert(result.error || "Unable to reset campaign.");
    return;
  }
  selectedDomains.delete(record.id);
  updateDomainActionBar();
  alert(`Campaign for ${record.domain} was reset.`);
  await renderDomainTable();
}

// 2. Add bulkEditSelected function
function editSelected() {
  const ids = Array.from(selectedDomains);
  if (ids.length === 1) {
    openModal(ids[0]);
  } else {
    openBulkModal(ids);
  }
}

// Fix: Trigger reset at the beginning of opening the modal
function openBulkModal(ids) {
  resetBulkModal(); // Guaranteed clean slate
  document.getElementById("bulk-edit-modal").style.display = "block";
  document.getElementById("bulk-ids").value = ids.join(",");
}

// Ensure resetBulkModal correctly clears inputs and sets radio buttons
function resetBulkModal() {
  // Map field key -> radio button mode name used in the HTML
  const fieldModeMap = {
    expiry: "expiry",
    domainStatus: "domain-status",
    price: "price",
  };

  for (const [field, mode] of Object.entries(fieldModeMap)) {
    // Reset radio button to "No Change"
    const radio = document.querySelector(
      `input[name="${mode}-mode"][value="nochange"]`,
    );
    // Note: radio.value property is buggy for radios; use .checked directly
    if (radio) radio.checked = true;

    // Disable and clear input/select
    const input = document.getElementById(`bulk-${field}`);
    if (input) {
      input.disabled = true;
      input.value = "";
    }
  }
}

// 1. Fix: Ensure closeBulkModal calls reset and update render logic for cache-busting
function closeBulkModal() {
  document.getElementById("bulk-edit-modal").style.display = "none";
  resetBulkModal();
}

async function saveBulkEdit() {
  const ids = document.getElementById("bulk-ids").value.split(",").map(Number);
  const updates = {};
  const summaryList = [];

  const fields = [
    { id: "bulk-expiry", key: "expiry", label: "Expiry" },
    { id: "bulk-domainStatus", key: "domainStatus", label: "Domain Status" },
    { id: "bulk-price", key: "price", label: "Price" },
  ];

  fields.forEach((f) => {
    const input = document.getElementById(f.id);
    if (!input.disabled) {
      updates[f.key] = input.value;
      summaryList.push(`${f.label}: ${input.value}`);
    }
  });

  if (summaryList.length === 0) {
    alert("No changes selected.");
    return;
  }

  if (
    confirm(
      `Confirm bulk update for ${ids.length} domains:\n\n${summaryList.join("\n")}`,
    )
  ) {
    const res = await fetch("/api/domains/bulk-edit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids, updates }),
    });

    if (res.ok) {
      alert("Bulk update successful.");
      await renderDomainTable();
      closeBulkModal();
    } else {
      const err = await res.json();
      alert("Error: " + (err.error || "Update failed"));
    }
  }
}

async function bulkDeleteDomains() {
  const selected = Array.from(selectedDomains);
  if (selected.length === 0) return;

  const names = domains
    .filter((d) => selectedDomains.has(d.id))
    .map((d) => d.domain)
    .join(", ");

  if (
    !confirm(
      `Delete domains?\n\nAre you sure you want to delete:\n${names}\n\nThis action cannot be undone.`,
    )
  ) {
    return;
  }

  for (let id of selected) {
    const res = await fetch(`/api/domains/${id}`, { method: "DELETE" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(
        `Failed to delete domain ID ${id}: ${err.error || "Unknown error"}`,
      );
    }
  }
  clearAllDomainSelections();
  renderDomainTable();
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  div.innerHTML;
}

function openBulkImportModal() {
  bulkImportFiles.campaignHistory = null;
  bulkImportFiles.emailUsage = null;
  bulkImportConflictSelections = {};
  bulkImportState.matching = null;
  document.getElementById("campaign-history-csv").value = "";
  document.getElementById("email-usage-csv").value = "";
  document.getElementById("campaign-history-csv-name").textContent =
    "No file selected";
  document.getElementById("email-usage-csv-name").textContent =
    "No file selected";
  resetBulkImportDerivedState();
  const actionButton = document.getElementById("bulk-import-continue-btn");
  actionButton.disabled = true;
  actionButton.style.display = "inline-block";
  actionButton.textContent = "Review matching";
  actionButton.onclick = submitBulkImport;
  document.getElementById("bulk-import-modal").style.display = "flex";
}

function resetBulkImportDerivedState() {
  bulkImportConflictSelections = {};
  bulkImportState.matching = null;
  document.getElementById("bulk-import-error").textContent = "";
  document.getElementById("bulk-import-review").style.display = "none";
  document.getElementById("bulk-import-summary").textContent = "";
  document.getElementById("bulk-import-unmatched").innerHTML = "";
  document.getElementById("bulk-import-matched").innerHTML = "";
  document.getElementById("bulk-import-invalid").textContent = "";
  document.getElementById("bulk-import-conflicts").innerHTML = "";
  document.getElementById("bulk-import-blocked-reason").textContent = "";
  ["bulk-import-mapping-preview", "bulk-import-eligibility", "bulk-import-result"].forEach((id) => {
    const element = document.getElementById(id);
    element.style.display = "none";
    element.innerHTML = "";
  });
  document.getElementById("bulk-import-confirmation").style.display = "none";
  const actionButton = document.getElementById("bulk-import-continue-btn");
  actionButton.style.display = "inline-block";
  actionButton.textContent = "Review matching";
  actionButton.onclick = submitBulkImport;
  actionButton.disabled = !(bulkImportFiles.campaignHistory && bulkImportFiles.emailUsage);
}

function closeBulkImportModal() {
  document.getElementById("bulk-import-modal").style.display = "none";
  document.getElementById("bulk-import-error").textContent = "";
  document.getElementById("bulk-import-blocked-reason").textContent = "";
}

function updateBulkImportContinueState() {
  const btn = document.getElementById("bulk-import-continue-btn");
  if (btn) {
    btn.disabled = !(
      bulkImportFiles.campaignHistory && bulkImportFiles.emailUsage
    );
  }
}

function handleBulkImportFileChange(type, event) {
  const file = event.target.files[0] || null;
  bulkImportFiles[type] = file;

  const nameEl =
    type === "campaignHistory"
      ? document.getElementById("campaign-history-csv-name")
      : document.getElementById("email-usage-csv-name");
  if (nameEl) {
    nameEl.textContent = file ? file.name : "No file selected";
  }
  resetBulkImportDerivedState();
}

function isCsvFile(file) {
  if (!file) return false;
  const name = (file.name || "").toLowerCase();
  const type = (file.type || "").toLowerCase();
  return name.endsWith(".csv") || type === "text/csv";
}

async function submitBulkImport() {
  const campaignHistory = bulkImportFiles.campaignHistory;
  const emailUsage = bulkImportFiles.emailUsage;

  if (!campaignHistory || !emailUsage) {
    document.getElementById("bulk-import-error").textContent =
      "Both CSV files are required.";
    return;
  }

  if (!isCsvFile(campaignHistory) || !isCsvFile(emailUsage)) {
    document.getElementById("bulk-import-error").textContent =
      "Both files must be CSV files.";
    return;
  }

  const formData = new FormData();
  formData.append("campaign_history_csv", campaignHistory);
  formData.append("email_usage_csv", emailUsage);

  const res = await fetch("/api/domains/import", {
    method: "POST",
    body: formData,
  });

  const data = await res.json().catch(() => ({}));

  if (res.ok) {
    console.log("API RESPONSE:", data);

    bulkImportState.matching = data.matching;


    renderBulkImportReview();
  } else {
    const errorEl = document.getElementById("bulk-import-error");
    errorEl.textContent = data.error || "Import failed.";
    if (data.duplicates && data.duplicates.length) {
      const details = document.createElement("div");
      data.duplicates.forEach((duplicate) => {
        const item = document.createElement("div");
        const rows = duplicate.rows.map((row) => row.row).join(", ");
        item.textContent = `${duplicate.normalized_domain}: CSV rows ${rows}`;
        details.appendChild(item);
      });
      errorEl.appendChild(details);
    }
  }
}

function renderBulkImportReview() {
  updateBulkImportReviewState();
}

function getBulkImportReviewCounts() {
  const matching = bulkImportState.matching;
  if (!matching || !Array.isArray(matching.results)) {
    return null;
  }
  const results = matching.results;
  const unmatched = results.filter((result) => !result.matched);
  const needsAttention = results.filter(
    (result) =>
      result.matched &&
      (result.invalid_email_codes.length > 0 ||
        result.duplicate_campaign_history ||
        (result.requires_conflict_selection &&
          bulkImportConflictSelections[result.normalized_domain] === undefined)),
  );
  const ready = results.filter(
    (result) => result.matched && !needsAttention.includes(result),
  );
  return { results, unmatched, needsAttention, ready };
}

function updateBulkImportReviewState() {
  console.log("DURING RENDER:", bulkImportState.matching);
  if (!bulkImportState.matching) {
    document.getElementById("bulk-import-error").textContent =
      "Bulk import review data is no longer available. Please restart the review.";
    return;
  }
  const { results, unmatched, needsAttention, ready } =
    getBulkImportReviewCounts();
  const invalidCodes = [
    ...new Set(results.flatMap((result) => result.invalid_email_codes)),
  ];
  const conflictResults = results.filter((result) => result.requires_conflict_selection);
  const duplicateResults = results.filter((result) => result.duplicate_campaign_history);
  document.getElementById("bulk-import-summary").textContent =
    `Campaigns found: ${results.length} | Ready: ${ready.length} | ` +
    `Needs attention: ${needsAttention.length} | Unmatched: ${unmatched.length} | ` +
    `Duplicates: ${duplicateResults.length}`;

  document.getElementById("bulk-import-unmatched-summary").textContent =
    `View unmatched domains (${unmatched.length})`;
  document.getElementById("bulk-import-matched-summary").textContent =
    `View matched domains (${results.length - unmatched.length})`;

  const invalid = document.getElementById("bulk-import-invalid");
  invalid.textContent = invalidCodes.length
    ? `⚠ ${invalidCodes.length} email account codes not found: ${invalidCodes.join(", ")}`
    : "No invalid email accounts found.";

  const conflicts = document.getElementById("bulk-import-conflicts");
  conflicts.innerHTML = "";
  conflictResults
    .forEach((result) => {
      const item = document.createElement("div");
      item.textContent = `⚠ ${result.domain}: multiple records found. Select the current record:`;
      result.email_usage_records.forEach((record, index) => {
        const label = document.createElement("label");
        label.style.display = "block";
        const input = document.createElement("input");
        input.type = "radio";
        input.name = `bulk-import-conflict-${result.normalized_domain}`;
        input.checked = bulkImportConflictSelections[result.normalized_domain] === index;
        input.onchange = () => {
          bulkImportConflictSelections[result.normalized_domain] = index;
          updateBulkImportReviewState();
        };
        label.appendChild(input);
        label.appendChild(
          document.createTextNode(
            ` Record ${index + 1}: ${record.email_usage_codes.join(", ")}`
          )
        );
        item.appendChild(label);
      });
      conflicts.appendChild(item);
    });
  duplicateResults.forEach((result) => {
    const item = document.createElement("div");
    const rows = (result.duplicate_campaign_history_rows || []).map((row) => row.row).join(", ");
    item.textContent = `⚠ ${result.domain}: duplicate Campaign History domain (CSV rows ${rows})`;
    conflicts.appendChild(item);
  });

  const unmatchedList = document.getElementById("bulk-import-unmatched");
  unmatchedList.innerHTML = "";
  results
    .filter((result) => !result.matched)
    .forEach((result) => {
      const item = document.createElement("li");
      item.textContent = result.domain;
      unmatchedList.appendChild(item);
    });

  const matched = document.getElementById("bulk-import-matched");
  matched.innerHTML = "";
  results
    .filter((result) => result.matched)
    .forEach((result) => {
      const item = document.createElement("div");
      item.textContent = `✓ ${result.domain} ${result.email_usage_codes.length} email accounts`;
      if (result.requires_conflict_selection) {
        item.textContent = `⚠ ${result.domain} (unresolved email record conflict)`;
      } else if (result.invalid_email_codes.length) {
        item.textContent += ` (invalid: ${result.invalid_email_codes.join(", ")})`;
      }
      matched.appendChild(item);
    });

  document.getElementById("bulk-import-review").style.display = "block";
  const button = document.getElementById("bulk-import-continue-btn");
  button.disabled = ready.length === 0;
  button.textContent = `Continue with ${ready.length} ready campaigns`;
  button.onclick = continueBulkImportReview;
  document.getElementById("bulk-import-blocked-reason").textContent =
    ready.length === 0
      ? "No campaigns are ready to continue."
      : `${needsAttention.length} campaigns will be skipped until their issues are resolved.`;
}

function continueBulkImportReview() {
  console.log("BEFORE CONTINUE:", bulkImportState.matching);
  const counts = getBulkImportReviewCounts();
  if (!counts) {
    document.getElementById("bulk-import-error").textContent =
      "Bulk import review data is no longer available. Please restart the review.";
    return;
  }
  const { ready } = counts;
  if (ready.length > 0) {
    const formData = new FormData();
    formData.append("campaign_history_csv", bulkImportFiles.campaignHistory);
    formData.append("email_usage_csv", bulkImportFiles.emailUsage);
    formData.append("preview_mapping", "1");
    formData.append("conflict_selections", JSON.stringify(bulkImportConflictSelections));
    fetch("/api/domains/import", { method: "POST", body: formData })
      .then((response) => response.json().then((data) => ({ response, data })))
      .then(({ response, data }) => {
        if (!response.ok) {
          document.getElementById("bulk-import-error").textContent = data.error || "Mapping preview failed.";
          return;
        }
        renderCampaignMappingPreview(data.mapping);
        renderImportEligibility(data.eligibility);
      });
  }
}

function renderImportEligibility(eligibility) {
  const container = document.getElementById("bulk-import-eligibility");
  const summaryOrder = ["READY_TO_IMPORT", "BLOCKED_NEEDS_ATTENTION", "INVALID_SOURCE_DATA", "SOLD_SOURCE_MARKER", "SKIP_UNMATCHED", "SKIP_EXTERNALLY_HANDLED", "SKIP_NO_CURRENT_CAMPAIGN_EVIDENCE", "SKIP_ALREADY_PRESENT"];
  const categoryOrder = ["BLOCKED_NEEDS_ATTENTION", "INVALID_SOURCE_DATA", "SKIP_UNMATCHED", "SOLD_SOURCE_MARKER", "SKIP_EXTERNALLY_HANDLED", "SKIP_NO_CURRENT_CAMPAIGN_EVIDENCE", "SKIP_ALREADY_PRESENT", "READY_TO_IMPORT"];
  container.innerHTML = "<h4>Final Import Eligibility</h4>";
  const summary = document.createElement("div");
  summary.textContent = summaryOrder.map((key) => `${key}: ${eligibility.summary[key] || 0}`).join(" | ");
  container.appendChild(summary);
  const details = document.createElement("details");
  const label = document.createElement("summary");
  label.textContent = `View eligibility details (${eligibility.results.length})`;
  details.appendChild(label);

  const grouped = new Map(categoryOrder.map((category) => [category, []]));
  eligibility.results.forEach((item) => {
    if (!grouped.has(item.final_eligibility)) {
      grouped.set(item.final_eligibility, []);
    }
    grouped.get(item.final_eligibility).push(item);
  });

  categoryOrder
    .concat([...grouped.keys()].filter((category) => !categoryOrder.includes(category)))
    .forEach((category) => {
      const items = grouped.get(category) || [];
      const section = document.createElement("details");
      section.dataset.eligibilityCategory = category;
      section.open = category !== "READY_TO_IMPORT" && items.length > 0;

      const sectionSummary = document.createElement("summary");
      sectionSummary.textContent = `${category} (${items.length}) `;
      const copyButton = document.createElement("button");
      copyButton.type = "button";
      copyButton.textContent = "Copy";
      copyButton.disabled = items.length === 0;
      copyButton.style.marginLeft = "8px";
      copyButton.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        copyImportEligibilityCategory(category, items, copyButton);
      });
      sectionSummary.appendChild(copyButton);
      section.appendChild(sectionSummary);

      if (items.length) {
        const list = document.createElement("div");
        items.forEach((item) => {
          const row = document.createElement("div");
          row.style.marginTop = "8px";
          row.textContent = formatImportEligibilityLine(item);
          list.appendChild(row);
        });
        section.appendChild(list);
      }
      details.appendChild(section);
    });

  container.appendChild(details);
  container.style.display = "block";
  const ready = eligibility.summary.READY_TO_IMPORT || 0;
  const button = document.getElementById("bulk-import-continue-btn");
  button.textContent = `${ready} campaigns ready for import`;
  button.disabled = ready === 0;
  button.onclick = () => showBulkImportConfirmation(ready);
  document.getElementById("bulk-import-blocked-reason").textContent = ready === 0 ? "No campaigns are currently eligible." : "Only eligible campaigns will proceed; others remain skipped or blocked.";
}

function formatImportEligibilityLine(item) {
  let line = `${item.domain} | ${item.final_eligibility} | ${item.mapping_classification} | ` +
    `${item.proposed_status || ""} | Sequence ${item.proposed_current_sequence} | Price ${item.proposed_current_price} | ` +
    `Last Contact ${item.last_contact || "UNKNOWN"} | Start ${item.start_date || "UNKNOWN_START_DATE"} | ` +
    `Email Accounts: ${(item.validated_campaign_email_codes || []).join(", ") || "NONE"}`;
  const reasons = [item.classification_reason].filter(Boolean)
    .concat(item.blocking_reasons || [], item.warnings || []);
  if (reasons.length) line += ` | ${reasons.join("; ")}`;
  return line;
}

async function copyImportEligibilityCategory(category, items, button) {
  const text = `${category}: ${items.length}\n\n${items.map(formatImportEligibilityLine).join("\n")}`;
  try {
    if (typeof navigator !== "undefined" && navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      const copied = document.execCommand && document.execCommand("copy");
      textarea.remove();
      if (!copied) throw new Error("Copy is unavailable");
    }
    const originalLabel = button.textContent;
    button.textContent = "Copied";
    setTimeout(() => { button.textContent = originalLabel; }, 1200);
  } catch (error) {
    button.textContent = "Copy failed";
    setTimeout(() => { button.textContent = "Copy"; }, 1200);
  }
}

function showBulkImportConfirmation(ready) {
  const confirmation = document.getElementById("bulk-import-confirmation");
  document.getElementById("bulk-import-confirmation-text").textContent =
    `Import ${ready} eligible campaigns? Blocked, invalid, sold, unmatched, and already-present records will remain untouched.`;
  confirmation.style.display = "block";
  document.getElementById("bulk-import-confirm-btn").textContent = `Import ${ready} campaigns`;
  document.getElementById("bulk-import-confirm-btn").onclick = submitFinalBulkImport;
  document.getElementById("bulk-import-cancel-confirm-btn").onclick = () => { confirmation.style.display = "none"; };
}

async function submitFinalBulkImport() {
  const confirmation = document.getElementById("bulk-import-confirmation");
  const importButton = document.getElementById("bulk-import-confirm-btn");
  importButton.disabled = true;
  document.getElementById("bulk-import-cancel-confirm-btn").disabled = true;
  importButton.textContent = "Importing...";
  const formData = new FormData();
  formData.append("campaign_history_csv", bulkImportFiles.campaignHistory);
  formData.append("email_usage_csv", bulkImportFiles.emailUsage);
  formData.append("conflict_selections", JSON.stringify(bulkImportConflictSelections));
  try {
    const response = await fetch("/api/domains/import/final", { method: "POST", body: formData });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Final import failed.");
    renderBulkImportResult(data.results || []);
    confirmation.style.display = "none";
  } catch (error) {
    document.getElementById("bulk-import-error").textContent = error.message;
    importButton.disabled = false;
    document.getElementById("bulk-import-cancel-confirm-btn").disabled = false;
    importButton.textContent = "Retry import";
  }
}

function renderBulkImportResult(results) {
  const counts = { IMPORTED: 0, SKIPPED_ALREADY_PRESENT: 0, SKIPPED: 0, FAILED: 0 };
  results.forEach((result) => { counts[result.status] = (counts[result.status] || 0) + 1; });
  const container = document.getElementById("bulk-import-result");
  container.innerHTML = "<strong>Import Complete</strong>";
  const summary = document.createElement("div");
  summary.textContent = `Imported: ${counts.IMPORTED} | Already present: ${counts.SKIPPED_ALREADY_PRESENT} | Skipped: ${counts.SKIPPED} | Failed: ${counts.FAILED}`;
  container.appendChild(summary);
  results.filter((result) => result.status === "FAILED").forEach((result) => {
    const row = document.createElement("div");
    row.textContent = `${result.domain} - ${result.reason || "Unknown failure"}`;
    container.appendChild(row);
  });
  container.style.display = "block";
  const button = document.getElementById("bulk-import-continue-btn");
  button.style.display = "none";
  const cancel = document.querySelector("#bulk-import-modal button[onclick=\"closeBulkImportModal()\"]");
  if (cancel) { cancel.textContent = "Close"; cancel.onclick = () => { closeBulkImportModal(); renderDomainTable(); }; }
}

function renderCampaignMappingPreview(mapping) {
  document.querySelectorAll("#bulk-import-review details").forEach((details) => {
    details.open = false;
  });
  const container = document.getElementById("bulk-import-mapping-preview");
  container.innerHTML = "<h4>Campaign Mapping Preview</h4>";
  const summary = document.createElement("div");
  summary.textContent = Object.entries(mapping.summary)
    .map(([classification, count]) => `${classification}: ${count}`)
    .join(" | ");
  container.appendChild(summary);
  const details = document.createElement("details");
  details.open = false;
  const label = document.createElement("summary");
  label.textContent = `View mapping details (${mapping.results.length})`;
  details.appendChild(label);
  const list = document.createElement("div");
  mapping.results.forEach((item) => {
    const row = document.createElement("div");
    row.style.marginTop = "8px";
    row.textContent = `${item.domain} | ${item.classification} | ${item.proposed_status || ""} | ` +
      `Sequence ${item.proposed_current_sequence} | Price ${item.proposed_current_price} | ` +
      `Last Contact ${item.last_contact || "UNKNOWN"} | Start ${item.start_date || "UNKNOWN_START_DATE"}` +
      `${item.handled_by ? ` | Handled By ${item.handled_by}` : ""}` +
      `${item.classification_reason ? ` | ${item.classification_reason}` : ""}`;
    if (item.warnings.length) row.textContent += ` | ${item.warnings.join("; ")}`;
    list.appendChild(row);
  });
  details.appendChild(list);
  container.appendChild(details);
  container.style.display = "block";
}

// Update domains.js to support the new selective edit modal
// 2. Update logic in domains.js
function toggleField(id) {
  const el = document.getElementById(id);
  el.disabled = !el.disabled;
  if (!el.disabled) el.focus();
}

async function saveDomain() {
  const id = document.getElementById("edit-id").value;
  const updates = {};
  const summary = [];

  const fields = [
    { id: "form-domain", key: "domain" },
    { id: "form-expiry", key: "expiry" },
    { id: "form-status", key: "status" },
  ];

  fields.forEach((f) => {
    const input = document.getElementById(f.id);
    if (!input.disabled) {
      updates[f.key] = input.value;
      summary.push(`${f.key}: ${input.value}`);
    }
  });

  // Ensure domain is included for POST
  if (!id) {
    updates.domain = document.getElementById("form-domain").value;
    if (!updates.domain) {
      alert("Domain name is required.");
      return;
    }
  }

  if (summary.length === 0 && id) {
    alert("No changes made.");
    return;
  }

  // Determine method/URL
  const method = id ? "PUT" : "POST";
  const url = id ? `/api/domains/${id}` : "/api/domains";

  // Update Domain / Campaign
  const res = await fetch(url, {
    method: method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });

  if (res.ok) {
    alert(`Domain ${id ? "updated" : "added"} successfully.`);
    renderDomainTable();
    closeModal();
  } else {
    let errorMsg = "Unknown error";
    try {
      const err = await res.json();
      errorMsg = err.error || errorMsg;
    } catch (e) {
      // Fallback if not JSON
    }
    alert("Save failed: " + errorMsg);
  }
}

// 3. Fix modal population in domains.js
function openModal(id = null) {
  document.getElementById("domain-modal").style.display = "block";
  const modalTitle = document.getElementById("modal-title");
  const domainInput = document.getElementById("form-domain");
  const c = domains.find((x) => x.id === id);

  const statusEl = document.getElementById("form-status");
  if (c) {
    modalTitle.innerText = "Edit Domain";
    document.getElementById("edit-id").value = c.id;
    domainInput.value = c.domain;
    domainInput.readOnly = true;
    document.getElementById("form-expiry").value = c.expiry || "";

    statusEl.value = c.status || "";
    statusEl.disabled = true;
  } else {
    modalTitle.innerText = "Add Domain";
    document.getElementById("edit-id").value = "";
    domainInput.value = "";
    domainInput.readOnly = false;
    document.getElementById("form-expiry").value = "";

    statusEl.value = "";
    statusEl.disabled = false;
  }
}

// Removed validateEmailAccounts and recheckAccounts
function closeModal() {
  document.getElementById("domain-modal").style.display = "none";
}

async function openActionModal() {
  const ids = Array.from(selectedDomains);
  if (ids.length !== 1) return;
  document.getElementById("action-modal").style.display = "block";
  setActionMode("new");
}

function closeActionModal() {
  document.getElementById("action-modal").style.display = "none";
  emailPickerStates.delete("new-action-email-picker");
  emailPickerStates.delete("edit-action-email-picker");
}

function escapeEmailPickerHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function orderEmailPickerAccounts(accounts) {
  return [...(accounts || [])].sort((left, right) => {
    const leftOrder = Number(left.order ?? left.profile_order ?? Number.MAX_SAFE_INTEGER);
    const rightOrder = Number(right.order ?? right.profile_order ?? Number.MAX_SAFE_INTEGER);
    if (leftOrder !== rightOrder) return leftOrder - rightOrder;
    return String(left.code).localeCompare(String(right.code));
  });
}

async function loadEmailPickerAccounts() {
  if (allEmailAccounts.length > 0) return allEmailAccounts;

  try {
    const response = await fetch("/api/email-accounts");
    const accounts = await response.json();
    if (Array.isArray(accounts)) allEmailAccounts = accounts;
  } catch (_error) {
    // Leave the picker empty if account metadata is temporarily unavailable.
  }
  return allEmailAccounts;
}

function emailPickerSectionMarkup(pickerId) {
  return `
    <div class="form-group email-picker-section">
      <div class="email-picker-label-row">
        <span class="email-picker-label">Email Used:</span>
        <span class="email-picker-controls">
          <button type="button" class="btn btn-subtle btn-compact" id="${pickerId}-edit">Edit</button>
          <button type="button" class="btn btn-subtle btn-compact" id="${pickerId}-save" hidden>Save</button>
          <button type="button" class="btn btn-subtle btn-compact" id="${pickerId}-cancel" hidden>Cancel</button>
        </span>
      </div>
      <div id="${pickerId}" class="email-account-picker" role="group" aria-label="Email accounts"></div>
      <div id="${pickerId}-summary" class="email-picker-summary" aria-live="polite"></div>
    </div>
  `;
}

function emailPickerCodesForState(state, editing = state.editing) {
  const selectedCodes = editing ? state.editingCodes : state.confirmedCodes;
  const orderedCodes = state.accounts
    .filter((account) => selectedCodes.has(String(account.code)))
    .map((account) => String(account.code));
  const knownCodes = new Set(orderedCodes);
  for (const code of selectedCodes) {
    if (!knownCodes.has(code)) orderedCodes.push(code);
  }
  return orderedCodes;
}

function buildEmailPickerMarkup(accounts, selectedCodes, editing = false) {
  const selected = new Set(Array.from(selectedCodes || [], (code) => String(code)));
  return orderEmailPickerAccounts(accounts)
    .map((account) => {
      const code = String(account.code);
      const safeCode = escapeEmailPickerHtml(code);
      const isSelected = selected.has(code);
      const isDisabled = account.enabled === false;
      const classes = [
        "email-picker-cell",
        isSelected ? "email-picker-cell-selected" : "",
        isDisabled ? "email-picker-cell-disabled" : "",
      ].filter(Boolean).join(" ");

      if (isDisabled) {
        const removeButton = isSelected && editing
          ? `<button type="button" class="email-picker-remove" data-remove-email-code="${safeCode}" aria-label="Remove disabled historical account ${safeCode}">&times;</button>`
          : "";
        if (!isSelected) {
          return `<button type="button" class="${classes}" data-email-code="${safeCode}" disabled aria-disabled="true" title="Disabled email account">${safeCode}</button>`;
        }
        return `<span class="${classes}" data-email-code="${safeCode}" aria-disabled="true" title="Disabled email account">${safeCode}${removeButton}</span>`;
      }

      const lockedAttributes = editing ? "" : ' disabled aria-disabled="true"';
      return `<button type="button" class="${classes}" data-email-code="${safeCode}" aria-pressed="${isSelected}"${lockedAttributes}>${safeCode}</button>`;
    })
    .join("");
}

function updateEmailPickerSummary(pickerId) {
  const summary = document.getElementById(`${pickerId}-summary`);
  if (!summary) return;
  const state = emailPickerStates.get(pickerId);
  if (!state) return;
  const codes = emailPickerCodesForState(state);
  summary.textContent = codes.length ? `Selected: ${codes.join(", ")}` : "No email accounts selected";
}

function updateEmailPickerControls(pickerId) {
  const state = emailPickerStates.get(pickerId);
  if (!state) return;

  const editButton = document.getElementById(`${pickerId}-edit`);
  const saveButton = document.getElementById(`${pickerId}-save`);
  const cancelButton = document.getElementById(`${pickerId}-cancel`);
  if (editButton) editButton.hidden = state.editing;
  if (saveButton) saveButton.hidden = !state.editing;
  if (cancelButton) cancelButton.hidden = !state.editing;
}

function renderEmailPickerView(pickerId) {
  const state = emailPickerStates.get(pickerId);
  if (!state) return;

  const picker = document.getElementById(pickerId);
  if (picker) {
    picker.innerHTML = buildEmailPickerMarkup(
      state.accounts,
      emailPickerCodesForState(state),
      state.editing,
    );
    if (picker.querySelectorAll) {
      picker.querySelectorAll("button[data-email-code]").forEach((button) => {
        button.addEventListener("click", () => {
          toggleEmailPickerCode(pickerId, button.dataset.emailCode);
        });
      });
      picker.querySelectorAll("button[data-remove-email-code]").forEach((button) => {
        button.addEventListener("click", () => {
          removeDisabledEmailPickerCode(pickerId, button.dataset.removeEmailCode);
        });
      });
    }
  }

  updateEmailPickerControls(pickerId);
  updateEmailPickerSummary(pickerId);
}

function attachEmailPickerControls(pickerId) {
  const editButton = document.getElementById(`${pickerId}-edit`);
  const saveButton = document.getElementById(`${pickerId}-save`);
  const cancelButton = document.getElementById(`${pickerId}-cancel`);
  if (editButton) editButton.onclick = () => startEmailPickerEdit(pickerId);
  if (saveButton) saveButton.onclick = () => saveEmailPickerEdit(pickerId);
  if (cancelButton) cancelButton.onclick = () => cancelEmailPickerEdit(pickerId);
}

function updateEmailPickerButtons(pickerId) {
  renderEmailPickerView(pickerId);
}

function renderEmailAccountPicker(pickerId, accounts, persistedCodes, selectionSource = "history") {
  const orderedAccounts = orderEmailPickerAccounts(accounts);
  const original = new Set(Array.from(persistedCodes || [], (code) => String(code)));
  emailPickerStates.set(pickerId, {
    accounts: orderedAccounts,
    originalCodes: new Set(original),
    confirmedCodes: new Set(original),
    editingCodes: new Set(original),
    selectionSource,
    emailSelectionExplicitlyEdited: false,
    editing: false,
  });

  attachEmailPickerControls(pickerId);
  renderEmailPickerView(pickerId);
}

function startEmailPickerEdit(pickerId) {
  const state = emailPickerStates.get(pickerId);
  if (!state || state.editing) return;

  state.editingCodes = new Set(state.confirmedCodes);
  state.editing = true;
  renderEmailPickerView(pickerId);
}

function emailPickerConfirmationMessage(fromCodes, toCodes) {
  const formatCodes = (codes) => codes.length ? codes.join(", ") : "None";
  return `Change Email Used?\n\nFrom: ${formatCodes(fromCodes)}\nTo: ${formatCodes(toCodes)}\n\nConfirm this local change?`;
}

function saveEmailPickerEdit(pickerId) {
  const state = emailPickerStates.get(pickerId);
  if (!state || !state.editing) return false;

  const fromCodes = emailPickerCodesForState(state, false);
  const toCodes = emailPickerCodesForState(state, true);
  if (!confirm(emailPickerConfirmationMessage(fromCodes, toCodes))) return false;

  state.confirmedCodes = new Set(state.editingCodes);
  state.editingCodes = new Set(state.confirmedCodes);
  state.emailSelectionExplicitlyEdited = true;
  state.editing = false;
  renderEmailPickerView(pickerId);
  return true;
}

function cancelEmailPickerEdit(pickerId) {
  const state = emailPickerStates.get(pickerId);
  if (!state || !state.editing) return;

  state.editingCodes = new Set(state.confirmedCodes);
  state.editing = false;
  renderEmailPickerView(pickerId);
}

function getEmailPickerEditingCodes(pickerId) {
  const state = emailPickerStates.get(pickerId);
  return state ? emailPickerCodesForState(state, true) : [];
}

function getEmailPickerSelectedCodes(pickerId) {
  const state = emailPickerStates.get(pickerId);
  return state ? emailPickerCodesForState(state, false) : [];
}

function toggleEmailPickerCode(pickerId, code) {
  const state = emailPickerStates.get(pickerId);
  const account = state?.accounts.find((item) => item.code === code);
  if (!state || !state.editing || !account || account.enabled === false) return;

  if (state.editingCodes.has(code)) state.editingCodes.delete(code);
  else state.editingCodes.add(code);
  updateEmailPickerButtons(pickerId);
}

function removeDisabledEmailPickerCode(pickerId, code) {
  const state = emailPickerStates.get(pickerId);
  const account = state?.accounts.find((item) => item.code === code);
  if (!state || !state.editing || !account || account.enabled !== false) return;

  state.editingCodes.delete(code);
  updateEmailPickerButtons(pickerId);
}

async function setActionMode(mode) {
  editActionLoadRequestId += 1;
  const container = document.getElementById("action-mode-content");
  const record = selectedDomainRecord();
  const campaignId = campaignIdForDomainRecord(record);
  const campaign = record;
  if (campaignId == null) {
    container.innerHTML = "<p>This domain has no campaign.</p>";
    return;
  }

  const tabNew = document.getElementById("tab-new");
  const tabEdit = document.getElementById("tab-edit");

  // Add Domain Header
  const modalHeader = document.querySelector("#action-modal h3");
  if (campaign) {
    modalHeader.innerHTML = `<div>${campaign.domain}</div><div style="font-size: 0.8em; font-weight: normal;">Campaign Action</div>`;
  }

  if (tabNew && tabEdit) {
    if (mode === "new") {
      tabNew.style.background = "#007bff";
      tabNew.style.color = "white";
      tabNew.style.fontWeight = "bold";
      tabEdit.style.background = "#e0e0e0";
      tabEdit.style.color = "black";
      tabEdit.style.fontWeight = "normal";
    } else {
      tabEdit.style.background = "#007bff";
      tabEdit.style.color = "white";
      tabEdit.style.fontWeight = "bold";
      tabNew.style.background = "#e0e0e0";
      tabNew.style.color = "black";
      tabNew.style.fontWeight = "normal";
    }
  }

  if (mode === "new") {
    // Determine default emails
    let exactEmails = [];
    let hasFirstFollowUp = false;
    const defaultActionDate = businessTodayIso || formatDateInputValue(new Date());
    if (campaign && campaign.hasValues) {
      // Fetch last action's emails
      const res = await fetch(`/api/campaigns/${campaignId}/actions`);
      const history = await res.json();
      hasFirstFollowUp = Array.isArray(history) && history.some(
        (h) => h.action_type === "FIRST_FOLLOW_UP",
      );
      if (history.length > 0) {
        const lastAction = history[history.length - 1];
        const emailRes = await fetch(
          `/api/campaigns/${campaignId}/actions/${lastAction.sequence}/emails`,
        );
        const usedEmails = await emailRes.json();
        if (Array.isArray(usedEmails)) exactEmails = usedEmails;
      }
    }
    // New Action uses the exact latest usage when recorded.  Imported
    // campaigns have no per-action mappings, so the operational endpoint
    // safely supplies their campaign-level associations instead.
    if (!exactEmails.length) {
      try {
        const operationalRes = await fetch(
          `/api/campaigns/${campaignId}/operational-emails`,
        );
        const operational = await operationalRes.json();
        if (operationalRes.ok && Array.isArray(operational.codes)) {
          exactEmails = operational.codes;
        }
      } catch (_error) {
        // Leave the display blank if the optional operational lookup fails.
      }
    }
    const pickerAccounts = await loadEmailPickerAccounts();
    const firstFollowUpOption = hasFirstFollowUp
      ? ""
      : '<option value="FIRST_FOLLOW_UP">First Follow-up</option>';

    container.innerHTML = `
    ${emailPickerSectionMarkup("new-action-email-picker")}
    <div class="form-group">
      <label>Action Type:
          <select id="action-type">
            ${
              campaign && campaign.hasValues
                ? `
            <option value="">-- Select Action --</option>
            ${firstFollowUpOption}
            <option value="FOLLOW_UP">Follow-up</option>
            <option value="PRICE_REDUCTION">Price Reduction</option>
            `
                : `<option value="FIRST_OUTREACH">First Outreach</option>`
            }
        </select>
        </label>
      </div>
      <div class="form-group">
      <label>Campaign Status:
          <select id="action-status">
            <option value="ACTIVE" selected>Active</option>
            <option value="DORMANT">Dormant</option>
            <option value="RESTING">Resting</option>
        </select>
      </label>
    </div>
    <div class="form-group">
        <label>Date: <input type="date" id="action-date" value="${defaultActionDate}"></label>
    </div>
    <div class="form-group">
        <label>Price: <input type="number" id="action-price"></label>
    </div>
    <div class="form-group">
        <label>Notes: <textarea id="action-notes"></textarea></label>
      </div>
      <button id="save-new-action-btn" type="button" onclick="saveNewAction(${campaignId})">Save Action</button>
    `;
    renderEmailAccountPicker("new-action-email-picker", pickerAccounts, exactEmails);
  } else {
    // Edit Mode
    const res = await fetch(`/api/campaigns/${campaignId}/actions`);
    const history = await res.json();

    let options = history
      .map(
        (h) =>
          `<option value="${h.sequence}">Sequence ${h.sequence} (${h.action_type})</option>`,
      )
      .join("");

    container.innerHTML = `
      <div class="form-group">
        <label>Sequence:
          <select id="edit-seq-select" onchange="loadActionForEdit(${campaignId})">
            <option value="">-- Select Sequence --</option>
            ${options}
          </select>
        </label>
      </div>
      <div id="edit-action-fields"></div>
    `;
  }
}

async function loadActionForEdit(campaignId) {
  const requestId = ++editActionLoadRequestId;
  const seq = document.getElementById("edit-seq-select").value;
  if (!seq) return;
  const res = await fetch(`/api/campaigns/${campaignId}/actions/${seq}`);
  const data = await res.json();
  if (requestId !== editActionLoadRequestId) return;
  const usedEmails = Array.isArray(data.email_codes) ? data.email_codes : [];
  const emailSource = data.email_source || "none";
  const pickerAccounts = await loadEmailPickerAccounts();
  if (requestId !== editActionLoadRequestId) return;

  const campaign = domains.find((d) => d.campaign_id == campaignId);
  const currentStatus = campaign ? campaign.status : "DORMANT";
  const container = document.getElementById("edit-action-fields");
  container.innerHTML = `
    <div class="form-group">
      <label>Action Type:
        <select id="edit-type">
          <option value="FIRST_OUTREACH" ${data.action_type === "FIRST_OUTREACH" ? "selected" : ""}>First Outreach</option>
          <option value="FIRST_FOLLOW_UP" ${data.action_type === "FIRST_FOLLOW_UP" ? "selected" : ""}>First Follow-up</option>
          <option value="FOLLOW_UP" ${data.action_type === "FOLLOW_UP" ? "selected" : ""}>Follow-up</option>
          <option value="PRICE_REDUCTION" ${data.action_type === "PRICE_REDUCTION" ? "selected" : ""}>Price Reduction</option>
        </select>
      </label>
    </div>
    <div class="form-group">
      <label>Campaign Status:
        <select id="edit-status">
          <option value="DORMANT" ${currentStatus === "DORMANT" ? "selected" : ""}>Dormant</option>
          <option value="ACTIVE" ${currentStatus === "ACTIVE" ? "selected" : ""}>Active</option>
          <option value="RESTING" ${currentStatus === "RESTING" ? "selected" : ""}>Resting</option>
        </select>
      </label>
    </div>
    <div class="form-group">
      <label>Date: <input type="date" id="edit-date" value="${formatDateInputValue(data.action_date)}"></label>
    </div>
    <div class="form-group">
      <label>Price: <input type="number" id="edit-price" value="${data.price_after}"></label>
    </div>
    ${emailPickerSectionMarkup("edit-action-email-picker")}
    <div class="form-group">
      <label>Notes: <textarea id="edit-notes">${data.notes || ""}</textarea></label>
    </div>
    <button id="save-edit-action-btn" type="button" onclick="saveEditAction(${campaignId}, ${seq})">Save Changes</button>
  `;
  renderEmailAccountPicker(
    "edit-action-email-picker",
    pickerAccounts,
    usedEmails,
    emailSource,
  );
}

async function saveNewAction(campaignId) {
  const saveButton = document.getElementById("save-new-action-btn");
  if (saveButton && saveButton.disabled) return;

  const emailCodes = getEmailPickerSelectedCodes("new-action-email-picker");

  if (emailCodes.length === 0) {
    alert(
      "No email account was entered. Please select at least one email account before saving.",
    );
    return;
  }

  if (saveButton) {
    saveButton.disabled = true;
    saveButton.textContent = "Saving…";
  }

  const payload = {
    action_type: document.getElementById("action-type").value,
    action_date: formatDateInputValue(document.getElementById("action-date").value),
    price_after: document.getElementById("action-price").value,
    notes: document.getElementById("action-notes").value,
    campaign_status: document.getElementById("action-status").value,
    email_codes: emailCodes,
  };

  try {
    const res = await fetch(`/api/campaigns/${campaignId}/actions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const result = await res.json().catch(() => ({}));
    if (res.ok) {
      alert("Action saved!");
      closeActionModal();
      try {
        await renderDomainTable();
      } catch (_error) {
        // The action response was already confirmed; leave the saved state intact.
      }
    } else {
      alert(result.error || "Unable to save action. Please review the form and try again.");
    }
  } catch (_error) {
    alert(
      "Could not confirm whether the action was saved. Refresh the campaign before trying again.",
    );
  } finally {
    if (saveButton) {
      saveButton.disabled = false;
      saveButton.textContent = "Save Action";
    }
  }
}

async function saveEditAction(campaignId, seq) {
  const saveButton = document.getElementById("save-edit-action-btn");
  if (saveButton && saveButton.disabled) return;

  const emailCodes = getEmailPickerSelectedCodes("edit-action-email-picker");
  const emailPickerState = emailPickerStates.get("edit-action-email-picker");
  const emailSelectionExplicitlyEdited = Boolean(
    emailPickerState?.emailSelectionExplicitlyEdited,
  );

  if (emailSelectionExplicitlyEdited && emailCodes.length === 0) {
    alert(
      "No email account was entered. Please select at least one email account before saving.",
    );
    return;
  }

  if (saveButton) {
    saveButton.disabled = true;
    saveButton.textContent = "Saving…";
  }

  const payload = {
    action_type: document.getElementById("edit-type").value,
    action_date: formatDateInputValue(document.getElementById("edit-date").value),
    price_after: document.getElementById("edit-price").value,
    notes: document.getElementById("edit-notes").value,
    campaign_status: document.getElementById("edit-status").value,
  };
  if (emailSelectionExplicitlyEdited) payload.email_codes = emailCodes;

  try {
    const res = await fetch(`/api/campaigns/${campaignId}/actions/${seq}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const result = await res.json().catch(() => ({}));
    if (res.ok) {
      alert("Changes saved!");
      closeActionModal();
      // Re-fetch domain table to update status, cache-bust
      try {
        await renderDomainTable();
      } catch (_error) {
        // The action response was already confirmed; leave the saved state intact.
      }
    } else {
      alert(result.error || "Unable to save action changes. Please review the form and try again.");
    }
  } catch (_error) {
    alert(
      "Could not confirm whether the action was saved. Refresh the campaign before trying again.",
    );
  } finally {
    if (saveButton) {
      saveButton.disabled = false;
      saveButton.textContent = "Save Changes";
    }
  }
}

// Render the table on page load
document.addEventListener("DOMContentLoaded", async () => {
  await renderDomainTable();

  const urlParams = new URLSearchParams(window.location.search);
  const historyId = urlParams.get("history_id");
  const domain = urlParams.get("domain");

  if (historyId && domain) {
    // History modal expects numeric ID, found in domains array
    openHistoryModal(Number(historyId), domain);
  }
});
