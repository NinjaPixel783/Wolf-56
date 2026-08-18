// dashboard.js — Logique du tableau de bord principal PC Monitor

const socket = io();

let devicesCache = [];
let activeDeviceForModal = null;

// ---------------------------------------------------------------------
// Navigation entre vues
// ---------------------------------------------------------------------
document.querySelectorAll(".nav-item[data-view]").forEach((link) => {
  link.addEventListener("click", (e) => {
    e.preventDefault();
    document.querySelectorAll(".nav-item[data-view]").forEach((l) => l.classList.remove("active"));
    link.classList.add("active");
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    document.getElementById(link.dataset.view).classList.add("active");
    document.getElementById("page-title").textContent = link.textContent.trim();

    if (link.dataset.view === "view-alerts") loadAlerts();
    if (link.dataset.view === "view-history") loadHistory();
    if (link.dataset.view === "view-settings") loadSettings();
    if (link.dataset.view === "view-security") loadSecurity();
  });
});

// ---------------------------------------------------------------------
// Toasts
// ---------------------------------------------------------------------
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 5000);
}

// ---------------------------------------------------------------------
// Copie de l'adresse du serveur
// ---------------------------------------------------------------------
document.getElementById("copy-server-address").addEventListener("click", () => {
  const text = document.querySelector(".server-address code").textContent;
  navigator.clipboard.writeText(text).then(() => showToast("Adresse copiée.", "success"));
});

// ---------------------------------------------------------------------
// Chargement des appareils
// ---------------------------------------------------------------------
async function loadDevices() {
  const resp = await fetch("/api/devices");
  const data = await resp.json();
  devicesCache = data.devices;

  document.getElementById("stat-total").textContent = data.total;
  document.getElementById("stat-online").textContent = data.online;
  document.getElementById("stat-offline").textContent = data.offline;

  const cpuValues = data.devices.map((d) => d.cpu_percent).filter((v) => v !== null && v !== undefined);
  const ramValues = data.devices.map((d) => d.ram_percent).filter((v) => v !== null && v !== undefined);
  document.getElementById("stat-cpu-avg").textContent = cpuValues.length
    ? Math.round(cpuValues.reduce((a, b) => a + b, 0) / cpuValues.length) + "%" : "0%";
  document.getElementById("stat-ram-avg").textContent = ramValues.length
    ? Math.round(ramValues.reduce((a, b) => a + b, 0) / ramValues.length) + "%" : "0%";

  renderDeviceGrid("device-grid", data.devices);
  renderDeviceGrid("device-grid-full", data.devices);

  const alertsResp = await fetch("/api/alerts");
  const alertsData = await alertsResp.json();
  document.getElementById("stat-alerts").textContent = alertsData.alerts.length;
}

function barClass(percent) {
  if (percent >= 90) return "danger";
  if (percent >= 70) return "warn";
  return "";
}

