const $ = (id) => document.getElementById(id);
const player = new Audio();
player.preload = "auto";
const song = { questions: [], total: 5, win: 5, listen: 3000, think: 7, i: 0, score: 0, timer: null, clipTimer: null, locked: false, run: 0 };
let lastMode = "game";
const game = { questions: [], total: 5, win: 4, seconds: 15, i: 0, score: 0, timer: null, locked: false, run: 0 };

function show(screen) {
  document.querySelectorAll(".screen").forEach((s) => s.classList.remove("active"));
  $("screen-" + screen).classList.add("active");
  document.body.dataset.screen = screen;
}

function quoted(text) { return "“" + text + "”"; }

function idle() {
  clearTimeout(game.timer);
  clearTimeout(song.timer);
  clearTimeout(song.clipTimer);
  player.pause();
  game.run++;
  song.run++;
}

function go(name, push = true) {
  if (name === "game") startGame();
  else if (name === "song") startSong();
  else { idle(); show("menu"); }
  if (!push) return;
  try {
    history.pushState(null, "", name === "menu" ? location.pathname + location.search : "#" + name);
  } catch (e) {}
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
    const friendly = (resp.status === 503 || resp.status === 429) && typeof data.detail === "string";
    throw new Error(friendly ? data.detail : "Something went wrong. Please try again.");
  }
  return data;
}

async function getJson(url) {
  const resp = await fetch(url);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    console.error(data.detail);
    const friendly = (resp.status === 503 || resp.status === 429) && typeof data.detail === "string";
    throw new Error(friendly ? data.detail : "Something went wrong. Please try again.");
  }
  return data;
}

function gameError(e) {
  $("g-error").textContent = e instanceof TypeError ? "Can't reach the server. Please try again." : e.message;
}

function mergeSeen(list, data) {
  const ids = data.questions.map((q) => q.id);
  const base = data.reset ? [] : list;
  return Array.from(new Set(base.concat(ids))).slice(-1500);
}

