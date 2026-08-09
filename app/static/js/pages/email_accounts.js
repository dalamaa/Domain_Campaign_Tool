let selectedCodes = new Set();

function renderEmailTable() {
  const body = document.querySelector("#email-table-body");
  if (!body) return;
  const sorted = getSortedAccounts();
  body.innerHTML = sorted
    .map(
      (acc) =>
        `<tr data-code="${acc.code}" draggable="true" class="${selectedCodes.has(acc.code) ? "selected" : ""}"><td><input type="checkbox" ${selectedCodes.has(acc.code) ? "checked" : ""} onchange="toggleSelection('${acc.code}')"></td><td class="drag-handle">::</td><td>${acc.code}</td><td>${acc.group}</td><td>${acc.order}</td><td>${acc.state}</td><td>${acc.reservedFor || "-"}</td></tr>`,
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

function bulkDelete() {
  selectedCodes.forEach((code) => {
    const idx = mockEmailAccounts.findIndex((a) => a.code === code);
    if (idx !== -1) mockEmailAccounts.splice(idx, 1);
  });
  selectedCodes.clear();
  updateActionBar();
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

// Ensure init logic runs once DOM is ready
document.addEventListener("DOMContentLoaded", () => {
    if (document.querySelector("#email-table-body")) {
        renderEmailTable();
    }
});

