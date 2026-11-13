/**
 * PitchPulse 2026 - Stadium Operations & Accessible Wayfinding Frontend
 * WCAG 2.1 AA Compliant • Zero XSS • Native SpeechSynthesis • Focus-Trapped Modals
 */

const API_BASE = "";
let currentProfile = "wheelchair";
let selectedLang = "en";
let gatePollInterval = null;
let lastFocusedElement = null;

// Initialize on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  setupLanguageSelector();
  setupMobilityProfiles();
  setupModalKeyboardHandlers();
  loadGateData();
  calculateRoute();
  loadConcessionsData();
  setupPollingWithVisibility();
  if (window.lucide) {
    window.lucide.createIcons();
  }
});

/* ==========================================================================
   1. Toast Notifications (Replaces alert() with aria-live status alerts)
   ========================================================================== */
function showToast(message, type = "info") {
  let container = document.getElementById("toastContainer");
  if (!container) {
    container = document.createElement("div");
    container.id = "toastContainer";
    container.className = "toast-container";
    container.setAttribute("aria-live", "polite");
    container.setAttribute("aria-atomic", "true");
    document.body.appendChild(container);
  }

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.setAttribute("role", "status");

  const iconSpan = document.createElement("span");
  iconSpan.textContent = type === "success" ? "✓" : type === "error" ? "⚠" : "ℹ";
  toast.appendChild(iconSpan);

  const textSpan = document.createElement("span");
  textSpan.textContent = message;
  toast.appendChild(textSpan);

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transition = "opacity 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

/* ==========================================================================
   2. Speech Synthesis (Text-to-Speech Accessibility Feature)
   ========================================================================== */
function speakText(text, langCode = "en") {
  if (!("speechSynthesis" in window)) {
    showToast("Speech synthesis is not supported on this browser.", "info");
    return;
  }
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  const langMap = { en: "en-US", es: "es-ES", fr: "fr-FR", pt: "pt-BR", ar: "ar-SA" };
  utterance.lang = langMap[langCode] || "en-US";
  utterance.rate = 1.0;
  window.speechSynthesis.speak(utterance);
}

/* ==========================================================================
   3. Multilingual Support (EN, ES, FR, PT, AR with RTL support)
   ========================================================================== */
function setupLanguageSelector() {
  const container = document.getElementById("langSelectorGroup");
  if (!container) return;

  const languages = [
    { code: "en", label: "EN 🇺🇸" },
    { code: "es", label: "ES 🇪🇸" },
    { code: "fr", label: "FR 🇫🇷" },
    { code: "pt", label: "PT 🇧🇷" },
    { code: "ar", label: "AR 🇸🇦" },
  ];

  container.innerHTML = "";
  languages.forEach((lang) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.dataset.lang = lang.code;
    btn.textContent = lang.label;
    btn.setAttribute("aria-label", `Switch language to ${lang.label}`);
    btn.className = `px-3.5 py-2 rounded-xl text-xs font-bold transition-all ${
      selectedLang === lang.code
        ? "bg-pitch-green text-slate-950 shadow-md font-extrabold"
        : "bg-slate-900 text-slate-300 hover:text-white"
    }`;

    btn.addEventListener("click", () => {
      setLanguage(lang.code);
    });
    container.appendChild(btn);
  });
}

function setLanguage(lang) {
  selectedLang = lang;
  document.documentElement.lang = lang;
  if (lang === "ar") {
    document.documentElement.setAttribute("dir", "rtl");
  } else {
    document.documentElement.removeAttribute("dir");
  }

  // Update button active states
  const buttons = document.querySelectorAll("#langSelectorGroup button");
  buttons.forEach((btn) => {
    if (btn.dataset.lang === lang) {
      btn.className = "px-3.5 py-2 rounded-xl text-xs font-bold transition-all bg-pitch-green text-slate-950 shadow-md font-extrabold";
    } else {
      btn.className = "px-3.5 py-2 rounded-xl text-xs font-bold transition-all bg-slate-900 text-slate-300 hover:text-white";
    }
  });

  showToast(`Language set to ${lang.toUpperCase()}`, "info");
}