const SEEN_KEY = "wlit-seen3";
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
    saveSeen(mergeSeen(loadSeen(), data));
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
  if (btn) btn.classList.add("picked");
  const q = game.questions[game.i];

  let r;
  try {
    r = await postJson("/api/game/check", { id: q.id, choice });
  } catch (e) {
    if (run !== game.run) return;
    gameError(e);
    options.forEach((o) => { o.disabled = false; o.classList.remove("picked"); });
    game.locked = false;
    return;
  }
  if (run !== game.run) return;

  options.forEach((o) => {
    o.classList.remove("picked");
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

function finishGame(state = game, mode = "game") {
  lastMode = mode;
  const won = state.score >= state.win;
  $("go-title").textContent = won ? "You win!" : "So close!";
  $("go-icon").src = won ? "img/lucky.png" : mode === "song" ? "img/cd.png" : "img/mystery.png";
  $("go-score").textContent = `${state.score} / ${state.total}`;
  $("go-text").textContent = won
    ? "Show this screen at the stand and claim your prize."
    : `You need ${state.win - state.score} more to win a prize. Give it another go!`;
  show("gameover");
}

$("g-next").addEventListener("click", () => {
  game.i++;
  if (game.i < game.total) showQuestion(); else finishGame();
});
$("go-again").addEventListener("click", () => go(lastMode, false));

const SONG_SEEN_KEY = "wlit-seen-song2";
let songSeenMem = [];

function loadSongSeen() {
  try {
    const raw = localStorage.getItem(SONG_SEEN_KEY);
    if (raw) return JSON.parse(raw).filter(Number.isInteger);
  } catch (e) {}
  return songSeenMem;
}

function saveSongSeen(list) {
  songSeenMem = list;
  try {
    localStorage.setItem(SONG_SEEN_KEY, JSON.stringify(list));
  } catch (e) {}
}

const SILENCE = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=";

function unlockAudio() {
  try {
    player.src = SILENCE;
    const p = player.play();
    if (p && p.catch) p.catch(() => {});
  } catch (e) {}
}

function songError(e) {
  $("s-error").textContent = e instanceof TypeError ? "Can't reach the server. Please try again." : e.message;
}

async function startSong() {
  idle();
  const run = song.run;
  show("song");
  $("s-error").textContent = "";
  $("s-options").innerHTML = "";
  $("s-reveal").classList.remove("on");
  $("s-round").textContent = "Round 1/" + song.total;
  $("s-score").textContent = "Score 0";
  $("s-status").textContent = "Loading";
  $("s-hear").classList.remove("on");
  $("s-eq").classList.remove("on");
  $("s-cd").className = "s-cd";
  $("s-timer").className = "held";
  try {
    const data = await getJson("/api/song/new?seen=" + loadSongSeen().join(","));
    if (run !== song.run) return;
    Object.assign(song, { questions: data.questions, total: data.total, win: data.win_score, listen: data.listen_ms, think: data.think_seconds, i: 0, score: 0 });
    saveSongSeen(mergeSeen(loadSongSeen(), data));
    preloadClip(data.questions[0] && data.questions[0].clip);
    showSong();
  } catch (e) {
    if (run === song.run) songError(e);
  }
}

function listening(on) {
  $("s-eq").classList.toggle("on", on);
  $("s-cd").classList.toggle("spinning", on);
}

function waitReady(run) {
  return new Promise((resolve, reject) => {
    if (player.readyState >= 3) { resolve(); return; }
    const done = () => { cleanup(); resolve(); };
    const fail = () => { cleanup(); reject(new Error("The clip could not be loaded. Please try again.")); };
    const cleanup = () => {
      clearTimeout(t);
      player.removeEventListener("canplay", done);
      player.removeEventListener("error", fail);
    };
    const t = setTimeout(fail, 8000);
    player.addEventListener("canplay", done);
    player.addEventListener("error", fail);
  });
}

async function playClip(q, run) {
  $("s-hear").classList.remove("on");
  $("s-status").textContent = "Loading clip";
  $("s-cd").classList.add("spinning");
  player.pause();
  player.src = q.clip;
  player.load();
  await waitReady(run);
  if (run !== song.run) return;
  $("s-cd").classList.remove("spinning");
  try { player.currentTime = q.start || 0; } catch (e) {}
  try {
    await player.play();
  } catch (e) {
    if (run !== song.run) return;
    $("s-status").textContent = "Ready?";
    $("s-hear").classList.add("on");
    return;
  }
  if (run !== song.run) return;
  $("s-status").textContent = "Listen";
  listening(true);
  song.clipTimer = setTimeout(() => {
    player.pause();
    listening(false);
    if (run === song.run) startThinking(run);
  }, song.listen);
}

function startThinking(run) {
  song.locked = false;
  $("s-status").textContent = "Your turn";
  document.querySelectorAll("#s-options .opt").forEach((o) => { o.disabled = false; });
  const bar = $("s-timer");
  bar.className = "";
  bar.style.animation = "none";
  void bar.offsetWidth;
  bar.style.animation = `drain ${song.think}s linear forwards`;
  clearTimeout(song.timer);
  song.timer = setTimeout(() => answerSong(null, null), song.think * 1000);
}

const preloader = new Audio();
preloader.preload = "auto";

function preloadClip(url) {
  if (!url) return;
  try {
    preloader.src = url;
    preloader.load();
  } catch (e) {}
}

async function showSong() {
  const q = song.questions[song.i];
  const next = song.questions[song.i + 1];
  if (next) setTimeout(() => preloadClip(next.clip), 1500);
  const run = song.run;
  song.locked = true;
  $("s-error").textContent = "";
  $("s-cd").className = "s-cd";
  $("s-round").textContent = `Round ${song.i + 1}/${song.total}`;
  $("s-score").textContent = `Score ${song.score}`;
  $("s-reveal").classList.remove("on");
  const bar = $("s-timer");
  bar.style.animation = "none";
  bar.className = "held";

  const box = $("s-options");
  box.innerHTML = "";
  q.options.forEach((name) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "opt";
    b.textContent = name;
    b.disabled = true;
    b.addEventListener("click", () => answerSong(name, b));
    box.appendChild(b);
  });

  try {
    await playClip(q, run);
  } catch (e) {
    if (run === song.run) songError(e);
  }
}

$("s-hear").addEventListener("click", async () => {
  const q = song.questions[song.i];
  const run = song.run;
  try {
    await player.play();
  } catch (e) { return; }
  if (run !== song.run) return;
  $("s-hear").classList.remove("on");
  $("s-status").textContent = "Listen";
  listening(true);
  clearTimeout(song.clipTimer);
  song.clipTimer = setTimeout(() => {
    player.pause();
    listening(false);
    if (run === song.run) startThinking(run);
  }, song.listen);
});

async function answerSong(choice, btn) {
  if (song.locked) return;
  song.locked = true;
  clearTimeout(song.timer);
  const run = song.run;
  $("s-timer").style.animationPlayState = "paused";
  const options = document.querySelectorAll("#s-options .opt");
  options.forEach((o) => { o.disabled = true; });
  if (btn) btn.classList.add("picked");
  const q = song.questions[song.i];

  let r;
  try {
    r = await postJson("/api/song/check", { id: q.id, choice });
  } catch (e) {
    if (run !== song.run) return;
    songError(e);
    options.forEach((o) => { o.disabled = false; o.classList.remove("picked"); });
    song.locked = false;
    return;
  }
  if (run !== song.run) return;

  options.forEach((o) => {
    o.classList.remove("picked");
    if (o.textContent === r.answer) o.classList.add("right");
    else if (o === btn) o.classList.add("wrong");
  });
  $("s-status").textContent = r.correct ? "Nice" : "Missed";
  $("s-cd").classList.add(r.correct ? "ok" : "bad");
  if (r.correct) song.score++;
  $("s-score").textContent = `Score ${song.score}`;
  const verdict = $("s-verdict");
  verdict.textContent = r.correct ? "Correct!" : choice ? "Nope!" : "Time's up!";
  verdict.className = "g-verdict " + (r.correct ? "good" : "bad");
  $("s-answer").textContent = r.answer;
  $("s-next").textContent = song.i + 1 < song.total ? "Next" : "See result";
  $("s-reveal").classList.add("on");
}

$("s-next").addEventListener("click", () => {
  song.i++;
  if (song.i < song.total) showSong(); else finishGame(song, "song");
});
$("back").addEventListener("click", () => go("menu"));
const WARP = {
  game: { icon: "img/lucky.png", text: "Shuffling the lines" },
  song: { icon: "img/note.png", text: "Tuning the radio" },
};
let warping = false;

function warp(name) {
  if (warping) return;
  if (name === "song") unlockAudio();
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

["img/tunnel-pink.jpg", "img/tunnel-blue.jpg", "img/tunnel-green.jpg", "img/lucky.png", "img/mystery.png", "img/note.png", "img/cd.png"]
  .forEach((src) => { new Image().src = src; });

document.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => warp(b.dataset.go)));

window.addEventListener("popstate", () => {
  const name = location.hash.slice(1);
  go(name === "game" || name === "song" ? name : "menu", false);
});

fetch("/api/song/ready")
  .then((r) => r.json())
  .then((d) => { if (!d || !d.ready) $("card-song").hidden = true; })
  .catch(() => {});

const first = location.hash.slice(1);
go(first === "game" || first === "song" ? first : "menu", false);
