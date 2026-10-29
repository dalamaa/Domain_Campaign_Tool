const DASHBOARD_SECTION_ORDER_DEFAULT = [
  "first_followups",
  "normal_followups",
  "recently_worked",
  "cooling",
  "resting_suggestions",
  "expiring_soon",
  "ready_for_campaign",
];
let dashboardSectionOrder = null;
const dashboardTableSortState = {};
let dashboardRefreshInProgress = false;

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

async function moveDashboardSectionByKeyboard(section, offset) {
  const sections = getDashboardSectionElements();
  const currentIndex = sections.indexOf(section);
  const nextIndex = currentIndex + offset;
  if (currentIndex < 0 || nextIndex < 0 || nextIndex >= sections.length) return;

  const previousOrder = normalizeDashboardSectionOrder(
    dashboardSectionOrder || getCurrentDashboardSectionOrder(),
  );
  const nextSection = sections[nextIndex];
  const container = section.parentElement;
  if (offset < 0) container.insertBefore(section, nextSection);
  else container.insertBefore(section, nextSection.nextSibling);

  const nextOrder = getCurrentDashboardSectionOrder();
  dashboardSectionOrder = nextOrder;
  const label = section.querySelector(".accordion-toggle")?.textContent.trim() || "Section";
  setDashboardSectionOrderStatus(`Moving ${label} to position ${nextIndex + 1}.`);
  await saveDashboardSectionOrder(nextOrder, previousOrder);
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

    handle.addEventListener("keydown", async (event) => {
      if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
      event.preventDefault();
      const offset = event.key === "ArrowUp" ? -1 : 1;
      await moveDashboardSectionByKeyboard(section, offset);
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
  if (tableId === "todays_campaigns") {
    updateTodayBoardSortControls(table);
  }
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
  if (dashboardRefreshInProgress) return;
  dashboardRefreshInProgress = true;
  const refreshButton = document.getElementById("dashboard-refresh-button");
  if (refreshButton) {
    refreshButton.disabled = true;
    refreshButton.textContent = "Refreshing…";
  }

  try {
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
    await updateReservationBoard();
    await loadDashboardSectionOrder();
    await renderSuggestedWork();
    await renderTodaysCampaigns();
  } finally {
    dashboardRefreshInProgress = false;
    if (refreshButton) {
      refreshButton.disabled = false;
      refreshButton.textContent = "Refresh";
    }
  }
}

const TODAY_BOARD_SORT_COLUMNS = [
  { key: "domain", label: "Domain", type: "text" },
  { key: "status", label: "Status", type: "text" },
  { key: "sequence", label: "Sequence", type: "number" },
  { key: "current_price", label: "Current Price", type: "number" },
  { key: "emails", label: "Email", type: "text" },
  { key: "shared_emails", label: "Shared Email", type: "text" },
];

function escapeDashboardHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

function updateTodayBoardDragHandles(table) {
  const sorted = Boolean(dashboardTableSortState.todays_campaigns);
  const rows = Array.from(table.tBodies[0]?.rows || []);
  rows.forEach((row) => {
    const handle = row.querySelector(".today-board-drag-handle");
    if (!handle) return;
    handle.draggable = !sorted;
    handle.tabIndex = sorted ? -1 : 0;
    handle.setAttribute("aria-disabled", sorted ? "true" : "false");
    handle.classList.toggle("is-disabled", sorted);
  });
}

function updateTodayBoardSortControls(table) {
  const sorted = Boolean(dashboardTableSortState.todays_campaigns);
  const customOrderButton = document.getElementById("today-board-custom-order");
  if (customOrderButton) {
    customOrderButton.hidden = !sorted;
  }
  const status = document.getElementById("today-board-status");
  if (status) status.textContent = sorted ? "Temporary column sort is active." : "";
  updateTodayBoardDragHandles(table);
}

function resetTodayBoardSort(table) {
  delete dashboardTableSortState.todays_campaigns;
  table.querySelectorAll("[data-sort-indicator]").forEach((indicator) => {
    indicator.textContent = "↕";
  });
  table.querySelectorAll("th[aria-sort]").forEach((header) => {
    header.removeAttribute("aria-sort");
  });
  updateTodayBoardSortControls(table);
}

function initializeTodayBoardTable() {
  const table = document.getElementById("todays-campaigns-table");
  if (!table || table.dataset.todayBoardInitialized === "true") return table;
  table.dataset.todayBoardInitialized = "true";

  setupDashboardSortableTable(table, "todays_campaigns", TODAY_BOARD_SORT_COLUMNS);
  table.addEventListener("change", async (event) => {
    const checkbox = event.target.closest(".today-board-done-checkbox");
    if (checkbox) await updateTodayBoardDone(checkbox);
  });
  table.addEventListener("click", async (event) => {
    const removeButton = event.target.closest(".today-board-remove");
    if (removeButton) await removeTodayBoardEntry(removeButton);
  });
  table.addEventListener("keydown", async (event) => {
    const handle = event.target.closest(".today-board-drag-handle");
    if (!handle || dashboardTableSortState.todays_campaigns) return;
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    event.preventDefault();
    const row = handle.closest("tr");
    const rows = Array.from(table.tBodies[0].rows);
    const index = rows.indexOf(row);
    const nextIndex = index + (event.key === "ArrowUp" ? -1 : 1);
    if (nextIndex < 0 || nextIndex >= rows.length) return;
    if (event.key === "ArrowUp") {
      row.parentElement.insertBefore(row, rows[nextIndex]);
    } else {
      row.parentElement.insertBefore(rows[nextIndex], row);
    }
    await persistTodayBoardOrder(
      Array.from(table.tBodies[0].rows, (item) => Number(item.dataset.campaignId)),
      row.dataset.campaignId,
    );
  });
  table.addEventListener("dragstart", (event) => {
    const handle = event.target.closest(".today-board-drag-handle");
    const row = handle?.closest("tr");
    if (!handle || !row || dashboardTableSortState.todays_campaigns) {
      event.preventDefault();
      return;
    }
    row.classList.add("today-board-dragging");
    table.dataset.todayBoardDropHandled = "false";
    handle.setAttribute("aria-grabbed", "true");
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", row.dataset.campaignId);
    }
    event.stopPropagation();
  });
  table.addEventListener("dragover", (event) => {
    const targetRow = event.target.closest("tbody tr.today-board-row");
    const draggingRow = table.querySelector("tbody tr.today-board-dragging");
    if (
      !targetRow ||
      !draggingRow ||
      targetRow === draggingRow ||
      dashboardTableSortState.todays_campaigns
    ) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
    const bounds = targetRow.getBoundingClientRect();
    if (event.clientY < bounds.top + bounds.height / 2) {
      targetRow.parentElement.insertBefore(draggingRow, targetRow);
    } else {
      targetRow.parentElement.insertBefore(draggingRow, targetRow.nextSibling);
    }
  });
  table.addEventListener("drop", async (event) => {
    const draggingRow = table.querySelector("tbody tr.today-board-dragging");
    if (!draggingRow) return;
    event.preventDefault();
    event.stopPropagation();
    table.dataset.todayBoardDropHandled = "true";
    const campaignId = draggingRow.dataset.campaignId;
    const campaignIds = Array.from(
      table.tBodies[0].rows,
      (row) => Number(row.dataset.campaignId),
    );
    draggingRow.classList.remove("today-board-dragging");
    await persistTodayBoardOrder(campaignIds, campaignId);
  });
  table.addEventListener("dragend", (event) => {
    const handle = event.target.closest(".today-board-drag-handle");
    if (handle) handle.setAttribute("aria-grabbed", "false");
    table.querySelector("tbody tr.today-board-dragging")?.classList.remove("today-board-dragging");
    const dropped = table.dataset.todayBoardDropHandled === "true";
    delete table.dataset.todayBoardDropHandled;
    if (!dropped) renderTodaysCampaigns();
  });

  document.getElementById("today-board-custom-order")?.addEventListener(
    "click",
    () => renderTodaysCampaigns(),
  );
  document.getElementById("today-board-reset")?.addEventListener(
    "click",
    resetTodayBoard,
  );
  return table;
}

async function postTodayBoardRequest(url, payload = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Today board update failed.");
  return data;
}

async function renderTodaysCampaigns() {
  const table = initializeTodayBoardTable();
  const container = table?.querySelector("tbody");
  if (!container) return;

  try {
    const response = await fetch("/api/dashboard/todays-campaigns");
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Unable to load Today board.");

    resetTodayBoardSort(table);
    container.innerHTML = data.map((campaign) => {
      const domain = escapeDashboardHtml(campaign.domain);
      const emails = campaign.emails || [];
      const sharedEmails = campaign.shared_emails || [];
      const encodedDomain = encodeURIComponent(campaign.domain || "");
      const checked = campaign.is_done ? " checked" : "";
      const doneClass = campaign.is_done ? " today-board-done" : "";
      return `
        <tr class="today-board-row${doneClass}"
          data-campaign-id="${campaign.campaign_id}"
          data-sort-domain="${domain}"
          data-sort-status="${escapeDashboardHtml(campaign.status)}"
          data-sort-sequence="${campaign.sequence ?? ""}"
          data-sort-current-price="${campaign.current_price ?? ""}"
          data-sort-emails="${escapeDashboardHtml(emails.join(", "))}"
          data-sort-shared-emails="${escapeDashboardHtml(sharedEmails.join(", "))}"
        >
          <td><input class="today-board-done-checkbox" type="checkbox"${checked} aria-label="Mark ${domain} as done"></td>
          <td class="dashboard-domain-cell"><a class="today-board-domain" href="/domains?history_id=${campaign.campaign_id}&domain=${encodedDomain}" target="_blank" rel="noopener noreferrer">${domain}</a></td>
          <td>${escapeDashboardHtml(campaign.status)}</td>
          <td>${escapeDashboardHtml(campaign.sequence)}</td>
          <td>$${escapeDashboardHtml(campaign.current_price)}</td>
          <td>${escapeDashboardHtml(emails.join(", "))}</td>
          <td>${escapeDashboardHtml(sharedEmails.join(", ")) || "—"}</td>
          <td class="today-board-drag-cell">
          <span class="today-board-drag-handle" draggable="true" role="button" tabindex="0" aria-label="Reorder ${domain}; use arrow keys to move" aria-grabbed="false" title="Drag to reorder">⋮⋮</span>
          </td>
          <td><button type="button" class="today-board-remove" aria-label="Remove ${domain} from Today board" title="Remove from Today board">×</button></td>
        </tr>`;
    }).join("");
    updateTodayBoardDragHandles(table);
  } catch (error) {
    container.innerHTML = `<tr><td colspan="9" class="dashboard-error">${escapeDashboardHtml(error.message)}</td></tr>`;
  }
}

async function updateTodayBoardDone(checkbox) {
  const campaignId = checkbox.closest("tr")?.dataset.campaignId;
  if (!campaignId) return;
  const done = checkbox.checked;
  checkbox.disabled = true;
  try {
    await postTodayBoardRequest(
      `/api/dashboard/todays-campaigns/${campaignId}/done`,
      { is_done: done },
    );
    checkbox.closest("tr")?.classList.toggle("today-board-done", done);
    if (typeof showToast === "function") {
      showToast(done ? "Marked done for today." : "Done mark cleared.");
    }
  } catch (error) {
    checkbox.checked = !done;
    if (typeof showToast === "function") showToast(error.message, "error");
  } finally {
    checkbox.disabled = false;
  }
}

async function persistTodayBoardOrder(campaignIds, focusCampaignId = null) {
  const focusHandle = () => {
    if (!focusCampaignId) return;
    document
      .querySelector(`#todays-campaigns-table tr[data-campaign-id="${focusCampaignId}"] .today-board-drag-handle`)
      ?.focus();
  };
  try {
    await postTodayBoardRequest(
      "/api/dashboard/todays-campaigns/reorder",
      { campaign_ids: campaignIds },
    );
    await renderTodaysCampaigns();
    focusHandle();
  } catch (error) {
    if (typeof showToast === "function") showToast(error.message, "error");
    await renderTodaysCampaigns();
    focusHandle();
  }
}

async function removeTodayBoardEntry(button) {
  const row = button.closest("tr");
  const campaignId = row?.dataset.campaignId;
  const domain = row?.querySelector(".today-board-domain")?.textContent || "this campaign";
  if (!campaignId || !window.confirm(`Remove ${domain} from today's board only? Its reservation will remain unchanged.`)) return;

  row.remove();
  const table = document.getElementById("todays-campaigns-table");
  updateTodayBoardDragHandles(table);
  try {
    await postTodayBoardRequest(
      `/api/dashboard/todays-campaigns/${campaignId}/remove`,
    );
    if (typeof showToast === "function") showToast("Removed from Today board. Reservation unchanged.");
  } catch (error) {
    if (typeof showToast === "function") showToast(error.message, "error");
    await renderTodaysCampaigns();
  }
}

async function resetTodayBoard() {
  const confirmation = "This resets only today's board order, Done state, and Today-only removals. Campaigns and reservations are not changed.";
  if (!window.confirm(confirmation)) return;

  const button = document.getElementById("today-board-reset");
  if (button) button.disabled = true;
  try {
    await postTodayBoardRequest("/api/dashboard/todays-campaigns/reset");
    await renderTodaysCampaigns();
    if (typeof showToast === "function") showToast("Today board reset.");
  } catch (error) {
    if (typeof showToast === "function") showToast(error.message, "error");
  } finally {
    if (button) button.disabled = false;
  }
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
      const code = escapeDashboardHtml(acc.code);
      const stateLabel = escapeDashboardHtml(presentation.label);
      const count = escapeDashboardHtml(acc.count ?? 0);
      const limit = escapeDashboardHtml(acc.limit ?? 0);
      const reservedDomains = acc.state === "RESERVED" && Array.isArray(acc.reserved_domains)
        ? acc.reserved_domains.map((domain) => String(domain ?? ""))
        : [];
      const visibleDomains = reservedDomains.slice(0, 2);
      const additionalDomains = reservedDomains.slice(2);
      const domainMarkup = visibleDomains.length
        ? `<div class="reservation-board-domains" role="list" aria-label="Reserved domains">
            ${visibleDomains.map((domain) => {
              const fullDomain = escapeDashboardHtml(domain);
              return `<span class="reservation-board-domain" role="listitem" title="${fullDomain}" aria-label="${fullDomain}">${fullDomain}</span>`;
            }).join("")}
            ${additionalDomains.length ? (() => {
              const additionalNames = escapeDashboardHtml(additionalDomains.join(", "));
              const additionalLabel = `${additionalDomains.length} more domains: ${additionalNames}`;
              return `<span class="reservation-board-domain reservation-board-more" title="Additional domains: ${additionalNames}" aria-label="${escapeDashboardHtml(additionalLabel)}">+${additionalDomains.length} more</span>`;
            })() : ""}
          </div>`
        : "";

      return `
        <div class="acc-item ${presentation.className}">
          <strong class="reservation-board-code" title="${code}">${code}</strong>
          ${domainMarkup}
          <div class="reservation-board-meta">
            <span class="reservation-board-state">${stateLabel}</span>
            <span class="reservation-board-count">${count}/${limit}</span>
          </div>
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

function attachDashboardReservationActions(container) {
  if (!container) return;
  container.querySelectorAll("button.dashboard-reservation-button[data-action]").forEach((button) => {
    button.onclick = async (event) => {
      const clicked = event.currentTarget;
      const action = clicked.dataset.action;
      const campaignId = clicked.dataset.campaignId;
      if (action === "reserve") {
        await reserveFromDashboardButton(clicked, campaignId);
        return;
      }
      if (action !== "unreserve") return;

      clicked.disabled = true;
      try {
        const response = await fetch(`/api/campaigns/${campaignId}/reservation`, {
          method: "DELETE",
        });
        const result = await response.json();
        if (!response.ok) {
          throw new Error(result.error || "Unable to unreserve campaign.");
        }
        await refreshDashboard();
      } catch (error) {
        alert(error.message || "Unable to unreserve campaign.");
        clicked.disabled = false;
      }
    };
  });
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

function renderDashboardActionAge(campaign) {
  const days = campaign.days_since_action;
  const date = campaign.latest_action_date;
  if (days == null) return '<span class="dashboard-muted">—</span>';
  const title = date
    ? ` title="Last worked ${escapeDashboardHtml(date)}"`
    : "";
  const label = days === 0 ? "Today" : `${days}d ago`;
  return `<span class="last-contact"${title}>${label}</span>`;
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

function renderDashboardTemperature(temperature, label, emoji, symbolOnly = false) {
  const normalized = String(temperature || "NOT_STARTED").toUpperCase();
  const fallbackLabels = {
    HOT: "Hot",
    TEPID: "Tepid",
    COOLING: "Cooling",
    READY: "Ready",
    NOT_STARTED: "Not started",
  };
  const text = label || fallbackLabels[normalized] || "Not started";
  const icon = emoji || "";
  const display = symbolOnly ? icon : `${icon} ${text}`;
  return `<span class="dashboard-temperature temperature-${normalized.toLowerCase()}" title="${text}" aria-label="${text}">${display}</span>`;
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

function renderDashboardRowActions(actions) {
  return `<div class="dashboard-row-actions">${actions || ""}</div>`;
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

    attachDashboardReservationActions(container);
  };

  const getResButtons = (c) => {
    const res = c.reservation || { state: "Unreserved", reserved_by: null };
    const status = String(c.campaign_status || c.status || "").toUpperCase();
    let buttons = "";

    if (res.state === "Reserved" && res.reserved_by === c.domain) {
      buttons = `<button type="button" class="dashboard-reservation-button" data-action="reserve" data-campaign-id="${c.campaign_id}" title="Reserve campaign" aria-label="Reserve campaign" disabled>+</button><button type="button" class="dashboard-reservation-button" data-action="unreserve" data-campaign-id="${c.campaign_id}" title="Unreserve campaign" aria-label="Unreserve campaign">×</button>`;
    } else if (res.state === "Reserved") {
      buttons = `<button type="button" class="dashboard-reservation-button" data-action="reserve" data-campaign-id="${c.campaign_id}" title="Reserve campaign" aria-label="Reserve campaign" disabled>+</button><button type="button" class="dashboard-reservation-button" data-action="unreserve" data-campaign-id="${c.campaign_id}" title="Unreserve campaign" aria-label="Unreserve campaign" disabled>×</button><span aria-label="Reserved by another campaign" title="Reserved by another campaign">⚠</span>`;
    } else if (status === "DORMANT") {
      buttons = '<span class="dashboard-reservation-unavailable" title="Start the campaign before reserving it">Start first</span>';
    } else {
      buttons = `<button type="button" class="dashboard-reservation-button" data-action="reserve" data-campaign-id="${c.campaign_id}" title="Reserve campaign" aria-label="Reserve campaign">+</button><button type="button" class="dashboard-reservation-button" data-action="unreserve" data-campaign-id="${c.campaign_id}" title="Unreserve campaign" aria-label="Unreserve campaign" disabled>×</button>`;
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
          <td class="dashboard-reservation-cell">${renderDashboardRowActions(getResButtons(c))}</td>
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
                <th>Actions</th>
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
                  <td class="dashboard-actions-cell">${renderDashboardRowActions(`${getResButtons(campaign)}<button type="button" class="dashboard-rest-action" data-action="rest" data-campaign-id="${campaign.campaign_id}" data-domain="${campaign.domain}" title="Move to Resting" aria-label="Move to Resting">R</button>`)}</td>
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
      attachDashboardReservationActions(container);

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
            showToast(`${domain} moved to Resting.`);
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

  const renderCooling = async () => {
    const container = document.getElementById("cooling");
    const count = document.getElementById("cooling-count");
    if (!container) return;

    container.innerHTML = "<p>Loading Cooling...</p>";
    try {
      const response = await fetch("/api/dashboard/cooling");
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Unable to load Cooling.");
      }

      const domains = data.domains || [];
      if (count) count.textContent = data.count ?? domains.length;
      if (domains.length === 0) {
        container.innerHTML = "<p>No campaigns are currently Cooling.</p>";
        return;
      }

      const columns = [
        { key: "domain", label: "Domain", type: "text", defaultDirection: "asc" },
        { key: "temperature", label: "Temperature", type: "text", defaultDirection: "asc" },
        { key: "status", label: "Status", type: "text", defaultDirection: "asc", className: "dashboard-status-cell" },
        { key: "last_contact", label: "LC", sortLabel: "Sort by Last Contact", type: "date", defaultDirection: "asc", className: "dashboard-metric-column" },
        { key: "expiry", label: "Expiry", type: "number", defaultDirection: "asc", className: "dashboard-metric-column" },
        { key: "sequence", label: "Seq", type: "number", defaultDirection: "asc", className: "dashboard-metric-column" },
      ];

      container.innerHTML = `
        <div class="table-container">
          <table class="dashboard-suggested-table dashboard-cooling-table" data-sort-table="cooling">
            <thead>
              <tr>
                ${renderDashboardSortHeaders(columns.slice(0, 3))}
                <th>Email Used</th>
                ${renderDashboardSortHeaders(columns.slice(3))}
                <th>Price Progression</th><th>Actions</th>
              </tr>
            </thead>
            <tbody>
              ${domains.map((campaign) => `
                <tr
                  data-sort-domain="${campaign.domain || ""}"
                  data-sort-temperature="${campaign.temperature || ""}"
                  data-sort-status="${campaign.status || ""}"
                  data-sort-last-contact="${campaign.last_contact_date || ""}"
                  data-sort-expiry="${campaign.days_until_expiry ?? ""}"
                  data-sort-sequence="${campaign.current_sequence ?? ""}"
                >
                  <td class="dashboard-domain-cell">${renderDashboardDomain(campaign.domain)}</td>
                  <td>${renderDashboardTemperature(campaign.temperature, campaign.temperature_label, campaign.temperature_emoji, true)}</td>
                  <td class="dashboard-status-cell">${renderDashboardStatus(campaign.status)}</td>
                  <td class="dashboard-email-cell">${renderDashboardEmailSummary(campaign.operational_emails)}</td>
                  <td class="dashboard-metric-column">${renderDashboardLastContact(campaign)}</td>
                  <td class="dashboard-metric-column">${renderDashboardExpiry(campaign)}</td>
                  <td class="dashboard-metric-column">${renderDashboardSequence(campaign.current_sequence)}</td>
                  <td class="dashboard-price-cell">${renderDashboardPriceProgression(campaign.price_progression, campaign.price_progression_items)}</td>
                  <td class="dashboard-actions-cell">${renderDashboardRowActions(`${getResButtons(campaign)}${campaign.can_rest ? `<button type="button" class="dashboard-rest-action" data-action="rest" data-campaign-id="${campaign.campaign_id}" data-domain="${campaign.domain}" title="Move to Resting" aria-label="Move to Resting">R</button>` : ""}`)}</td>
                </tr>`).join("")}
            </tbody>
          </table>
        </div>
      `;

      const table = container.querySelector('table[data-sort-table="cooling"]');
      setupDashboardSortableTable(table, "cooling", columns);
      attachDashboardReservationActions(container);
      container.querySelectorAll("button[data-action='rest']").forEach((button) => {
        button.onclick = async () => {
          const domain = button.dataset.domain;
          const campaignId = button.dataset.campaignId;
          if (!window.confirm(`Move ${domain} to Resting?`)) return;
          button.disabled = true;
          try {
            const response = await fetch(`/api/campaigns/${campaignId}/rest`, { method: "POST" });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || "Unable to move campaign to Resting.");
            await refreshDashboard();
            showToast(`${domain} moved to Resting.`);
          } catch (error) {
            showToast(error.message || "Unable to move campaign to Resting.", "error");
            button.disabled = false;
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
                <th>Price Progression</th><th>Reserve</th>
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
                  <td class="dashboard-reservation-cell">${renderDashboardRowActions(getResButtons({
                    ...domain,
                    domain: domain.domain_name,
                    status: domain.campaign_status,
                  }))}</td>
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
      attachDashboardReservationActions(container);
    } catch (error) {
      if (count) count.textContent = "—";
      container.innerHTML = `<p class="dashboard-error">${error.message}</p>`;
    }
  };

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

    attachDashboardReservationActions(container);
  };

  const renderRecentlyWorked = async () => {
    const container = document.getElementById("recently-worked");
    const count = document.getElementById("recently-worked-count");
    if (!container) return;

    container.innerHTML = "<p>Loading Recently Worked...</p>";
    try {
      const response = await fetch("/api/dashboard/recently-worked");
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Unable to load Recently Worked.");
      }

      const domains = data.domains || [];
      if (count) count.textContent = data.count ?? domains.length;
      if (domains.length === 0) {
        container.innerHTML = "<p>No campaigns were worked recently.</p>";
        return;
      }

      const columns = [
        { key: "domain", label: "Domain", type: "text", defaultDirection: "asc" },
        { key: "temperature", label: "Temperature", type: "text", defaultDirection: "asc" },
        { key: "days_since_action", label: "Worked", sortLabel: "Sort by Recent Action", type: "number", defaultDirection: "asc", className: "dashboard-metric-column" },
        { key: "expiry", label: "Expiry", type: "number", defaultDirection: "asc", className: "dashboard-metric-column" },
        { key: "sequence", label: "Seq", type: "number", defaultDirection: "asc", className: "dashboard-metric-column" },
      ];

      container.innerHTML = `
        <div class="table-container">
          <table class="dashboard-suggested-table dashboard-followup-table" data-sort-table="recently_worked">
            <thead>
              <tr>
                ${renderDashboardSortHeaders(columns.slice(0, 2))}
                <th>Email Used</th>
                ${renderDashboardSortHeaders(columns.slice(2))}
                <th>Reserve</th>
              </tr>
            </thead>
            <tbody>
              ${domains.map((campaign) => `
                <tr
                  data-sort-domain="${campaign.domain || ""}"
                  data-sort-temperature="${campaign.temperature || ""}"
                  data-sort-days-since-action="${campaign.days_since_action ?? ""}"
                  data-sort-expiry="${campaign.days_until_expiry ?? ""}"
                  data-sort-sequence="${campaign.current_sequence ?? ""}"
                >
                  <td class="dashboard-domain-cell">${renderDashboardDomain(campaign.domain)}</td>
                  <td>${renderDashboardTemperature(campaign.temperature, campaign.label, campaign.emoji)}</td>
                  <td class="dashboard-email-cell">${renderDashboardEmailSummary(campaign.operational_emails)}</td>
                  <td class="dashboard-metric-column">${renderDashboardActionAge(campaign)}</td>
                  <td class="dashboard-metric-column">${renderDashboardExpiry(campaign)}</td>
                  <td class="dashboard-metric-column">${renderDashboardSequence(campaign.current_sequence)}</td>
                  <td class="dashboard-reservation-cell">${renderDashboardRowActions(getResButtons(campaign))}</td>
                </tr>`).join("")}
            </tbody>
          </table>
        </div>
      `;
      setupDashboardSortableTable(
        container.querySelector('table[data-sort-table="recently_worked"]'),
        "recently_worked",
        columns,
      );
      attachDashboardReservationActions(container);
    } catch (error) {
      if (count) count.textContent = "—";
      container.innerHTML = `<p class="dashboard-error">${error.message}</p>`;
    }
  };

  return Promise.all([
    renderFirstFollowups(),
    renderNormalFollowups(),
    renderRecentlyWorked(),
    renderCooling(),
    renderRestingSuggestions(),
    renderExpiringSoon(),
    renderReadyForCampaign(),
  ]);
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
  if (!el) return;
  const expanded = el.style.display === "block";
  el.style.display = expanded ? "none" : "block";
  const toggle = document.querySelector(`.accordion-toggle[aria-controls="${id}"]`);
  if (toggle) toggle.setAttribute("aria-expanded", String(!expanded));
}

document.addEventListener("DOMContentLoaded", refreshDashboard);