/* ==========================================================================
   4. Gate Telemetry & Sensor Polling (Auto-pauses when tab is hidden)
   ========================================================================== */
function setupPollingWithVisibility() {
  startGatePolling();
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      stopGatePolling();
    } else {
      startGatePolling();
      loadGateData();
    }
  });
}

function startGatePolling() {
  if (!gatePollInterval) {
    gatePollInterval = setInterval(loadGateData, 30000);
  }
}

function stopGatePolling() {
  if (gatePollInterval) {
    clearInterval(gatePollInterval);
    gatePollInterval = null;
  }
}

async function loadGateData() {
  try {
    const res = await fetch(`${API_BASE}/api/stadium/gates`);
    if (res.ok) {
      const gates = await res.json();
      renderGates(gates);
      return;
    }
  } catch (err) {
    console.warn("Using offline gate sensor values:", err);
  }

  // Resilient fallback gate data
  renderGates([
    { gate_id: "gate-a", name: "Gate A — North Main Plaza", density_percentage: 42, wait_time_minutes: 4, accessible_ramp: true, status_level: "normal", predicted_surge_15m: 54 },
    { gate_id: "gate-b", name: "Gate B — East ADA Concourse", density_percentage: 28, wait_time_minutes: 2, accessible_ramp: true, status_level: "normal", predicted_surge_15m: 35 },
    { gate_id: "gate-c", name: "Gate C — South Boulevard", density_percentage: 78, wait_time_minutes: 14, accessible_ramp: false, status_level: "surge", predicted_surge_15m: 91 },
    { gate_id: "gate-d", name: "Gate D — West Transit Hub", density_percentage: 35, wait_time_minutes: 3, accessible_ramp: true, status_level: "normal", predicted_surge_15m: 42 },
  ]);
}

