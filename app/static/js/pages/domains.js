// 1. domains.js
let selectedDomains = new Set();
let searchTerm = "";
let currentSort = { key: "daysSince", direction: "asc" };
let domains = [];

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
  const today = new Date();

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
    } else if (["expiry", "lastContact"].includes(key)) {
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
  // 1. Fetch
  domains = await fetchDomains();
  console.log("Domains data loaded:", domains);

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

  // Update Select All checkbox state based on filtered results
  const selectAll = document.getElementById("select-all-checkbox");
  if (selectAll) {
    const selectedCount = filtered.filter((c) =>
      selectedDomains.has(c.id),
    ).length;
    selectAll.checked =
      filtered.length > 0 && selectedCount === filtered.length;
    selectAll.indeterminate =
      selectedCount > 0 && selectedCount < filtered.length;
  }

  body.innerHTML = filtered
    .map((c) => {
      const expiryDate = c.expiry ? new Date(c.expiry) : null;
      const lastContactDate = c.lastContact ? new Date(c.lastContact) : null;
      const today = new Date();

      const daysLeft = expiryDate
        ? Math.floor((expiryDate - today) / (1000 * 60 * 60 * 24))
        : "N/A";
      const daysSince = lastContactDate
        ? Math.floor((today - lastContactDate) / (1000 * 60 * 60 * 24))
        : "N/A";
      return `
        <tr class="${selectedDomains.has(c.id) ? "selected" : ""}">
            <td><input type="checkbox" ${selectedDomains.has(c.id) ? "checked" : ""} onchange="toggleDomainSelection(${c.id})"></td>
            <td onclick="openHistoryModal(${c.id}, '${c.domain}')" style="cursor:pointer; text-decoration: underline;">${c.domain}</td>
            <td>${c.expiry || "N/A"}</td>
            <td>${daysLeft} days</td>
            <td>${c.status || "Dormant"}</td>
            <td>${c.price ? `$${c.price}` : "N/A"}</td>
            <td>${daysSince} days</td>
            <td>${c.hasValues ? c.seq : "Not started"}</td>
            <td>${c.lastAction || "N/A"}</td>
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
      <td>${new Date(h.date).toLocaleString()}</td>
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

function toggleDomainSelection(id) {
  if (selectedDomains.has(id)) selectedDomains.delete(id);
  else selectedDomains.add(id);
  updateDomainActionBar();
  renderDomainTable();
}

function toggleSelectAll(masterCheckbox) {
  const filtered = domains.filter(
    (c) => c.domain && c.domain.toLowerCase().includes(searchTerm),
  );

  if (masterCheckbox.checked) {
    filtered.forEach((c) => selectedDomains.add(c.id));
  } else {
    filtered.forEach((c) => selectedDomains.delete(c.id));
  }
  updateDomainActionBar();
  renderDomainTable();
}

// 1. Update updateDomainActionBar in domains.js
function updateDomainActionBar() {
  const count = selectedDomains.size;
  const editBtn = document.getElementById("edit-btn");
  const delBtn = document.getElementById("delete-btn");
  const bulkEditBtn = document.getElementById("bulk-edit-btn");
  const actionBtn = document.getElementById("action-btn");

  // Enable buttons if anything is selected
  if (editBtn) editBtn.disabled = count === 0;
  if (delBtn) delBtn.disabled = count === 0;
  if (bulkEditBtn) bulkEditBtn.disabled = count === 0;
  if (actionBtn) actionBtn.disabled = count !== 1; // Only allow for single selection
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
    status: "status",
    price: "price",
    lastContact: "contact",
    seq: "seq",
    lastAction: "action",
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
    { id: "bulk-status", key: "status", label: "Status" },
    { id: "bulk-price", key: "price", label: "Price" },
    { id: "bulk-lastContact", key: "lastContact", label: "Last Contact" },
    { id: "bulk-seq", key: "seq", label: "Sequence" },
    { id: "bulk-lastAction", key: "lastAction", label: "Last Action" },
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
  for (let id of selectedDomains) {
    await fetch(`/api/domains/${id}`, { method: "DELETE" });
  }
  selectedDomains.clear();
  updateDomainActionBar();
  renderDomainTable();
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  div.innerHTML;
}

// 1. Improved CSV parsing using a more flexible approach in domains.js
async function handleCSVImport(event) {
  const file = event.target.files[0];
  const reader = new FileReader();
  reader.onload = async (e) => {
    const text = e.target.result;
    const lines = text.split(/\r?\n/).filter((line) => line.trim() !== "");

    // Detect delimiter (comma, semicolon, or tab)
    const firstLine = lines[0];
    const delimiter = [",", "\t", ";"].reduce(
      (prev, curr) =>
        firstLine.split(curr).length > prev.split(curr).length ? curr : prev,
      ",",
    );
    const headers = firstLine
      .split(delimiter)
      .map((h) => h.trim().toLowerCase());

    const fieldMap = {
      domain: headers.findIndex((h) => h === "domain"),
      expiry: headers.findIndex((h) => h === "expiry"),
      status: headers.findIndex((h) => h === "status"),
      price: headers.findIndex((h) => h === "price"),
      lastContact: headers.findIndex((h) => h === "last contact"),
      seq: headers.findIndex((h) => h === "seq"),
      lastAction: headers.findIndex((h) => h === "last action"),
    };

    if (fieldMap.domain === -1) {
      alert("Import failed. Required column missing: Domain.");
      return;
    }

    const processed = lines.slice(1).map((line) => {
      const cols = line.split(delimiter).map((c) => c.trim());
      return {
        domain: cols[fieldMap.domain],
        expiry: fieldMap.expiry !== -1 ? cols[fieldMap.expiry] : null,
        status: fieldMap.status !== -1 ? cols[fieldMap.status] : null,
        price: fieldMap.price !== -1 ? cols[fieldMap.price] : null,
        lastContact:
          fieldMap.lastContact !== -1 ? cols[fieldMap.lastContact] : null,
        seq: fieldMap.seq !== -1 ? cols[fieldMap.seq] : null,
        lastAction:
          fieldMap.lastAction !== -1 ? cols[fieldMap.lastAction] : null,
      };
    });

    // Send to backend
    const res = await fetch("/api/domains/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domains: processed }),
    });

    if (res.ok) {
      alert("Successfully imported records.");
      renderDomainTable();
    } else {
      const err = await res.json();
      alert("Import failed: " + (err.error || "Unknown server error"));
    }
  };
  reader.readAsText(file);
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

  if (summary.length === 0) {
    alert("No changes made.");
    return;
  }

  // Update Domain / Campaign
  const res = await fetch(`/api/domains/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });

  if (res.ok) {
    alert("Domain updated successfully.");
    renderDomainTable();
    closeModal();
  } else {
    const err = await res.json();
    alert("Update failed: " + (err.error || "Unknown error"));
  }
}

