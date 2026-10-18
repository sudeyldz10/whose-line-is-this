const $ = (id) => document.getElementById(id);
const mic = $("mic");
const statusEl = $("status");
const heardEl = $("heard");
const errorEl = $("error");

const MAX_RECORD_MS = 10000;
const SILENCE_MS = 1400;
const SPEECH_LEVEL = 0.02;
const TARGET_RATE = 16000;

let recording = null;
let statusTimer = null;
const game = { questions: [], total: 5, win: 4, seconds: 15, i: 0, score: 0, timer: null, locked: false, run: 0 };

function show(screen) {
  document.querySelectorAll(".screen").forEach((s) => s.classList.remove("active"));
  $("screen-" + screen).classList.add("active");
  document.body.dataset.screen = screen;
}

function setStatus(text) { statusEl.textContent = text; }

function quoted(text) { return "“" + text + "”"; }

function idle() {
  stopRecording(true);
  clearInterval(statusTimer);
  clearTimeout(game.timer);
  game.run++;
  mic.className = "mic";
}

function reset() {
  idle();
  setStatus("Tap the mic");
  heardEl.textContent = "";
  errorEl.textContent = "";
  show("home");
}

function go(name, push = true) {
  if (name === "find") reset();
  else if (name === "game") startGame();
  else { idle(); show("menu"); }
  if (!push) return;
  try {
    history.pushState(null, "", name === "menu" ? location.pathname + location.search : "#" + name);
  } catch (e) {}
}

function startSearchMessages() {
  const msgs = ["Searching the web", "Comparing sources", "Verifying the character"];
  let i = 0;
  setStatus(msgs[0]);
  statusTimer = setInterval(() => { i = (i + 1) % msgs.length; setStatus(msgs[i]); }, 2400);
}

async function postJson(url, body) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    console.error(data.detail);
    throw new Error("Something went wrong. Please try again.");
  }
  return data;
}

async function getJson(url) {
  const resp = await fetch(url);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    console.error(data.detail);
    throw new Error("Something went wrong. Please try again.");
  }
  return data;
}

function showError(e) {
  clearInterval(statusTimer);
  mic.className = "mic";
  setStatus("Tap the mic");
  errorEl.textContent = e instanceof TypeError ? "Can't reach the server. Please try again." : e.message;
}

async function guess(text, searchQuery) {
  mic.className = "mic busy";
  heardEl.textContent = quoted(text);
  errorEl.textContent = "";
  startSearchMessages();
  try {
    const data = await postJson("/api/guess", { text, search_query: searchQuery || null });
    clearInterval(statusTimer);
    mic.className = "mic";
    if (data.found) showResult(data); else showNotFound();
  } catch (e) {
    showError(e);
  }
}

function confidenceLabel(c) {
  return c >= 0.8 ? "High" : c >= 0.6 ? "Medium" : "Low";
}

function plain(t) {
  return String(t || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function heardNote(d) {
  const parts = [];
  if (d.heard && plain(d.heard) !== plain(d.quote)) parts.push(`You said: ${quoted(d.heard)}`);
  if (d.official_quote === false) parts.push("Wording may differ from the original.");
  return parts.join(" ");
}

function showResult(d) {
  $("r-character").textContent = d.character;
  $("r-title").textContent = d.title + (d.year ? ` (${d.year})` : "");
  $("r-quote").textContent = quoted(d.quote);
  $("r-heard").textContent = heardNote(d);
  $("r-conf").textContent = `Confidence: ${confidenceLabel(d.confidence)} ${Math.round(d.confidence * 100)}%`;

  const img = $("r-photo");
  const kind = $("r-photo-kind");
  if (d.image) {
    img.src = d.image;
    img.alt = d.character;
    img.style.display = "block";
    kind.textContent = d.image_kind === "actor" ? `Actor: ${d.actor}` : "Poster";
    kind.style.display = "";
  } else {
    img.style.display = "none";
    kind.style.display = "none";
  }

  const src = $("r-source");
  src.textContent = d.source_title || d.source_url;
  src.href = d.source_url;
  const tm = $("r-tmdb");
  if (d.tmdb_url) { tm.href = d.tmdb_url; tm.style.display = "inline"; } else { tm.style.display = "none"; }

  $("r-disclaimer").textContent = d.confidence < 0.8
    ? "This match may be unverified. Please check the source."
    : "";
  show("result");
}

function showNotFound() {
  show("notfound");
}

function encodeWav(samples, rate) {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buf);
  const tag = (offset, text) => { for (let i = 0; i < text.length; i++) v.setUint8(offset + i, text.charCodeAt(i)); };
  tag(0, "RIFF");
  v.setUint32(4, 36 + samples.length * 2, true);
  tag(8, "WAVE");
  tag(12, "fmt ");
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true);
  v.setUint16(22, 1, true);
  v.setUint32(24, rate, true);
  v.setUint32(28, rate * 2, true);
  v.setUint16(32, 2, true);
  v.setUint16(34, 16, true);
  tag(36, "data");
  v.setUint32(40, samples.length * 2, true);
  let offset = 44;
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    offset += 2;
  }
  return new Uint8Array(buf);
}