function renderGates(gates) {
  const container = document.getElementById("gatesGrid");
  if (!container) return;
  container.innerHTML = "";

  // Show simulated data notice above the grid
  let notice = document.getElementById("simulatedDataNotice");
  if (!notice) {
    notice = document.createElement("p");
    notice.id = "simulatedDataNotice";
    notice.className = "text-xs text-pitch-yellow font-bold mb-3 flex items-center gap-1";
    notice.setAttribute("role", "status");
    notice.setAttribute("aria-live", "polite");
    notice.textContent = "⚠ DEMO — SIMULATED DATA. Not real sensor readings.";
    container.parentElement.insertBefore(notice, container);
  }

  const fetchedAt = new Date().toLocaleTimeString();

  gates.forEach((g) => {
    const card = document.createElement("article");
    card.className = "glass-panel p-5 rounded-2xl border border-pitch-border flex flex-col justify-between";

    const isSurge = g.density_percentage >= 70;
    const isModerate = g.density_percentage >= 40 && !isSurge;

    const statusBadgeClass = isSurge
      ? "density-badge-surge"
      : isModerate
      ? "density-badge-moderate"
      : "density-badge-normal";

    const statusText = isSurge ? "⚠ SURGE" : isModerate ? "MODERATE" : "✓ NORMAL";

    // Header
    const headerDiv = document.createElement("div");
    headerDiv.className = "flex items-center justify-between mb-3";

    const nameH3 = document.createElement("h3");
    nameH3.className = "font-extrabold text-sm text-white";
    nameH3.textContent = g.name.split("—")[0].trim();
    headerDiv.appendChild(nameH3);

    const badge = document.createElement("span");
    badge.className = `px-2.5 py-1 rounded-full text-xs font-black uppercase tracking-wider ${statusBadgeClass}`;
    badge.textContent = statusText;
    headerDiv.appendChild(badge);

    card.appendChild(headerDiv);

    // Subtitle
    const subP = document.createElement("p");
    subP.className = "text-xs text-slate-400 mb-4";
    subP.textContent = g.name.includes("—") ? g.name.split("—")[1].trim() : g.name;
    card.appendChild(subP);

    // Density Bar
    const densityWrapper = document.createElement("div");
    densityWrapper.className = "space-y-1.5 mb-4";

    const densityHeader = document.createElement("div");
    densityHeader.className = "flex justify-between text-xs font-bold";

    const densityLabel = document.createElement("span");
    densityLabel.className = "text-slate-300";
    densityLabel.textContent = "Crowd Density";
    densityHeader.appendChild(densityLabel);

    const densityValue = document.createElement("span");
    densityValue.className = isSurge ? "text-pitch-red font-black" : "text-pitch-green font-black";
    densityValue.textContent = `${g.density_percentage}%`;
    densityHeader.appendChild(densityValue);
    densityWrapper.appendChild(densityHeader);

    const progressBar = document.createElement("div");
    progressBar.className = "w-full h-2 rounded-full bg-slate-900 overflow-hidden";
    const progressFill = document.createElement("div");
    progressFill.className = `h-full rounded-full ${isSurge ? "bg-pitch-red" : isModerate ? "bg-pitch-yellow" : "bg-pitch-green"}`;
    progressFill.style.width = `${g.density_percentage}%`;
    progressBar.appendChild(progressFill);
    densityWrapper.appendChild(progressBar);

    card.appendChild(densityWrapper);

    // Details Grid
    const detailsDiv = document.createElement("div");
    detailsDiv.className = "text-xs space-y-1.5 pt-3 border-t border-pitch-border";

    const waitRow = document.createElement("div");
    waitRow.className = "flex justify-between";
    const waitLbl = document.createElement("span");
    waitLbl.className = "text-slate-400";
    waitLbl.textContent = "Queue Wait:";
    const waitVal = document.createElement("span");
    waitVal.className = "font-extrabold text-white";
    waitVal.textContent = `${g.wait_time_minutes} mins`;
    waitRow.appendChild(waitLbl);
    waitRow.appendChild(waitVal);
    detailsDiv.appendChild(waitRow);

    const rampRow = document.createElement("div");
    rampRow.className = "flex justify-between";
    const rampLbl = document.createElement("span");
    rampLbl.className = "text-slate-400";
    rampLbl.textContent = "Step-Free:";
    const rampVal = document.createElement("span");
    rampVal.className = `font-bold ${g.accessible_ramp ? "text-pitch-green" : "text-slate-500"}`;
    rampVal.textContent = g.accessible_ramp ? "♿ Verified Ramp" : "Stairs Only";
    rampRow.appendChild(rampLbl);
    rampRow.appendChild(rampVal);
    detailsDiv.appendChild(rampRow);

    const surgeForecastRow = document.createElement("div");
    surgeForecastRow.className = "flex justify-between";
    const surgeLbl = document.createElement("span");
    surgeLbl.className = "text-slate-400";
    surgeLbl.textContent = "15m Forecast:";
    const surgeVal = document.createElement("span");
    surgeVal.className = "font-bold text-pitch-yellow";
    surgeVal.textContent = `${g.predicted_surge_15m || g.density_percentage}%`;
    surgeForecastRow.appendChild(surgeLbl);
    surgeForecastRow.appendChild(surgeVal);
    detailsDiv.appendChild(surgeForecastRow);

    // Data freshness indicator
    const freshRow = document.createElement("div");
    freshRow.className = "flex justify-between pt-1 border-t border-slate-800 mt-1";
    const freshLabel = document.createElement("span");
    freshLabel.className = "text-slate-500 italic";
    freshLabel.textContent = "⚠ Simulated · Updated:";
    const freshValue = document.createElement("span");
    freshValue.className = "text-slate-500 font-mono text-xs";
    freshValue.textContent = fetchedAt;
    freshRow.appendChild(freshLabel);
    freshRow.appendChild(freshValue);
    detailsDiv.appendChild(freshRow);

    card.appendChild(detailsDiv);
    container.appendChild(card);
  });
}

