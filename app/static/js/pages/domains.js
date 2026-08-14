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

// 1. Update updateDomainActionBar in domains.js
function updateDomainActionBar() {
  const count = selectedDomains.size;
  const editBtn = document.getElementById("edit-btn");
  const delBtn = document.getElementById("delete-btn");

  // Enable Edit for multiple selections too
  if (editBtn) editBtn.disabled = count === 0;
  if (delBtn) delBtn.disabled = count === 0;
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

  // Mandatory Validation Loop
  const fieldsToValidate = [
    { id: "form-seq", label: "Sequence" },
    { id: "form-lastAction", label: "Last Action" },
    { id: "form-status", label: "Status" },
    { id: "form-price", label: "Price" },
  ];

  for (const field of fieldsToValidate) {
    const input = document.getElementById(field.id);
    if (!input.disabled) {
      if (input.value === null || input.value === "") {
        alert(`Please select or enter a value for ${field.label}.`);
        return;
      }
    }
  }

  // Get values for history check
  const seq = document.getElementById("form-seq").value;

  // Check history only if sequence is being changed/submitted
  if (!document.getElementById("form-seq").disabled) {
    const checkRes = await fetch(`/api/domains/${id}/history/check`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ seq: seq }),
    });
    const checkData = await checkRes.json();

    if (checkRes.status === 400) {
      alert(checkData.message);
      return;
    }

    if (
      !confirm(`Action: ${checkData.action}\n${checkData.message}\n\nContinue?`)
    ) {
      return;
    }
  }

  const fields = [
    { id: "form-expiry", key: "expiry" },
    { id: "form-status", key: "status" },
    { id: "form-price", key: "price" },
    { id: "form-lastContact", key: "lastContact" },
    { id: "form-seq", key: "seq" },
    { id: "form-lastAction", key: "lastAction" },
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

  // Update Campaign and History
  await fetch(`/api/domains/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });

  // Only update history if we successfully validated sequence above
  if (!document.getElementById("form-seq").disabled) {
    await fetch(`/api/domains/${id}/history`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        seq: seq,
        price: updates.price,
        notes: "Domain updated via edit modal",
      }),
    });
  }
  alert("Domain updated successfully.");
  renderDomainTable();
  closeModal();
}
// 3. Fix modal population in domains.js
function openModal(id = null) {
  document.getElementById("domain-modal").style.display = "block";
  const modalTitle = document.getElementById("modal-title");
  const c = domains.find((x) => x.id === id);

  const seqEl = document.getElementById("form-seq");
  const actionEl = document.getElementById("form-lastAction");
  const statusEl = document.getElementById("form-status");
  const priceEl = document.getElementById("form-price");

  if (c) {
    modalTitle.innerText = "Edit Domain";
    document.getElementById("edit-id").value = c.id;
    document.getElementById("form-domain").value = c.domain;
    document.getElementById("form-expiry").value = c.expiry || "";

    // Map the backend status enum value (e.g. "ACTIVE") to the select's
    // option value (e.g. "Active") so real statuses display correctly.
    const statusSelectValue = {
      ACTIVE: "Active",
      RESTING: "Resting",
      SOLD: "Sold",
      EXPIRED: "Expired",
      ARCHIVED: "Archived",
      DORMANT: "Dormant",
    }[c.status ? String(c.status).toUpperCase() : ""];

    // For a domain that hasn't been started (Dormant status / sequence 0),
    // leave Status, Price, Sequence, and Last Action on their placeholders so
    // the user can deliberately set real values rather than inheriting defaults.
    const hasValues = c.hasValues;
    statusEl.value = hasValues ? statusSelectValue || "" : "";
    priceEl.value = hasValues ? c.price || "" : "";
    document.getElementById("form-lastContact").value = c.lastContact || "";
    seqEl.value = hasValues ? c.seq || "" : "";
    actionEl.value = hasValues ? c.lastAction || "" : "";

    // Ensure they stay disabled initially
    statusEl.disabled = true;
    priceEl.disabled = true;
    seqEl.disabled = true;
    actionEl.disabled = true;
  } else {
    modalTitle.innerText = "Add Domain";
    document.getElementById("edit-id").value = "";
    document.getElementById("form-domain").value = "";
    document.getElementById("form-expiry").value = "";
    document.getElementById("form-lastContact").value = "";

    // Explicitly reset to placeholder
    statusEl.value = "";
    priceEl.value = "";
    seqEl.value = "";
    actionEl.value = "";
    // Disable them so user has to click edit
    statusEl.disabled = true;
    priceEl.disabled = true;
    seqEl.disabled = true;
    actionEl.disabled = true;
  }
}

function closeModal() {
  document.getElementById("domain-modal").style.display = "none";
}

// Render the table on page load
document.addEventListener("DOMContentLoaded", renderDomainTable);