async function toWav(blob) {
  const Ctx = window.AudioContext || window.webkitAudioContext;
  const ctx = new Ctx();
  const decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
  ctx.close();
  const offline = new OfflineAudioContext(1, Math.max(1, Math.ceil(decoded.duration * TARGET_RATE)), TARGET_RATE);
  const source = offline.createBufferSource();
  source.buffer = decoded;
  source.connect(offline.destination);
  source.start();
  const rendered = await offline.startRendering();
  return encodeWav(rendered.getChannelData(0), TARGET_RATE);
}

function toBase64(bytes) {
  let text = "";
  const step = 0x8000;
  for (let i = 0; i < bytes.length; i += step) {
    text += String.fromCharCode.apply(null, bytes.subarray(i, i + step));
  }
  return btoa(text);
}

function stopRecording(discard) {
  if (!recording) return;
  const current = recording;
  current.discard = !!discard;
  if (current.recorder.state !== "inactive") current.recorder.stop();
}

async function finishRecording(current) {
  clearInterval(current.timer);
  current.stream.getTracks().forEach((t) => t.stop());
  current.ctx.close();
  if (recording === current) recording = null;
  if (current.discard) return;

  if (!current.spoke) {
    mic.className = "mic";
    setStatus("Tap the mic");
    errorEl.textContent = "Didn't hear anything. Try again.";
    return;
  }

  mic.className = "mic busy";
  setStatus("Transcribing");
  try {
    const wav = await toWav(new Blob(current.chunks, { type: current.recorder.mimeType }));
    const heard = await postJson("/api/transcribe", { audio: toBase64(wav), mime: "audio/wav" });
    if (!heard.transcript) {
      mic.className = "mic";
      setStatus("Tap the mic");
      errorEl.textContent = "Couldn't catch that. Try again.";
      return;
    }
    await guess(heard.quote || heard.transcript, heard.search_query);
  } catch (e) {
    showError(e);
  }
}

async function listen() {
  if (!navigator.mediaDevices || !window.MediaRecorder) {
    errorEl.textContent = "This browser can't record audio. Use Chrome or type the line.";
    return;
  }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    errorEl.textContent = "Microphone permission denied. Allow it or type the line.";
    return;
  }

  const Ctx = window.AudioContext || window.webkitAudioContext;
  const ctx = new Ctx();
  if (ctx.state === "suspended") ctx.resume().catch(() => {});
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 1024;
  ctx.createMediaStreamSource(stream).connect(analyser);
  const level = new Float32Array(analyser.fftSize);

  const recorder = new MediaRecorder(stream);
  const current = { recorder, stream, ctx, chunks: [], spoke: false, discard: false, timer: null };
  recorder.ondataavailable = (e) => { if (e.data.size) current.chunks.push(e.data); };
  recorder.onstop = () => finishRecording(current);

  const startedAt = Date.now();
  let lastVoice = startedAt;
  current.timer = setInterval(() => {
    analyser.getFloatTimeDomainData(level);
    let sum = 0;
    for (let i = 0; i < level.length; i++) sum += level[i] * level[i];
    const now = Date.now();
    if (Math.sqrt(sum / level.length) > SPEECH_LEVEL) {
      current.spoke = true;
      lastVoice = now;
    }
    if ((current.spoke && now - lastVoice > SILENCE_MS) || now - startedAt > MAX_RECORD_MS) stopRecording();
  }, 100);

  recording = current;
  recorder.start();
  mic.className = "mic listening";
  setStatus("Listening");
  heardEl.textContent = "";
  errorEl.textContent = "";
}

mic.addEventListener("click", () => {
  if (mic.classList.contains("listening")) stopRecording();
  else if (!mic.classList.contains("busy")) listen();
});

$("manual").addEventListener("submit", (e) => {
  e.preventDefault();
  const v = $("manual-text").value.trim();
  if (v.length >= 3) guess(v);
});

function gameError(e) {
  $("g-error").textContent = e instanceof TypeError ? "Can't reach the server. Please try again." : e.message;
}

const SEEN_KEY = "wlit-seen2";
let seenMem = [];

function loadSeen() {
  try {
    const raw = localStorage.getItem(SEEN_KEY);
    if (raw) return JSON.parse(raw).filter(Number.isInteger);
  } catch (e) {}
  return seenMem;
}

function saveSeen(list) {
  seenMem = list;
  try {
    localStorage.setItem(SEEN_KEY, JSON.stringify(list));
  } catch (e) {}
}

