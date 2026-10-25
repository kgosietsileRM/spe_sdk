import { laneColor, renderCongestionChart, renderLegend, renderQueueChart } from "./charts.js";
import { Playback } from "./playback.js";

const $ = (id) => document.getElementById(id);

const dom = {
  clock: $("clock"),
  feedName: $("feed-name"),
  detectionLabel: $("detection-label"),
  connection: $("connection"),
  connectionLabel: $("connection-label"),
  form: $("run-form"),
  formError: $("form-error"),
  source: $("source"),
  preset: $("preset"),
  frames: $("frames"),
  framesLabel: $("frames-label"),
  fps: $("fps"),
  mode: $("mode"),
  url: $("url"),
  model: $("model"),
  confidence: $("confidence"),
  run: $("run"),
  cancel: $("cancel"),
  runState: $("run-state"),
  progressText: $("progress-text"),
  progressBar: $("progress-bar"),
  runFrames: $("run-frames"),
  runElapsed: $("run-elapsed"),
  stageEyebrow: $("stage-eyebrow"),
  stageTitle: $("stage-title"),
  stageChip: $("stage-chip"),
  reportLink: $("report-link"),
  frame: $("frame"),
  placeholder: $("placeholder"),
  frameOverlay: $("frame-overlay"),
  overlayCamera: $("overlay-camera"),
  overlayTime: $("overlay-time"),
  overlayFrame: $("overlay-frame"),
  overlaySource: $("overlay-source"),
  playToggle: $("play-toggle"),
  playIcon: $("play-icon"),
  scrubber: $("scrubber"),
  incidentMarks: $("incident-marks"),
  playClock: $("play-clock"),
  laneSummary: $("lane-summary"),
  laneCards: $("lane-cards"),
  congestionChart: $("congestion-chart"),
  queueChart: $("queue-chart"),
  congestionLegend: $("congestion-legend"),
  kpiActive: $("kpi-active"),
  kpiActiveSub: $("kpi-active-sub"),
  kpiCongestion: $("kpi-congestion"),
  kpiCongestionSub: $("kpi-congestion-sub"),
  kpiSpeed: $("kpi-speed"),
  kpiIncidents: $("kpi-incidents"),
  kpiIncidentsSub: $("kpi-incidents-sub"),
  advisoryState: $("advisory-state"),
  advisoryPriority: $("advisory-priority"),
  advisoryMetering: $("advisory-metering"),
  advisoryActions: $("advisory-actions"),
  advisoryReasons: $("advisory-reasons"),
  incidentList: $("incident-list"),
  incidentCount: $("incident-count"),
  zoneMap: $("zone-map"),
  zoneCaption: $("zone-caption"),
  sessionList: $("session-list"),
  sessionCount: $("session-count"),
  stopped: $("policy-stopped"),
  stoppedOut: $("policy-stopped-out"),
  duration: $("policy-duration"),
  durationOut: $("policy-duration-out"),
  congestion: $("policy-congestion"),
  congestionOut: $("policy-congestion-out"),
  policyApply: $("policy-apply"),
};

const state = {
  sessionId: null,
  session: null,
  status: "idle",
  history: [],
  incidents: [],
  advisory: {},
  policy: { stopped_speed: 55, stopped_seconds: 1.5, congestion_high: 70 },
  presets: {},
  fps: 5,
  startedAt: null,
  finishedAt: null,
  pollTimer: null,
  cursor: 0,
  syncedPolicy: null,
  busy: false,
};

const playback = new Playback({
  frame: dom.frame,
  scrubber: dom.scrubber,
  clock: dom.playClock,
  button: dom.playToggle,
  icon: dom.playIcon,
  marks: dom.incidentMarks,
  onFrame: (item, index) => {
    state.cursor = index;
    renderSnapshot(item);
    renderCharts();
  },
});

function clock(value) {
  const seconds = Math.max(0, Number(value) || 0);
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}