function refreshGateData() {
  loadGateData();
  showToast("Gate sensors refreshed.", "success");
}

/* ==========================================================================
   5. Accessible Step-Free Wayfinding
   ========================================================================== */
function setupMobilityProfiles() {
  const bWheel = document.getElementById("btnProfileWheelchair");
  const bSens = document.getElementById("btnProfileSensory");
  const bLow = document.getElementById("btnProfileLowMobility");

  if (bWheel) bWheel.addEventListener("click", () => setMobilityProfile("wheelchair"));
  if (bSens) bSens.addEventListener("click", () => setMobilityProfile("sensory_sensitive"));
  if (bLow) bLow.addEventListener("click", () => setMobilityProfile("low_mobility"));
}

function setMobilityProfile(profile) {
  currentProfile = profile;
  const buttons = [
    { id: "btnProfileWheelchair", prof: "wheelchair", borderClass: "border-pitch-green", bgClass: "bg-pitch-green/10" },
    { id: "btnProfileSensory", prof: "sensory_sensitive", borderClass: "border-pitch-yellow", bgClass: "bg-pitch-yellow/10" },
    { id: "btnProfileLowMobility", prof: "low_mobility", borderClass: "border-pitch-red", bgClass: "bg-pitch-red/10" },
  ];

  buttons.forEach(({ id, prof, borderClass, bgClass }) => {
    const btn = document.getElementById(id);
    if (!btn) return;
    if (prof === profile) {
      btn.className = `w-full p-4 rounded-xl border ${borderClass} ${bgClass} text-left flex items-center justify-between text-xs font-bold text-white transition-all`;
      btn.setAttribute("aria-pressed", "true");
    } else {
      btn.className = "w-full p-4 rounded-xl border border-pitch-border bg-slate-900/60 hover:bg-slate-900 text-left flex items-center justify-between text-xs font-bold text-slate-300 transition-all";
      btn.setAttribute("aria-pressed", "false");
    }
  });

  calculateRoute();
}

async function calculateRoute() {
  const sectionInput = document.getElementById("ticketSectionInput");
  const section = (sectionInput ? sectionInput.value.trim() : "") || "104";

  try {
    const res = await fetch(`${API_BASE}/api/stadium/route`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticket_section: section, mobility_profile: currentProfile }),
    });
    if (res.ok) {
      const data = await res.json();
      renderRoute(data, section);
      return;
    }
  } catch (err) {
    console.warn("Using offline accessible route calculation:", err);
  }

  // Safe offline fallback
  renderRoute({
    recommended_gate: "Gate B (East Accessible Concourse) — MetLife Stadium",
    accessible_path: [
      "Enter via Gate B (East Concourse) — dedicated step-free ramp",
      "Follow high-contrast green tactile floor path",
      "Board Elevator Bank 2 to Concourse Level 1",
      `Direct step-free passage to Section ${section.toUpperCase()} viewing deck`,
    ],
    step_free: true,
    nearest_quiet_room: "Sensory Quiet Suite #2 (North Mezzanine Level 2)",
    nearest_elevator: "Elevator Bank 2 (North ADA Tower)",
    estimated_walk_minutes: 4,
    google_maps_directions_url: "https://www.google.com/maps/dir/?api=1&origin=40.8135,-74.0745&travelmode=transit",
  }, section);
}