function renderDeviceGrid(containerId, devices) {
  const container = document.getElementById(containerId);
  container.innerHTML = "";

  if (devices.length === 0) {
    container.innerHTML = '<div class="empty-state">Aucun appareil enregistré pour le moment. Lancez l\'agent sur un PC pour le voir apparaître ici.</div>';
    return;
  }

  devices.forEach((device) => {
    const card = document.createElement("div");
    card.className = "device-card";
    card.dataset.deviceId = device.id;

    const statusLabel = device.status === "online" ? "🟢 EN LIGNE" : "🔴 HORS LIGNE";
    const cpu = device.cpu_percent ?? 0;
    const ram = device.ram_percent ?? 0;
    const disk = device.disk_percent ?? 0;
    const battery = device.battery_percent;

    card.innerHTML = `
      <div class="device-card-header">
        <h4>🖥️ ${escapeHtml(device.name)}</h4>
        <span class="status-badge status-${device.status}">${statusLabel}</span>
      </div>

      <div class="metric-row">
        <div class="metric-label"><span>CPU</span><span>${device.cpu_percent ?? "—"}%</span></div>
        <div class="progress-bar"><div class="progress-fill ${barClass(cpu)}" style="width:${cpu}%"></div></div>
      </div>
      <div class="metric-row">
        <div class="metric-label"><span>RAM</span><span>${device.ram_percent ?? "—"}%</span></div>
        <div class="progress-bar"><div class="progress-fill ${barClass(ram)}" style="width:${ram}%"></div></div>
      </div>
      <div class="metric-row">
        <div class="metric-label"><span>DISQUE</span><span>${device.disk_percent ?? "—"}%</span></div>
        <div class="progress-bar"><div class="progress-fill ${barClass(disk)}" style="width:${disk}%"></div></div>
      </div>

      <div class="device-meta">
        <span>${battery !== null && battery !== undefined ? "🔋 " + battery + "%" : "Batterie non disponible"}</span>
        <span>${device.hostname || ""}</span>
      </div>

      <div class="device-card-actions">
        <button class="btn btn-secondary btn-details">DÉTAILS</button>
        ${device.status === "online"
          ? `<button class="btn btn-secondary btn-restart">🔄 REDÉMARRER</button>
             <button class="btn btn-danger btn-shutdown">⏻ ÉTEINDRE</button>`
          : `<button class="btn btn-primary btn-wake">🟢 ALLUMER</button>`}
      </div>
    `;

    card.querySelector(".btn-details").addEventListener("click", () => {
      window.location.href = `/device/${device.id}`;
    });
    card.querySelector("h4").addEventListener("click", () => {
      window.location.href = `/device/${device.id}`;
    });

    const restartBtn = card.querySelector(".btn-restart");
    if (restartBtn) restartBtn.addEventListener("click", () => confirmAction(device, "restart"));

    const shutdownBtn = card.querySelector(".btn-shutdown");
    if (shutdownBtn) shutdownBtn.addEventListener("click", () => confirmAction(device, "shutdown"));

    const wakeBtn = card.querySelector(".btn-wake");
    if (wakeBtn) wakeBtn.addEventListener("click", () => sendWake(device));

    container.appendChild(card);
  });
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

// ---------------------------------------------------------------------
// Modale de confirmation générique (redémarrer / éteindre)
// ---------------------------------------------------------------------
const confirmModal = document.getElementById("modal-confirm");
let pendingConfirmAction = null;

function confirmAction(device, action) {
  activeDeviceForModal = device;
  pendingConfirmAction = action;
  const label = action === "restart" ? "redémarrer" : "éteindre";
  document.getElementById("modal-confirm-title").textContent =
    action === "restart" ? "Confirmer le redémarrage" : "Confirmer l'arrêt";
  document.getElementById("modal-confirm-text").textContent =
    `Êtes-vous sûr de vouloir ${label} : ${device.name} ?`;
  confirmModal.classList.remove("hidden");
}

document.getElementById("modal-confirm-cancel").addEventListener("click", () => {
  confirmModal.classList.add("hidden");
});

document.getElementById("modal-confirm-ok").addEventListener("click", async () => {
  confirmModal.classList.add("hidden");
  if (!activeDeviceForModal || !pendingConfirmAction) return;

  const resp = await fetch(`/api/devices/${activeDeviceForModal.id}/${pendingConfirmAction}`, { method: "POST" });
  const data = await resp.json();
  if (resp.ok) {
    showToast(data.message, "success");
  } else {
    showToast(data.error || "Erreur lors de l'envoi de la commande.", "error");
  }
  loadDevices();
});

async function sendWake(device) {
  const resp = await fetch(`/api/devices/${device.id}/wake`, { method: "POST" });
  const data = await resp.json();
  if (resp.ok) {
    showToast(data.message, "success");
  } else {
    let msg = data.error;
    if (data.details) msg += " — " + data.details.join(", ");
    showToast(msg, "error");
  }
  loadDevices();
}

// ---------------------------------------------------------------------
// Alertes
// ---------------------------------------------------------------------
async function loadAlerts() {
  const resp = await fetch("/api/alerts");
  const data = await resp.json();
  const container = document.getElementById("alerts-list");
  container.innerHTML = "";

  if (data.alerts.length === 0) {
    container.innerHTML = '<div class="empty-state">Aucune alerte pour le moment.</div>';
    return;
  }

  const icons = { cpu: "⚠️", ram: "⚠️", disk: "⚠️", battery: "⚠️", offline: "🔴" };

  data.alerts.forEach((alert) => {
    const item = document.createElement("div");
    item.className = "list-item";
    const time = new Date(alert.timestamp * 1000).toLocaleString("fr-FR");
    item.innerHTML = `
      <span class="item-time">${time}</span>
      <span>${icons[alert.type] || "⚠️"} <strong>${escapeHtml(alert.device_name)}</strong> — ${escapeHtml(alert.message)}</span>
    `;
    container.appendChild(item);
  });
}

// ---------------------------------------------------------------------
// Historique des commandes
// ---------------------------------------------------------------------
const actionLabels = {
  shutdown: "Éteindre",
  restart: "Redémarrage",
  wake: "Wake-on-LAN",
  emergency_shutdown: "Arrêt d'urgence (PANIC98)",
};

const statusBadgeClass = { success: "badge-success", failed: "badge-failed", pending: "badge-pending", sent: "badge-sent" };
const statusLabelText = { success: "✓ Réussi", failed: "✗ Échec", pending: "… En attente", sent: "→ Envoyé" };

async function loadHistory() {
  const resp = await fetch("/api/history");
  const data = await resp.json();

  const historyContainer = document.getElementById("history-list");
  const emergencyContainer = document.getElementById("emergency-history-list");
  historyContainer.innerHTML = "";
  emergencyContainer.innerHTML = "";

  if (data.commands.length === 0) {
    historyContainer.innerHTML = '<div class="empty-state">Aucune commande exécutée pour le moment.</div>';
    emergencyContainer.innerHTML = '<div class="empty-state">Aucune action d\'urgence pour le moment.</div>';
    return;
  }

  let emergencyCount = 0;

  data.commands.forEach((cmd) => {
    const time = new Date(cmd.timestamp * 1000).toLocaleString("fr-FR");
    const item = document.createElement("div");
    item.className = "list-item";
    item.innerHTML = `
      <span class="item-time">${time}</span>
      <span><strong>${escapeHtml(cmd.device_name)}</strong> — ${actionLabels[cmd.action] || cmd.action} (${escapeHtml(cmd.username || "")})</span>
      <span class="item-badge ${statusBadgeClass[cmd.status] || ""}">${statusLabelText[cmd.status] || cmd.status}</span>
    `;

    if (cmd.action === "emergency_shutdown") {
      emergencyContainer.appendChild(item.cloneNode(true));
      emergencyCount++;
    } else {
      historyContainer.appendChild(item);
    }
  });

  if (emergencyCount === 0) {
    emergencyContainer.innerHTML = '<div class="empty-state">Aucune action d\'urgence pour le moment.</div>';
  }
}

// ---------------------------------------------------------------------
// Paramètres
// ---------------------------------------------------------------------
async function loadSettings() {
  const resp = await fetch("/api/settings");
  const s = await resp.json();
  document.getElementById("set-server-name").value = s.server_name || "";
  document.getElementById("set-interval").value = s.collect_interval || 2;
  document.getElementById("set-port").value = s.port || 8765;
  document.getElementById("set-cpu").value = s.cpu_threshold || 90;
  document.getElementById("set-ram").value = s.ram_threshold || 90;
  document.getElementById("set-battery").value = s.battery_threshold || 15;
}

document.getElementById("settings-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    server_name: document.getElementById("set-server-name").value,
    collect_interval: document.getElementById("set-interval").value,
    cpu_threshold: document.getElementById("set-cpu").value,
    ram_threshold: document.getElementById("set-ram").value,
    battery_threshold: document.getElementById("set-battery").value,
  };
  const resp = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (resp.ok) showToast("Paramètres enregistrés.", "success");
  else showToast("Erreur lors de l'enregistrement.", "error");
});

