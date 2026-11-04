const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
function fixture(replies) {
  let now = 0;
  const updates = [], creates = [];
  let tabUrl = null;
  const context = vm.createContext({
    console, URL, setTimeout: fn => { now += 500; fn(); },
    Date: {now: () => now},
    browser: {
      runtime: {connectNative: () => ({onMessage: {addListener() {}}, onDisconnect: {addListener() {}}, postMessage() {}})},
      tabs: {
        create: async x => {creates.push(x); tabUrl = x.url; return {id: 7};},
        get: async id => {assert.equal(id,7); if (!tabUrl) throw new Error('closed'); return {id, url:tabUrl};},
        update: async (id, x) => {updates.push([id, x]); tabUrl = x.url;},
        executeScript: async (id, opts) => {assert.equal(id, 7);assert.ok(opts.code.includes('function page')); return [replies.shift() || {}];}
      }
    }
  });
  vm.runInContext(fs.readFileSync('integrations/firefox/background.js','utf8'), context);
  return {context, updates, creates, navigate: url => {tabUrl = url;},
    run: () => vm.runInContext("play({query:'AC/DC Thunderstruck',deadline:45000})", context)};
}
const candidate = {title: 'AC/DC - Thunderstruck (Official Video)', id: 'v2AC41dglnM'};
const state = time => ({ready:true,id:candidate.id,title:candidate.title,ad:false,paused:false,muted:false,volume:1,ended:false,time,readyState:4});
(async () => {
  let f = fixture([[{title:'Unrelated',id:'aaaaaaaaaaa'},candidate],state(1),state(1.5)]);
  let r = await f.run(); assert.equal(r.status,'playing'); assert.equal(r.title,candidate.title);
  assert.equal(f.updates[0][1].url,'https://www.youtube.com/watch?v=v2AC41dglnM');
  assert.equal(f.creates.length,1);
  assert.equal(f.creates[0].active,false);
  assert.equal(f.updates.length,1);
  assert.equal('active' in f.updates[0][1],false);
  for (const next of ['reuse', 'closed', 'navigated']) {
    f = fixture([[candidate],state(1),state(1.5),[candidate],state(1),state(1.5)]);
    assert.equal((await f.run()).status,'playing');
    if (next === 'closed') f.navigate(null);
    if (next === 'navigated') f.navigate('https://www.youtube.com/watch?v=aaaaaaaaaaa');
    assert.equal((await f.run()).status,'playing');
    assert.equal(f.creates.length,next === 'reuse' ? 1 : 2);
    assert.ok(f.creates.every(x => x.active === false));
    assert.ok(f.updates.every(([,x]) => !('active' in x)));
  }
  f = fixture([[{title:'Unrelated',id:'aaaaaaaaaaa'}]]); assert.equal((await f.run()).status,'no_match'); assert.equal(f.updates.length,0);
  f = fixture([[candidate],{...state(0),paused:true,playError:'NotAllowedError'}]); assert.equal((await f.run()).status,'autoplay_blocked');
  f = fixture([[candidate],...Array(100).fill({...state(0),paused:true})]); assert.equal((await f.run()).status,'timeout');
  f = fixture([[candidate],...Array(20).fill({...state(0),paused:true,readyState:0}),state(1),state(1.5)]);
  assert.equal((await f.run()).status,'playing');
  f = fixture([[candidate],...Array(100).fill({...state(0),paused:true,playError:'play_failed'})]);
  assert.equal((await f.run()).status,'timeout');
  f = fixture([[candidate],...Array(100).fill({...state(1),ad:true})]); assert.equal((await f.run()).status,'timeout');
  f = fixture([[candidate],...Array(100).fill({...state(1),muted:true})]); assert.equal((await f.run()).status,'timeout');
  f = fixture([[candidate],...Array(100).fill(state(1))]); assert.equal((await f.run()).status,'timeout');
  f = fixture([]); await assert.rejects(vm.runInContext("play({query:'AC/DC Thunderstruck',deadline:45000,cancelled:true})",f.context));
  // Exercise the injected page function too, including actual promise rejection
  // and a pending play() promise. All media objects are mocks; no audio plays.
  for (const outcome of ['allowed', 'NotAllowedError', 'AbortError', 'pending', 'throw']) {
    const video = {...state(0),paused:true,currentTime:0,
      play: () => {
        if (outcome === 'throw') throw {name:'NotSupportedError'};
        if (outcome === 'pending') return new Promise(() => {});
        return outcome === 'allowed' ? Promise.resolve() : Promise.reject({name:outcome});
      }};
    const c = fixture([]).context;
    Object.assign(c, {setTimeout, clearTimeout,
      location:{hostname:'www.youtube.com',href:'https://www.youtube.com/watch?v='+candidate.id},
      document:{querySelector: selector => selector === 'video.html5-main-video' ? video :
        selector === '#movie_player' ? {classList:{contains:() => false}} : {textContent:candidate.title}}});
    const result = await vm.runInContext("page('play')",c);
    assert.equal(result.playError, outcome === 'NotAllowedError' ? 'NotAllowedError' :
      ['AbortError','throw'].includes(outcome) ? 'play_failed' : null);
  }
  console.log('18 Firefox extension scenarios passed (mock browser, no playback).');
})().catch(e => {console.error(e); process.exitCode=1;});
