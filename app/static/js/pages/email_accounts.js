let selectedCodes = new Set();

// Update email_accounts.js to use API
async function renderEmailTable() {
  const response = await fetch("/api/email-accounts");
  const accounts = await response.json();

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

function bulkToggle() {
  selectedCodes.forEach((code) => {
    const acc = mockEmailAccounts.find((a) => a.code === code);
    acc.state = acc.state === "Disabled" ? "Available" : "Disabled";
  });
  selectedCodes.clear();
  updateActionBar();
  renderEmailTable();
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

// In app/static/js/pages/email_accounts.js

// Auto-derive group
document.getElementById("form-code").addEventListener("input", async (e) => {
  const code = e.target.value.toUpperCase();
  const match = code.match(/^([A-Za-z]+)(\d+)$/);
  if (match) {
    document.getElementById("form-group").value = match[1];

    // Fetch suggested order
    const res = await fetch("/api/email-accounts/suggest-order", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });
    const data = await res.json();
    document.getElementById("form-order").value = data.suggested_order;
  }
});

async function saveNewAccount() {
  const code = document.getElementById("form-code").value.toUpperCase();
  const group = document.getElementById("form-group").value;
  const order = parseInt(document.getElementById("form-order").value);

  // 1. Check order availability
  const checkRes = await fetch("/api/email-accounts/check-order", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ order }),
  });
  const checkData = await checkRes.json();

  let shiftExisting = false;
  if (checkData.occupied) {
    if (
      confirm(
        `Order ${order} is currently assigned to ${checkData.conflicting_code}. Insert this account at order ${order} and move the following accounts down?`,
      )
    ) {
      shiftExisting = true;
    } else {
      return;
    }
  }

  // 2. Perform Save with Overwrite capability
  const res = await fetch("/api/email-accounts/add", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      code,
      group,
      order,
      shift_existing: shiftExisting,
      overwrite: false,
    }),
  });

  const result = await res.json();

  if (result.error === "Code already exists") {
    if (
      confirm(
        `Code ${code} already exists. Do you want to overwrite this account?`,
      )
    ) {
      // Overwrite logic - re-submit with overwrite: true
      await fetch("/api/email-accounts/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          code,
          group,
          order,
          shift_existing: false,
          overwrite: true,
        }),
      });
      closeAddModal();
      renderEmailTable();
    }
  } else if (res.ok) {
    closeAddModal();
    renderEmailTable();
  }
}

// Add Fix Order logic in email_accounts.js

async function fixOrder() {
    if (!confirm("Profile order gaps will be fixed. Account order will remain unchanged. Continue?")) {
        return;
    }

    const res = await fetch('/api/email-accounts/fix-order', { method: 'POST' });
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

