let selectedCodes = new Set();
let emailAccounts = [];

// Update email_accounts.js to handle existing code lookup
async function checkCodeExists(code) {
  const res = await fetch(`/api/email-accounts/check-code?code=${code}`);
  return await res.json();
}

// Update email_accounts.js to use API
async function renderEmailTable() {
  const response = await fetch("/api/email-accounts");
  const accounts = await response.json();
  emailAccounts = accounts;

  const body = document.querySelector("#email-table-body");
  if (!body) return;

  body.innerHTML = accounts
    .map(
      (acc) => `
        <tr data-code="${acc.code}" draggable="true" class="${selectedCodes.has(acc.code) ? "selected" : ""}">
            <td><input type="checkbox" ${selectedCodes.has(acc.code) ? "checked" : ""} onchange="toggleSelection('${acc.code}')"></td>
            <td class="drag-handle">::</td>
            <td>${acc.code}</td>
            <td>${acc.group}</td>
            <td>${acc.order}</td>
            <td>${acc.enabled ? "Available" : "Disabled"}</td>
            <td>-</td>
        </tr>
    `,
    )
    .join("");
  updateActionBar();
  makeDraggable();
}

function toggleSelection(code) {
  if (selectedCodes.has(code)) selectedCodes.delete(code);
  else selectedCodes.add(code);
  updateActionBar();
}

function updateActionBar() {
  const bar = document.getElementById("action-bar");
  if (!bar) return;
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

// Fix logic for makeDraggable - it was missing from pages/email_accounts.js after the move
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
  if (!tbody) return;
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

function toggleAccount(code) {
  const acc = mockEmailAccounts.find((a) => a.code === code);
  acc.state = acc.state === "Disabled" ? "Available" : "Disabled";
  renderEmailTable();
}

async function bulkToggle() {
  const updates = [];
  for (const code of selectedCodes) {
    const account = emailAccounts.find((candidate) => candidate.code === code);
    if (!account) {
      alert(`Email account ${code} is no longer available. Refreshing the list.`);
      selectedCodes.clear();
      await renderEmailTable();
      return;
    }
    updates.push({ code: account.code, enabled: !Boolean(account.enabled) });
  }

  if (!updates.length) return;

  try {
    const response = await fetch("/api/email-accounts/status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ accounts: updates }),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(result.error || "Unable to update email account status.");
    }
    selectedCodes.clear();
    await renderEmailTable();
    alert("Email account status updated.");
  } catch (error) {
    alert(error.message);
  }
}

async function bulkDelete() {
  for (let code of selectedCodes) {
    await fetch(`/api/email-accounts/${code}`, { method: "DELETE" });
  }
  selectedCodes.clear();
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

function openAddModal() {
  document.getElementById("add-email-modal").style.display = "block";
}
function closeAddModal() {
  document.getElementById("add-email-modal").style.display = "none";
}

function openBulkAddModal() {
  document.getElementById("bulk-add-email-modal").style.display = "block";
  document.getElementById("bulk-add-preview").textContent = "";
  document.getElementById("confirm-bulk-add-btn").disabled = true;
}

function closeBulkAddModal() {
  document.getElementById("bulk-add-email-modal").style.display = "none";
}

function bulkAddPayload() {
  return {
    codes: document.getElementById("bulk-account-codes").value,
    enabled: document.getElementById("bulk-account-enabled").value === "true",
  };
}

function renderBulkAddPreview(data) {
  const container = document.getElementById("bulk-add-preview");
  const confirmButton = document.getElementById("confirm-bulk-add-btn");
  if (!container || !confirmButton) return;

  const lines = [];
  if (data.error) lines.push(data.error);
  (data.rows || []).forEach((row) => {
    const group = row.group || "—";
    const order = row.proposed_order == null ? "—" : row.proposed_order;
    const state = row.enabled ? "Enabled" : "Disabled";
    const suffix = row.error ? ` | ${row.error}` : "";
    lines.push(`${row.code || "(blank)"} | Group ${group} | Proposed Order ${order} | ${state} | ${row.validation_status}${suffix}`);
  });
  if ((data.duplicate_codes || []).length) {
    lines.push(`Duplicate codes: ${data.duplicate_codes.join(", ")}`);
  }
  if ((data.existing_codes || []).length) {
    lines.push(`Already present: ${data.existing_codes.join(", ")}`);
  }
  if ((data.invalid_codes || []).length) {
    lines.push(`Invalid codes: ${data.invalid_codes.join(", ")}`);
  }
  container.textContent = lines.join("\n");
  confirmButton.disabled = data.valid !== true;
}

async function previewBulkAdd() {
  const response = await fetch("/api/email-accounts/bulk/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(bulkAddPayload()),
  });
  const data = await response.json().catch(() => ({ error: "Unable to preview accounts." }));
  renderBulkAddPreview(data);
}

async function confirmBulkAdd() {
  const response = await fetch("/api/email-accounts/bulk", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(bulkAddPayload()),
  });
  const data = await response.json().catch(() => ({ error: "Unable to add email accounts." }));
  if (!response.ok) {
    renderBulkAddPreview(data);
    return;
  }
  closeBulkAddModal();
  document.getElementById("bulk-account-codes").value = "";
  await renderEmailTable();
  alert(`${data.accounts.length} email account${data.accounts.length === 1 ? "" : "s"} added.`);
}

