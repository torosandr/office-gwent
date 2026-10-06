'use strict';
// Short original synthesized sounds: no downloads or external audio services.
window.GameSound = (() => {
  const key = 'office-gwent-muted';
  let muted = false, context = null, master = null, voices = new Set();
  let roomCode = null, lastId = 0, ready = false;
  try { muted = localStorage.getItem(key) === '1'; } catch (_) {}
  const button = document.querySelector('#sound-toggle');
  function updateButton() {
    button.textContent = muted ? '🔇' : '🔊';
    button.title = muted ? 'Включить звук' : 'Выключить звук';
    button.setAttribute('aria-label', button.title);
    button.setAttribute('aria-pressed', String(muted));
  }
  function unlock() {
    if (muted) return;
    try {
      if (!context) {
        const Audio = window.AudioContext || window.webkitAudioContext;
        if (!Audio) return;
        context = new Audio(); master = context.createGain();
        master.gain.value = 0.32; master.connect(context.destination);
      }
      if (context.state === 'suspended') context.resume().catch(() => {});
    } catch (_) { /* Audio unavailable: the game remains playable. */ }
  }
  function stop() {
    for (const voice of voices) { try { voice.stop(); } catch (_) {} }
    voices.clear();
  }
  function tone(frequency, start, duration, volume = 0.2, type = 'sine', end = frequency) {
    const source = context.createOscillator(), gain = context.createGain();
    source.type = type; source.frequency.setValueAtTime(frequency, start);
    source.frequency.exponentialRampToValueAtTime(Math.max(20, end), start + duration);
    gain.gain.setValueAtTime(0, start);
    gain.gain.linearRampToValueAtTime(volume, start + Math.min(0.012, duration / 4));
    gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);
    source.connect(gain); gain.connect(master); voices.add(source);
    source.onended = () => { voices.delete(source); source.disconnect(); gain.disconnect(); };
    source.start(start); source.stop(start + duration + 0.02);
  }
  function noise(start, duration, volume = 0.22, frequency = 1200) {
    const buffer = context.createBuffer(1, Math.ceil(context.sampleRate * duration), context.sampleRate);
    const samples = buffer.getChannelData(0);
    for (let i = 0; i < samples.length; i++) samples[i] = Math.random() * 2 - 1;
    const source = context.createBufferSource(), filter = context.createBiquadFilter(), gain = context.createGain();
    source.buffer = buffer; filter.type = 'lowpass'; filter.frequency.value = frequency;
    gain.gain.setValueAtTime(volume, start); gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);
    source.connect(filter); filter.connect(gain); gain.connect(master); voices.add(source);
    source.onended = () => { voices.delete(source); source.disconnect(); filter.disconnect(); gain.disconnect(); };
    source.start(start); source.stop(start + duration + 0.02);
  }
  function play(kind, delay = 0) {
    if (muted || document.hidden || !context || context.state !== 'running' || voices.size > 40) return;
    const t = context.currentTime + delay;
    try {
      switch (kind) {
        case 'click': tone(650,t,0.045,0.14,'triangle',350); break;
        case 'error': tone(155,t,0.11,0.2,'triangle',105); tone(120,t+0.12,0.12,0.16,'triangle'); break;
        case 'card': noise(t,0.12,0.18,2600); tone(190,t+0.075,0.075,0.15,'triangle',90); break;
        case 'draw': noise(t,0.09,0.12,3600); break;
        case 'attack_unit': noise(t,0.13,0.4,1600); tone(150,t,0.16,0.3,'triangle',48); break;
        case 'attack_hero': noise(t,0.2,0.38,900); tone(95,t,0.28,0.38,'triangle',30); break;
        case 'spell_unit': tone(850,t,0.13,0.22,'sine',160); noise(t+0.09,0.14,0.3,2500); break;
        case 'spell_hero': tone(1100,t,0.17,0.2,'sine',90); noise(t+0.12,0.23,0.32,1300); tone(70,t+0.12,0.25,0.28,'triangle',30); break;
        case 'heal': [523,659,784,1047].forEach((f,i)=>tone(f,t+i*0.075,0.25,0.16)); break;
        case 'hero': [330,440,660].forEach((f,i)=>tone(f,t+i*0.07,0.24,0.19,'triangle')); break;
        case 'death': noise(t,0.18,0.24,1100); tone(230,t,0.22,0.16,'triangle',45); break;
        case 'turn': tone(660,t,0.12,0.14); tone(880,t+0.13,0.18,0.14); break;
        case 'victory': [523,659,784,1047].forEach((f,i)=>tone(f,t+i*0.13,0.36,0.2,'triangle')); break;
        case 'defeat': [392,330,262,196].forEach((f,i)=>tone(f,t+i*0.16,0.4,0.17,'triangle')); break;
      }
    } catch (_) { /* Sound failure must never interrupt actions. */ }
  }
  function accept(room) {
    if (!room || !['active','finished'].includes(room.phase)) {
      roomCode = null; lastId = 0; ready = false; return;
    }
    const events = room.events || [];
    const latest = events.reduce((max,e)=>Math.max(max,e.id),0);
    if (!ready || roomCode !== room.code) {
      roomCode = room.code; lastId = latest; ready = true; return;
    }
    const fresh = events.filter(e=>e.id > lastId);
    lastId = Math.max(lastId, latest); // Consume even while muted/hidden/locked.
    const now = Date.now()/1000;
    const audible = fresh.filter(e=>now-e.at < 10 && now-e.at > -30)
      .filter(e=>!['turn','draw'].includes(e.kind) || e.player === room.player_number);
    // If reconnect delivers several actions, play only the latest action's cues.
    const newest = audible.length ? audible[audible.length-1].at : null;
    let delay = 0;
    for (const e of audible.filter(e=>e.at === newest)) {
      const kind = e.kind === 'result' ? (e.player === room.player_number ? 'victory' : 'defeat') : e.kind;
      play(kind,delay); delay += 0.12;
    }
  }
  button.addEventListener('click', () => {
    muted = !muted;
    try { localStorage.setItem(key,muted?'1':'0'); } catch (_) {}
    updateButton();
    if (muted) stop(); else { unlock(); play('click'); }
  });
  document.addEventListener('pointerdown',unlock,{passive:true});
  document.addEventListener('keydown',unlock);
  document.addEventListener('click',event=>{
    if (event.defaultPrevented || event.target.closest('#sound-toggle')) return;
    const target = event.target.closest('button,a,[role="button"]');
    if (target && !target.disabled) { unlock(); play('click'); }
  });
  document.addEventListener('visibilitychange',()=>{if(document.hidden){stop();ready=false;}});
  window.addEventListener('storage',event=>{
    if(event.key === key){muted=event.newValue==='1';updateButton();if(muted)stop();}
  });
  updateButton();
  return {play,accept};
})();