// 3. Fix modal population in domains.js
function openModal(id = null) {
  document.getElementById("domain-modal").style.display = "block";
  const modalTitle = document.getElementById("modal-title");
  const c = domains.find((x) => x.id === id);

  const statusEl = document.getElementById("form-status");
  if (c) {
    modalTitle.innerText = "Edit Domain";
    document.getElementById("edit-id").value = c.id;
    document.getElementById("form-domain").value = c.domain;
    document.getElementById("form-expiry").value = c.expiry || "";

    statusEl.value = c.status || "";
    statusEl.disabled = true;
  } else {
    modalTitle.innerText = "Add Domain";
    document.getElementById("edit-id").value = "";
    document.getElementById("form-domain").value = "";
    document.getElementById("form-expiry").value = "";

    statusEl.value = "";
    statusEl.disabled = false;
  }
}

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
}

async function setActionMode(mode) {
  const container = document.getElementById("action-mode-content");
  const campaignId = Array.from(selectedDomains)[0];

  const tabNew = document.getElementById("tab-new");
  const tabEdit = document.getElementById("tab-edit");

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
    container.innerHTML = `
      <div class="form-group">
        <label>Action Type:
          <select id="action-type">
            <option value="FIRST_OUTREACH">First Outreach</option>
            <option value="FIRST_FOLLOW_UP">First Follow-up</option>
            <option value="FOLLOW_UP">Follow-up</option>
            <option value="PRICE_REDUCTION">Price Reduction</option>
          </select>
        </label>
      </div>
      <div class="form-group">
        <label>Campaign Status:
          <select id="action-status">
            <option value="DORMANT">Dormant</option>
            <option value="ACTIVE">Active</option>
            <option value="RESTING">Resting</option>
          </select>
        </label>
      </div>
    <div class="form-group">
        <label>Date: <input type="datetime-local" id="action-date"></label>
    </div>
    <div class="form-group">
        <label>Price: <input type="number" id="action-price"></label>
    </div>
    <div class="form-group">
        <label>Notes: <textarea id="action-notes"></textarea></label>
      </div>
      <button onclick="saveNewAction(${campaignId})">Save Action</button>
    `;
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
  const seq = document.getElementById("edit-seq-select").value;
  if (!seq) return;
  const res = await fetch(`/api/campaigns/${campaignId}/actions/${seq}`);
  const data = await res.json();

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
      <label>Date: <input type="datetime-local" id="edit-date" value="${data.action_date.slice(0, 16)}"></label>
    </div>
    <div class="form-group">
      <label>Price: <input type="number" id="edit-price" value="${data.price_after}"></label>
    </div>
    <div class="form-group">
      <label>Notes: <textarea id="edit-notes">${data.notes || ""}</textarea></label>
    </div>
    <button onclick="saveEditAction(${campaignId}, ${seq})">Save Changes</button>
  `;
}

async function saveNewAction(campaignId) {
  const payload = {
    action_type: document.getElementById("action-type").value,
    action_date: document.getElementById("action-date").value,
    price_after: document.getElementById("action-price").value,
    notes: document.getElementById("action-notes").value,
    campaign_status: document.getElementById("action-status").value,
  };

  const res = await fetch(`/api/campaigns/${campaignId}/actions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (res.ok) {
    alert("Action saved!");
    closeActionModal();
    renderDomainTable();
  } else {
    alert("Failed to save action");
  }
}

async function saveEditAction(campaignId, seq) {
  const payload = {
    action_type: document.getElementById("edit-type").value,
    action_date: document.getElementById("edit-date").value,
    price_after: document.getElementById("edit-price").value,
    notes: document.getElementById("edit-notes").value,
  };

  const res = await fetch(`/api/campaigns/${campaignId}/actions/${seq}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (res.ok) {
    alert("Changes saved!");
    closeActionModal();
    renderDomainTable();
  } else {
    alert("Failed to save changes");
  }
}

// Render the table on page load
document.addEventListener("DOMContentLoaded", renderDomainTable);
