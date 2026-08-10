// 1. domains.js
let selectedDomains = new Set();
let searchTerm = "";
let currentSort = { key: null, direction: 'asc' };

function updateSearch(val) {
  searchTerm = val.trim().toLowerCase();
  renderDomainTable();
}

function sortTable(key) {
    if (currentSort.key === key) {
        currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
    } else {
        currentSort.key = key;
        currentSort.direction = 'asc';
    }

    mockCampaigns.sort((a, b) => {
        let valA = a[key] || '';
        let valB = b[key] || '';

        // Handle dates and numbers for sorting
        if (['expiry', 'lastContact'].includes(key)) {
            valA = new Date(valA);
            valB = new Date(valB);
        } else if (key === 'price' || key === 'seq') {
            valA = Number(valA);
            valB = Number(valB);
        } else {
            valA = valA.toString().toLowerCase();
            valB = valB.toString().toLowerCase();
        }

        if (valA < valB) return currentSort.direction === 'asc' ? -1 : 1;
        if (valA > valB) return currentSort.direction === 'asc' ? 1 : -1;
        return 0;
    });

  renderDomainTable();
}

function renderDomainTable() {
  const body = document.getElementById("domain-table-body");
  if (!body) return;

  // Filter by search
  const filtered = mockCampaigns.filter((c) =>
    c.domain.toLowerCase().includes(searchTerm),
  );
  // Show count
  const countEl = document.getElementById("domain-count");
  if (countEl)
    countEl.textContent = `${filtered.length} of ${mockCampaigns.length} domains`;
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
            <td><span class="pill">${c.lastAction || "N/A"}</span></td>
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

function bulkDeleteDomains() {
  selectedDomains.forEach((id) => {
    const idx = mockCampaigns.findIndex((c) => c.id === id);
    if (idx !== -1) mockCampaigns.splice(idx, 1);
  });
  selectedDomains.clear();
  updateDomainActionBar();
  renderDomainTable();
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function handleCSVImport(event) {
  const file = event.target.files[0];
  if (!file || (file.type !== "text/csv" && !file.name.endsWith(".csv"))) {
    alert("Invalid file. Please select a CSV file.");
    return;
  }

  const reader = new FileReader();
  reader.onload = (e) => {
    const text = e.target.result;
    const rows = text.split("\n");
    const headers = rows[0].split(",").map((h) => h.trim().toLowerCase());
    const fieldMap = {
      domain: headers.findIndex((h) => h === "domain"),
      expiry: headers.findIndex((h) => h === "expiry"),
      status: headers.findIndex((h) => h === "status"),
      price: headers.findIndex((h) => h === "price"),
      lastContact: headers.findIndex((h) => h === "last contact"),
      seq: headers.findIndex((h) => h === "seq"),
      lastAction: headers.findIndex((h) => h === "last action"),
    };

    const validStatuses = ["active", "resting", "sold", "expired", "archived"];
    const errors = [];
    const processedDomains = [];

    rows.slice(1).forEach((row, idx) => {
      if (!row.trim()) return;
      const cols = row.split(",").map((c) => c.trim());
      const rowNum = idx + 2;

      const domain = cols[fieldMap.domain];
      if (!domain) {
        errors.push(`Row ${rowNum}: Missing Domain`);
        return;
      }

      const expiry = fieldMap.expiry !== -1 ? cols[fieldMap.expiry] : "";
      if (expiry && isNaN(Date.parse(expiry))) {
        errors.push(`Row ${rowNum}: Invalid Expiry Date`);
        return;
      }

      const status = fieldMap.status !== -1 ? cols[fieldMap.status] : "";
      if (status && !validStatuses.includes(status.toLowerCase())) {
        errors.push(`Row ${rowNum}: Invalid Status`);
        return;
      }

      const price = fieldMap.price !== -1 ? cols[fieldMap.price] : "";
      if (price && isNaN(price)) {
        errors.push(`Row ${rowNum}: Invalid Price`);
        return;
      }

      const seq = fieldMap.seq !== -1 ? cols[fieldMap.seq] : "";
      if (seq && (isNaN(seq) || parseInt(seq) < 1 || parseInt(seq) > 8)) {
        errors.push(`Row ${rowNum}: Seq must be between 1 and 8`);
        return;
      }

      processedDomains.push({
        id: mockCampaigns.length + processedDomains.length + 1,
        domain: escapeHtml(domain),
        expiry: expiry,
        status: status || "Active",
        price: price || 0,
        lastContact:
          fieldMap.lastContact !== -1 ? cols[fieldMap.lastContact] : "",
        seq: seq || 1,
        lastAction:
          fieldMap.lastAction !== -1
            ? escapeHtml(cols[fieldMap.lastAction])
            : "",
        action: "Other",
      });
    });

    if (errors.length > 0) {
      alert(
        `Import failed. ${errors.length} rows contain invalid data:\n${errors.join("\n")}`,
      );
    } else {
      mockCampaigns.push(...processedDomains);
      renderDomainTable();
    }
  };
  reader.readAsText(file);
}

// Add missing modal functions back to domains.js
function openModal(id = null) {
  document.getElementById("domain-modal").style.display = "block";
  if (id) {
    const c = mockCampaigns.find((x) => x.id === id);
    document.getElementById("edit-id").value = c.id;
    document.getElementById("form-domain").value = c.domain;
  }
}

function closeModal() {
  document.getElementById("domain-modal").style.display = "none";
}

// 1. Update saveDomain to handle the new modal fields
function saveDomain() {
  const id = document.getElementById("edit-id").value;
  const data = {
    domain: document.getElementById("form-domain").value,
    expiry: document.getElementById("form-expiry").value,
    lastContact: document.getElementById("form-lastContact").value,
    price: parseInt(document.getElementById("form-price").value),
    status: document.getElementById("form-status").value,
    seq: document.getElementById("form-seq").value,
    lastAction: document.getElementById("form-lastAction").value,
  };

  if (id) {
    const c = mockCampaigns.find((x) => x.id == id);
    Object.assign(c, data);
  } else {
    mockCampaigns.push({
      id: mockCampaigns.length + 1,
      ...data,
    });
  }
  renderDomainTable();
  closeModal();
}

