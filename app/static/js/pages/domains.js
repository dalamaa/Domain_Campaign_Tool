// 1. domains.js
let selectedDomains = new Set();
let searchTerm = "";

function updateSearch(val) {
  searchTerm = val.trim().toLowerCase();
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

function handleCSVImport(event) {
  const file = event.target.files[0];
  const reader = new FileReader();
  reader.onload = (e) => {
    const text = e.target.result;
    const rows = text.split("\n");
    const headers = rows[0].split(",").map((h) => h.trim().toLowerCase());

    const map = {
      domain: headers.findIndex((h) => h === "domain"),
      expiry: headers.findIndex((h) => h === "expiry date"),
      status: headers.findIndex((h) => h === "status"),
      price: headers.findIndex((h) => h === "current price"),
    };

    if (map.domain === -1) {
      alert("Missing Domain column");
      return;
    }

    const newDomains = rows
      .slice(1)
      .filter((r) => r.trim())
      .map((r) => {
        const cols = r.split(",");
        return {
          id: mockCampaigns.length + 1,
          domain: cols[map.domain]?.trim() || "Unknown",
          status: map.status !== -1 ? cols[map.status].trim() : "Active",
          expiry: map.expiry !== -1 ? cols[map.expiry].trim() : "2026-12-31",
          price: map.price !== -1 ? parseInt(cols[map.price]) : 500,
          seq: 1,
          lastContact: "2026-08-01",
          action: "First Follow-up",
        };
      });
    mockCampaigns.push(...newDomains);
    renderDomainTable();
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
