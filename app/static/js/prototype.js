// 1. Mock Database Structures
// 1. Reset: All email accounts are Available initially.
const allEmailCodes = [
  "D03",
  "D04",
  "D05",
  "D07",
  "M01",
  "M02",
  "M04",
  "M05",
  "M06",
  "M07",
  "M08",
  "M09",
  "M10",
  "M11",
  "M12",
  "M13",
  "M14",
  "M15",
  "M16",
  "M17",
  "M18",
  "M19",
  "M20",
  "ML06",
  "ML07",
  "ML08",
  "N04",
  "N09",
  "N10",
  "T01",
  "T03",
  "T04",
  "T05",
  "T06",
  "T07",
  "T08",
  "T09",
  "T10",
  "T12",
  "T13",
  "T14",
  "T15",
  "T16",
  "T17",
  "T18",
  "Y01",
  "Y02",
  "Y03",
  "Y04",
  "Z00",
  "Z01",
  "Z04",
  "Z08",
  "Z09",
];

const mockEmailAccounts = allEmailCodes.map((code, index) => ({
  code,
  group: code.startsWith("ML") ? "ML" : code[0],
  order: index + 1,
  state: "Available", // START CLEAN: Nothing pre-reserved
  reservedFor: null,
}));

let selectedCodes = new Set();

// 2. Clean Campaigns
const mockCampaigns = Array.from({ length: 35 }, (_, i) => {
  const groups = ["M", "T", "N", "Y", "Z"];
  const group = groups[i % groups.length];
  const block = allEmailCodes
    .filter((c) => c.startsWith(group))
    .slice(i % 3, (i % 3) + 2);

  return {
    id: i + 1,
    domain: `example${i + 1}.com`,
    status: i < 10 ? "Active" : i < 20 ? "Resting" : "Active",
    action: [
      "First Follow-up",
      "Normal Follow-up",
      "Price Reduction",
      "Ready To Restart",
      "Expiring Soon",
    ][i % 5],
    price: 300 + i * 10,
    seq: (i % 3) + 1,
    expiry: new Date(Date.now() + Math.random() * 60 * 24 * 60 * 60 * 1000)
      .toISOString()
      .split("T")[0],
    lastContact: "2026-08-01",
    suggestedBlock: block.length > 0 ? block : ["M01", "M02"],
    isReserved: false, // Explicitly False
  };
});

function syncCampaignStates() {
  mockCampaigns.forEach((c) => {
    const blocks = c.suggestedBlock;
    const allReserved = blocks.every((code) => {
      const acc = mockEmailAccounts.find((a) => a.code === code);
      return acc && acc.state === "Reserved" && acc.reservedFor === c.domain;
    });
    c.isReserved = allReserved;
  });
}

function toggleAccordion(id) {
  const el = document.getElementById(id);
  el.style.display = el.style.display === "block" ? "none" : "block";
}

function showSidePanel(domainName) {
  const campaign = mockCampaigns.find((c) => c.domain === domainName);
  if (!campaign) return;

  const panel = document.getElementById("side-panel");
  const content = document.getElementById("panel-content");
  content.innerHTML = `
        <h3>${campaign.domain}</h3>
        <p><strong>Status:</strong> ${campaign.status}</p>
        <p><strong>Current Price:</strong> $${campaign.price}</p>
        <p><strong>Last Contact:</strong> ${campaign.lastContact}</p>
        <h4>History</h4>
        <ul>
            <li>Aug 4: Follow-up Sent ($${campaign.price})</li>
        </ul>
        <button onclick="hideSidePanel()">Close</button>
    `;
  panel.classList.remove("hidden");
}

function hideSidePanel() {
  document.getElementById("side-panel").classList.add("hidden");
}

function openSidePanel(id) {
  const campaign = mockCampaigns.find((c) => c.id === id);
  if (campaign) showSidePanel(campaign.domain);
}