function renderRoute(data, section) {
  const titleEl = document.getElementById("routeTitle");
  const timeEl = document.getElementById("routeTime");
  const quietEl = document.getElementById("routeQuietRoom");
  const elevEl = document.getElementById("routeElevator");
  const stepsContainer = document.getElementById("routeStepsList");
  const mapsLink = document.getElementById("mapsTransitLink");

  if (titleEl) titleEl.textContent = `Route to Section ${section.toUpperCase()}`;
  if (timeEl) timeEl.textContent = `${data.estimated_walk_minutes} mins`;
  if (quietEl) quietEl.textContent = data.nearest_quiet_room;
  if (elevEl) elevEl.textContent = data.nearest_elevator;

  if (mapsLink && data.google_maps_directions_url) {
    mapsLink.href = data.google_maps_directions_url;
    mapsLink.classList.remove("hidden");
  }

  if (stepsContainer) {
    stepsContainer.innerHTML = "";
    data.accessible_path.forEach((step, idx) => {
      const row = document.createElement("div");
      row.className = "flex items-start gap-3";

      const numBadge = document.createElement("div");
      numBadge.className = "w-6 h-6 rounded-full bg-pitch-green text-slate-950 font-black text-xs flex items-center justify-center shrink-0 mt-0.5";
      numBadge.textContent = String(idx + 1);
      row.appendChild(numBadge);

      const stepText = document.createElement("div");
      stepText.className = "text-xs text-slate-200 font-medium leading-relaxed";
      stepText.textContent = step;
      row.appendChild(stepText);

      stepsContainer.appendChild(row);
    });
  }
}

/* ==========================================================================
   6. Gemini Multilingual AI Concierge (Safe DOM, Read-Aloud, Real Latency)
   ========================================================================== */
function askSamplePrompt(promptText) {
  const input = document.getElementById("chatInput");
  if (!input) return;
  input.value = promptText;
  submitChatQuery();
}

