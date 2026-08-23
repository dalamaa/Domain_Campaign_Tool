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

async function updateReservationBoard() {
  const res = await fetch("/api/dashboard/reservation-board");
  const data = await res.json();
  const list = document.getElementById("email-accounts-list");
  if (!list) return;
  list.innerHTML = data
    .map((acc) => {
      let stateClass = "";
      let stateLabel = acc.state.replace("_", " ");
      let domainLabel = "";

      if (acc.state === "UNRESERVED") stateClass = "unreserved";
      else if (acc.state === "RESERVED") {
        stateClass = "reserved";
        domainLabel = `<br><small>${acc.reserved_domain || ""}</small>`;
      } else if (acc.state === "USED") stateClass = "used";
      else if (acc.state === "DISABLED") stateClass = "disabled";

      return `
        <div class="acc-item ${stateClass}">
          <strong>${acc.code}</strong>${domainLabel}
          <br><small>${stateLabel}</small>
          <br><small>0/${/* Replace 0 with real count when available */ "2"}</small>
        </div>`;
    })
    .join("");
}

function renderSuggestedWork() {
  const categories = [
    { id: "first-followup", action: "First Follow-up" },
    { id: "normal-followup", action: "Normal Follow-up" },
  ];

  // Custom renderer for first-followup to use API data
  const renderFirstFollowups = async () => {
    const container = document.getElementById("first-followup");
    if (!container) return;

    const res = await fetch("/api/dashboard/first-follow-ups");
    const data = await res.json();

    container.innerHTML = `
      <h4>Due</h4>
      <div class="table-container">${renderTable(data.due)}</div>
      <h4>Past Due</h4>
      <div class="table-container">${renderTable(data.past_due)}</div>
    `;

    // Attach event delegation for Reserve/Unreserve
    container.querySelectorAll("button[data-action]").forEach((btn) => {
      btn.onclick = async (e) => {
        const action = e.target.dataset.action;
        const campId = e.target.dataset.campaignId;
        if (action === "reserve") {
          const resp = await fetch(`/api/campaigns/${campId}/reservation`, {
            method: "POST",
          });
          if (resp.ok) refreshDashboard();
          else {
            const err = await resp.json();
            alert(err.details ? err.details.join("\n") : err.error);
          }
        } else if (action === "unreserve") {
          await fetch(`/api/campaigns/${campId}/reservation`, {
            method: "DELETE",
          });
          refreshDashboard();
        }
      };
    });
  };

  const getResButtons = (c) => {
    const res = c.reservation;
    let buttons = "";

    if (res.state === "Reserved" && res.reserved_by === c.domain) {
      buttons = `<button data-action="reserve" data-campaign-id="${c.campaign_id}" disabled>Reserve</button>
                     <button data-action="unreserve" data-campaign-id="${c.campaign_id}">Unreserve</button>`;
    } else if (res.state === "Reserved") {
      buttons = `<button data-action="reserve" data-campaign-id="${c.campaign_id}" disabled>Reserve</button>
                     <button data-action="unreserve" data-campaign-id="${c.campaign_id}" disabled>Unreserve</button> ⚠`;
    } else {
      buttons = `<button data-action="reserve" data-campaign-id="${c.campaign_id}">Reserve</button>
                     <button data-action="unreserve" data-campaign-id="${c.campaign_id}" disabled>Unreserve</button>`;
    }

    return buttons;
  };

  const renderTable = (list, isNormal = false) => `
    <table>
      <thead>
        <tr><th>Domain</th><th>Days Since ${isNormal ? "Contact" : "Outreach"}</th><th>Emails Used</th><th>Reservation</th></tr>
      </thead>
      <tbody>
        ${list
          .map(
            (c) => `
        <tr>
          <td>${c.domain}</td>
          <td>${isNormal ? c.days_since_contact || "N/A" : c.days_since_outreach}</td>
          <td>${c.emails_used.length > 0 ? c.emails_used.join(", ") : "—"}</td>
          <td>${getResButtons(c)}</td>
        </tr>`,
          )
          .join("")}
      </tbody>
    </table>
  `;

  renderFirstFollowups();

  // Prepare structure for Normal Follow-ups
  const normalFollowupContainer = document.getElementById("normal-followup");
  if (normalFollowupContainer) {
    normalFollowupContainer.innerHTML = `
      <h4>Due</h4>
      <div class="table-container">${renderTable([], true)}</div>
      <h4>Past Due</h4>
      <div class="table-container">${renderTable([], true)}</div>
    `;
  }
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