function reserveBlock(domain) {
  const campaign = mockCampaigns.find((c) => c.domain === domain);
  const isReserved = campaign.isReserved;

  if (isReserved) {
    campaign.suggestedBlock.forEach((code) => {
      const acc = mockEmailAccounts.find((a) => a.code === code);
      acc.state = "Available";
      acc.reservedFor = null;
    });
    campaign.isReserved = false;
  } else {
    const conflicts = campaign.suggestedBlock.filter(
      (code) =>
        mockEmailAccounts.find((a) => a.code === code).state === "Reserved",
    );

    if (conflicts.length > 0) {
      alert(`Conflict: ${conflicts.join(", ")} already reserved!`);
      return;
    }

    campaign.suggestedBlock.forEach((code) => {
      const acc = mockEmailAccounts.find((a) => a.code === code);
      acc.state = "Reserved";
      acc.reservedFor = domain;
    });
    campaign.isReserved = true;
  }
  refreshDashboard();
}

function getSortedAccounts() {
  return [...mockEmailAccounts].sort((a, b) => a.order - b.order);
}

function refreshDashboard() {
  syncCampaignStates();
  document.getElementById("total-domains").textContent = mockCampaigns.length;
  document.getElementById("active-campaigns").textContent =
    mockCampaigns.filter((c) => c.status === "Active").length;
  document.getElementById("resting-campaigns").textContent =
    mockCampaigns.filter((c) => c.status === "Resting").length;

  updateReservationBoard();
  renderSuggestedWork();
}

function updateReservationBoard() {
  const list = document.getElementById("email-accounts-list");
  if (!list) return;
  list.innerHTML = getSortedAccounts()
    .map(
      (acc) => `
        <div class="acc-item ${acc.state.toLowerCase()}">
            <strong>${acc.code}</strong><br>
            <small>${acc.reservedFor || acc.state}</small>
        </div>
    `,
    )
    .join("");
}
function renderSuggestedWork() {
  const categories = [
    { id: "first-followup", action: "First Follow-up" },
    { id: "normal-followup", action: "Normal Follow-up" },
    { id: "price-reduction", action: "Price Reduction" },
  ];

  categories.forEach((cat) => {
    const container = document.getElementById(cat.id);
    const data = mockCampaigns.filter((c) => c.action === cat.action);
    if (!container) return;
    container.innerHTML = `<table>
            <tr><th>Domain</th><th>Block</th><th>Action</th></tr>
            ${data
              .map(
                (c) => `<tr>
                <td>${c.domain}</td>
                <td>${c.suggestedBlock.join(", ")}</td>
                <td>
                    <button onclick="reserveBlock('${c.domain}')"
                            style="background-color: ${c.isReserved ? "#ffc107" : "#28a745"}; color: white;">
                        ${c.isReserved ? "Unreserve" : "Reserve"}
                    </button>
                </td>
            </tr>`,
              )
              .join("")}
        </table>`;
  });
}

function renderEmailTable() {
  const body = document.querySelector("#email-table-body");
  if (!body) return; // Only run if we are on the right page
  const sorted = getSortedAccounts();
  body.innerHTML = sorted
    .map(
      (acc) => `
    <tr data-code="${acc.code}" draggable="true">
        <td><input type="checkbox" ${selectedCodes.has(acc.code) ? "checked" : ""} onchange="toggleSelection('${acc.code}')"></td>
        <td class="drag-handle">⋮⋮</td>
        <td>${acc.code}</td>
        <td>${acc.group}</td>
        <td>${acc.order}</td>
        <td>${acc.state}</td>
        <td>${acc.reservedFor || "-"}</td>
    </tr>
`,
    )
    .join("");

  // Re-enable action bar visibility based on selection
  updateActionBar();
  makeDraggable();
}

// Ensure init logic runs only once
if (document.querySelector("#email-table-body")) {
  renderEmailTable();
}

