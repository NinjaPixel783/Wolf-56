// device.js — Logique de la page détaillée d'un appareil PC Monitor

const socket = io();
const deviceId = document.getElementById("device-page").dataset.deviceId;

let cpuHistory = [];
let ramHistory = [];

function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 5000);
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

function formatUptime(seconds) {
  if (!seconds && seconds !== 0) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  let out = "";
  if (d > 0) out += `${d}j `;
  out += `${h}h${String(m).padStart(2, "0")}`;
  return out;
}

function formatBytes(bytes) {
  if (bytes === undefined || bytes === null) return "—";
  const units = ["o", "Ko", "Mo", "Go", "To"];
  let val = bytes;
  let i = 0;
  while (val >= 1024 && i < units.length - 1) {
    val /= 1024;
    i++;
  }
  return `${val.toFixed(1)} ${units[i]}`;
}

// ---------------------------------------------------------------------
// Petit graphique en ligne, dessiné sur canvas, sans dépendance externe
// ---------------------------------------------------------------------
function drawLineChart(canvasId, values, color) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const width = canvas.width = canvas.clientWidth;
  const height = canvas.height;

  ctx.clearRect(0, 0, width, height);

  if (!values.length) return;

  const max = 100;
  const min = 0;
  const stepX = values.length > 1 ? width / (values.length - 1) : width;

  ctx.beginPath();
  values.forEach((v, i) => {
    const x = i * stepX;
    const y = height - ((v - min) / (max - min)) * height;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.stroke();

  // remplissage léger sous la courbe
  ctx.lineTo(width, height);
  ctx.lineTo(0, height);
  ctx.closePath();
  ctx.fillStyle = color + "22";
  ctx.fill();
}

// ---------------------------------------------------------------------
// Chargement des données de l'appareil
// ---------------------------------------------------------------------
async function loadDeviceDetail() {
  const resp = await fetch(`/api/devices/${deviceId}`);
  if (!resp.ok) {
    showToast("Appareil introuvable.", "error");
    return;
  }
  const data = await resp.json();
  const device = data.device;

  document.getElementById("device-title").textContent = device.name;
  const badge = document.getElementById("device-status-badge");
  badge.className = `status-badge status-${device.status}`;
  badge.textContent = device.status === "online" ? "🟢 EN LIGNE" : "🔴 HORS LIGNE";

  document.getElementById("info-name").textContent = device.name;
  document.getElementById("info-uuid").textContent = device.id;
  document.getElementById("info-hostname").textContent = device.hostname || "—";
  document.getElementById("info-os").textContent = device.os_name || "—";
  document.getElementById("info-version").textContent = device.os_version || "—";
  document.getElementById("info-arch").textContent = device.architecture || "—";
  document.getElementById("info-last-seen").textContent = device.last_seen
    ? new Date(device.last_seen * 1000).toLocaleString("fr-FR") : "—";

  document.getElementById("wol-mac").textContent = device.mac_address || "—";
  document.getElementById("wol-status").textContent = device.wol_enabled ? "🟢 Activé" : "🔴 Désactivé";

  cpuHistory = data.history.map((h) => h.cpu_percent ?? 0);
  ramHistory = data.history.map((h) => h.ram_percent ?? 0);
  drawLineChart("cpu-chart", cpuHistory, "#2563EB");
  drawLineChart("ram-chart", ramHistory, "#16A34A");

  const latestCpu = cpuHistory.length ? cpuHistory[cpuHistory.length - 1] : null;
  const latestRam = ramHistory.length ? ramHistory[ramHistory.length - 1] : null;
  document.getElementById("cpu-value").textContent = latestCpu !== null ? `${latestCpu}%` : "Non disponible";
  document.getElementById("ram-value").textContent = latestRam !== null ? `${latestRam}%` : "Non disponible";

  const payload = data.latest_payload;

  // Disques
  const diskContainer = document.getElementById("disk-list");
  if (payload && payload.disks && payload.disks.length) {
    diskContainer.innerHTML = payload.disks.map((d) => `
      <div class="metric-row">
        <div class="metric-label"><span>${escapeHtml(d.letter)}</span><span>${d.percent}% (${formatBytes(d.used_bytes)} / ${formatBytes(d.total_bytes)})</span></div>
        <div class="progress-bar"><div class="progress-fill ${d.percent >= 90 ? 'danger' : d.percent >= 70 ? 'warn' : ''}" style="width:${d.percent}%"></div></div>
      </div>
    `).join("");
  } else {
    diskContainer.innerHTML = '<p class="hint">Non disponible</p>';
  }

  // Batterie
  const batteryContainer = document.getElementById("battery-info");
  if (payload && payload.battery && payload.battery.available) {
    const b = payload.battery;
    batteryContainer.innerHTML = `
      <p>🔋 ${b.percent}% ${b.plugged_in ? "⚡ (branchée)" : "(sur batterie)"}</p>
      <p class="hint">${b.time_left ? "Temps restant estimé : " + b.time_left : ""}</p>
    `;
  } else {
    batteryContainer.innerHTML = '<p class="hint">Non disponible</p>';
  }

  // Température
  const tempContainer = document.getElementById("temperature-info");
  if (payload && payload.temperature && payload.temperature.available) {
    tempContainer.innerHTML = `<p>${payload.temperature.celsius.toFixed(1)} °C (${escapeHtml(payload.temperature.label || "")})</p>`;
  } else {
    tempContainer.innerHTML = '<p class="hint">Température : Non disponible</p>';
  }

  // Réseau
  const netContainer = document.getElementById("network-info");
  if (payload && payload.network && payload.network.length) {
    netContainer.innerHTML = payload.network.map((n) => `
      <p><strong>${escapeHtml(n.name)}</strong> — ${n.up ? "Connecté" : "Déconnecté"}<br>
      <span class="hint">IP : ${escapeHtml(n.ip || "—")} · MAC : ${escapeHtml(n.mac || "—")}${n.speed_mbps ? " · " + n.speed_mbps + " Mbps" : ""}</span></p>
    `).join("");
  } else {
    netContainer.innerHTML = '<p class="hint">Non disponible</p>';
  }

  // Uptime
  if (payload && payload.system) {
    document.getElementById("info-uptime").textContent = formatUptime(payload.system.uptime_seconds);
  }

  // Mini historique
  const historyMini = document.getElementById("history-mini");
  if (data.history.length) {
    const rows = data.history.slice(-8).reverse().map((h) => {
      const t = new Date(h.timestamp * 1000).toLocaleTimeString("fr-FR");
      return `<div class="list-item"><span class="item-time">${t}</span><span>CPU ${h.cpu_percent ?? "—"}% · RAM ${h.ram_percent ?? "—"}%</span></div>`;
    }).join("");
    historyMini.innerHTML = rows;
  } else {
    historyMini.innerHTML = '<div class="empty-state">Pas encore de données.</div>';
  }
}

// ---------------------------------------------------------------------
// Renommer
// ---------------------------------------------------------------------
const renameModal = document.getElementById("modal-rename");
document.getElementById("btn-rename").addEventListener("click", () => {
  document.getElementById("rename-input").value = document.getElementById("device-title").textContent;
  renameModal.classList.remove("hidden");
});
document.getElementById("rename-cancel").addEventListener("click", () => renameModal.classList.add("hidden"));
document.getElementById("rename-ok").addEventListener("click", async () => {
  const newName = document.getElementById("rename-input").value.trim();
  if (!newName) return;
  const resp = await fetch(`/api/devices/${deviceId}/rename`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: newName }),
  });
  renameModal.classList.add("hidden");
  if (resp.ok) {
    showToast("Appareil renommé.", "success");
    loadDeviceDetail();
  } else {
    showToast("Erreur lors du renommage.", "error");
  }
});

