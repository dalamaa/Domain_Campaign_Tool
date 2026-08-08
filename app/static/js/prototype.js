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

// Issue identification:
// The issue is that the initial mockEmailAccounts setup manually sets state = 'Reserved'
// for some accounts (index % 5 === 0), but the campaign objects in mockCampaigns
// were not initialized with `isReserved = true` to match that state.
// Therefore, the UI renders the button as "Reserve" because isReserved is undefined (falsy),
// but clicking it triggers a conflict because the accounts are already marked 'Reserved' in mockEmailAccounts.

// Fix: Sync mockCampaigns state with mockEmailAccounts state during initialization.

function syncCampaignStates() {
  mockCampaigns.forEach((c) => {
    // A campaign is reserved if ALL of its required email blocks are currently in 'Reserved' state
    // AND 'reservedFor' matches the domain.
    const blocks = c.suggestedBlock;
    const allReserved = blocks.every((code) => {
      const acc = mockEmailAccounts.find((a) => a.code === code);
      return acc && acc.state === "Reserved" && acc.reservedFor === c.domain;
    });
    c.isReserved = allReserved;
  });
}

// Updated initialization to ensure sync
syncCampaignStates();
refreshDashboard();

// UI Logic
// Fix: Accordion logic
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

// Reservation Logic Toggle
function reserveBlock(domain) {
  const campaign = mockCampaigns.find((c) => c.domain === domain);
  const isReserved = campaign.isReserved;

  if (isReserved) {
    // Unreserve
    campaign.suggestedBlock.forEach((code) => {
      const acc = mockEmailAccounts.find((a) => a.code === code);
      acc.state = "Available";
      acc.reservedFor = null;
    });
    campaign.isReserved = false;
  } else {
    // Reserve
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

// 2. Logic to filter and render
// Fix: Render Logic
function refreshDashboard() {
  syncCampaignStates(); // Always sync state before rendering

  // 1. Overview
  document.getElementById("total-domains").textContent = mockCampaigns.length;
  document.getElementById("active-campaigns").textContent =
    mockCampaigns.filter((c) => c.status === "Active").length;
  document.getElementById("resting-campaigns").textContent =
    mockCampaigns.filter((c) => c.status === "Resting").length;

  // 2. Email Board
  updateReservationBoard();
  renderSuggestedWork();
}

// Update the render logic for the Reservation Board to show which campaign holds an account
function updateReservationBoard() {
  const list = document.getElementById("email-accounts-list");
  list.innerHTML = mockEmailAccounts
    .map((acc) => {
      let display = `<strong>${acc.code}</strong>`;
      if (acc.reservedFor) {
        display += `<br><small>${acc.reservedFor}</small>`;
      }
      return `<div class="acc-item ${acc.state.toLowerCase()}">${display}</div>`;
    })
    .join("");
}

// Render Suggested Work Sections with Toggle Logic
function renderSuggestedWork() {
  const categories = [
    { id: "first-followup", action: "First Follow-up" },
    { id: "normal-followup", action: "Normal Follow-up" },
    { id: "price-reduction", action: "Price Reduction" },
  ];

  categories.forEach((cat) => {
    const container = document.getElementById(cat.id);
    const data = mockCampaigns.filter((c) => c.action === cat.action);
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

// Refresh call at end of file
refreshDashboard();