async function submitChatQuery() {
  const input = document.getElementById("chatInput");
  if (!input) return;
  const prompt = input.value.trim();
  if (!prompt) return;

  const stream = document.getElementById("chatStream");
  if (!stream) return;

  // Append user message securely via textContent
  const userWrapper = document.createElement("div");
  userWrapper.className = "flex gap-3 justify-end chat-user";

  const userBubble = document.createElement("div");
  userBubble.className = "bg-pitch-green text-slate-950 font-bold p-3.5 rounded-2xl rounded-tr-none text-xs max-w-[85%]";
  userBubble.textContent = prompt;
  userWrapper.appendChild(userBubble);
  stream.appendChild(userWrapper);

  input.value = "";
  stream.scrollTop = stream.scrollHeight;

  // AI response container placeholder
  const aiWrapper = document.createElement("div");
  aiWrapper.className = "flex gap-3 chat-bot";

  const botAvatar = document.createElement("div");
  botAvatar.className = "w-8 h-8 rounded-xl bg-gradient-to-tr from-pitch-green to-pitch-yellow text-slate-950 flex items-center justify-center shrink-0 font-black text-xs";
  botAvatar.textContent = "AI";
  aiWrapper.appendChild(botAvatar);

  const botBubble = document.createElement("div");
  botBubble.className = "bg-pitch-slate p-4 rounded-2xl rounded-tl-none border border-pitch-border text-slate-200 leading-relaxed max-w-[85%] text-xs space-y-2";

  const textPara = document.createElement("p");
  textPara.textContent = "Thinking...";
  botBubble.appendChild(textPara);

  aiWrapper.appendChild(botBubble);
  stream.appendChild(aiWrapper);
  stream.scrollTop = stream.scrollHeight;

  try {
    const res = await fetch(`${API_BASE}/api/assistant/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, language: selectedLang, user_role: "fan" }),
    });

    if (res.ok) {
      const data = await res.json();
      textPara.textContent = data.response;

      // Metadata footer
      const metaDiv = document.createElement("div");
      metaDiv.className = "flex items-center justify-between pt-2 border-t border-pitch-border/60 text-xs text-slate-400";

      const sourceSpan = document.createElement("span");
      sourceSpan.className = "font-mono text-pitch-green";
      sourceSpan.textContent = `${data.source} • ${data.latency_ms}ms`;
      metaDiv.appendChild(sourceSpan);

      // Read Aloud button
      const speakBtn = document.createElement("button");
      speakBtn.type = "button";
      speakBtn.className = "speak-btn";
      const iconSpan = document.createElement("span");
      iconSpan.textContent = "🔊 ";
      const textSpan = document.createElement("span");
      textSpan.textContent = "Read Aloud";
      speakBtn.appendChild(iconSpan);
      speakBtn.appendChild(textSpan);
      speakBtn.setAttribute("aria-label", "Read AI response aloud");
      speakBtn.addEventListener("click", () => speakText(data.response, selectedLang));
      metaDiv.appendChild(speakBtn);

      botBubble.appendChild(metaDiv);

      const latencyBadge = document.getElementById("aiLatency");
      if (latencyBadge) latencyBadge.textContent = `${data.latency_ms}ms`;
      stream.scrollTop = stream.scrollHeight;
      return;
    }
  } catch (err) {
    console.warn("AI endpoint unreachable, falling back:", err);
  }

  // Fallback response handling
  textPara.textContent =
    "🚨 First Aid & Assistance: Gate B has full step-free ramp access and Sensory Suite #2. For medical support, proceed to Section 110 or contact operations staff.";
  stream.scrollTop = stream.scrollHeight;
}

/* ==========================================================================
   7. Concessions & Free Refill Points
   ========================================================================== */
async function loadConcessionsData() {
  const container = document.getElementById("concessionsGrid");
  if (!container) return;

  try {
    const res = await fetch(`${API_BASE}/api/stadium/concessions`);
    if (res.ok) {
      const stands = await res.json();
      renderConcessions(stands);
      return;
    }
  } catch (err) {
    console.warn("Using offline concessions data:", err);
  }

  renderConcessions([
    { stand_id: "c-1", name: "Pitchside Artisan Grill", section: "Sec 112", queue_wait_minutes: 3, has_water_refill: true, dietary_options: ["Halal", "Vegan", "Gluten-Free"] },
    { stand_id: "c-2", name: "World Cup Cantina", section: "Sec 104", queue_wait_minutes: 11, has_water_refill: true, dietary_options: ["Vegetarian"] },
    { stand_id: "c-3", name: "Eco Hydration & Fruit Bar", section: "Sec 128", queue_wait_minutes: 1, has_water_refill: true, dietary_options: ["Organic", "Nut-Free"] },
  ]);
}

function renderConcessions(stands) {
  const container = document.getElementById("concessionsGrid");
  if (!container) return;
  container.innerHTML = "";

  stands.forEach((c) => {
    const card = document.createElement("div");
    card.className = "glass-panel p-5 rounded-2xl border border-pitch-border flex flex-col justify-between";

    const header = document.createElement("div");
    header.className = "flex items-center justify-between mb-2";
    const secBadge = document.createElement("span");
    secBadge.className = "text-xs font-black text-pitch-yellow";
    secBadge.textContent = c.section;
    const waitBadge = document.createElement("span");
    waitBadge.className = "text-xs font-extrabold text-white";
    waitBadge.textContent = `Wait: ${c.queue_wait_minutes} mins`;
    header.appendChild(secBadge);
    header.appendChild(waitBadge);
    card.appendChild(header);

    const title = document.createElement("h3");
    title.className = "text-base font-extrabold text-white mb-1";
    title.textContent = c.name;
    card.appendChild(title);

    const optionsP = document.createElement("p");
    optionsP.className = "text-xs text-slate-400 mb-3";
    optionsP.textContent = Array.isArray(c.dietary_options) ? c.dietary_options.join(", ") : c.dietary_options;
    card.appendChild(optionsP);

    if (c.has_water_refill) {
      const refillBadge = document.createElement("div");
      refillBadge.className = "pt-3 border-t border-pitch-border flex items-center gap-1.5 text-xs text-pitch-green font-bold";
      const iconSpan = document.createElement("span");
      iconSpan.textContent = "💧";
      const textSpan = document.createElement("span");
      textSpan.textContent = "Free Eco-Water Refill Station";
      refillBadge.appendChild(iconSpan);
      refillBadge.appendChild(textSpan);
      card.appendChild(refillBadge);
    }

    container.appendChild(card);
  });
}

/* ==========================================================================
   8. Incident Reporting Modal (Focus-Trapped, Esc-Close, Staff Authenticated)
   ========================================================================== */
function openIncidentModal() {
  const modal = document.getElementById("incidentModal");
  if (!modal) return;
  lastFocusedElement = document.activeElement;
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");

  const firstInput = modal.querySelector("input, select, textarea, button");
  if (firstInput) firstInput.focus();
}

function closeIncidentModal() {
  const modal = document.getElementById("incidentModal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
  if (lastFocusedElement) {
    lastFocusedElement.focus();
  }
}

function setupModalKeyboardHandlers() {
  const modal = document.getElementById("incidentModal");
  if (!modal) return;

  modal.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeIncidentModal();
      return;
    }
    // Focus Trap
    if (e.key === "Tab") {
      const focusables = modal.querySelectorAll("input, select, textarea, button:not([disabled])");
      const first = focusables[0];
      const last = focusables[focusables.length - 1];

      if (e.shiftKey && document.activeElement === first) {
        last.focus();
        e.preventDefault();
      } else if (!e.shiftKey && document.activeElement === last) {
        first.focus();
        e.preventDefault();
      }
    }
  });
}

async function submitIncident() {
  const zone = document.getElementById("incZone").value;
  const type = document.getElementById("incType").value;
  const priority = document.getElementById("incPriority").value;
  const desc = document.getElementById("incDesc").value.trim() || "Crowd surge reported near turnstiles.";
  const staffToken = document.getElementById("staffTokenInput").value.trim();

  if (!staffToken) {
    showToast("Please enter your staff authentication token before dispatching.", "error");
    document.getElementById("staffTokenInput").focus();
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/api/stadium/incident`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Staff-Token": staffToken,
      },
      body: JSON.stringify({
        zone,
        incident_type: type,
        priority,
        description: desc,
        reporter_role: "venue_staff",
      }),
    });

    if (res.ok) {
      const data = await res.json();
      closeIncidentModal();
      showToast(
        `Incident ${data.incident_id} confirmed. AI recommendation generated. Assigned team: ${data.assigned_team}. ETA: ${data.estimated_response_minutes} min.`,
        "success"
      );
      return;
    }

    // Handle specific HTTP error codes
    if (res.status === 401) {
      showToast("Authentication Failed: Invalid or missing staff token.", "error");
      return;
    } else if (res.status === 403) {
      showToast("Authorization Denied: Your token does not have permission for incident dispatch.", "error");
      return;
    } else if (res.status === 422) {
      showToast("Invalid incident data: Please check all fields and try again.", "error");
      return;
    } else if (res.status === 429) {
      showToast("Too many requests. Please wait a moment before retrying.", "error");
      return;
    } else if (res.status === 503) {
      showToast("Incident dispatch is temporarily unavailable — contact stadium operations directly.", "error");
      return;
    } else {
      let detail = `Server error (HTTP ${res.status}).`;
      try {
        const errData = await res.json();
        if (errData.detail) detail = `Error: ${errData.detail}`;
      } catch (_) { /* ignore JSON parse errors */ }
      showToast(`${detail} Incident NOT dispatched. Contact operations directly.`, "error");
      return;
    }
  } catch (err) {
    console.warn("Incident submission network error:", err);
    showToast("Network error — incident NOT dispatched. Contact stadium operations directly.", "error");
  }
}

// Global hookups for HTML inline buttons
window.openIncidentModal = openIncidentModal;
window.closeIncidentModal = closeIncidentModal;
window.submitIncident = submitIncident;
window.refreshGateData = refreshGateData;
window.askSamplePrompt = askSamplePrompt;
window.submitChatQuery = submitChatQuery;