// ---------------------------------------------------------------------
// Redémarrer / Éteindre
// ---------------------------------------------------------------------
const confirmModal = document.getElementById("modal-confirm");
let pendingAction = null;

function askConfirm(action) {
  pendingAction = action;
  const label = action === "restart" ? "redémarrer" : "éteindre";
  document.getElementById("modal-confirm-title").textContent = action === "restart" ? "Confirmer le redémarrage" : "Confirmer l'arrêt";
  document.getElementById("modal-confirm-text").textContent =
    `Êtes-vous sûr de vouloir ${label} : ${document.getElementById("device-title").textContent} ?`;
  confirmModal.classList.remove("hidden");
}

document.getElementById("btn-restart").addEventListener("click", () => askConfirm("restart"));
document.getElementById("btn-shutdown").addEventListener("click", () => askConfirm("shutdown"));
document.getElementById("modal-confirm-cancel").addEventListener("click", () => confirmModal.classList.add("hidden"));
document.getElementById("modal-confirm-ok").addEventListener("click", async () => {
  confirmModal.classList.add("hidden");
  if (!pendingAction) return;
  const resp = await fetch(`/api/devices/${deviceId}/${pendingAction}`, { method: "POST" });
  const data = await resp.json();
  showToast(resp.ok ? data.message : (data.error || "Erreur."), resp.ok ? "success" : "error");
  loadDeviceDetail();
});

