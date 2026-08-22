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

async function refreshDashboard() {
  const expiryDays = document.getElementById("expiry-filter").value;
  const res = await fetch(`/api/dashboard/overview?expiry_days=${expiryDays}`);
  const data = await res.json();

  document.getElementById("total-domains").textContent = data.total_domains;
  document.getElementById("active-campaigns").textContent =
    data.active_campaigns;
  document.getElementById("resting-campaigns").textContent =
    data.resting_campaigns;
  document.getElementById("dormant-campaigns").textContent =
    data.dormant_campaigns;
  document.getElementById("expiring-count").textContent = data.expiring_count;

  // Preserve mock logic for the rest of the board
  syncCampaignStates();
  updateReservationBoard();
  renderSuggestedWork();
}

function updateReservationBoard() {
  const list = document.getElementById("email-accounts-list");
  if (!list) return;
  list.innerHTML = getSortedAccounts()
    .map((acc) => {
      let stateClass = "";
      let stateLabel = acc.state;
      let domainLabel = "";

      if (acc.state === "Available") stateClass = "available";
      else if (acc.state === "Reserved") {
        stateClass = "reserved";
        domainLabel = `<br><small>${acc.reservedFor || ""}</small>`;
      } else if (acc.state === "Completed Today")
        stateClass = "completed-today";
      else if (acc.state === "Disabled") stateClass = "disabled";

      return `
        <div class="acc-item ${stateClass}">
          <strong>${acc.code}</strong>${domainLabel}
          <br><small>${stateLabel}</small>
        </div>`;
    })
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
