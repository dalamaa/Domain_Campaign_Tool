// Shared data and state
const allEmailCodes = [
  "D03",
  "D04",
  "D05",
  "D07",
  "M01",
  "M02",
  "M04",
  "M05",
  "M06",
  "M07",
  "M08",
  "M09",
  "M10",
  "M11",
  "M12",
  "M13",
  "M14",
  "M15",
  "M16",
  "M17",
  "M18",
  "M19",
  "M20",
  "ML06",
  "ML07",
  "ML08",
  "N04",
  "N09",
  "N10",
  "T01",
  "T03",
  "T04",
  "T05",
  "T06",
  "T07",
  "T08",
  "T09",
  "T10",
  "T12",
  "T13",
  "T14",
  "T15",
  "T16",
  "T17",
  "T18",
  "Y01",
  "Y02",
  "Y03",
  "Y04",
  "Z00",
  "Z01",
  "Z04",
  "Z08",
  "Z09",
];

const mockEmailAccounts = allEmailCodes.map((code, index) => ({
  code,
  group: code.startsWith("ML") ? "ML" : code[0],
  order: index + 1,
  state: "Available",
  reservedFor: null,
}));

const mockCampaigns = Array.from({ length: 35 }, (_, i) => {
  const groups = ["M", "T", "N", "Y", "Z"];
  const group = groups[i % groups.length];
  const block = allEmailCodes
    .filter((c) => c.startsWith(group))
    .slice(i % 3, (i % 3) + 2);
  return {
    id: i + 1,
    domain: `example${i + 1}.com`,
    status: i < 10 ? "Active" : i < 20 ? "Resting" : "Active",
    action: [
      "First Follow-up",
      "Normal Follow-up",
      "Price Reduction",
      "Ready To Restart",
      "Expiring Soon",
    ][i % 5],
    price: 300 + i * 10,
    seq: (i % 3) + 1,
    expiry: new Date(Date.now() + Math.random() * 60 * 24 * 60 * 60 * 1000)
      .toISOString()
      .split("T")[0],
    lastContact: "2026-08-01",
    suggestedBlock: block.length > 0 ? block : ["M01", "M02"],
    isReserved: false,
  };
});

function getSortedAccounts() {
  return [...mockEmailAccounts].sort((a, b) => a.order - b.order);
}

// Side panel visibility helpers
// 2. Update side panel logic in shared.js to show full detail
function showSidePanel(domainName) {
  const campaign = mockCampaigns.find((c) => c.domain === domainName);
  if (!campaign) return;

  const panel = document.getElementById("side-panel");
  const content = document.getElementById("panel-content");
  if (!panel || !content) return;

  const daysSince = Math.floor(
    (new Date() - new Date(campaign.lastContact)) / (1000 * 60 * 60 * 24),
  );
  const daysUntil = Math.floor(
    (new Date(campaign.expiry) - new Date()) / (1000 * 60 * 60 * 24),
  );
  content.innerHTML = `
        <h3>${campaign.domain}</h3>
        <p><strong>Status:</strong> ${campaign.status}</p>
        <p><strong>Price:</strong> $${campaign.price} | <strong>Seq:</strong> ${campaign.seq}</p>
        <p><strong>Last Action:</strong> ${campaign.lastAction || "N/A"}</p>
        <p><strong>Last Contact:</strong> ${campaign.lastContact} (${daysSince} days ago)</p>
        <p><strong>Expiry:</strong> ${campaign.expiry} (${daysUntil} days left)</p>
        <p><strong>Email Block:</strong> ${campaign.suggestedBlock ? campaign.suggestedBlock.join(", ") : "None"}</p>
        <p><strong>Reservation:</strong> ${campaign.isReserved ? "Reserved" : "No reservation"}</p>
        <h4>Campaign History</h4>
        <ul>
            <li>${campaign.lastContact}: ${campaign.lastAction || "Action"} ($${campaign.price})</li>
        </ul>
        <button onclick="hideSidePanel()">Close</button>
    `;
  panel.classList.remove("hidden");
}

function hideSidePanel() {
  const panel = document.getElementById("side-panel");
  if (panel) panel.classList.add("hidden");
}
