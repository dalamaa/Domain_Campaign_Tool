const DASHBOARD_SECTION_ORDER_DEFAULT = [
  "first_followups",
  "normal_followups",
  "resting_suggestions",
  "expiring_soon",
  "ready_for_campaign",
];
let dashboardSectionOrder = null;
const dashboardTableSortState = {};

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

function dashboardSortIsUnknown(value, type) {
  if (
    value == null ||
    value === "" ||
    ["n/a", "—", "unknown", "null"].includes(String(value).trim().toLowerCase())
  ) {
    return true;
  }
  if (type === "number") return !Number.isFinite(Number(value));
  if (type === "date") return Number.isNaN(Date.parse(value));
  return false;
}

function compareDashboardSortValues(left, right, type, direction) {
  const leftUnknown = dashboardSortIsUnknown(left, type);
  const rightUnknown = dashboardSortIsUnknown(right, type);
  if (leftUnknown || rightUnknown) {
    if (leftUnknown && rightUnknown) return 0;
    return leftUnknown ? 1 : -1;
  }

  let comparison;
  if (type === "number") {
    comparison = Number(left) - Number(right);
  } else if (type === "date") {
    comparison = Date.parse(left) - Date.parse(right);
  } else {
    comparison = String(left).localeCompare(String(right), undefined, {
      sensitivity: "base",
    });
  }
  return comparison * direction;
}

function dashboardSortAttribute(key) {
  return `data-sort-${key.replace(/_/g, "-")}`;
}

function updateDashboardSortIndicators(table, sortKey, direction) {
  table.querySelectorAll("[data-sort-indicator]").forEach((indicator) => {
    indicator.textContent = "↕";
  });
  const activeIndicator = table.querySelector(
    `[data-sort-indicator="${sortKey}"]`,
  );
  if (activeIndicator) activeIndicator.textContent = direction === 1 ? "▲" : "▼";
  table.querySelectorAll("th[data-sort-column]").forEach((header) => {
    header.removeAttribute("aria-sort");
  });
  const activeHeader = table.querySelector(`th[data-sort-column="${sortKey}"]`);
  if (activeHeader) {
    activeHeader.setAttribute("aria-sort", direction === 1 ? "ascending" : "descending");
  }
}

function sortDashboardTable(table, tableId, column) {
  if (!table) return;
  const previous = dashboardTableSortState[tableId];
  const direction =
    previous && previous.key === column.key
      ? previous.direction * -1
      : column.defaultDirection === "desc"
        ? -1
        : 1;
  dashboardTableSortState[tableId] = { key: column.key, direction };

  const body = table.tBodies[0];
  if (!body) return;
  const rows = Array.from(body.rows);
  rows
    .map((row, index) => ({ row, index }))
    .sort((left, right) => {
      const attribute = dashboardSortAttribute(column.key);
      const comparison = compareDashboardSortValues(
        left.row.getAttribute(attribute),
        right.row.getAttribute(attribute),
        column.type,
        direction,
      );
      return comparison || left.index - right.index;
    })
    .forEach(({ row }) => body.appendChild(row));
  updateDashboardSortIndicators(table, column.key, direction);
}

function setupDashboardSortableTable(table, tableId, columns) {
  if (!table) return;
  delete dashboardTableSortState[tableId];
  table.querySelectorAll("button[data-sort-key]").forEach((button) => {
    button.addEventListener("click", () => {
      const column = columns.find((item) => item.key === button.dataset.sortKey);
      if (column) sortDashboardTable(table, tableId, column);
    });
  });
}

