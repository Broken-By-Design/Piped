// --- WebSocket connection ---------------------
let ws;
let loopModes = ["off", "one", "queue"];
let currentLoop = "off";
let isPaused = false;

function connectWS() {
  // Fix WebSocket protocol: uses wss:// if on https, otherwise ws://
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${protocol}//${location.host}/ws`);

  ws.onopen = () => {
    document.getElementById("status").textContent = "Connected";
    document.getElementById("status").classList.add("connected");
  };

  ws.onmessage = (event) => {
    const state = JSON.parse(event.data);
    updateUI(state);
  };

  ws.onclose = () => {
    document.getElementById("status").textContent = "Reconnecting...";
    document.getElementById("status").classList.remove("connected");
    setTimeout(connectWS, 3000);
  };

  ws.onerror = () => ws.close();
}

connectWS();

// --- Fetch initial state ----------------------
fetch("/api/state")
  .then((r) => r.json())
  .then((state) => updateUI(state))
  .catch(() => {});

// --- Update UI from state object --------------
function updateUI(state) {
  // Now playing
  const track = state.current;
  if (track) {
    document.getElementById("trackTitle").textContent = track.title;
    document.getElementById("trackArtist").textContent = track.artist;
    document.getElementById("thumbnail").src = track.thumbnail;
    document.getElementById("trackSource").textContent =
      track.source === "tidal" ? "🌊 Tidal" : "📺 YouTube";
  } else {
    document.getElementById("trackTitle").textContent = "Nothing playing";
    document.getElementById("trackArtist").textContent = "—";
    document.getElementById("thumbnail").src = "";
    document.getElementById("trackSource").textContent = "";
  }

  // Pause/resume button
  isPaused = state.is_paused;
  document.getElementById("btnPause").textContent = isPaused ? "▶" : "⏸";

  // Loop button
  currentLoop = state.loop_mode;
  const loopIcons = { off: "➡️", one: "🔂", queue: "🔁" };
  document.getElementById("btnLoop").textContent =
    loopIcons[currentLoop] || "➡️";
  document
    .getElementById("btnLoop")
    .classList.toggle("activate", currentLoop !== "off");

  // Shuffle button
  document
    .getElementById("btnShuffle")
    .classList.toggle("active", state.shuffle);

  // Volume slider
  document.getElementById("volumeSlider").value = state.volume;
  document.getElementById("volumeLable").textContent = state.volume + "%";

  // Queue
  renderQueue(state.queue || []);
}

// --- Render queue list ------------------------
function renderQueue(queue) {
  const el = document.getElementById("queueList");
  if (queue.length === 0) {
    el.innerHTML =
      '<div class="empty-msg">Queue is empty - add something!</div>';
    return;
  }
  el.innerHTML = queue
    .map(
      (t, i) => `
    <div class="queue-item">
      <span class="qi-num">${i + 1}</span>
      <img src="${t.thumbnail}" alt="">
      <div>
        <div class="qi-title">${t.title}</div>
        <div class="qi-artist">${t.artist}</div>
      </div>
    </div>
    `,
    )
    .join("");
}

// --- API helpers ------------------------------
async function api(endpoint, body = null) {
  const opts = {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  };
  if (body) opts.body = JSON.stringify(body);
  await fetch(`/api/${endpoint}`, opts);
  // State update arrives via WebSocket automatically
}

function togglePause() {
  api(isPaused ? "resume" : "pause");
}

function cycleLoop() {
  const idx = loopModes.indexOf(currentLoop);
  const next = loopModes[(idx + 1) % loopModes.length];
  api("loop", { mode: next });
}

function skipTrack() {
  api("skip");
}

function setVolume(val) {
  document.getElementById("volumeLable").textContent = val + "%";
  api("volume", { volume: parseInt(val) });
}

// --- Search form ------------------------------
document.getElementById("searchForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const query = document.getElementById("searchInput").value.trim();
  if (!query) return;
  document.getElementById("searchInput").value = "";
  await api("play", { query, requested_by: "web-user" });
});