async function startGame() {
  idle();
  const run = game.run;
  show("game");
  $("g-error").textContent = "";
  $("g-line").textContent = "";
  $("g-options").innerHTML = "";
  $("g-reveal").classList.remove("on");
  $("g-round").textContent = "Round 1/" + game.total;
  $("g-score").textContent = "Score 0";
  $("g-timer").style.animation = "none";
  try {
    const data = await getJson("/api/game/new?seen=" + loadSeen().join(","));
    if (run !== game.run) return;
    Object.assign(game, { questions: data.questions, total: data.total, win: data.win_score, seconds: data.seconds, i: 0, score: 0 });
    saveSeen(loadSeen().concat(data.questions.map((q) => q.id)).slice(-60));
    showQuestion();
  } catch (e) {
    if (run === game.run) gameError(e);
  }
}

function showQuestion() {
  const q = game.questions[game.i];
  game.locked = false;
  $("g-error").textContent = "";
  $("g-mystery").className = "g-mystery";
  $("g-round").textContent = `Round ${game.i + 1}/${game.total}`;
  $("g-score").textContent = `Score ${game.score}`;
  const line = $("g-line");
  line.textContent = quoted(q.line);
  line.classList.toggle("long", q.line.length > 40);
  line.style.animation = "none";
  void line.offsetWidth;
  line.style.animation = "";

  const box = $("g-options");
  box.innerHTML = "";
  q.options.forEach((name) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "opt";
    b.textContent = name;
    b.addEventListener("click", () => answer(name, b));
    box.appendChild(b);
  });
  $("g-reveal").classList.remove("on");

  const bar = $("g-timer");
  bar.style.animation = "none";
  void bar.offsetWidth;
  bar.style.animation = `drain ${game.seconds}s linear forwards`;
  clearTimeout(game.timer);
  game.timer = setTimeout(() => answer(null, null), game.seconds * 1000);
}

async function answer(choice, btn) {
  if (game.locked) return;
  game.locked = true;
  clearTimeout(game.timer);
  const run = game.run;
  $("g-timer").style.animationPlayState = "paused";
  const options = document.querySelectorAll("#g-options .opt");
  options.forEach((o) => { o.disabled = true; });
  const q = game.questions[game.i];

  let r;
  try {
    r = await postJson("/api/game/check", { id: q.id, choice });
  } catch (e) {
    if (run !== game.run) return;
    gameError(e);
    options.forEach((o) => { o.disabled = false; });
    game.locked = false;
    return;
  }
  if (run !== game.run) return;

  options.forEach((o) => {
    if (o.textContent === r.character) o.classList.add("right");
    else if (o === btn) o.classList.add("wrong");
  });
  $("g-mystery").classList.add(r.correct ? "ok" : "bad");
  if (r.correct) game.score++;
  $("g-score").textContent = `Score ${game.score}`;
  const verdict = $("g-verdict");
  verdict.textContent = r.correct ? "Correct!" : choice ? "Nope!" : "Time's up!";
  verdict.className = "g-verdict " + (r.correct ? "good" : "bad");
  $("g-answer").textContent = `${r.character} · ${r.title} (${r.year})`;
  $("g-next").textContent = game.i + 1 < game.total ? "Next" : "See result";
  $("g-reveal").classList.add("on");
}

function finishGame() {
  const won = game.score >= game.win;
  $("go-title").textContent = won ? "You win!" : "So close!";
  $("go-icon").src = won ? "img/lucky.png" : "img/mystery.png";
  $("go-score").textContent = `${game.score} / ${game.total}`;
  $("go-text").textContent = won
    ? "Show this screen at the stand and claim your prize."
    : `You need ${game.win - game.score} more to win a prize. Give it another go!`;
  show("gameover");
}

$("g-next").addEventListener("click", () => {
  game.i++;
  if (game.i < game.total) showQuestion(); else finishGame();
});
$("go-again").addEventListener("click", () => go("game", false));
$("back").addEventListener("click", () => go("menu"));
const WARP = {
  find: { icon: "img/magnifier.png", text: "Warming up the mic" },
  game: { icon: "img/lucky.png", text: "Shuffling the lines" },
};
let warping = false;

function warp(name) {
  if (warping) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { go(name); return; }
  warping = true;
  const el = $("warp");
  $("warp-icon").src = WARP[name].icon;
  $("warp-text").textContent = WARP[name].text;
  el.className = "warp on " + name;
  setTimeout(() => go(name), 450);
  setTimeout(() => el.classList.add("out"), 1100);
  setTimeout(() => { el.className = "warp"; warping = false; }, 1500);
}

["img/tunnel-pink.jpg", "img/tunnel-blue.jpg", "img/magnifier.png", "img/lucky.png", "img/mystery.png"]
  .forEach((src) => { new Image().src = src; });

document.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => warp(b.dataset.go)));

window.addEventListener("popstate", () => {
  const name = location.hash.slice(1);
  go(name === "find" || name === "game" ? name : "menu", false);
});

$("retry").addEventListener("click", reset);
$("retry2").addEventListener("click", reset);

const first = location.hash.slice(1);
go(first === "find" || first === "game" ? first : "menu", false);