// In app/static/js/pages/email_accounts.js

const codeInput = document.getElementById("form-code");

// Ensure we only have one listener
codeInput.onblur = async (e) => {
  const code = e.target.value.toUpperCase();
  if (!code) return;

  // 1. Reset state
  window.originalAccount = null;

  // 2. Check Database
  const data = await checkCodeExists(code);

  if (data.exists) {
    // Pre-populate actual DB values - DO NOT run suggestion logic
    document.getElementById("form-group").value = data.account.group;
    document.getElementById("form-order").value = data.account.order;
    window.originalAccount = data.account;
  } else {
    // 3. Suggest New Order (ONLY if not exists)
    const match = code.match(/^([A-Za-z]+)(\d+)$/);
    if (match) {
      document.getElementById("form-group").value = match[1];

      const res = await fetch("/api/email-accounts/suggest-order", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      const sugData = await res.json();
      document.getElementById("form-order").value = sugData.suggested_order;
    }
  }
};

async function saveNewAccount() {
  const code = document.getElementById("form-code").value.trim().toUpperCase();
  const group = document.getElementById("form-group").value;
  const order = parseInt(document.getElementById("form-order").value);

  // Check if it exists
  const checkRes = await fetch(`/api/email-accounts/check-code?code=${code}`);
  const checkData = await checkRes.json();

  let isOverwrite = false;
  if (checkData.exists) {
    // Compare with original to see if changed
    const original = window.originalAccount;
    if (original && (original.group !== group || original.order !== order)) {
      if (
        !confirm(
          `Code ${code} already exists. Do you want to overwrite this account?`,
        )
      ) {
        return;
      }
      isOverwrite = true;
    } else {
      // No changes, no need to save
      closeAddModal();
      return;
    }
  }

  // Check for order conflict
  const conflictRes = await fetch("/api/email-accounts/check-order", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ order }),
  });
  const conflictData = await conflictRes.json();

  let shiftExisting = false;
  if (
    conflictData.occupied &&
    (!isOverwrite || conflictData.conflicting_code !== code)
  ) {
    if (
      confirm(
        `Order ${order} is currently assigned to ${conflictData.conflicting_code}. Insert this account and move others down?`,
      )
    ) {
      shiftExisting = true;
    } else {
      return;
    }
  }

  // Perform Save
  const res = await fetch("/api/email-accounts/add", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      code,
      group,
      order,
      shift_existing: shiftExisting,
      overwrite: isOverwrite,
    }),
  });

  if (res.ok) {
    closeAddModal();
    renderEmailTable();
  } else {
    const result = await res.json().catch(() => ({}));
    alert(result.error || "Unable to save email account.");
  }
}

// Add Fix Order logic in email_accounts.js

async function fixOrder() {
  if (
    !confirm(
      "Profile order gaps will be fixed. Account order will remain unchanged. Continue?",
    )
  ) {
    return;
  }

  const res = await fetch("/api/email-accounts/fix-order", { method: "POST" });
  const result = await res.json();

  alert(result.message);
  if (result.fixed) {
    renderEmailTable();
  }
}

// Ensure init logic runs once DOM is ready
document.addEventListener("DOMContentLoaded", () => {
  if (document.querySelector("#email-table-body")) {
    renderEmailTable();
  }
});
