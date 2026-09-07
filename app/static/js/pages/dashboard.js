const DASHBOARD_SECTION_ORDER_DEFAULT = [
  "first_followups",
  "normal_followups",
  "resting_suggestions",
  "expiring_soon",
  "ready_for_campaign",
];
let dashboardSectionOrder = null;

function normalizeDashboardSectionOrder(order, availableSectionIds = null) {
  const knownSectionIds = Array.from(
    new Set(availableSectionIds || DASHBOARD_SECTION_ORDER_DEFAULT),
  );
  const normalized = [];
  if (Array.isArray(order)) {
    order.forEach((sectionId) => {
      if (
        typeof sectionId === "string" &&
        knownSectionIds.includes(sectionId) &&
        !normalized.includes(sectionId)
      ) {
        normalized.push(sectionId);
      }
    });
  }
  return normalized.concat(
    knownSectionIds.filter(
      (sectionId) => !normalized.includes(sectionId),
    ),
  );
}

function getDashboardSectionElements() {
  return Array.from(
    document.querySelectorAll(
      ".suggested-work .dashboard-section[data-dashboard-section]",
    ),
  );
}

function getCurrentDashboardSectionOrder() {
  const sectionIds = getDashboardSectionElements().map(
    (section) => section.dataset.dashboardSection,
  );
  return normalizeDashboardSectionOrder(sectionIds, sectionIds);
}

function applyDashboardSectionOrder(order) {
  const container = document.querySelector(".suggested-work");
  if (!container) return;

  const sections = new Map(
    getDashboardSectionElements().map((section) => [
      section.dataset.dashboardSection,
      section,
    ]),
  );
  normalizeDashboardSectionOrder(order, Array.from(sections.keys())).forEach(
    (sectionId) => {
      const section = sections.get(sectionId);
      if (section) container.appendChild(section);
    },
  );
}

function setDashboardSectionOrderStatus(message, isError = false) {
  const status = document.getElementById("dashboard-section-order-status");
  if (!status) return;
  status.textContent = message;
  status.style.color = isError ? "#b00020" : "#28632d";
}

async function saveDashboardSectionOrder(order, previousOrder) {
  try {
    const response = await fetch("/api/settings/dashboard-section-order", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ order }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Unable to save dashboard section order.");
    }
    dashboardSectionOrder = normalizeDashboardSectionOrder(
      data.order || order,
      getDashboardSectionElements().map(
        (section) => section.dataset.dashboardSection,
      ),
    );
    applyDashboardSectionOrder(dashboardSectionOrder);
    setDashboardSectionOrderStatus("Section order saved.");
  } catch (error) {
    dashboardSectionOrder = normalizeDashboardSectionOrder(
      previousOrder,
      getDashboardSectionElements().map(
        (section) => section.dataset.dashboardSection,
      ),
    );
    applyDashboardSectionOrder(dashboardSectionOrder);
    setDashboardSectionOrderStatus(
      "Unable to save section order; previous order restored.",
      true,
    );
  }
}

function initializeDashboardSectionSorting() {
  const container = document.querySelector(".suggested-work");
  if (!container || container.dataset.sectionSortingInitialized === "true") {
    return;
  }
  container.dataset.sectionSortingInitialized = "true";

  getDashboardSectionElements().forEach((section) => {
    const handle = section.querySelector(".dashboard-section-drag-handle");
    if (!handle) return;

    handle.addEventListener("dragstart", (event) => {
      section.classList.add("dragging");
      if (event.dataTransfer) {
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData(
          "text/plain",
          section.dataset.dashboardSection,
        );
      }
      event.stopPropagation();
    });

    handle.addEventListener("dragend", () => {
      section.classList.remove("dragging");
    });

    handle.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
    });

    section.addEventListener("dragover", (event) => {
      const dragging = container.querySelector(".dashboard-section.dragging");
      if (!dragging || dragging === section) return;
      event.preventDefault();
      if (event.dataTransfer) event.dataTransfer.dropEffect = "move";

      const bounds = section.getBoundingClientRect();
      const insertBefore = event.clientY < bounds.top + bounds.height / 2;
      if (insertBefore) {
        container.insertBefore(dragging, section);
      } else {
        container.insertBefore(dragging, section.nextSibling);
      }
    });

    section.addEventListener("drop", async (event) => {
      event.preventDefault();
      const dragging = container.querySelector(".dashboard-section.dragging");
      if (!dragging) return;

      const previousOrder = normalizeDashboardSectionOrder(
        dashboardSectionOrder || getCurrentDashboardSectionOrder(),
      );
      const nextOrder = getCurrentDashboardSectionOrder();
      if (nextOrder.join("|") === previousOrder.join("|")) return;
      dashboardSectionOrder = nextOrder;
      await saveDashboardSectionOrder(nextOrder, previousOrder);
    });
  });
}