function renderDashboardSortHeaders(columns) {
  return columns
    .map(
      (column) => {
        const sortLabel = column.sortLabel || `Sort by ${column.label}`;
        return `<th${column.className ? ` class="${column.className}"` : ""} data-sort-column="${column.key}"><button type="button" class="dashboard-sort-button" data-sort-key="${column.key}" title="${sortLabel}" aria-label="${sortLabel}">${column.label} <span data-sort-indicator="${column.key}">↕</span></button></th>`;
      },
    )
    .join("");
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

function reservationBoardStatePresentation(state) {
  if (state === "AVAILABLE") return { className: "available", label: "Unreserved" };
  if (state === "RESERVED") return { className: "reserved", label: state };
  if (state === "USED") return { className: "used", label: state };
  if (state === "COMPLETED_TODAY") return { className: "completed-today", label: state.replace("_", " ") };
  if (state === "DISABLED") return { className: "disabled", label: state };
  return { className: "", label: String(state || "").replace("_", " ") };
}

async function updateReservationBoard() {
  const res = await fetch("/api/dashboard/reservation-board");
  const data = await res.json();
  const list = document.getElementById("email-accounts-list");
  if (!list) return;
  list.innerHTML = data
    .map((acc) => {
      const presentation = reservationBoardStatePresentation(acc.state);
      const stateClass = presentation.className;
      const stateLabel = presentation.label;
      let domainLabel = "";

      if (acc.state === "RESERVED") {
        domainLabel = `<br><small>${(acc.reserved_domains || []).join("<br>")}</small>`;
      }

      return `
        <div class="acc-item ${stateClass}">
          <strong>${acc.code}</strong>${domainLabel}
          <br><small>${stateLabel}</small>
          <br><small>${acc.count}/${acc.limit}</small>
        </div>`;
    })
    .join("");
}

async function reserveFromDashboardButton(button, campaignId) {
  const originalText = button.textContent;
  const originalDisabled = button.disabled;
  button.disabled = true;
  button.textContent = "Reserving...";

  try {
    const response = await fetch(`/api/campaigns/${campaignId}/reservation`, {
      method: "POST",
    });
    let payload = {};
    try {
      payload = await response.json();
    } catch (_error) {
      // Keep the user-facing error useful when the server returned HTML/text.
    }
    if (!response.ok) {
      const details = Array.isArray(payload.details)
        ? payload.details.join("\n")
        : payload.error;
      throw new Error(details || `Unable to reserve campaign (${response.status}).`);
    }

    // The refreshed server response is authoritative for the new button state.
    await refreshDashboard();
  } catch (error) {
    button.disabled = originalDisabled;
    button.textContent = originalText;
    alert(error && error.message ? error.message : "Unable to reserve campaign.");
  }
}

function escapeDashboardHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderDashboardDomain(domain) {
  const value = domain == null || domain === "" ? "—" : String(domain);
  const escapedValue = escapeDashboardHtml(value);
  return `<span class="dashboard-domain-value" title="${escapedValue}" aria-label="${escapedValue}">${escapedValue}</span>`;
}

function renderDashboardEmailSummary(codes) {
  const values = Array.isArray(codes) ? codes.filter(Boolean) : [];
  if (values.length === 0) return '<span class="compact-email-list">—</span>';
  const full = values.join(", ");
  return `<span class="compact-email-list" title="${full}" aria-label="Operational emails: ${full}">${full}</span>`;
}

function renderDashboardLastContact(campaign) {
  const days = campaign.days_since_last_contact;
  const date = campaign.last_contact_date;
  if (days == null) return '<span class="dashboard-muted">—</span>';
  const title = date ? ` title="${date}"` : "";
  return `<span class="last-contact"${title}>${days}d</span>`;
}

function renderDashboardExpiry(campaign) {
  const days = campaign.days_until_expiry;
  const expiry = campaign.expiry_date;
  const severity = campaign.expiry_severity || "neutral";
  if (days == null) return '<span class="expiry-neutral">—</span>';
  const title = expiry ? ` title="${expiry}"` : "";
  return `<span class="expiry-${severity}"${title}>${days}d</span>`;
}

function renderDashboardDays(value, label = "") {
  if (value == null) return '<span class="dashboard-muted">—</span>';
  const title = label
    ? ` title="${escapeDashboardHtml(`${label}: ${value} days`)}"`
    : "";
  return `<span class="dashboard-day-value"${title}>${value}d</span>`;
}

function renderDashboardStatus(status) {
  const normalized = String(status || "").toUpperCase();
  const labels = {
    ACTIVE: "Active",
    RESTING: "Resting",
    DORMANT: "Dormant",
  };
  const fullLabel = labels[normalized];
  if (!fullLabel) return '<span class="dashboard-muted">—</span>';
  const abbreviation = normalized.charAt(0);
  return `<span class="dashboard-status-badge" title="${fullLabel}" aria-label="${fullLabel}">${abbreviation}</span>`;
}

function renderDashboardSequence(sequence) {
  if (sequence == null) return '<span class="dashboard-muted">—</span>';
  return `<span class="sequence-badge">S${sequence}</span>`;
}

function renderDashboardPriceProgression(progression, progressionItems = []) {
  const items = Array.isArray(progressionItems) ? progressionItems : [];
  const rawValue = progression || "";
  if (!rawValue && items.length === 0) {
    return '<span class="compact-price-progression">—</span>';
  }

  const value = items.length > 0
    ? items.map((item) => (item.price == null ? "—" : item.price)).join(" › ")
    : String(rawValue)
        .split(" › ")
        .map((item) => item.replace(/^[NP](?=\d)/, ""))
        .join(" › ");
  const tooltip = items.length > 0
    ? items
        .map((item) => {
          const sequence = item.sequence == null ? "Unsequenced" : `S${item.sequence}`;
          const action = item.action_type || "Unknown action";
          const price = item.price == null ? "—" : `$${item.price}`;
          const date = item.action_date ? ` (${item.action_date})` : "";
          return `${sequence}: ${price} — ${action}${date}`;
        })
        .join("\n")
    : `Price progression: ${rawValue}`;
  return `<span class="compact-price-progression" title="${tooltip}" aria-label="Price progression: ${value}">${value}</span>`;
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
      <div class="table-container">${renderTable(data.due, false, "first_followup_due")}</div>
      <h4>Past Due</h4>
      <div class="table-container">${renderTable(data.past_due, false, "first_followup_past_due")}</div>
    `;
    setupDashboardSortableTable(
      container.querySelector('table[data-sort-table="first_followup_due"]'),
      "first_followup_due",
      followupSortColumns(),
    );
    setupDashboardSortableTable(
      container.querySelector('table[data-sort-table="first_followup_past_due"]'),
      "first_followup_past_due",
      followupSortColumns(),
    );

    // Attach event delegation for Reserve/Unreserve
    container.querySelectorAll("button[data-action]").forEach((btn) => {
      btn.onclick = async (e) => {
        const action = e.currentTarget.dataset.action;
        const campId = e.currentTarget.dataset.campaignId;
        if (action === "reserve") {
          await reserveFromDashboardButton(e.currentTarget, campId);
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
      buttons = `<button type="button" class="dashboard-reservation-button" data-action="reserve" data-campaign-id="${c.campaign_id}" title="Reserve campaign" aria-label="Reserve campaign" disabled>+</button>
                     <button type="button" class="dashboard-reservation-button" data-action="unreserve" data-campaign-id="${c.campaign_id}" title="Unreserve campaign" aria-label="Unreserve campaign">×</button>`;
    } else if (res.state === "Reserved") {
      buttons = `<button type="button" class="dashboard-reservation-button" data-action="reserve" data-campaign-id="${c.campaign_id}" title="Reserve campaign" aria-label="Reserve campaign" disabled>+</button>
                     <button type="button" class="dashboard-reservation-button" data-action="unreserve" data-campaign-id="${c.campaign_id}" title="Unreserve campaign" aria-label="Unreserve campaign" disabled>×</button> ⚠`;
    } else {
      buttons = `<button type="button" class="dashboard-reservation-button" data-action="reserve" data-campaign-id="${c.campaign_id}" title="Reserve campaign" aria-label="Reserve campaign">+</button>
                     <button type="button" class="dashboard-reservation-button" data-action="unreserve" data-campaign-id="${c.campaign_id}" title="Unreserve campaign" aria-label="Unreserve campaign" disabled>×</button>`;
    }

    return buttons;
  };

  const followupSortColumns = () => [
    { key: "domain", label: "Domain", type: "text", defaultDirection: "asc" },
    { key: "last_contact", label: "LC", sortLabel: "Sort by Last Contact", type: "date", defaultDirection: "desc", className: "dashboard-metric-column" },
    { key: "expiry", label: "Expiry", type: "number", defaultDirection: "asc", className: "dashboard-metric-column" },
    { key: "sequence", label: "Seq", type: "number", defaultDirection: "asc", className: "dashboard-metric-column" },
  ];

  const renderTable = (list, isNormal = false, tableId = "followup") => `
    <table class="dashboard-suggested-table dashboard-followup-table" data-sort-table="${tableId}">
      <thead>
        <tr>
          ${renderDashboardSortHeaders([followupSortColumns()[0]])}
          <th>Email Used</th>
          ${renderDashboardSortHeaders([followupSortColumns()[1], followupSortColumns()[2], followupSortColumns()[3]])}
          <th>Price Progression</th><th>Reserve</th><th>Rest</th>
        </tr>
      </thead>
      <tbody>
        ${list
          .map(
            (c) => `
        <tr data-sort-domain="${c.domain}" data-sort-days="${isNormal ? c.days_since_contact ?? "" : c.days_since_outreach ?? ""}"
          data-sort-last-contact="${c.last_contact_date || ""}"
          data-sort-expiry="${c.days_until_expiry ?? ""}"
          data-sort-sequence="${c.current_sequence ?? ""}">
          <td class="dashboard-domain-cell">${renderDashboardDomain(c.domain)}</td>
          <td class="dashboard-email-cell">${renderDashboardEmailSummary(c.operational_emails || c.emails_used)}</td>
          <td class="dashboard-metric-column">${renderDashboardLastContact(c)}</td>
          <td class="dashboard-metric-column">${renderDashboardExpiry(c)}</td>
          <td class="dashboard-metric-column">${renderDashboardSequence(c.current_sequence)}</td>
          <td class="dashboard-price-cell">${renderDashboardPriceProgression(c.price_progression, c.price_progression_items)}</td>
          <td class="dashboard-reservation-cell">${getResButtons(c)}</td>
          <td class="dashboard-rest-cell">${c.resting_suggested ? '<span class="rest-suggested rest-indicator" title="Rest suggested" aria-label="Rest suggested">R</span>' : ""}</td>
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

      const columns = [
        { key: "domain", label: "Domain", type: "text", defaultDirection: "asc" },
        { key: "status", label: "Status", type: "text", defaultDirection: "asc", className: "dashboard-status-cell" },
        { key: "last_contact", label: "LC", sortLabel: "Sort by Last Contact", type: "date", defaultDirection: "asc", className: "dashboard-metric-column" },
        { key: "known_activity_age", label: "Known Activity", type: "number", defaultDirection: "desc", className: "dashboard-metric-column" },
        { key: "expiry", label: "Expiry", type: "date", defaultDirection: "asc", className: "dashboard-metric-column" },
        { key: "sequence", label: "Seq", type: "number", defaultDirection: "asc", className: "dashboard-metric-column" },
      ];

      container.innerHTML = `
        <div class="table-container">
          <table class="dashboard-suggested-table dashboard-resting-table" data-sort-table="resting_suggestions">
            <thead>
              <tr>
                ${renderDashboardSortHeaders(columns.slice(0, 2))}
                <th>Email Used</th>
                ${renderDashboardSortHeaders(columns.slice(2))}
                <th>Price Progression</th>
                <th>Rest</th>
              </tr>
            </thead>
            <tbody>
              ${suggestions
                .map(
                  (campaign) => `
                <tr
                  data-sort-domain="${campaign.domain}"
                  data-sort-status="${campaign.status || ""}"
                  data-sort-sequence="${campaign.eligibility_metrics.current_sequence ?? ""}"
                  data-sort-last-contact="${campaign.last_contact_date || ""}"
                  data-sort-known-activity-age="${campaign.eligibility_metrics.known_activity_age_days ?? ""}"
                  data-sort-expiry="${campaign.expiry_date || ""}"
                >
                  <td class="dashboard-domain-cell">${renderDashboardDomain(campaign.domain)}</td>
                  <td class="dashboard-status-cell">${renderDashboardStatus(campaign.status || "ACTIVE")}</td>
                  <td class="dashboard-email-cell">${renderDashboardEmailSummary(campaign.operational_emails)}</td>
                  <td class="dashboard-metric-column">${renderDashboardLastContact({
                    last_contact_date: campaign.last_contact_date,
                    days_since_last_contact: campaign.eligibility_metrics.days_since_last_contact,
                  })}</td>
                  <td class="dashboard-metric-column">${renderDashboardDays(campaign.eligibility_metrics.known_activity_age_days, "Known activity age")}</td>
                  <td class="dashboard-metric-column">${renderDashboardExpiry(campaign)}</td>
                  <td class="dashboard-metric-column">${renderDashboardSequence(campaign.current_sequence)}</td>
                  <td class="dashboard-price-cell">${renderDashboardPriceProgression(campaign.price_progression, campaign.price_progression_items)}</td>
                  <td class="dashboard-rest-cell">
                    <button
                      type="button"
                      class="dashboard-rest-action"
                      data-action="rest"
                      data-campaign-id="${campaign.campaign_id}"
                      data-domain="${campaign.domain}"
                      title="Move to Resting"
                      aria-label="Move to Resting"
                    >R</button>
                  </td>
                </tr>`,
                )
                .join("")}
            </tbody>
          </table>
        </div>
      `;

      setupDashboardSortableTable(
        container.querySelector('table[data-sort-table="resting_suggestions"]'),
        "resting_suggestions",
        columns,
      );

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

      const columns = [
        { key: "domain", label: "Domain", type: "text", defaultDirection: "asc" },
        { key: "status", label: "Status", type: "text", defaultDirection: "asc", className: "dashboard-status-cell" },
        { key: "last_contact", label: "LC", sortLabel: "Sort by Last Contact", type: "date", defaultDirection: "asc", className: "dashboard-metric-column" },
        { key: "expiry", label: "Expiry", type: "date", defaultDirection: "asc", className: "dashboard-metric-column" },
        { key: "sequence", label: "Seq", type: "number", defaultDirection: "asc", className: "dashboard-metric-column" },
      ];
      container.innerHTML = `
        <div class="table-container">
          <table class="dashboard-suggested-table dashboard-expiring-table" data-sort-table="expiring_soon">
            <thead>
              <tr>
                ${renderDashboardSortHeaders(columns.slice(0, 2))}
                <th>Email Used</th>
                ${renderDashboardSortHeaders(columns.slice(2))}
                <th>Price Progression</th>
              </tr>
            </thead>
            <tbody>
              ${domains
                .map(
                  (domain) => `
                <tr
                  data-sort-domain="${domain.domain_name || ""}"
                  data-sort-days-left="${domain.days_until_expiry ?? ""}"
                  data-sort-campaign="${domain.campaign_status || ""}"
                  data-sort-sequence="${domain.current_sequence ?? ""}"
                  data-sort-last-contact="${domain.last_contact_date || ""}"
                  data-sort-days-since-last-contact="${domain.days_since_last_contact ?? ""}"
                  data-sort-expiry="${domain.expiry_date || ""}"
                >
                  <td class="dashboard-domain-cell">${renderDashboardDomain(domain.domain_name)}</td>
                  <td class="dashboard-status-cell">${renderDashboardStatus(domain.campaign_status)}</td>
                  <td class="dashboard-email-cell">${renderDashboardEmailSummary(domain.operational_emails)}</td>
                  <td class="dashboard-metric-column">${renderDashboardLastContact(domain)}</td>
                  <td class="dashboard-metric-column">${renderDashboardExpiry(domain)}</td>
                  <td class="dashboard-metric-column">${renderDashboardSequence(domain.current_sequence)}</td>
                  <td class="dashboard-price-cell">${renderDashboardPriceProgression(domain.price_progression, domain.price_progression_items)}</td>
                </tr>`,
                )
                .join("")}
            </tbody>
          </table>
        </div>
      `;
      setupDashboardSortableTable(
        container.querySelector('table[data-sort-table="expiring_soon"]'),
        "expiring_soon",
        columns,
      );
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

      const columns = [
        { key: "domain", label: "Domain", type: "text", defaultDirection: "asc" },
        { key: "status", label: "Status", type: "text", defaultDirection: "asc", className: "dashboard-status-cell" },
        { key: "last_contact", label: "LC", sortLabel: "Sort by Last Contact", type: "date", defaultDirection: "asc", className: "dashboard-metric-column" },
        { key: "expiry", label: "Expiry", type: "date", defaultDirection: "asc", className: "dashboard-metric-column" },
        { key: "sequence", label: "Seq", type: "number", defaultDirection: "asc", className: "dashboard-metric-column" },
      ];
      container.innerHTML = `
        <div class="table-container">
          <table class="dashboard-suggested-table dashboard-ready-table" data-sort-table="ready_for_campaign">
            <thead>
              <tr>
                ${renderDashboardSortHeaders(columns.slice(0, 2))}
                <th>Email Used</th>
                ${renderDashboardSortHeaders(columns.slice(2))}
                <th>Price Progression</th>
              </tr>
            </thead>
            <tbody>
              ${domains
                .map(
                  (domain) => `
                <tr
                  data-sort-domain="${domain.domain_name || ""}"
                  data-sort-status="${domain.campaign_status || ""}"
                  data-sort-last-contact="${domain.last_contact_date || ""}"
                  data-sort-days-since="${domain.days_since_last_contact ?? ""}"
                  data-sort-sequence="${domain.current_sequence ?? ""}"
                  data-sort-expiry="${domain.expiry_date || ""}"
                  data-sort-days-left="${domain.days_until_expiry ?? ""}"
                >
                  <td class="dashboard-domain-cell">${renderDashboardDomain(domain.domain_name)}</td>
                  <td class="dashboard-status-cell">${renderDashboardStatus(domain.campaign_status)}</td>
                  <td class="dashboard-email-cell">${renderDashboardEmailSummary(domain.operational_emails)}</td>
                  <td class="dashboard-metric-column">${renderDashboardLastContact(domain)}</td>
                  <td class="dashboard-metric-column">${renderDashboardExpiry(domain)}</td>
                  <td class="dashboard-metric-column">${renderDashboardSequence(domain.current_sequence)}</td>
                  <td class="dashboard-price-cell">${renderDashboardPriceProgression(domain.price_progression, domain.price_progression_items)}</td>
                </tr>`,
                )
                .join("")}
            </tbody>
          </table>
        </div>
      `;
      setupDashboardSortableTable(
        container.querySelector('table[data-sort-table="ready_for_campaign"]'),
        "ready_for_campaign",
        columns,
      );
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
      <div class="table-container">${renderTable(data.due, true, "normal_followup_due")}</div>
      <h4>Past Due</h4>
      <div class="table-container">${renderTable(data.past_due, true, "normal_followup_past_due")}</div>
    `;
    setupDashboardSortableTable(
      container.querySelector('table[data-sort-table="normal_followup_due"]'),
      "normal_followup_due",
      followupSortColumns(),
    );
    setupDashboardSortableTable(
      container.querySelector('table[data-sort-table="normal_followup_past_due"]'),
      "normal_followup_past_due",
      followupSortColumns(),
    );

    // Attach event delegation for Reserve/Unreserve
    container.querySelectorAll("button[data-action]").forEach((btn) => {
      btn.onclick = async (e) => {
        const action = e.currentTarget.dataset.action;
        const campId = e.currentTarget.dataset.campaignId;
        if (action === "reserve") {
          await reserveFromDashboardButton(e.currentTarget, campId);
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
