// 1. domains.js
let selectedDomains = new Set();
let searchTerm = "";
let currentSort = { key: null, direction: "asc" };
let domains = [];

async function fetchDomains() {
  const res = await fetch("/api/domains");
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

  domains.sort((a, b) => {
    let valA = a[key] || "";
    let valB = b[key] || "";

    // Handle dates and numbers for sorting
    if (["expiry", "lastContact"].includes(key)) {
      valA = new Date(valA);
      valB = new Date(valB);
    } else if (key === "price" || key === "seq") {
      valA = Number(valA);
      valB = Number(valB);
    } else {
      valA = valA.toString().toLowerCase();
      valB = valB.toString().toLowerCase();
    }

    if (valA < valB) return currentSort.direction === "asc" ? -1 : 1;
    if (valA > valB) return currentSort.direction === "asc" ? 1 : -1;
    return 0;
  });

  renderDomainTable();
}

async function renderDomainTable() {
  domains = await fetchDomains();
  const body = document.getElementById("domain-table-body");
  if (!body) return;

  // Filter by search
  const filtered = domains.filter((c) =>
    c.domain.toLowerCase().includes(searchTerm),
  );
  // Show count
  const countEl = document.getElementById("domain-count");
  if (countEl)
    countEl.textContent = `${filtered.length} of ${domains.length} domains`;
  body.innerHTML = filtered
    .map((c) => {
      const daysLeft = Math.floor(
        (new Date(c.expiry) - new Date()) / (1000 * 60 * 60 * 24),
      );
      const daysSince = Math.floor(
        (new Date() - new Date(c.lastContact)) / (1000 * 60 * 60 * 24),
      );

      return `
        <tr class="${selectedDomains.has(c.id) ? "selected" : ""}">
            <td><input type="checkbox" ${selectedDomains.has(c.id) ? "checked" : ""} onchange="toggleDomainSelection(${c.id})"></td>
            <td onclick="showSidePanel('${c.domain}')" style="cursor:pointer">${c.domain}</td>
            <td>${c.expiry}</td>
            <td>${daysLeft} days</td>
            <td>${c.status}</td>
            <td>$${c.price}</td>
            <td>${daysSince} days</td>
            <td>${c.seq}</td>
            <td>${c.action || c.lastAction || "N/A"}</td>
        </tr>
        `;
    })
    .join("");
}

function toggleDomainSelection(id) {
  if (selectedDomains.has(id)) selectedDomains.delete(id);
  else selectedDomains.add(id);
  updateDomainActionBar();
  renderDomainTable();
}

function updateDomainActionBar() {
  const count = selectedDomains.size;
  const editBtn = document.getElementById("edit-btn");
  const delBtn = document.getElementById("delete-btn");
  if (editBtn) editBtn.disabled = count !== 1;
  if (delBtn) delBtn.disabled = count === 0;
}

function editSelected() {
  const id = Array.from(selectedDomains)[0];
  openModal(id);
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
  return div.innerHTML;
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

// 1. Update saveDomain to handle a fresh state for new campaigns
async function saveDomain() {
  const id = document.getElementById("edit-id").value;
  const data = {
    domain: document.getElementById("form-domain").value,
    expiry: document.getElementById("form-expiry").value || null,
    lastContact: document.getElementById("form-lastContact").value || null,
    price: parseInt(document.getElementById("form-price").value) || 0,
    status: document.getElementById("form-status").value || "Active",
    seq: parseInt(document.getElementById("form-seq").value) || 1,
    lastAction:
      document.getElementById("form-lastAction").value || "First Outreach",
  };

  if (id) {
    await fetch(`/api/domains/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
  } else {
    await fetch("/api/domains", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
  }
  renderDomainTable();
  closeModal();
}

// 2. Update openModal to correctly handle empty/new states
function openModal(id = null) {
  document.getElementById("domain-modal").style.display = "block";
  const modalTitle = document.getElementById("modal-title");

  if (id) {
    modalTitle.innerText = "Edit Domain";
    const c = domains.find((x) => x.id === id);
    document.getElementById("edit-id").value = c.id;
    document.getElementById("form-domain").value = c.domain || "";
    document.getElementById("form-expiry").value = c.expiry || "";
    document.getElementById("form-lastContact").value = c.lastContact || "";
    document.getElementById("form-price").value = c.price || 0;
    document.getElementById("form-status").value = c.status || "Active";
    document.getElementById("form-seq").value = c.seq || 1;
    document.getElementById("form-lastAction").value =
      c.lastAction || "First Outreach";
  } else {
    modalTitle.innerText = "Add Domain";
    document.getElementById("edit-id").value = "";
    document.getElementById("form-domain").value = "";
    document.getElementById("form-expiry").value = "";
    document.getElementById("form-lastContact").value = "";
    document.getElementById("form-price").value = 0;
    document.getElementById("form-status").value = "Active";
    document.getElementById("form-seq").value = 1;
    document.getElementById("form-lastAction").value = "First Outreach";
  }
}

function closeModal() {
  document.getElementById("domain-modal").style.display = "none";
}
