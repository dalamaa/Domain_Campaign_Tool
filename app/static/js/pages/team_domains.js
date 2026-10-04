(() => {
  "use strict";

  const state = {
    members: [],
    assignments: [],
    sortKey: "expiry_date",
    sortAscending: true,
  };

  const byId = (id) => document.getElementById(id);

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function formatDate(value) {
    if (!value) return "—";
    return new Date(`${value}T00:00:00`).toLocaleDateString();
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Unable to complete the request.");
    return data;
  }

  function openDialog(dialogId) {
    byId(dialogId).hidden = false;
  }

  function closeDialog(dialogId) {
    byId(dialogId).hidden = true;
  }

  function renderMemberOptions() {
    const filter = byId("team-member-filter");
    const assignment = byId("team-assignment-member");
    const selectedFilter = filter.value;
    const selectedAssignment = assignment.value;
    const options = state.members.map((member) =>
      `<option value="${member.id}">${escapeHtml(member.name)} (${escapeHtml(member.member_type)})</option>`,
    ).join("");
    filter.innerHTML = `<option value="">All team members</option>${options}`;
    assignment.innerHTML = options;
    filter.value = state.members.some((member) => String(member.id) === selectedFilter)
      ? selectedFilter : "";
    if (state.members.some((member) => String(member.id) === selectedAssignment)) {
      assignment.value = selectedAssignment;
    }
  }

  function filteredAssignments() {
    const search = byId("team-domain-search").value.trim().toLowerCase();
    const memberId = byId("team-member-filter").value;
    return state.assignments
      .filter((assignment) => !search || assignment.domain_name.toLowerCase().includes(search))
      .filter((assignment) => !memberId || String(assignment.team_member_id) === memberId)
      .sort((left, right) => {
        const leftValue = left[state.sortKey];
        const rightValue = right[state.sortKey];
        const comparison = String(leftValue).localeCompare(String(rightValue), undefined, {
          numeric: true,
          sensitivity: "base",
        });
        return state.sortAscending ? comparison : -comparison;
      });
  }

  function renderAssignments() {
    const assignments = filteredAssignments();
    byId("team-domain-count").textContent = `${assignments.length} assignment${assignments.length === 1 ? "" : "s"}`;
    byId("team-domain-empty").hidden = assignments.length !== 0;
    byId("team-domain-table-body").innerHTML = assignments.map((assignment) => {
      const ageClass = `team-age-${assignment.campaign_age_state}`;
      const expiryClass = `team-expiry-${assignment.expiry_state}`;
      const ageLabel = assignment.campaign_age_state === "normal"
        ? `${assignment.campaign_age_days}d`
        : `${assignment.campaign_age_days}d · ${escapeHtml(assignment.campaign_age_label)}`;
      return `<tr>
        <td>${escapeHtml(assignment.team_member_name)}</td>
        <td>${escapeHtml(assignment.domain_name)}</td>
        <td>${escapeHtml(formatDate(assignment.assigned_date))}</td>
        <td class="${expiryClass}">${escapeHtml(formatDate(assignment.expiry_date))}<small>${escapeHtml(assignment.expiry_label)}</small></td>
        <td class="${ageClass}">${ageLabel}</td>
        <td class="team-domain-row-actions">
          <button class="btn btn-subtle btn-compact" type="button" data-edit-assignment="${assignment.id}">Edit</button>
          <button class="btn btn-subtle btn-compact" type="button" data-delete-assignment="${assignment.id}">Delete</button>
        </td>
      </tr>`;
    }).join("");
  }

  function renderMembers() {
    byId("team-member-empty").hidden = state.members.length !== 0;
    byId("team-member-table-body").innerHTML = state.members.map((member) => `<tr>
      <td>${escapeHtml(member.name)}</td>
      <td>${escapeHtml(member.member_type)}</td>
      <td>${member.assignment_count}</td>
      <td class="team-domain-row-actions">
        <button class="btn btn-subtle btn-compact" type="button" data-edit-member="${member.id}">Edit</button>
        <button class="btn btn-subtle btn-compact" type="button" data-delete-member="${member.id}">Remove</button>
      </td>
    </tr>`).join("");
  }

  async function loadTeamDomains() {
    try {
      const [members, assignments] = await Promise.all([
        fetchJson("/api/team-members"),
        fetchJson("/api/team-domain-assignments"),
      ]);
      state.members = members;
      state.assignments = assignments;
      renderMemberOptions();
      renderMembers();
      renderAssignments();
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  function resetMemberForm(member = null) {
    byId("team-member-id").value = member?.id || "";
    byId("team-member-name").value = member?.name || "";
    byId("team-member-type").value = member?.member_type || "STAFF";
    byId("team-member-dialog-title").textContent = member ? "Edit Team Member" : "Add Team Member";
    byId("team-member-form-error").textContent = "";
  }

  function resetAssignmentForm(assignment = null) {
    byId("team-assignment-id").value = assignment?.id || "";
    byId("team-assignment-member").value = assignment?.team_member_id || "";
    byId("team-assignment-domain").value = assignment?.domain_name || "";
    byId("team-assignment-assigned-date").value = assignment?.assigned_date || "";
    byId("team-assignment-expiry-date").value = assignment?.expiry_date || "";
    byId("team-assignment-dialog-title").textContent = assignment ? "Edit Assignment" : "Add Assignment";
    byId("team-assignment-form-error").textContent = "";
  }

  async function saveMember(event) {
    event.preventDefault();
    const id = byId("team-member-id").value;
    const payload = {
      name: byId("team-member-name").value,
      member_type: byId("team-member-type").value,
    };
    try {
      await fetchJson(id ? `/api/team-members/${id}` : "/api/team-members", {
        method: id ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      closeDialog("team-member-dialog");
      showToast("Team member saved.");
      await loadTeamDomains();
    } catch (error) {
      byId("team-member-form-error").textContent = error.message;
    }
  }

  async function saveAssignment(event) {
    event.preventDefault();
    const id = byId("team-assignment-id").value;
    const payload = {
      team_member_id: Number(byId("team-assignment-member").value),
      domain_name: byId("team-assignment-domain").value,
      assigned_date: byId("team-assignment-assigned-date").value,
      expiry_date: byId("team-assignment-expiry-date").value,
    };
    try {
      await fetchJson(id ? `/api/team-domain-assignments/${id}` : "/api/team-domain-assignments", {
        method: id ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      closeDialog("team-assignment-dialog");
      showToast("Team domain assignment saved.");
      await loadTeamDomains();
    } catch (error) {
      byId("team-assignment-form-error").textContent = error.message;
    }
  }

  async function deleteMember(id) {
    if (!window.confirm("Remove this team member? Members with assignments cannot be removed.")) return;
    try {
      await fetchJson(`/api/team-members/${id}`, { method: "DELETE" });
      showToast("Team member removed.");
      await loadTeamDomains();
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  async function deleteAssignment(id) {
    if (!window.confirm("Delete this Team Domains assignment?")) return;
    try {
      await fetchJson(`/api/team-domain-assignments/${id}`, { method: "DELETE" });
      showToast("Assignment deleted.");
      await loadTeamDomains();
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  function bindEvents() {
    byId("add-team-member-button").addEventListener("click", () => {
      resetMemberForm();
      openDialog("team-member-dialog");
    });
    byId("add-team-assignment-button").addEventListener("click", () => {
      if (!state.members.length) {
        showToast("Add a team member before adding an assignment.", "error");
        return;
      }
      resetAssignmentForm();
      openDialog("team-assignment-dialog");
    });
    byId("refresh-team-domains-button").addEventListener("click", loadTeamDomains);
    byId("team-domain-search").addEventListener("input", renderAssignments);
    byId("team-member-filter").addEventListener("change", renderAssignments);
    byId("team-member-form").addEventListener("submit", saveMember);
    byId("team-assignment-form").addEventListener("submit", saveAssignment);
    document.querySelectorAll("[data-close-dialog]").forEach((button) => {
      button.addEventListener("click", () => closeDialog(button.dataset.closeDialog));
    });
    document.querySelectorAll(".team-domain-sort").forEach((button) => {
      button.addEventListener("click", () => {
        if (state.sortKey === button.dataset.sortKey) state.sortAscending = !state.sortAscending;
        else {
          state.sortKey = button.dataset.sortKey;
          state.sortAscending = true;
        }
        renderAssignments();
      });
    });
    byId("team-member-table-body").addEventListener("click", (event) => {
      const edit = event.target.closest("[data-edit-member]");
      const remove = event.target.closest("[data-delete-member]");
      if (edit) {
        resetMemberForm(state.members.find((member) => String(member.id) === edit.dataset.editMember));
        openDialog("team-member-dialog");
      } else if (remove) deleteMember(remove.dataset.deleteMember);
    });
    byId("team-domain-table-body").addEventListener("click", (event) => {
      const edit = event.target.closest("[data-edit-assignment]");
      const remove = event.target.closest("[data-delete-assignment]");
      if (edit) {
        resetAssignmentForm(state.assignments.find((assignment) => String(assignment.id) === edit.dataset.editAssignment));
        openDialog("team-assignment-dialog");
      } else if (remove) deleteAssignment(remove.dataset.deleteAssignment);
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    bindEvents();
    loadTeamDomains();
  });
})();