// ---------------------------------------------------------------------
// Wake-on-LAN
// ---------------------------------------------------------------------
async function sendWake() {
  const resp = await fetch(`/api/devices/${deviceId}/wake`, { method: "POST" });
  const data = await resp.json();
  const resultEl = document.getElementById("wol-result");
  if (resp.ok) {
    resultEl.textContent = "Paquet Wake-on-LAN envoyé.";
    showToast(data.message, "success");
  } else {
    resultEl.textContent = `Wake-on-LAN indisponible. Vérifiez : ${(data.details || []).join(", ")}`;
    showToast(data.error, "error");
  }
}
document.getElementById("btn-wake").addEventListener("click", sendWake);
document.getElementById("btn-test-wol").addEventListener("click", sendWake);

// ---------------------------------------------------------------------
// Mode urgence — PANIC98
// ---------------------------------------------------------------------
const emergencyCodeModal = document.getElementById("modal-emergency-code");
const emergencyConfirmModal = document.getElementById("modal-emergency-confirm");

document.getElementById("btn-emergency").addEventListener("click", () => {
  document.getElementById("emergency-code-input").value = "";
  document.getElementById("emergency-error").classList.add("hidden");
  emergencyCodeModal.classList.remove("hidden");
});

document.getElementById("emergency-cancel-1").addEventListener("click", () => {
  emergencyCodeModal.classList.add("hidden");
});

document.getElementById("emergency-continue").addEventListener("click", async () => {
  const code = document.getElementById("emergency-code-input").value;
  const errorEl = document.getElementById("emergency-error");

  const resp = await fetch(`/api/devices/${deviceId}/emergency/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  });
  const data = await resp.json();

  if (!resp.ok) {
    errorEl.textContent = data.error || "Code incorrect. Aucune action effectuée.";
    errorEl.classList.remove("hidden");
    return;
  }

  emergencyCodeModal.classList.add("hidden");
  document.getElementById("emergency-device-name").textContent = data.device_name;
  emergencyConfirmModal.classList.remove("hidden");
  emergencyConfirmModal.dataset.verifiedCode = code;
});

document.getElementById("emergency-cancel-2").addEventListener("click", () => {
  emergencyConfirmModal.classList.add("hidden");
});

document.getElementById("emergency-confirm-final").addEventListener("click", async () => {
  const code = emergencyConfirmModal.dataset.verifiedCode;
  const resp = await fetch(`/api/devices/${deviceId}/emergency/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  });
  const data = await resp.json();
  emergencyConfirmModal.classList.add("hidden");

  if (resp.ok) {
    showToast(data.message, "success");
  } else {
    showToast(data.error || "Erreur lors du déclenchement du mode urgence.", "error");
  }
  loadDeviceDetail();
});

// ---------------------------------------------------------------------
// Temps réel
// ---------------------------------------------------------------------
socket.on("telemetry_update", (payload) => {
  if (payload.device_id === deviceId) loadDeviceDetail();
});
socket.on("device_offline", (data) => {
  if (data.device_id === deviceId) loadDeviceDetail();
});
socket.on("command_sent", (data) => {
  if (data.device_id === deviceId) showToast(`Commande '${data.action}' transmise à l'agent.`, "success");
});

// ---------------------------------------------------------------------
// Initialisation
// ---------------------------------------------------------------------
loadDeviceDetail();
setInterval(loadDeviceDetail, 4000);
const devicePage = document.getElementById("device-page");

if (devicePage) {

    const deviceId = devicePage.dataset.deviceId;

    const startButton =
        document.getElementById("btn-screen-start");

    const stopButton =
        document.getElementById("btn-screen-stop");

    const viewer =
        document.getElementById("screen-viewer");

    const status =
        document.getElementById("screen-status");


    startButton?.addEventListener("click", async () => {

        const response = await fetch(
            `/api/devices/${deviceId}/screen/start`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                }
            }
        );

        const data = await response.json();

        if (!response.ok) {

            alert(
                data.error ||
                "Impossible d'activer le partage d'écran."
            );

            return;
        }

        status.textContent =
            "Partage d'écran demandé...";

        status.classList.add(
            "screen-active"
        );
    });


    stopButton?.addEventListener("click", async () => {

        const response = await fetch(
            `/api/devices/${deviceId}/screen/stop`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                }
            }
        );

        if (response.ok) {

            viewer.innerHTML = `
                <div class="screen-placeholder">
                    <div>ÉCRAN NON DISPONIBLE</div>
                    <span>
                        Partage d'écran arrêté.
                    </span>
                </div>
            `;

            status.textContent =
                "Partage d'écran désactivé";

            status.classList.remove(
                "screen-active"
            );
        }
    });


    function refreshScreen() {

        const image = new Image();

        image.onload = () => {

            viewer.innerHTML = "";

            image.className =
                "remote-screen";

            viewer.appendChild(image);
        };

        image.src =
            `/api/devices/${deviceId}/screen/frame?t=${Date.now()}`;
    }


    setInterval(
        refreshScreen,
        250
    );
}