async function loadDashboardSectionOrder() {
  if (dashboardSectionOrder) {
    applyDashboardSectionOrder(dashboardSectionOrder);
    initializeDashboardSectionSorting();
    return;
  }

  let order = DASHBOARD_SECTION_ORDER_DEFAULT;
  try {
    const response = await fetch("/api/settings/dashboard-section-order");
    const data = await response.json();
    if (response.ok) order = data.order;
  } catch (error) {
    // The default order keeps the dashboard usable if settings are unavailable.
  }
  dashboardSectionOrder = normalizeDashboardSectionOrder(
    order,
    getDashboardSectionElements().map(
      (section) => section.dataset.dashboardSection,
    ),
  );
  applyDashboardSectionOrder(dashboardSectionOrder);
  initializeDashboardSectionSorting();
}

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

function getFollowupResultCount(data) {
  if (Number.isInteger(data.count)) return data.count;
  return (data.due || []).length + (data.past_due || []).length;
}

async function refreshDashboard() {
  const res = await fetch("/api/dashboard/overview");
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
  await loadDashboardSectionOrder();
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
    const count = document.getElementById("first-followup-count");
    if (!container) return;

    const res = await fetch("/api/dashboard/first-follow-ups");
    const data = await res.json();
    if (count) count.textContent = getFollowupResultCount(data);

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

  const renderExpiringSoon = async () => {
    const container = document.getElementById("expiring-soon");
    const count = document.getElementById("expiring-soon-count");
    if (!container) return;

    container.innerHTML = "<p>Loading Expiring Soon...</p>";
    try {
      const response = await fetch("/api/dashboard/expiring-soon");
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Unable to load Expiring Soon.");
      }

      const domains = data.domains || [];
      if (count) count.textContent = data.count ?? domains.length;
      if (domains.length === 0) {
        container.innerHTML =
          "<p>No domains are currently expiring within the configured window.</p>";
        return;
      }

      const display = (value) => (value == null || value === "" ? "—" : value);
      const sequenceDisplay = (value) =>
        value == null ? "—" : value === 0 ? "Not started" : value;
      container.innerHTML = `
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th>Domain</th>
                <th>Expiry</th>
                <th>Days Left</th>
                <th>Campaign</th>
                <th>Sequence</th>
                <th>Last Contact</th>
                <th>Days Since Last Contact</th>
              </tr>
            </thead>
            <tbody>
              ${domains
                .map(
                  (domain) => `
                <tr>
                  <td>${display(domain.domain_name)}</td>
                  <td>${display(domain.expiry_date)}</td>
                  <td>${display(domain.days_until_expiry)}</td>
                  <td>${display(domain.campaign_status)}</td>
                  <td>${sequenceDisplay(domain.current_sequence)}</td>
                  <td>${display(domain.last_contact_date)}</td>
                  <td>${display(domain.days_since_last_contact)}</td>
                </tr>`,
                )
                .join("")}
            </tbody>
          </table>
        </div>
      `;
    } catch (error) {
      if (count) count.textContent = "—";
      container.innerHTML = `<p class="dashboard-error">${error.message}</p>`;
    }
  };

  const renderReadyForCampaign = async () => {
    const container = document.getElementById("ready-for-campaign");
    const count = document.getElementById("ready-for-campaign-count");
    if (!container) return;

    container.innerHTML = "<p>Loading Ready for Campaign...</p>";
    try {
      const response = await fetch("/api/dashboard/ready-for-campaign");
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Unable to load Ready for Campaign.");
      }

      const domains = data.domains || [];
      if (count) count.textContent = data.count ?? domains.length;
      if (domains.length === 0) {
        container.innerHTML =
          "<p>No domains are currently ready for a campaign.</p>";
        return;
      }

      const display = (value) => (value == null || value === "" ? "—" : value);
      const sequenceDisplay = (value) =>
        value == null ? "—" : value === 0 ? "Not started" : value;
      container.innerHTML = `
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th>Domain</th>
                <th>Status</th>
                <th>Reason</th>
                <th>Last Contact</th>
                <th>Days Since</th>
                <th>Sequence</th>
                <th>Expiry</th>
                <th>Days Left</th>
              </tr>
            </thead>
            <tbody>
              ${domains
                .map(
                  (domain) => `
                <tr>
                  <td>${display(domain.domain_name)}</td>
                  <td>${display(domain.campaign_status)}</td>
                  <td>${display(domain.ready_reason)}</td>
                  <td>${display(domain.last_contact_date)}</td>
                  <td>${display(domain.days_since_last_contact)}</td>
                  <td>${sequenceDisplay(domain.current_sequence)}</td>
                  <td>${display(domain.expiry_date)}</td>
                  <td>${display(domain.days_until_expiry)}</td>
                </tr>`,
                )
                .join("")}
            </tbody>
          </table>
        </div>
      `;
    } catch (error) {
      if (count) count.textContent = "—";
      container.innerHTML = `<p class="dashboard-error">${error.message}</p>`;
    }
  };

  renderFirstFollowups();

  // Render Normal Follow-ups
  const renderNormalFollowups = async () => {
    const container = document.getElementById("normal-followup");
    const count = document.getElementById("normal-followup-count");
    if (!container) return;

    const res = await fetch("/api/dashboard/normal-follow-ups");
    const data = await res.json();
    if (count) count.textContent = getFollowupResultCount(data);
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
  renderExpiringSoon();
  renderReadyForCampaign();
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
