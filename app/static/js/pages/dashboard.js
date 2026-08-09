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

function refreshDashboard() {
  syncCampaignStates();
  const totalDomainsEl = document.getElementById("total-domains");
  if (totalDomainsEl) totalDomainsEl.textContent = mockCampaigns.length;

  const activeCampaignsEl = document.getElementById("active-campaigns");
  if (activeCampaignsEl)
    activeCampaignsEl.textContent = mockCampaigns.filter(
      (c) => c.status === "Active",
    ).length;

  const restingCampaignsEl = document.getElementById("resting-campaigns");
  if (restingCampaignsEl)
    restingCampaignsEl.textContent = mockCampaigns.filter(
      (c) => c.status === "Resting",
    ).length;

  updateReservationBoard();
  renderSuggestedWork();
}

function updateReservationBoard() {
  const list = document.getElementById("email-accounts-list");
  if (!list) return;
  list.innerHTML = getSortedAccounts()
    .map(
      (acc) =>
        `<div class="acc-item ${acc.state.toLowerCase()}"><strong>${acc.code}</strong><br><small>${acc.reservedFor || acc.state}</small></div>`,
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
    if (!container) return;
    const data = mockCampaigns.filter((c) => c.action === cat.action);
    container.innerHTML = `<table><tr><th>Domain</th><th>Block</th><th>Action</th></tr>${data.map((c) => `<tr><td>${c.domain}</td><td>${c.suggestedBlock.join(", ")}</td><td><button onclick="reserveBlock('${c.domain}')" style="background-color: ${c.isReserved ? "#ffc107" : "#28a745"}; color: white;">${c.isReserved ? "Unreserve" : "Reserve"}</button></td></tr>`).join("")}</table>`;
  });
}

function reserveBlock(domain) {
  const campaign = mockCampaigns.find((c) => c.domain === domain);
  if (campaign.isReserved) {
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

// Fix Dashboard: Add missing toggleAccordion
function toggleAccordion(id) {
  const el = document.getElementById(id);
  if (el) el.style.display = el.style.display === "block" ? "none" : "block";
}

document.addEventListener("DOMContentLoaded", refreshDashboard);