function toggleSelection(code) {
  if (selectedCodes.has(code)) selectedCodes.delete(code);
  else selectedCodes.add(code);
  updateActionBar();
}

// Ensure the action bar starts hidden
document.addEventListener("DOMContentLoaded", () => {
  const bar = document.getElementById("action-bar");
  if (bar) bar.style.display = "block";
});

// Update Action Bar logic
function updateActionBar() {
  const bar = document.getElementById("action-bar");
  if (!bar) return;

  // Always keep block display
  bar.style.display = "block";

  const count = selectedCodes.size;
  const moveUp = document.getElementById("move-up-btn");
  const moveDown = document.getElementById("move-down-btn");
  const editBtn = document.getElementById("edit-btn");
  const delBtn = document.getElementById("delete-btn");

  if (moveUp) moveUp.disabled = count !== 1;
  if (moveDown) moveDown.disabled = count !== 1;
  if (editBtn) editBtn.disabled = count === 0;
  if (delBtn) delBtn.disabled = count === 0;
}

function makeDraggable() {
  const rows = document.querySelectorAll("#email-table-body tr");
  rows.forEach((row) => {
    row.addEventListener("dragstart", (e) => {
      e.target.classList.add("dragging");
      e.dataTransfer.setData("text/plain", e.target.dataset.code);
    });
    row.addEventListener("dragend", (e) =>
      e.target.classList.remove("dragging"),
    );
  });

  const tbody = document.querySelector("#email-table-body");
  tbody.addEventListener("dragover", (e) => {
    e.preventDefault();
    const dragging = document.querySelector(".dragging");
    const afterElement = getDragAfterElement(tbody, e.clientY);
    if (afterElement == null) {
      tbody.appendChild(dragging);
    } else {
      tbody.insertBefore(dragging, afterElement);
    }
  });

  tbody.addEventListener("drop", (e) => {
    updateOrderFromDOM();
  });
}

function getDragAfterElement(container, y) {
  const draggableElements = [
    ...container.querySelectorAll("tr:not(.dragging)"),
  ];
  return draggableElements.reduce(
    (closest, child) => {
      const box = child.getBoundingClientRect();
      const offset = y - box.top - box.height / 2;
      if (offset < 0 && offset > closest.offset) {
        return { offset: offset, element: child };
      } else {
        return closest;
      }
    },
    { offset: Number.NEGATIVE_INFINITY },
  ).element;
}

function updateOrderFromDOM() {
  const rows = document.querySelectorAll("#email-table-body tr");
  rows.forEach((row, index) => {
    const code = row.dataset.code;
    const account = mockEmailAccounts.find((a) => a.code === code);
    account.order = index + 1;
  });
  mockEmailAccounts.sort((a, b) => a.order - b.order);
  renderEmailTable();
}

function bulkToggle() {
  selectedCodes.forEach((code) => {
    const acc = mockEmailAccounts.find((a) => a.code === code);
    acc.state = acc.state === "Disabled" ? "Available" : "Disabled";
  });
  selectedCodes.clear();
  updateActionBar();
  renderEmailTable();
}

function bulkDelete() {
  selectedCodes.forEach((code) => {
    const idx = mockEmailAccounts.findIndex((a) => a.code === code);
    if (idx !== -1) mockEmailAccounts.splice(idx, 1);
  });
  selectedCodes.clear();
  updateActionBar();
  renderEmailTable();
}

function bulkMove(dir) {
  const code = Array.from(selectedCodes)[0];
  const idx = mockEmailAccounts.findIndex((a) => a.code === code);
  const newIdx = idx + dir;
  if (newIdx >= 0 && newIdx < mockEmailAccounts.length) {
    [mockEmailAccounts[idx].order, mockEmailAccounts[newIdx].order] = [
      mockEmailAccounts[newIdx].order,
      mockEmailAccounts[idx].order,
    ];
    mockEmailAccounts.sort((a, b) => a.order - b.order);
    renderEmailTable();
  }
}

refreshDashboard();