// ---------------------------------------------------------------------
// Sécurité — appareils autorisés
// ---------------------------------------------------------------------
async function loadSecurity() {
  const resp = await fetch("/api/devices");
  const data = await resp.json();
  const container = document.getElementById("security-list");
  container.innerHTML = "";

  if (data.devices.length === 0) {
    container.innerHTML = '<div class="empty-state">Aucun appareil enregistré.</div>';
    return;
  }

  data.devices.forEach((device) => {
    const item = document.createElement("div");
    item.className = "list-item";
    item.innerHTML = `
      <span><strong>${escapeHtml(device.name)}</strong> — Token : ${device.revoked ? "révoqué" : "********"}</span>
      <span>
        ${device.revoked
          ? '<span class="item-badge badge-failed">RÉVOQUÉ</span>'
          : `<button class="btn btn-danger btn-revoke">RÉVOQUER</button>`}
      </span>
    `;
    const revokeBtn = item.querySelector(".btn-revoke");
    if (revokeBtn) {
      revokeBtn.addEventListener("click", async () => {
        if (!confirm(`Révoquer le token de ${device.name} ? L'appareil ne pourra plus envoyer de données ni recevoir de commandes.`)) return;
        const r = await fetch(`/api/devices/${device.id}/revoke`, { method: "POST" });
        if (r.ok) {
          showToast("Appareil révoqué.", "success");
          loadSecurity();
          loadDevices();
        } else {
          showToast("Erreur lors de la révocation.", "error");
        }
      });
    }
    container.appendChild(item);
  });
}

// ---------------------------------------------------------------------
// Temps réel (Socket.IO)
// ---------------------------------------------------------------------
socket.on("telemetry_update", () => loadDevices());
socket.on("device_offline", (data) => {
  showToast(`🔴 ${data.device_name} est passé hors ligne.`, "warning");
  loadDevices();
});
socket.on("device_registered", () => loadDevices());
socket.on("new_alert", (alert) => {
  showToast(`⚠️ ${alert.device_name} — ${alert.message}`, "warning");
  loadDevices();
});
socket.on("command_sent", () => loadHistory());
socket.on("command_queued", () => loadHistory());

// ---------------------------------------------------------------------
// Initialisation
// ---------------------------------------------------------------------
loadDevices();
setInterval(loadDevices, 5000);
