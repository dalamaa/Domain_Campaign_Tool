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
  renderTodaysCampaigns();
}

async function renderTodaysCampaigns() {
  const container = document
    .getElementById("todays-campaigns-table")
    .querySelector("tbody");
  if (!container) return;

  const res = await fetch("/api/dashboard/todays-campaigns");
  const data = await res.json();

  container.innerHTML = data
    .map(
      (c) => `
    <tr>
      <td><a href="/domains?history_id=${c.campaign_id}&domain=${encodeURIComponent(c.domain)}" target="_blank" rel="noopener noreferrer">${c.domain}</a></td>
      <td>${c.status}</td>
      <td>${c.sequence}</td>
      <td>$${c.current_price}</td>
      <td>${c.emails.join(", ")}</td>
      <td>${c.shared_emails.join(", ") || "—"}</td>
    </tr>`,
    )
    .join("");
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
        domainLabel = `<br><small>${(acc.reserved_domains || []).join("<br>")}</small>`;
      } else if (acc.state === "USED") stateClass = "used";
      else if (acc.state === "DISABLED") stateClass = "disabled";

      return `
        <div class="acc-item ${stateClass}">
          <strong>${acc.code}</strong>${domainLabel}
          <br><small>${stateLabel}</small>
          <br><small>${acc.count}/${acc.limit}</small>
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
        <tr><th>Domain</th><th>Days Since ${isNormal ? "Contact" : "Outreach"}</th><th>Emails Used</th><th>Reservation</th><th>Rest</th></tr>
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
          <td>${c.resting_suggested ? '<span class="rest-suggested" title="Rest suggested">🪙 Rest</span>' : ""}</td>
        </tr>`,
          )
          .join("")}
      </tbody>
    </table>
  `;

  const renderRestingSuggestions = async () => {
    const container = document.getElementById("resting-suggestions");
    const count = document.getElementById("resting-suggestions-count");
    if (!container) return;

    container.innerHTML = "<p>Loading Resting suggestions...</p>";
    try {
      const response = await fetch("/api/dashboard/resting-suggestions");
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Unable to load Resting suggestions.");
      }

      const suggestions = data.suggestions || [];
      if (count) count.textContent = data.count ?? suggestions.length;
      if (suggestions.length === 0) {
        container.innerHTML =
          "<p>No active campaigns currently meet the Resting rules.</p>";
        return;
      }

      const formatDays = (value) => (value == null ? "—" : `${value} days`);

      container.innerHTML = `
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th>Domain</th>
                <th>Sequence</th>
                <th>Last Contact</th>
                <th>Campaign Age</th>
                <th>Known Activity Age</th>
                <th>Expiry</th>
                <th>Reasons</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              ${suggestions
                .map(
                  (campaign) => `
                <tr>
                  <td>${campaign.domain}</td>
                  <td>${campaign.eligibility_metrics.current_sequence ?? "—"}</td>
                  <td>${campaign.last_contact_date || "—"}<br />
                    <small>${formatDays(campaign.eligibility_metrics.days_since_last_contact)}</small>
                  </td>
                  <td>${formatDays(campaign.eligibility_metrics.campaign_age_days)}</td>
                  <td>${formatDays(campaign.eligibility_metrics.known_activity_age_days)}</td>
                  <td>${
                    campaign.expiry_date
                      ? `${campaign.expiry_date} (${campaign.days_until_expiry} days)`
                      : "—"
                  }</td>
                  <td><ul>${(campaign.trigger_reasons || [])
                    .map((reason) => `<li>${reason.text}</li>`)
                    .join("")}</ul></td>
                  <td>
                    <button
                      type="button"
                      data-action="rest"
                      data-campaign-id="${campaign.campaign_id}"
                      data-domain="${campaign.domain}"
                    >Move to Resting</button>
                  </td>
                </tr>`,
                )
                .join("")}
            </tbody>
          </table>
        </div>
      `;

      container.querySelectorAll("button[data-action='rest']").forEach((button) => {
        button.onclick = async () => {
          const domain = button.dataset.domain;
          const campaignId = button.dataset.campaignId;
          if (!window.confirm(`Move ${domain} to Resting?`)) return;

          button.disabled = true;
          try {
            const response = await fetch(`/api/campaigns/${campaignId}/rest`, {
              method: "POST",
            });
            const result = await response.json();
            if (!response.ok) {
              throw new Error(result.error || "Unable to move campaign to Resting.");
            }
            await refreshDashboard();
            alert(`${domain} moved to Resting.`);
          } catch (error) {
            alert(error.message);
            try {
              await refreshDashboard();
            } catch (refreshError) {
              // Keep the dashboard usable even if a refresh also fails.
            }
          }
        };
      });
    } catch (error) {
      if (count) count.textContent = "—";
      container.innerHTML = `<p class="dashboard-error">${error.message}</p>`;
    }
  };

  renderFirstFollowups();

  // Render Normal Follow-ups
  const renderNormalFollowups = async () => {
    const container = document.getElementById("normal-followup");
    if (!container) return;

    const res = await fetch("/api/dashboard/normal-follow-ups");
    const data = await res.json();
    container.innerHTML = `
      <h4>Due</h4>
      <div class="table-container">${renderTable(data.due, true)}</div>
      <h4>Past Due</h4>
      <div class="table-container">${renderTable(data.past_due, true)}</div>
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

  renderNormalFollowups();
  renderRestingSuggestions();
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
