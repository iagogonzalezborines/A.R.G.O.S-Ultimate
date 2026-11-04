/* Narrow native bridge: no arbitrary code or selectors received from the model. */
let port;
let running = null;
let mediaTab = null;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
function check(job) {
  if (job.cancelled || Date.now() >= job.deadline) throw new Error('timeout');
}
async function inspect(tabId, action) {
  const code = '(' + page.toString() + ')(' + JSON.stringify(action) + ')';
  const results = await browser.tabs.executeScript(tabId, {code});
  return results[0];
}
// This function executes only in the tab created for this specific request.
async function page(action) {
  if (location.hostname !== 'www.youtube.com') return {blocked: true};
  if (action === 'search') {
    return [...document.querySelectorAll('ytd-video-renderer a#video-title')].slice(0, 12).map(a => {
      const u = new URL(a.href);
      return {title: (a.getAttribute('title') || a.textContent || '').trim().slice(0, 1000),
        id: u.origin === 'https://www.youtube.com' && u.pathname === '/watch' ? u.searchParams.get('v') : null};
    }).filter(v => /^[A-Za-z0-9_-]{11}$/.test(v.id));
  }
  const video = document.querySelector('video.html5-main-video');
  const player = document.querySelector('#movie_player');
  if (!video || !player) return {ready: false};
  const ad = player.classList.contains('ad-showing') || player.classList.contains('ad-interrupting');
  let playError = null;
  if (action === 'play' && !ad && video.paused) {
    // A paused/loading video alone does not prove a permission failure.
    // Bound the wait: play() can remain pending while media is loading.
    let timer;
    try {
      playError = await Promise.race([
        Promise.resolve(video.play()).then(() => null, error =>
          error?.name === 'NotAllowedError' ? 'NotAllowedError' : 'play_failed'),
        new Promise(resolve => { timer = setTimeout(() => resolve(null), 300); })
      ]);
    } catch (error) {
      playError = error?.name === 'NotAllowedError' ? 'NotAllowedError' : 'play_failed';
    } finally { clearTimeout(timer); }
  }
  return {ready: true, id: new URL(location.href).searchParams.get('v'),
    title: (document.querySelector('ytd-watch-metadata h1')?.textContent || '').trim().slice(0, 1000),
    ad, playError, paused: video.paused, muted: video.muted, volume: video.volume,
    ended: video.ended, time: video.currentTime, readyState: video.readyState};
}
function compact(text) { return text.normalize('NFKD').toLowerCase().replace(/[^a-z0-9]/g, ''); }
async function play(job) {
  check(job);
  const terms = job.query.split(/\s+/).map(compact).filter(Boolean);
  if (!terms.length) return {status: 'no_match'};
  const searchUrl = 'https://www.youtube.com/results?search_query=' + encodeURIComponent(job.query);
  let tab;
  if (mediaTab) {
    try {
      const previous = await browser.tabs.get(mediaTab.id);
      // Never take over a tab the user has navigated elsewhere, even on YouTube.
      if (previous.url === mediaTab.url) tab = previous;
    } catch (_) { /* The user closed the tab. */ }
  }
  check(job);
  if (tab) {
    await browser.tabs.update(tab.id, {url: searchUrl});
  } else {
    tab = await browser.tabs.create({url: searchUrl, active: false});
    job.createdTab = true;
  }
  mediaTab = {id: tab.id, url: searchUrl};
  job.tabId = tab.id;
  if (job.cancelled) {
    if (job.createdTab) await browser.tabs.remove(tab.id);
    check(job);
  }
  let selected;
  while (Date.now() < job.deadline - 10000) {
    check(job);
    let candidates;
    try { candidates = await inspect(tab.id, 'search'); } catch (_) { candidates = []; }
    if (Array.isArray(candidates) && candidates.length) {
      selected = candidates.find(v => terms.every(t => compact(v.title).includes(t)));
      if (!selected) return {status: 'no_match'};
      break;
    }
    await sleep(400);
  }
  if (!selected) return {status: 'page_blocked'};
  check(job);
  const url = 'https://www.youtube.com/watch?v=' + selected.id;
  await browser.tabs.update(tab.id, {url});
  mediaTab = {id: tab.id, url};
  let lastTime = null;
  while (Date.now() < job.deadline) {
    check(job);
    let state;
    try { state = await inspect(tab.id, 'play'); } catch (_) { state = {}; }
    check(job);
    if (state.ready && state.id === selected.id && !state.ad) {
      if (state.paused && state.playError === 'NotAllowedError')
        return {status: 'autoplay_blocked'};
      if (!state.paused && !state.ended && !state.muted && state.volume > 0 && state.readyState >= 2) {
        if (lastTime !== null && state.time > lastTime + 0.1)
          return {status: 'playing', title: state.title || selected.title, url};
        lastTime = state.time;
      } else {
        lastTime = null;
      }
    } else { lastTime = null; }
    await sleep(400);
  }
  return {status: 'timeout'};
}
function connect() {
  port = browser.runtime.connectNative('argos.firefox');
  port.onMessage.addListener(async message => {
    if (message.action === 'cancel') {
      if (running?.id === message.id) {
        running.cancelled = true;
        if (running.createdTab && running.tabId) browser.tabs.remove(running.tabId).catch(() => {});
      }
      return;
    }
    if (message.action !== 'play' || typeof message.query !== 'string' || message.query.length > 300 ||
        !/^[a-f0-9]{32}$/.test(message.id) || !Number.isFinite(message.deadline)) return;
    if (running) { port.postMessage({id: message.id, status: 'busy'}); return; }
    const job = {...message, deadline: Math.min(message.deadline, Date.now() + 45000)};
    const connection = port;
    running = job;
    try {
      const result = await play(job);
      check(job);
      connection.postMessage({id: job.id, ...result});
    } catch (_) {
      try { connection.postMessage({id: job.id, status: 'timeout'}); } catch (_) {}
    } finally { if (running === job) running = null; }
  });
  port.onDisconnect.addListener(() => {
    if (running) {
      running.cancelled = true;
      if (running.createdTab && running.tabId) browser.tabs.remove(running.tabId).catch(() => {});
    }
    setTimeout(connect, 3000);
  });
}
connect();