function timestamp(value) {
  if (!value) return "—";
  const date = new Date(Number(value) * 1000);
  return `${date.toLocaleDateString([], { month: "short", day: "2-digit" })} ${date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
}

function localClock() {
  return new Date().toLocaleTimeString([], { hour12: false });
}

function setConnection(kind, label) {
  dom.connection.className = `connection ${kind || ""}`.trim();
  dom.connectionLabel.textContent = label;
}

function showFormError(message) {
  if (!message) {
    dom.formError.hidden = true;
    dom.formError.textContent = "";
    return;
  }
  dom.formError.hidden = false;
  dom.formError.textContent = message;
}

function setStatusChip(label, kind) {
  dom.stageChip.textContent = label;
  dom.stageChip.className = `status-chip ${kind || ""}`.trim();
}

function setStage(eyebrow, title, label, kind) {
  dom.stageEyebrow.textContent = eyebrow;
  dom.stageTitle.textContent = title;
  setStatusChip(label, kind);
}

function setRunningControls(running) {
  for (const element of [dom.source, dom.preset, dom.frames, dom.fps, dom.mode, dom.url, dom.model, dom.confidence]) {
    element.disabled = running;
  }
  dom.run.disabled = running;
  dom.cancel.hidden = !running;
}

function statusLabel(status) {
  return {
    queued: "Queued",
    running: "Monitoring",
    done: "Complete",
    error: "Fault",
    cancelled: "Stopped",
    idle: "Standby",
  }[status] || "Standby";
}

function updateProgress(session) {
  const isLive = Boolean(session?.live);
  const percent = Math.max(0, Math.min(100, Number(session?.progress) || 0));
  dom.progressBar.classList.toggle("live", isLive);
  dom.progressBar.style.width = isLive ? "100%" : `${percent}%`;
  dom.progressText.textContent = isLive ? "LIVE" : `${Math.round(percent)}%`;
  dom.runFrames.textContent = isLive
    ? `${session?.sampled_frames || 0} frames logged`
    : `${session?.sampled_frames || 0} / ${session?.frames_total || 0} frames`;
  dom.runState.textContent = statusLabel(session?.status || "idle");
  dom.runState.classList.toggle("run-state-error", session?.status === "error");
  updateElapsed();
}

function updateElapsed() {
  if (!state.startedAt) {
    dom.runElapsed.textContent = "00:00";
    return;
  }
  const end = state.finishedAt || Date.now() / 1000;
  dom.runElapsed.textContent = clock(end - state.startedAt);
}

function selectedPreset() {
  return state.presets[dom.preset.value] || state.session?.preset || { rows: 2, columns: 3 };
}

function selectedSourceLabel() {
  return dom.source.options[dom.source.selectedIndex]?.textContent || dom.source.value;
}

function selectedSourceIsLive() {
  return dom.source.value === "live";
}

function updateFramesLabel() {
  if (!dom.framesLabel) return;
  dom.framesLabel.textContent = selectedSourceIsLive() ? "Live buffer" : "Sample frames";
}

async function refreshPreview() {
  if (state.status === "running" || state.status === "queued") return;
  const source = dom.source.value;
  const sourceLabel = selectedSourceLabel();
  const isLive = selectedSourceIsLive();
  const presetName = dom.preset.value;
  const preset = state.presets[presetName] || { name: presetName };
  dom.placeholder.hidden = false;
  dom.placeholder.querySelector("p").textContent = isLive ? "Resolving live camera feed…" : "Loading camera preview…";
  dom.frame.classList.remove("visible");
  dom.frame.alt = `Preview of ${sourceLabel}`;
  dom.frame.src = `/api/preview?source=${encodeURIComponent(source)}&preset=${encodeURIComponent(presetName)}&t=${Date.now()}`;
  dom.frame.onload = () => {
    dom.frame.classList.add("visible");
    dom.placeholder.hidden = true;
  };
  dom.frame.onerror = () => {
    dom.placeholder.hidden = false;
    dom.placeholder.querySelector("p").textContent = "Preview unavailable for this feed.";
  };
  dom.feedName.textContent = sourceLabel;
  dom.detectionLabel.textContent = dom.mode.value === "local" ? "Local" : "Engine";
  dom.overlayCamera.textContent = `CAM 02 · ${sourceLabel}`;
  dom.overlayTime.textContent = localClock();
  dom.overlayFrame.textContent = isLive ? "LIVE" : "PREVIEW";
  dom.overlaySource.textContent = `${preset.name || presetName} · ${preset.columns || "—"} lanes`;
  setStage("Preview", `${preset.name || presetName} camera preview`, isLive ? "LIVE" : "PREVIEW", "preview");
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  let data = {};
  try {
    data = await response.json();
  } catch {
    data = {};
  }
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function applySession(data, { loadReplay = true, syncPolicy = false } = {}) {
  const previousId = state.sessionId;
  state.sessionId = data.id;
  state.session = data;
  state.status = data.status;
  state.history = Array.isArray(data.history) ? data.history : [];
  state.incidents = Array.isArray(data.incidents) ? data.incidents : [];
  state.advisory = data.advisory || {};
  state.startedAt = data.started_at || null;
  state.finishedAt = data.finished_at || null;
  state.fps = Number(data.fps) || state.fps;
  if (syncPolicy || state.syncedPolicy !== data.id) {
    state.syncedPolicy = data.id;
    state.policy = { ...state.policy, ...(data.policy || {}) };
    applyPolicyControls();
  }

  const sourceName = data.source?.name || data.source?.key || dom.source.value;
  dom.feedName.textContent = sourceName;
  dom.detectionLabel.textContent = data.mode === "server" ? "Engine" : "Local";
  dom.overlayCamera.textContent = `CAM 02 · ${sourceName}`;
  dom.overlaySource.textContent = data.source?.width
    ? `${data.source.width}×${data.source.height} · ${data.source.fps} FPS`
    : "—";
  updateProgress(data);

  if (data.status === "running" || data.status === "queued") {
    setRunningControls(true);
    setConnection("busy", "Monitoring");
    setStage("Live monitoring", `${data.preset?.name || "Mainline"} · ${sourceName}`, "LIVE", "running");
    playback.setLive(data.id);
    const latest = state.history[state.history.length - 1];
    if (latest) {
      state.cursor = state.history.length - 1;
      playback.showLive(`/api/sessions/${data.id}/frame?t=${latest.frame}`);
      renderSnapshot(latest);
    } else {
      dom.playClock.textContent = "LIVE";
    }
    renderAdvisory();
    renderIncidents();
    renderCharts();
    return;
  }

  setRunningControls(false);
  dom.cancel.hidden = true;
  if (data.status === "done") {
    setConnection("live", "Complete");
    setStage("Replay", `${data.preset?.name || "Mainline"} · ${sourceName}`, "COMPLETE", "done");
    dom.reportLink.hidden = false;
    dom.reportLink.href = `/api/sessions/${data.id}/report`;
    renderAdvisory();
    renderIncidents();
    if (loadReplay && (previousId !== data.id || playback.mode !== "replay")) {
      playback.load({
        sessionId: data.id,
        history: state.history,
        incidents: state.incidents,
        fps: state.fps,
      });
    } else {
      playback.updateIncidents(state.incidents);
      playback.seek(Math.min(state.cursor, Math.max(0, state.history.length - 1)));
    }
    refreshSessions();
  } else if (data.status === "error") {
    setConnection("error", "Fault");
    setStage("Fault", "Monitoring interrupted", "FAULT", "error");
    showFormError(data.error || "The analysis stopped unexpectedly.");
    if (data.report_ready) {
      dom.reportLink.hidden = false;
      dom.reportLink.href = `/api/sessions/${data.id}/report`;
    } else {
      dom.reportLink.hidden = true;
    }
    playback.pause();
    renderCharts();
    renderAdvisory();
    renderIncidents();
    refreshSessions();
  } else if (data.status === "cancelled") {
    setConnection("", "Stopped");
    setStage("Stopped", "Monitoring stopped by operator", "STOPPED", "cancelled");
    if (data.report_ready) {
      dom.reportLink.hidden = false;
      dom.reportLink.href = `/api/sessions/${data.id}/report`;
    } else {
      dom.reportLink.hidden = true;
    }
    playback.pause();
    if (state.history.length) {
      playback.load({ sessionId: data.id, history: state.history, incidents: state.incidents, fps: state.fps });
    }
    renderCharts();
    renderAdvisory();
    renderIncidents();
    refreshSessions();
  }
}

function renderSnapshot(snapshot) {
  if (!snapshot) return;
  const lanes = snapshot.lanes || {};
  const active = Number(snapshot.active) || 0;
  const congestion = Number(snapshot.congestion) || 0;
  const open = (state.incidents || []).filter((item) => item.open).length;
  dom.kpiActive.textContent = String(active);
  dom.kpiActiveSub.textContent = `${Object.keys(lanes).length} lane${Object.keys(lanes).length === 1 ? "" : "s"} monitored`;
  dom.kpiCongestion.textContent = String(Math.round(congestion));
  dom.kpiCongestionSub.textContent = congestionLabel(congestion);
  dom.kpiSpeed.textContent = String(Math.round(Number(snapshot.speed) || 0));
  dom.kpiIncidents.textContent = String(open);
  dom.kpiIncidentsSub.textContent = open ? "Response required" : "No active alerts";
  document.querySelector(".alert-kpi")?.classList.toggle("hot", open > 0);

  dom.overlayTime.textContent = `T+${clock(snapshot.t)}`;
  dom.overlayFrame.textContent = `FRAME ${String(snapshot.frame || 0).padStart(4, "0")}`;
  dom.laneSummary.textContent = `${active} vehicles · queue ${snapshot.queue || 0} · congestion ${Math.round(congestion)}`;
  renderLanes(lanes);
  renderZoneMap(snapshot.zones || {});
}

function renderLanes(lanes) {
  const entries = Object.entries(lanes || {});
  if (!entries.length) {
    dom.laneCards.innerHTML = '<p class="empty">Lane telemetry appears when monitoring starts.</p>';
    return;
  }
  const preset = state.session?.preset || selectedPreset();
  const indices = new Map(entries.map(([lane], index) => [lane, index]));
  const groups = Array.isArray(preset.groups) && preset.groups.length
    ? preset.groups
    : [{ name: "", lanes: entries.map(([lane]) => lane) }];
  const grouped = new Set(groups.flatMap((group) => group.lanes || []));
  const sections = groups
    .map((group) => {
      const groupEntries = entries.filter(([lane]) => (group.lanes || []).includes(lane));
      if (!groupEntries.length) return "";
      const heading = group.name ? `<h3>${escapeText(group.name)}</h3>` : "";
      return `<section class="lane-group">${heading}<div class="lane-group-grid">${groupEntries
        .map(([lane, data]) => laneCard(lane, data, indices.get(lane)))
        .join("")}</div></section>`;
    })
    .filter(Boolean);
  const rest = entries.filter(([lane]) => !grouped.has(lane));
  if (rest.length) {
    sections.push(
      `<section class="lane-group"><div class="lane-group-grid">${rest
        .map(([lane, data]) => laneCard(lane, data, indices.get(lane)))
        .join("")}</div></section>`,
    );
  }
  dom.laneCards.innerHTML = sections.join("");
}

function laneCard(lane, data, index) {
  const congestion = Number(data.congestion) || 0;
  const status = laneState(congestion);
  const color = laneColor(lane, index);
  return `<article class="lane-card" style="--lane-color:${color}">
    <div class="lane-head">
      <span class="lane-name">Lane ${lane}</span>
      <span class="lane-state ${status.kind}">${status.label}</span>
    </div>
    <div class="lane-values">
      <div><span>Occ</span><strong>${data.occupancy ?? 0}</strong></div>
      <div><span>Queue</span><strong>${data.queue ?? 0}</strong></div>
      <div><span>Speed</span><strong>${Math.round(Number(data.speed) || 0)}</strong></div>
    </div>
    <div class="lane-bar"><i style="width:${Math.min(100, congestion)}%"></i></div>
  </article>`;
}

function laneState(congestion) {
  if (congestion >= 70) return { label: "CONGESTED", kind: "congested" };
  if (congestion >= 45) return { label: "WATCH", kind: "watch" };
  return { label: "NORMAL", kind: "" };
}

function congestionLabel(value) {
  if (value >= 70) return "Congested";
  if (value >= 45) return "Elevated";
  if (value >= 20) return "Guarded";
  return "Normal range";
}

function renderZoneMap(zones) {
  const preset = state.session?.preset || selectedPreset();
  const rows = Math.max(1, Number(preset.rows) || 2);
  const columns = Math.max(1, Number(preset.columns) || 3);
  dom.zoneMap.style.gridTemplateColumns = `repeat(${columns}, minmax(0, 1fr))`;
  let html = "";
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      const name = `${String.fromCharCode(65 + column)}${row + 1}`;
      const value = Number(zones[name]) || 0;
      const kind = value >= 2 ? "busy" : value >= 1 ? "occupied" : "";
      html += `<div class="zone-cell ${kind}" title="Zone ${name}: ${value} vehicles"><span>${name}</span><strong>${value}</strong></div>`;
    }
  }
  dom.zoneMap.innerHTML = html;
  dom.zoneCaption.textContent = state.status === "done" ? "REPLAY" : "LIVE";
}

function renderAdvisory() {
  const advisory = state.advisory || {};
  const kind = advisory.state || "normal";
  dom.advisoryState.textContent = kind.toUpperCase();
  dom.advisoryState.className = `status-chip ${kind}`;
  dom.advisoryPriority.textContent = String(advisory.priority || "low").toUpperCase();
  dom.advisoryMetering.textContent = String(advisory.metering || "OPEN");
  const actions = advisory.actions || ["Maintain normal operations"];
  dom.advisoryActions.innerHTML = actions.map((item) => `<li>${escapeText(item)}</li>`).join("");
  dom.advisoryReasons.textContent = (advisory.reasons || []).join(" · ") || "No active alerts; flow within normal range";
}

function renderIncidents() {
  const incidents = [...(state.incidents || [])].sort((a, b) => (b.start_frame || 0) - (a.start_frame || 0));
  const open = incidents.filter((item) => item.open).length;
  dom.incidentCount.textContent = String(incidents.length);
  dom.kpiIncidents.textContent = String(open);
  dom.kpiIncidentsSub.textContent = open ? "Response required" : "No active alerts";
  document.querySelector(".alert-kpi")?.classList.toggle("hot", open > 0);
  if (!incidents.length) {
    dom.incidentList.innerHTML = '<p class="empty">No incidents detected in this deployment.</p>';
    return;
  }
  dom.incidentList.innerHTML = incidents
    .map(
      (incident, index) => `<button type="button" class="incident-item ${incident.severity || "low"}" data-incident="${index}">
        <span class="incident-top">
          <span class="incident-type">${incidentLabel(incident.type)} · ${incident.lane === "ALL" ? "MAINLINE" : `LANE ${incident.lane}`}</span>
          <span class="incident-sev">${String(incident.severity || "low").toUpperCase()}</span>
        </span>
        <span class="incident-msg">${escapeText(incident.message || "")}</span>
        <span class="incident-meta"><span>${clock(incident.start_time)} – ${clock(incident.end_time)}</span><span>${incident.open ? "OPEN" : `T+${clock(incident.end_time)}`}</span></span>
      </button>`
    )
    .join("");
  dom.incidentList.querySelectorAll("[data-incident]").forEach((button) => {
    button.addEventListener("click", () => {
      const incident = incidents[Number(button.dataset.incident)];
      jumpToFrame(incident?.start_frame);
    });
  });
}

function renderCharts() {
  const lanes = Object.keys(state.history[state.history.length - 1]?.lanes || state.session?.lanes || {});
  renderLegend(dom.congestionLegend, lanes);
  renderCongestionChart(dom.congestionChart, state.history, state.incidents, state.cursor);
  renderQueueChart(dom.queueChart, state.history, state.cursor);
}

function jumpToFrame(frameNumber) {
  if (!Number.isFinite(frameNumber)) return;
  const index = state.history.findIndex((item) => item.frame === frameNumber);
  if (index < 0) return;
  playback.pause();
  playback.seek(index);
}

function applyPolicyControls() {
  const stopped = Number(state.policy.stopped_speed ?? 55);
  const duration = Number(state.policy.stopped_seconds ?? 1.5);
  const congestion = Number(state.policy.congestion_high ?? 70);
  dom.stopped.value = String(stopped);
  dom.duration.value = String(duration);
  dom.congestion.value = String(congestion);
  updatePolicyLabels();
}

function updatePolicyLabels() {
  dom.stoppedOut.textContent = dom.stopped.value;
  dom.durationOut.textContent = `${dom.duration.value} s`;
  dom.congestionOut.textContent = dom.congestion.value;
}

async function applyPolicy() {
  if (!state.sessionId) return;
  dom.policyApply.disabled = true;
  try {
    const policy = {
      stopped_speed: Number(dom.stopped.value),
      stopped_seconds: Number(dom.duration.value),
      congestion_high: Number(dom.congestion.value),
    };
    const data = await fetchJson(`/api/sessions/${state.sessionId}/what-if`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ policy }),
    });
    state.policy = data.policy;
    state.incidents = data.incidents || [];
    state.advisory = data.advisory || {};
    playback.updateIncidents(state.incidents);
    renderAdvisory();
    renderIncidents();
    renderCharts();
    showFormError("");
  } catch (error) {
    showFormError(error.message);
  } finally {
    dom.policyApply.disabled = false;
  }
}

async function startMonitoring(event) {
  event.preventDefault();
  if (state.busy) return;
  showFormError("");
  state.busy = true;
  state.sessionId = null;
  state.session = null;
  state.status = "queued";
  state.history = [];
  state.incidents = [];
  state.advisory = {};
  state.cursor = 0;
  state.syncedPolicy = null;
  dom.reportLink.hidden = true;
  dom.playToggle.disabled = true;
  dom.incidentList.innerHTML = '<p class="empty">Monitoring in progress.</p>';
  dom.incidentCount.textContent = "0";
  setRunningControls(true);
  dom.cancel.hidden = true;
  setConnection("busy", "Starting");
  setStage("Deployment", "Requesting camera feed", "QUEUED", "running");
  dom.placeholder.hidden = false;
  dom.placeholder.querySelector("p").textContent = selectedSourceIsLive()
    ? "Resolving live camera feed…"
    : "Preparing camera feed…";
  dom.frame.classList.remove("visible");
  updateProgress({
    progress: 0,
    sampled_frames: 0,
    frames_total: Number(dom.frames.value),
    status: "queued",
    live: selectedSourceIsLive(),
  });
  dom.runElapsed.textContent = "00:00";

  const payload = {
    source: dom.source.value,
    preset: dom.preset.value,
    frames: Number(dom.frames.value),
    fps: Number(dom.fps.value),
    mode: dom.mode.value,
    url: dom.url.value,
    model: dom.model.value,
    confidence: Number(dom.confidence.value),
  };
  try {
    const data = await fetchJson("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.sessionId = data.id;
    state.startedAt = Date.now() / 1000;
    state.finishedAt = null;
    playback.setLive(data.id);
    dom.cancel.hidden = false;
    poll();
    state.pollTimer = setInterval(poll, 600);
    refreshSessions();
  } catch (error) {
    state.busy = false;
    state.status = "error";
    setRunningControls(false);
    setConnection("error", "Fault");
    setStage("Fault", "Could not start monitoring", "FAULT", "error");
    showFormError(error.message);
  }
}

async function poll() {
  if (!state.sessionId) return;
  try {
    const data = await fetchJson(`/api/sessions/${state.sessionId}`);
    const finished = ["done", "error", "cancelled"].includes(data.status);
    applySession(data, { loadReplay: true });
    state.busy = data.status === "running" || data.status === "queued";
    if (finished) {
      stopPolling();
      state.busy = false;
    }
  } catch (error) {
    stopPolling();
    state.busy = false;
    setRunningControls(false);
    setConnection("error", "Link lost");
    showFormError(error.message);
  }
}

function stopPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = null;
}

async function cancelMonitoring() {
  if (!state.sessionId) return;
  dom.cancel.disabled = true;
  try {
    await fetchJson(`/api/sessions/${state.sessionId}/cancel`, { method: "POST" });
    dom.cancel.disabled = false;
  } catch (error) {
    dom.cancel.disabled = false;
    showFormError(error.message);
  }
}

async function loadSession(sessionId) {
  if (state.busy) {
    showFormError("Stop the current deployment before opening another session.");
    return;
  }
  try {
    const data = await fetchJson(`/api/sessions/${sessionId}`);
    state.busy = false;
    state.cursor = 0;
    applySession(data, { loadReplay: true, syncPolicy: true });
    if (data.status === "running" || data.status === "queued") {
      state.busy = true;
      poll();
      state.pollTimer = setInterval(poll, 600);
    }
    refreshSessions();
  } catch (error) {
    showFormError(error.message);
  }
}

async function refreshSessions() {
  try {
    const data = await fetchJson("/api/sessions");
    const sessions = data.sessions || [];
    dom.sessionCount.textContent = String(sessions.length);
    if (!sessions.length) {
      dom.sessionList.innerHTML = '<p class="empty">No completed deployments.</p>';
      return;
    }
    dom.sessionList.innerHTML = sessions
      .map((session) => {
        const total = session.incident_summary?.total || 0;
        const active = session.id === state.sessionId ? " active" : "";
        return `<button type="button" class="session-item${active}" data-session="${session.id}">
          <span class="session-meta"><strong>${escapeText(session.source?.name || session.source?.key || "Feed")}</strong><span>${statusLabel(session.status)}</span></span>
          <span>${escapeText(session.preset?.name || "Lane preset")} · ${timestamp(session.started_at)}</span>
          <span>${total} incident${total === 1 ? "" : "s"} · ${Math.round(session.summary?.congestion || 0)} congestion</span>
        </button>`;
      })
      .join("");
    dom.sessionList.querySelectorAll("[data-session]").forEach((button) => {
      button.addEventListener("click", () => loadSession(button.dataset.session));
    });
  } catch {
    // Session history is secondary; polling errors are surfaced elsewhere.
  }
}

async function loadPresets() {
  try {
    const data = await fetchJson("/api/presets");
    state.presets = data.presets || {};
  } catch {
    state.presets = {};
  }
}

function escapeText(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

function incidentLabel(type) {
  return {
    stopped_vehicle: "STOPPED VEHICLE",
    queue_buildup: "QUEUE BUILDUP",
    network_congestion: "CONGESTION",
    lane_imbalance: "IMBALANCE",
  }[type] || String(type || "ALERT").toUpperCase();
}

dom.form.addEventListener("submit", startMonitoring);
dom.cancel.addEventListener("click", cancelMonitoring);
dom.source.addEventListener("change", () => {
  updateFramesLabel();
  refreshPreview();
});
dom.preset.addEventListener("change", refreshPreview);
dom.mode.addEventListener("change", () => {
  dom.detectionLabel.textContent = dom.mode.value === "local" ? "Local" : "Engine";
});
dom.stopped.addEventListener("input", updatePolicyLabels);
dom.duration.addEventListener("input", updatePolicyLabels);
dom.congestion.addEventListener("input", updatePolicyLabels);
dom.policyApply.addEventListener("click", applyPolicy);

document.addEventListener("keydown", (event) => {
  const tag = event.target?.tagName?.toLowerCase();
  if (["input", "select", "textarea", "button"].includes(tag)) return;
  if (event.code === "Space") {
    event.preventDefault();
    playback.toggle();
  } else if (event.code === "ArrowRight") {
    event.preventDefault();
    playback.pause();
    playback.seek(state.cursor + 1);
  } else if (event.code === "ArrowLeft") {
    event.preventDefault();
    playback.pause();
    playback.seek(state.cursor - 1);
  }
});

setInterval(() => {
  dom.clock.textContent = localClock();
  updateElapsed();
}, 1000);
dom.clock.textContent = localClock();

renderLanes({});
renderAdvisory();
renderIncidents();
renderCharts();
updatePolicyLabels();
updateFramesLabel();
loadPresets().then(refreshPreview);
refreshSessions();
