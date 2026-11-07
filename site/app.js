/* unrecommended: browse and play videos from videos.json.
 *
 * Plain browser JavaScript, no build step. Pages are hash routes:
 *   #/               everything          #/g/<group>     one group
 *   #/c/<channelId>  one channel         #/later         watch later
 *   #/history        watched             #/about         about + your data
 *   #/v/<videoId>?from=<list route>      watch, "next" comes from that list
 * List routes take ?q=<search> and ?sort=old.
 */
"use strict";

(() => {
  const PAGE = 48;
  const VIDEO_ID = /^[0-9A-Za-z_-]{11}$/;
  const main = document.getElementById("main");
  const shelf = document.getElementById("shelf");
  const searchInput = document.getElementById("q");

  let site = { title: "unrecommended", description: "", kid_safe: false };
  let videos = [];
  const byId = new Map();
  let channels = {};
  let groups = [];

  // ------------------------------------------------------------ storage
  // One GitHub user's Pages sites share an origin, so key by path.
  const STORE_KEY = "unrecommended:" + location.pathname.replace(/[^/]*$/, "");
  const store = loadStore();

  function emptyStore() {
    return { watched: {}, later: [], progress: {}, prefs: {} };
  }

  function loadStore() {
    try {
      const s = JSON.parse(localStorage.getItem(STORE_KEY)) || {};
      return {
        watched: s.watched && typeof s.watched === "object" ? s.watched : {},
        later: Array.isArray(s.later) ? s.later.filter((id) => VIDEO_ID.test(id)) : [],
        progress: s.progress && typeof s.progress === "object" ? s.progress : {},
        prefs: s.prefs && typeof s.prefs === "object" ? s.prefs : {},
      };
    } catch {
      return emptyStore();
    }
  }

  function saveStore() {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(store));
    } catch {
      /* private mode or full: keep going without saving */
    }
  }

  function markWatched(id) {
    if (!store.watched[id]) store.watched[id] = Date.now();
    delete store.progress[id];
    saveStore();
  }

  function toggleLater(id) {
    const i = store.later.indexOf(id);
    if (i >= 0) store.later.splice(i, 1);
    else store.later.push(id);
    saveStore();
    return i < 0;
  }

  // ------------------------------------------------------------ helpers
  const esc = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  function ago(date) {
    if (!date) return "";
    const days = Math.round((Date.now() - Date.parse(date + "T12:00:00Z")) / 864e5);
    if (days < 1) return rtf.format(0, "day");
    if (days < 7) return rtf.format(-days, "day");
    if (days < 31) return rtf.format(-Math.round(days / 7), "week");
    if (days < 365) return rtf.format(-Math.round(days / 30.4), "month");
    return rtf.format(-Math.round(days / 365.25), "year");
  }

  function clock(sec) {
    sec = Math.max(0, Math.floor(sec || 0));
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = String(sec % 60).padStart(2, "0");
    return h ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
  }

  const channelName = (cid) => (channels[cid] && channels[cid].name) || "Unknown channel";
  const youtubeUrl = (id) => `https://www.youtube.com/watch?v=${id}`;

  const ICONS = {
    later: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M6 3h12v18l-6-4.5L6 21z"/></svg>',
    laterOn: '<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M6 3h12v18l-6-4.5L6 21z"/></svg>',
    play: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 4.5v15l13-7.5z"/></svg>',
    pause: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 4h4.5v16H6zM13.5 4H18v16h-4.5z"/></svg>',
    next: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M5 4.5v15l10-7.5zM16.5 4.5H19v15h-2.5z"/></svg>',
    prev: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 4.5v15L9 12zM5 4.5h2.5v15H5z"/></svg>',
    sound: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 9h4l5-4v14l-5-4H4z" fill="currentColor"/><path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12"/></svg>',
    mute: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 9h4l5-4v14l-5-4H4z" fill="currentColor"/><path d="M17 9.5l5 5M22 9.5l-5 5"/></svg>',
    full: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5"/></svg>',
    close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  };

  // ------------------------------------------------------------ routing
  function parseHash(hash) {
    const h = (hash || "#/").replace(/^#/, "") || "/";
    const [path, qs] = h.split("?");
    const parts = path.split("/").filter(Boolean).map((p) => {
      try {
        return decodeURIComponent(p);
      } catch {
        return p;
      }
    });
    return { parts, params: new URLSearchParams(qs || "") };
  }

  function makeHash(parts, params) {
    const path = "#/" + parts.map(encodeURIComponent).join("/");
    const qs = params && params.toString();
    return qs ? `${path}?${qs}` : path;
  }

  const watchHash = (id, from) => makeHash(["v", id], new URLSearchParams({ from }));

  // ------------------------------------------------------------ lists
  /** The videos a list route shows, before "hide watched" is applied. */
  function listFor(parts, params) {
    let list = videos;
    let title = "Everything";
    let kind = "all";
    const [what, arg] = parts;
    if (what === "g") {
      const g = groups.find((x) => x.name === arg);
      if (!g) return { list: [], title: "No such group", kind: "missing" };
      const set = new Set(g.channels);
      list = videos.filter((v) => set.has(v.channel));
      title = g.name;
      kind = "group";
    } else if (what === "c") {
      list = videos.filter((v) => v.channel === arg);
      title = channels[arg] ? channels[arg].name : "No such channel";
      kind = channels[arg] ? "channel" : "missing";
    } else if (what === "later") {
      list = store.later.map((id) => byId.get(id)).filter(Boolean);
      title = "Watch later";
      kind = "later";
    } else if (what === "history") {
      list = Object.entries(store.watched)
        .sort((a, b) => b[1] - a[1])
        .map(([id]) => byId.get(id))
        .filter(Boolean);
      title = "Watched";
      kind = "history";
    }
    const q = (params.get("q") || "").trim().toLowerCase();
    if (q) {
      const words = q.split(/\s+/);
      list = list.filter((v) => {
        const text = (v.title + " " + channelName(v.channel)).toLowerCase();
        return words.every((w) => text.includes(w));
      });
    }
    if (params.get("sort") === "old" && (kind === "all" || kind === "group" || kind === "channel")) {
      list = list.slice().reverse();
    }
    return { list, title, kind, q };
  }

  // ------------------------------------------------------------ shelf
  function renderShelf(parts) {
    const here = parts.length ? parts.join("/") : "";
    const chip = (href, label, key, count) =>
      `<a class="chip" href="${href}"${key === here ? ' aria-current="page"' : ""}>${esc(label)}${
        count != null ? ` <span class="count">${count}</span>` : ""
      }</a>`;
    shelf.innerHTML = [
      chip("#/", "Everything", ""),
      ...groups.map((g) => chip(makeHash(["g", g.name]), g.name, "g/" + g.name)),
      '<span class="spacer"></span>',
      chip("#/later", "Watch later", "later", store.later.filter((id) => byId.has(id)).length),
      chip("#/history", "Watched", "history"),
    ].join("");
  }

  // ------------------------------------------------------------ list page
  const listMemory = new Map(); // hash -> { shown, scroll }

  function laterButton(id) {
    const on = store.later.includes(id);
    return `<button type="button" class="icon-btn" data-later="${id}" aria-pressed="${on}" title="${
      on ? "Remove from Watch later" : "Watch later"
    }" aria-label="Watch later">${on ? ICONS.laterOn : ICONS.later}</button>`;
  }

  function thumb(v) {
    const p = store.progress[v.id];
    const pct = p && p[1] ? Math.min(100, (100 * p[0]) / p[1]) : 0;
    return `<div class="thumb"><img loading="lazy" alt="" src="https://i.ytimg.com/vi/${v.id}/mqdefault.jpg">${
      v.seconds ? `<span class="len">${clock(v.seconds)}</span>` : ""
    }${pct ? `<span class="bar" style="width:${pct.toFixed(1)}%"></span>` : ""}</div>`;
  }

  function card(v, from) {
    return `<li class="card${store.watched[v.id] ? " watched" : ""}">
      <a class="play" href="${esc(watchHash(v.id, from))}">${thumb(v)}<span class="title">${esc(v.title)}</span></a>
      <div class="meta"><a href="${makeHash(["c", v.channel])}">${esc(channelName(v.channel))}</a> · <time datetime="${esc(
        v.date || "",
      )}" title="${esc(v.date || "")}">${ago(v.date)}</time></div>
      ${laterButton(v.id)}
    </li>`;
  }

  function renderList(parts, params) {
    const hash = makeHash(parts, params);
    const { list, title, kind, q } = listFor(parts, params);
    const hide = !!store.prefs.hideWatched && kind !== "history";
    const shown = hide ? list.filter((v) => !store.watched[v.id]) : list;
    document.title = parts.length ? `${title} · ${site.title}` : site.title;
    searchInput.value = params.get("q") || "";

    const sortable = kind === "all" || kind === "group" || kind === "channel";
    const old = params.get("sort") === "old";
    const sortParams = new URLSearchParams(params);
    if (old) sortParams.delete("sort");
    else sortParams.set("sort", "old");

    let channelRow = "";
    if (kind === "group") {
      const g = groups.find((x) => x.name === parts[1]);
      channelRow = `<div class="channels">${g.channels
        .map((cid) => `<a class="chip" href="${makeHash(["c", cid])}">${esc(channelName(cid))}</a>`)
        .join("")}</div>`;
    } else if (kind === "channel" && channels[parts[1]] && channels[parts[1]].url) {
      channelRow = `<div class="channels external"><a class="chip" href="${esc(
        channels[parts[1]].url,
      )}" rel="noopener">This channel on YouTube ↗</a></div>`;
    }

    const count = `${shown.length} video${shown.length === 1 ? "" : "s"}${
      hide && shown.length !== list.length ? ` (${list.length - shown.length} watched hidden)` : ""
    }${q ? ` matching “${esc(q)}”` : ""}`;

    main.innerHTML = `
      <div class="list-head">
        <div><h1>${esc(title)}</h1><div class="sub">${count}</div></div>
        <div class="list-tools">
          ${sortable ? `<a class="chip" href="${esc(makeHash(parts, sortParams))}">${old ? "Oldest first" : "Newest first"} ⇅</a>` : ""}
          ${kind !== "history" ? `<button type="button" class="chip" id="hide-watched" aria-pressed="${hide}">Hide watched</button>` : ""}
        </div>
      </div>
      ${channelRow}
      ${shown.length ? '<ul class="grid" id="grid"></ul><div class="more" id="more"></div>' : emptyMessage(kind, q)}`;

    const grid = document.getElementById("grid");
    if (!grid) return;
    const memory = listMemory.get(hash);
    let count_ = 0;
    const more = document.getElementById("more");
    const showMore = (n) => {
      const next = shown.slice(count_, count_ + n);
      grid.insertAdjacentHTML("beforeend", next.map((v) => card(v, hash)).join(""));
      count_ += next.length;
      more.innerHTML = count_ < shown.length ? '<button type="button" class="button" id="more-btn">Show more</button>' : "";
      listMemory.set(hash, { shown: count_, scroll: window.scrollY });
    };
    showMore(memory ? Math.max(memory.shown, PAGE) : PAGE);
    more.addEventListener("click", (e) => {
      if (e.target.id === "more-btn") showMore(PAGE);
    });
    if ("IntersectionObserver" in window) {
      const io = new IntersectionObserver((entries) => {
        if (entries.some((en) => en.isIntersecting) && count_ < shown.length) showMore(PAGE);
      }, { rootMargin: "800px" });
      io.observe(more);
      cleanup = () => io.disconnect();
    }
    if (memory) requestAnimationFrame(() => window.scrollTo(0, memory.scroll));
  }

  function emptyMessage(kind, q) {
    if (q) return `<p class="empty">Nothing here matches “${esc(q)}”.</p>`;
    if (kind === "later") return '<p class="empty">Nothing saved yet. Use the bookmark under a video to watch it later.</p>';
    if (kind === "history") return '<p class="empty">Videos you watch will be listed here.</p>';
    if (kind === "missing") return '<p class="empty">That page is not in this list anymore. <a href="#/">See everything</a>.</p>';
    if (store.prefs.hideWatched) return '<p class="empty">You have watched everything here.</p>';
    return '<p class="empty">No videos yet.</p>';
  }

  // ------------------------------------------------------------ YouTube player
  let ytReady = null;
  function loadYouTubeApi() {
    if (!ytReady) {
      ytReady = new Promise((resolve, reject) => {
        if (window.YT && window.YT.Player) return resolve(window.YT);
        const prev = window.onYouTubeIframeAPIReady;
        window.onYouTubeIframeAPIReady = () => {
          if (prev) prev();
          resolve(window.YT);
        };
        const s = document.createElement("script");
        s.src = "https://www.youtube.com/iframe_api";
        s.onerror = () => {
          ytReady = null;
          reject(new Error("Could not load YouTube's player. Check the internet connection."));
        };
        document.head.appendChild(s);
      });
    }
    return ytReady;
  }

  /** Everything about the watch page that outlives one video. */
  const W = {
    player: null,
    mode: null, // "normal" or "tv"
    video: null,
    from: "#/",
    queue: [],
    queueLabel: "",
    stage: null,
    timer: null,
    idleTimer: null,
    errorTimer: null,
    seconds: 0,
  };

  function playerVars(start) {
    const common = { autoplay: 1, rel: 0, playsinline: 1, iv_load_policy: 3, start: Math.floor(start || 0), origin: location.origin };
    return W.mode === "tv" ? { ...common, controls: 0, disablekb: 1, fs: 0 } : { ...common, controls: 1, fs: 1 };
  }

  function resumeAt(v) {
    const p = store.progress[v.id];
    return p && p[0] > 15 && (!p[1] || p[0] < p[1] - 20) ? p[0] : 0;
  }

  async function createPlayer(v, start) {
    destroyPlayer();
    const el = document.createElement("div");
    el.className = "player";
    W.stage.prepend(el);
    let YT;
    try {
      YT = await loadYouTubeApi();
    } catch (err) {
      showStageMessage(`<p>${esc(err.message)}</p>`);
      return;
    }
    if (!el.isConnected) return; // left the page while loading
    W.player = new YT.Player(el, {
      host: "https://www.youtube-nocookie.com",
      videoId: v.id,
      playerVars: playerVars(start),
      events: {
        onReady: (e) => {
          applyMute();
          e.target.playVideo();
        },
        onStateChange: onStateChange,
        onError: onPlayerError,
      },
    });
  }

  function destroyPlayer() {
    clearInterval(W.timer);
    clearTimeout(W.errorTimer);
    W.timer = null;
    if (W.player) {
      try {
        W.player.destroy();
      } catch {
        /* already gone */
      }
    }
    W.player = null;
    if (W.stage) W.stage.querySelectorAll(".player, iframe").forEach((n) => n.remove());
  }

  function onStateChange(e) {
    const S = window.YT.PlayerState;
    const playing = e.data === S.PLAYING || e.data === S.BUFFERING;
    W.stage.classList.toggle("paused", !playing);
    updatePlayButton(playing);
    if (e.data === S.PLAYING) {
      clearStageMessage();
      if (!W.timer) W.timer = setInterval(tick, 1000);
    } else {
      clearInterval(W.timer);
      W.timer = null;
      saveProgress();
    }
    if (e.data === S.ENDED) {
      markWatched(W.video.id);
      if (parseHash(W.from).parts[0] === "later") {
        const i = store.later.indexOf(W.video.id);
        if (i >= 0) store.later.splice(i, 1);
        saveStore();
      }
      // Moving on right away is what keeps YouTube's end-screen
      // suggestions from ever showing.
      goNext(true);
    }
  }

  function onPlayerError(e) {
    const why = {
      2: "The link to this video looks wrong.",
      5: "This browser can't play this video.",
      100: "This video was removed or made private.",
      101: "The channel doesn't allow playing this video on other sites.",
      150: "The channel doesn't allow playing this video on other sites.",
      153: "YouTube refused to play this video here.",
    }[e.data] || "YouTube can't play this video here.";
    const next = nextVideo();
    const tv = W.mode === "tv";
    showStageMessage(
      `<p>${esc(why)}</p><div class="row">${
        next ? `<button type="button" class="button" data-act="next">Next video</button>` : ""
      }${!site.kid_safe ? `<a class="button external" href="${youtubeUrl(W.video.id)}" rel="noopener" target="_blank">Try it on YouTube ↗</a>` : ""}</div>${
        next && tv ? '<p class="notice">Skipping in a few seconds…</p>' : ""
      }`,
    );
    if (next && tv) W.errorTimer = setTimeout(() => goNext(true), 4000);
  }

  function showStageMessage(html) {
    clearStageMessage();
    W.stage.insertAdjacentHTML("beforeend", `<div class="stage-msg" role="alert">${html}</div>`);
  }

  function clearStageMessage() {
    if (W.stage) W.stage.querySelectorAll(".stage-msg").forEach((n) => n.remove());
  }

  function current() {
    if (!W.player || typeof W.player.getCurrentTime !== "function") return null;
    return { t: W.player.getCurrentTime() || 0, d: W.player.getDuration() || 0 };
  }

  function saveProgress() {
    const c = current();
    if (!c || !W.video || c.t < 5) return;
    if (c.d && c.t / c.d > 0.9) {
      markWatched(W.video.id);
    } else {
      store.progress[W.video.id] = [Math.floor(c.t), Math.floor(c.d)];
      saveStore();
    }
  }

  function tick() {
    const c = current();
    if (!c) return;
    W.seconds += 1;
    if (W.seconds % 5 === 0) saveProgress();
    const bar = W.stage.querySelector(".tvbar");
    if (bar) {
      bar.querySelector(".fill").style.width = c.d ? `${((100 * c.t) / c.d).toFixed(2)}%` : "0";
      bar.querySelector(".time").textContent = `${clock(c.t)} / ${clock(c.d)}`;
    }
  }

  function nextVideo(step = 1) {
    const q = W.queue;
    const i = q.findIndex((v) => v.id === W.video.id);
    if (i < 0) return null;
    if (step < 0) return q[i - 1] || null;
    // Prefer the next one not watched yet; otherwise simply the next one.
    for (let j = i + 1; j < q.length; j++) if (!store.watched[q[j].id]) return q[j];
    return q[i + 1] || null;
  }

  function goNext(auto) {
    clearTimeout(W.errorTimer);
    const v = nextVideo(1);
    if (v) {
      location.replace(watchHash(v.id, W.from));
    } else if (auto) {
      showStageMessage(
        `<p>That was the last video in this list.</p><div class="row"><a class="button" href="${esc(W.from)}" data-act="back">Back to the list</a></div>`,
      );
    }
  }

  function goPrev() {
    const v = nextVideo(-1);
    if (v) location.replace(watchHash(v.id, W.from));
  }

  function togglePlay() {
    if (!W.player || typeof W.player.getPlayerState !== "function") return;
    const S = window.YT.PlayerState;
    if (W.player.getPlayerState() === S.PLAYING) W.player.pauseVideo();
    else W.player.playVideo();
  }

  function seekBy(sec) {
    const c = current();
    if (c) W.player.seekTo(Math.max(0, c.t + sec), true);
  }

  function applyMute() {
    if (!W.player || typeof W.player.mute !== "function") return;
    if (store.prefs.muted) W.player.mute();
    else W.player.unMute();
    const b = W.stage && W.stage.querySelector('[data-act="mute"]');
    if (b) b.innerHTML = store.prefs.muted ? ICONS.mute : ICONS.sound;
  }

  function updatePlayButton(playing) {
    const b = W.stage && W.stage.querySelector('[data-act="play"]');
    if (b) {
      b.innerHTML = playing ? ICONS.pause : ICONS.play;
      b.setAttribute("aria-label", playing ? "Pause" : "Play");
    }
  }

  // TV mode: the player is covered so no click reaches YouTube's own
  // buttons, links or end-screen cards; our bar below does the controlling.
  function tvChrome() {
    return `<div class="tvcover" data-act="cover"><span class="bigplay">${ICONS.play}</span></div>
      <div class="tvbar">
        <div class="tvtitle"></div>
        <div class="seek" data-act="seek"><div class="track"><div class="fill"></div></div></div>
        <div class="row">
          <button type="button" class="icon-btn" data-act="prev" aria-label="Previous video">${ICONS.prev}</button>
          <button type="button" class="icon-btn" data-act="play" aria-label="Play">${ICONS.play}</button>
          <button type="button" class="icon-btn" data-act="next" aria-label="Next video">${ICONS.next}</button>
          <span class="time">0:00 / 0:00</span>
          <span class="grow"></span>
          <button type="button" class="icon-btn" data-act="mute" aria-label="Sound on or off">${store.prefs.muted ? ICONS.mute : ICONS.sound}</button>
          <button type="button" class="icon-btn" data-act="fullscreen" aria-label="Full screen">${ICONS.full}</button>
          <button type="button" class="icon-btn" data-act="exit" aria-label="${site.kid_safe ? "Back to the list" : "Leave TV mode"}">${ICONS.close}</button>
        </div>
      </div>`;
  }

  function setMode(mode, v) {
    const c = current();
    const start = c && W.video && W.video.id === v.id ? c.t : resumeAt(v);
    W.mode = mode;
    W.stage.querySelectorAll(".tvcover, .tvbar").forEach((n) => n.remove());
    W.stage.classList.toggle("tv", mode === "tv");
    if (mode === "tv") {
      W.stage.insertAdjacentHTML("beforeend", tvChrome());
      W.stage.querySelector(".tvtitle").textContent = v.title;
      W.stage.classList.add("paused");
      wakeControls();
      if (document.fullscreenEnabled && !document.fullscreenElement) {
        W.stage.requestFullscreen().catch(() => {});
      }
    } else if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    }
    createPlayer(v, start);
  }

  function wakeControls() {
    if (!W.stage) return;
    W.stage.classList.remove("idle");
    clearTimeout(W.idleTimer);
    W.idleTimer = setTimeout(() => W.stage && W.stage.classList.add("idle"), 2500);
  }

  function seekToPointer(e) {
    const c = current();
    const track = W.stage.querySelector(".seek .track");
    if (!c || !c.d || !track) return;
    const r = track.getBoundingClientRect();
    const f = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    W.player.seekTo(f * c.d, true);
  }

  function onStageClick(e) {
    const el = e.target.closest("[data-act]");
    // A tap while the controls are hidden only brings them back (on a
    // phone, that's how you reach them), instead of pausing as well.
    const hidden = W.stage.classList.contains("idle") && !W.stage.classList.contains("paused");
    wakeControls();
    if (!el) return;
    const act = el.dataset.act;
    if (act === "cover" && hidden) return;
    if (act === "cover") togglePlay();
    else if (act === "play") togglePlay();
    else if (act === "next") goNext(false);
    else if (act === "prev") goPrev();
    else if (act === "seek") seekToPointer(e);
    else if (act === "mute") {
      store.prefs.muted = !store.prefs.muted;
      saveStore();
      applyMute();
    } else if (act === "fullscreen") {
      if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
      else if (document.fullscreenEnabled) W.stage.requestFullscreen().catch(() => {});
    } else if (act === "exit") {
      if (site.kid_safe) location.hash = W.from;
      else setMode("normal", W.video);
    }
  }

  // ------------------------------------------------------------ watch page
  const LIST_ROUTES = new Set([undefined, "g", "c", "later", "history"]);

  function queueFor(from, v) {
    // `from` comes from the URL: accept only list routes, and rebuild it so
    // links made from it are always internal "#/..." routes.
    const r = parseHash(from);
    if (LIST_ROUTES.has(r.parts[0])) {
      const { list, title } = listFor(r.parts, r.params);
      if (list.some((x) => x.id === v.id)) return { list, label: title, from: makeHash(r.parts, r.params) };
    }
    // Opened from elsewhere (a shared link): continue with its channel.
    return {
      list: videos.filter((x) => x.channel === v.channel),
      label: channelName(v.channel),
      from: makeHash(["c", v.channel]),
    };
  }

  function renderWatch(id, params) {
    const v = VIDEO_ID.test(id) && byId.get(id);
    if (!v) {
      leaveWatch();
      main.innerHTML = '<p class="empty">This video is not in this list. <a href="#/">See everything</a>.</p>';
      return;
    }
    const sameStage = W.stage && W.stage.isConnected;
    const q = queueFor(params.get("from") || "#/", v);
    W.from = q.from;
    W.queue = q.list;
    W.queueLabel = q.label;
    document.title = `${v.title} · ${site.title}`;

    if (!sameStage) {
      main.innerHTML = `<div class="watch">
          <div>
            <div class="stage" id="stage"></div>
            <h1 id="w-title"></h1>
            <p class="meta" id="w-meta"></p>
            <div class="actions" id="w-actions"></div>
          </div>
          <aside class="queue" id="w-queue"></aside>
        </div>`;
      W.stage = document.getElementById("stage");
      W.stage.addEventListener("click", onStageClick);
      W.stage.addEventListener("pointermove", wakeControls);
      W.stage.addEventListener("touchstart", wakeControls, { passive: true });
    }

    const previous = W.video;
    W.video = v;
    W.seconds = 0;
    clearStageMessage();
    renderWatchInfo(v);

    if (!sameStage || !W.player) {
      W.mode = null;
      setMode(site.kid_safe || store.prefs.tv ? "tv" : "normal", v);
    } else if (!previous || previous.id !== v.id) {
      // Same player, new video: keeps full screen and TV mode as they are.
      const t = W.stage.querySelector(".tvtitle");
      if (t) {
        t.textContent = v.title;
        W.stage.querySelector(".seek .fill").style.width = "0";
        W.stage.querySelector(".tvbar .time").textContent = "0:00";
      }
      W.player.loadVideoById({ videoId: v.id, startSeconds: resumeAt(v) });
    }
    window.scrollTo(0, 0);
  }

  function renderWatchInfo(v) {
    document.getElementById("w-title").textContent = v.title;
    document.getElementById("w-meta").innerHTML = `<a href="${makeHash(["c", v.channel])}">${esc(
      channelName(v.channel),
    )}</a> · <time datetime="${esc(v.date || "")}" title="${esc(v.date || "")}">${ago(v.date)}</time>${
      v.seconds ? ` · ${clock(v.seconds)}` : ""
    }`;
    const on = store.later.includes(v.id);
    document.getElementById("w-actions").innerHTML = `
      <button type="button" class="button primary" id="w-tv">TV mode</button>
      <button type="button" class="button" id="w-next">Next video</button>
      <button type="button" class="button" data-later="${v.id}" aria-pressed="${on}">${on ? "Saved for later ✓" : "Watch later"}</button>
      <a class="button external" href="${youtubeUrl(v.id)}" rel="noopener" target="_blank">Open on YouTube ↗</a>`;

    const i = W.queue.findIndex((x) => x.id === v.id);
    const upcoming = W.queue.slice(i + 1, i + 13);
    const label = W.queueLabel;
    document.getElementById("w-queue").innerHTML = upcoming.length
      ? `<h2>Next in ${esc(label)}</h2><ol>${upcoming
          .map(
            (x) => `<li class="${store.watched[x.id] ? "watched" : ""}"><a href="${esc(watchHash(x.id, W.from))}">${thumb(x)}<span><span class="title">${esc(
              x.title,
            )}</span><br><span class="meta">${esc(channelName(x.channel))} · ${ago(x.date)}</span></span></a></li>`,
          )
          .join("")}</ol><p><a href="${esc(W.from)}">Back to ${esc(label)}</a></p>`
      : `<h2>End of ${esc(label)}</h2><p><a href="${esc(W.from)}">Back to the list</a></p>`;
  }

  function leaveWatch() {
    if (!W.stage) return;
    saveProgress();
    destroyPlayer();
    clearTimeout(W.idleTimer);
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    W.stage = null;
    W.video = null;
    W.mode = null;
  }

  // ------------------------------------------------------------ look
  const IMAGE = /^([A-Za-z0-9][A-Za-z0-9._-]*\.(svg|png|jpe?g|gif|webp|ico)|https:\/\/[^\s"'<>]+)$/i;

  /** Logo, favicon and accent colour from the `site:` settings. */
  function applyLook() {
    const logo = document.getElementById("site-logo");
    if (site.logo === undefined) site.logo = "logo.svg";
    if (site.logo && IMAGE.test(site.logo)) {
      logo.src = site.logo;
      logo.hidden = false;
    }
    if (site.favicon && IMAGE.test(site.favicon) && site.favicon !== "favicon.svg") {
      document.getElementById("favicon").href = site.favicon;
      document.getElementById("touch-icon").href = site.favicon;
    }
    if (/^#[0-9a-f]{6}$/i.test(site.accent || "")) {
      document.documentElement.style.setProperty("--accent", site.accent);
      document.querySelector('meta[name="theme-color"]').content = site.accent;
    }
  }

  /** The owner's own text: paragraphs, with web addresses made clickable
   * (left as plain text on kid-safe sites, which link nowhere). */
  function aboutHtml(text) {
    return text
      .split(/\n\s*\n/)
      .map((para) => {
        // Single line breaks are just where the text wrapped in the editor.
        let html = esc(para.trim().replace(/\s*\n\s*/g, " "));
        if (!site.kid_safe) {
          html = html.replace(/https?:\/\/[^\s<]+?(?=[.,;:!?)]*(\s|$))/g, (url) => `<a href="${url}" rel="noopener">${url}</a>`);
        }
        return `<p>${html}</p>`;
      })
      .join("");
  }

  // ------------------------------------------------------------ about page
  function renderAbout() {
    document.title = `About · ${site.title}`;
    main.innerHTML = "";
    main.appendChild(document.getElementById("tpl-about").content.cloneNode(true));
    if (site.about) {
      document.getElementById("owner-about").hidden = false;
      document.getElementById("owner-title").textContent = `About ${site.title}`;
      document.getElementById("owner-text").innerHTML = aboutHtml(site.about);
    } else {
      document.getElementById("site-about-title").textContent = "About this site";
    }
    const msg = document.getElementById("data-msg");
    document.getElementById("export").addEventListener("click", () => {
      const blob = new Blob([JSON.stringify({ unrecommended: 1, ...store }, null, 1)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${site.title.replace(/[^\w-]+/g, "-")}-my-data.json`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    });
    document.getElementById("import").addEventListener("change", async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      try {
        const data = JSON.parse(await file.text());
        if (!data || data.unrecommended !== 1) throw new Error("not a file saved from this page");
        for (const [id, when] of Object.entries(data.watched || {})) {
          if (VIDEO_ID.test(id) && Number.isFinite(when)) store.watched[id] = when;
        }
        for (const id of Array.isArray(data.later) ? data.later : []) {
          if (VIDEO_ID.test(id) && !store.later.includes(id)) store.later.push(id);
        }
        for (const [id, p] of Object.entries(data.progress || {})) {
          if (VIDEO_ID.test(id) && Array.isArray(p) && p.length === 2 && p.every(Number.isFinite)) store.progress[id] = p;
        }
        saveStore();
        msg.textContent = "Loaded. Your lists here now include what was in the file.";
      } catch (err) {
        msg.textContent = `Could not load that file (${err.message}).`;
      }
      e.target.value = "";
    });
    document.getElementById("forget").addEventListener("click", () => {
      if (!confirm("Forget what you watched, your Watch later list and where you stopped?")) return;
      Object.assign(store, emptyStore());
      saveStore();
      msg.textContent = "Done. This browser no longer remembers anything about what you watched.";
    });
  }

  // ------------------------------------------------------------ app
  let cleanup = null;

  function route() {
    if (cleanup) cleanup();
    cleanup = null;
    const { parts, params } = parseHash(location.hash);
    renderShelf(parts[0] === "v" ? parseHash(params.get("from") || "#/").parts : parts);
    if (parts[0] === "v") {
      renderWatch(parts[1], params);
      return;
    }
    leaveWatch();
    if (parts[0] === "about") renderAbout();
    else renderList(parts, params);
    main.focus({ preventScroll: true });
  }

  // Remember how far down each list was scrolled.
  window.addEventListener("scroll", () => {
    const m = listMemory.get(location.hash || "#/");
    if (m) m.scroll = window.scrollY;
  }, { passive: true });

  // Watch-later buttons, anywhere.
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-later]");
    if (b) {
      const on = toggleLater(b.dataset.later);
      b.setAttribute("aria-pressed", String(on));
      if (b.classList.contains("icon-btn")) {
        b.innerHTML = on ? ICONS.laterOn : ICONS.later;
        b.title = on ? "Remove from Watch later" : "Watch later";
      } else {
        b.textContent = on ? "Saved for later ✓" : "Watch later";
      }
      renderShelf(parseHash(location.hash).parts);
      return;
    }
    if (e.target.id === "hide-watched") {
      store.prefs.hideWatched = !store.prefs.hideWatched;
      saveStore();
      route();
    } else if (e.target.id === "w-tv" && W.video) {
      store.prefs.tv = true;
      saveStore();
      setMode("tv", W.video);
    } else if (e.target.id === "w-next") {
      goNext(false);
    }
  });

  // Leaving TV mode by hand turns the preference off again.
  document.addEventListener("click", (e) => {
    const b = e.target.closest('[data-act="exit"]');
    if (b && !site.kid_safe) {
      store.prefs.tv = false;
      saveStore();
    }
  }, true);

  // Search: filters the list you are looking at.
  let searchTimer = null;
  function applySearch(replace) {
    const { parts, params } = parseHash(location.hash);
    const listParts = parts[0] === "v" || parts[0] === "about" ? [] : parts;
    const p = parts[0] === "v" || parts[0] === "about" ? new URLSearchParams() : params;
    const q = searchInput.value.trim();
    if (q) p.set("q", q);
    else p.delete("q");
    const h = makeHash(listParts, p);
    if (replace) location.replace(h);
    else location.hash = h;
  }
  document.getElementById("search").addEventListener("submit", (e) => {
    e.preventDefault();
    clearTimeout(searchTimer);
    applySearch(false);
  });
  searchInput.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => applySearch(parseHash(location.hash).params.has("q")), 300);
  });

  // Keyboard, on the watch page.
  document.addEventListener("keydown", (e) => {
    if (!W.stage || e.altKey || e.ctrlKey || e.metaKey) return;
    if (e.target.closest("input, textarea, select")) return;
    const k = e.key;
    let handled = true;
    if (k === " " || k === "k") togglePlay();
    else if (k === "ArrowRight" || k === "l") seekBy(10);
    else if (k === "ArrowLeft" || k === "j") seekBy(-10);
    else if (k === "n") goNext(false);
    else if (k === "p") goPrev();
    else if (k === "t" && !site.kid_safe) setMode(W.mode === "tv" ? "normal" : "tv", W.video);
    else if (k === "Escape" && W.mode === "tv" && !site.kid_safe && !document.fullscreenElement) setMode("normal", W.video);
    else handled = false;
    if (handled) {
      e.preventDefault();
      wakeControls();
    }
  });

  window.addEventListener("hashchange", route);
  window.addEventListener("pagehide", saveProgress);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) saveProgress();
  });

  async function start() {
    let data;
    try {
      const res = await fetch("videos.json", { cache: "no-cache" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      data = await res.json();
    } catch (err) {
      main.innerHTML = `<div class="prose"><h1>No videos yet</h1><p>The list of videos could not be loaded (${esc(
        err.message,
      )}). If this site was just set up, its first build may still be running: wait a few minutes and reload. If it stays like this, see “Troubleshooting” in the project’s README.</p></div>`;
      return;
    }
    site = { ...site, ...(data.site || {}) };
    channels = data.channels || {};
    groups = (data.groups || []).filter((g) => g && g.name && Array.isArray(g.channels));
    videos = (data.videos || []).filter((v) => v && VIDEO_ID.test(v.id));
    videos.forEach((v) => byId.set(v.id, v));

    document.getElementById("site-title").textContent = site.title;
    document.getElementById("site-desc").textContent = site.description || "";
    document.body.classList.toggle("kid", !!site.kid_safe);
    applyLook();
    if (data.generated) {
      const when = data.generated.slice(0, 10);
      document.getElementById("updated").textContent = `List updated ${ago(when)}.`;
    }
    route();
  }

  start();
})();
