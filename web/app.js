'use strict';
const app = document.querySelector('#app');
const connection = document.querySelector('#connection');
const seat = new URLSearchParams(location.search).get('seat') === '2' ? '2' : '1';
const storageKey = `office-gwent-session-${seat}`;
document.querySelector('.brand').href = seat === '2' ? '/?seat=2' : '/';
let token = localStorage.getItem(storageKey) || '';
let state = null, selection = null, busy = false, polling = false, config = null;
let view = 'lobby', cardsData = null, deckCandidates = null;
let sequence = 0, appliedSequence = 0, renderKey = '', toastTimer;
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const infoAttr = data => 'data-info="' + esc(JSON.stringify(data)).replace(/"/g,'&quot;') + '"';
const icons = {'вахтер':'🛡️','стажер':'🧑‍💻','бухгалтер':'🧮','кофемашина':'☕','дедлайн':'⏰','срочное_совещание':'📣','сломанный_принтер':'🖨️','свободная_пятница':'🎉','посудомойка':'🌀','покур':'💨','капучино':'☕','нянячка_таня':'💚','зеленая_гречка':'🍚','эспрессо':'☕','бпла_в_окно':'⚡','сокращение':'✂️','проджект_менеджер':'🛡️','тестировщик':'🔎','маркетолог':'📈','степан':'👨‍💼','заседание_женклуба':'🧊','лень':'🦥','предвкушение':'🍻','пиво':'🍺','завал':'📚'};
const icon = cid => icons[cid] || (cid?.includes('панини') ? '🥪' : '🃏');

function toast(message) {
  const el = document.querySelector('#toast'); el.textContent = message; el.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('show'), 4200);
}
function setConnection(ok) {
  connection.textContent = ok ? (config?.local ? 'Локальная игра' : 'На связи') : 'Переподключение…';
  connection.classList.toggle('connection-error', !ok);
}
async function api(path, body) {
  const seq = ++sequence;
  const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch(path, {method:body ? 'POST' : 'GET', headers:{'Content-Type':'application/json', ...(token ? {Authorization:`Bearer ${token}`} : {})}, body:body ? JSON.stringify(body) : undefined, signal:controller.signal});
    const result = await response.json();
    if (!response.ok) { const error = new Error(result.error || 'Не удалось выполнить действие.'); error.status = response.status; throw error; }
    setConnection(true);
    if (Array.isArray(result)) return result; // массивы (напр. rating) не оборачиваем
    return {...result, _seq:seq};
  } catch (error) {
    window.GameSound.play('error');
    if (!error.status) { setConnection(false); error.message = 'Связь с сервером потеряна. Партия сохранена — попробуйте ещё раз.'; }
    throw error;
  } finally { clearTimeout(timeout); }
}
function accept(data) {
  if (data._seq < appliedSequence) return;
  appliedSequence = data._seq;
  if (state?.room?.code !== data.room?.code || state?.room?.version !== data.room?.version) selection = null;
  window.GameSound.accept(data.room);
  state = data;
  document.querySelector('#avatar').textContent = data.profile.name.slice(0,2).toUpperCase();
  const key = JSON.stringify([data.profile, data.room?.code, data.room?.version]);
  if (key !== renderKey) { renderKey = key; render(); }
}
async function refresh() {
  if (!token || busy || polling || view !== 'lobby') return;
  polling = true;
  try { accept(await api('/api/state')); }
  catch (error) {
    if (error.status === 401) { token = ''; localStorage.removeItem(storageKey); showLogin(); }
  } finally { polling = false; }
}
function genRequestId() {
  // crypto.randomUUID доступен не во всех браузерах/WebView — даём запасной вариант
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'id-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
}

async function mutate(path, data={}) {
  if (busy) return;
  busy = true; app.classList.add('busy');
  try { accept(await api(path, {...data, request_id:genRequestId()})); }
  catch (error) { toast(error.message); }
  finally { busy = false; app.classList.remove('busy'); if(state?.room?.phase === 'active') render(); await refresh(); }
}
function localLink() {
  return config.local ? `<a class="local-link" href="/?seat=${seat === '1' ? '2' : '1'}" target="_blank" rel="noopener">Открыть окно второго игрока</a>` : '';
}
function logout() {
  token = '';
  localStorage.removeItem(storageKey);
  state = null; selection = null; cardsData = null; deckCandidates = null; view = 'lobby';
  showLogin();
}
function showLogin(error='') {
  if (!config.local) {
    app.innerHTML = `<section class="login panel"><span class="eyebrow">Офисный Гвинт</span><h1>Встречаемся<br>за игровым столом.</h1><p class="muted">${esc(error || 'Откройте игру кнопкой в Telegram-боте.')}</p></section>`;
    return;
  }
app.innerHTML = `<section class="login"><span class="eyebrow">Перерыв на партию</span><h1>Кофе готов.<br>Ваш ход.</h1><p class="muted">Соберите команду и доведите стресс соперника до нуля.</p><form id="login-form" class="panel"><label for="name">Как вас называть?</label><input id="name" name="name" maxlength="32" autocomplete="nickname" value="${seat === '2' ? 'Пётр' : 'Анна'}"><label for="id">Игровой ID (необязательно)</label><input id="id" name="id" maxlength="32" placeholder="Вставьте ID из команды /my_id"><p class="muted tiny">Укажите «/my_id» у бота и вставьте цифры, чтобы загрузить свою колоду и героя. Или просто введите имя для гостя.</p><button type="submit">Войти в игровую</button></form>${localLink()}</section>`;
  document.querySelector('#login-form').addEventListener('submit', async event => {
    event.preventDefault(); if (busy) return; busy = true;
    const button = event.target.querySelector('button'); button.disabled = true;
    const body = {name:event.target.elements.name.value};
    const enteredId = (event.target.elements.id.value || '').trim();
    if (enteredId) body.id = enteredId;
    try { const data = await api('/api/auth/local', body); token = data.token; localStorage.setItem(storageKey, token); accept(data); }
    catch (error) { toast(error.message); button.disabled = false; }
    finally { busy = false; }
  });
}
function render() {
  if (!state) return;
  const r = state.room, p = state.profile;
if (!r || r.phase === 'closed') {
    if (view !== 'lobby') return renderMenu();
    app.innerHTML = `<section class="lobby"><div class="lobby-title"><span class="eyebrow">Игровая комната</span><h1>Хороший день,<br>чтобы обыграть коллегу.</h1><div class="profile-row"><span>${esc(p.name)}</span><span class="pill">🏆 ${p.wins} побед</span><span class="pill">🪙 ${p.coins} монет</span><button class="ghost" id="logout">Выйти</button></div></div><div class="panels"><section class="panel"><div class="symbol">🃏</div><h2>Собрать партию</h2><p class="muted">Создайте комнату и передайте код сопернику. В партии — два игрока.</p><button id="create">Создать партию</button></section><form class="panel" id="join-form"><div class="symbol">🤝</div><h2>Коллега уже ждёт?</h2><label for="code">Код комнаты</label><input id="code" name="code" maxlength="6" placeholder="Например, AB3D7K" autocomplete="off" autocapitalize="characters" required><button class="secondary" type="submit">Присоединиться</button></form></div>${menuNav()}<div class="lobby-nav extra"><button class="ghost" data-view="shop">🛒 Магазин</button><button class="ghost" data-view="deck">🃏 Моя колода</button><button class="ghost" data-view="cards">✨ Все карты</button><button class="ghost" data-view="rating">🏆 Рейтинг</button></div>${localLink()}</section>`;
    document.querySelector('#create').onclick = () => mutate('/api/rooms');
    document.querySelector('#join-form').onsubmit = event => { event.preventDefault(); mutate('/api/join', {code:event.target.elements.code.value.trim()}); };
    document.querySelector('#logout').onclick = logout;
    bindMenuNav();
    return;
  }
  if (r.phase === 'waiting') {
    app.innerHTML = `<section class="waiting panel"><span class="eyebrow">Комната готова</span><h1>Место для коллеги.</h1><p class="muted">Передайте этот код второму игроку.</p><div class="room-code">${esc(r.code)}</div><button id="copy">Скопировать код</button><p class="muted"><span class="wait-dot"></span>Ждём второго игрока</p><p class="muted tiny">Можно закрыть окно и вернуться — комната сохранится.</p><button id="leave" class="ghost">Отменить партию</button><div>${localLink()}</div></section>`;
    document.querySelector('#copy').onclick = async () => { try { await navigator.clipboard.writeText(r.code); toast('Код скопирован'); } catch { toast(`Код комнаты: ${r.code}`); } };
    document.querySelector('#leave').onclick = () => mutate('/api/leave');
    return;
  }
  renderGame(r);
}
function menuNav() {
  return '<div class="menu-nav-label muted tiny">Также доступно:</div>';
}
function bindMenuNav() {
  document.querySelectorAll('[data-view]').forEach(el => el.onclick = () => { view = el.dataset.view; renderMenu(); });
}
async function renderMenu() {
  if (!token) { showLogin(); return; }
  try {
    if (!cardsData) cardsData = await api('/api/cards');
    if (view === 'deck' && !deckCandidates) deckCandidates = await api('/api/deck-candidates');
    state = await api('/api/menu');
  } catch(error) { toast(error.message); return; }
  view = view || 'lobby';
  const p = state;
  const back = '<button class="ghost" data-view-back>← В игровую</button>';
  if (view === 'shop') {
    const items = (await api('/api/cards')).filter(c => c.for_sale);
    app.innerHTML = `<section class="lobby"><span class="eyebrow">Магазин</span><h1>Прокачка команды.</h1><p class="muted">Баланс: 🪙 ${esc(p.coins)}</p>${back}<div class="panels shop-grid">${items.map(c => `<div class="panel card-shop"><h2>${esc(c.name)}</h2><p class="muted tiny">${esc(c.desc||'')}</p><p class="muted"><b>${c.price} 🪙</b>${c.legendary?' · ⭐ Легендарная':''}</p><div ${infoAttr(c)} style="display:inline-block"><button data-buy="${esc(c.id)}">Купить</button></div></div>`).join('') || '<p class="muted">В магазине пока пусто.</p>'}</div></section>`;
    document.querySelectorAll('[data-buy]').forEach(el => el.onclick = async () => { cardsData = null; try { await api('/api/buy', {card:el.dataset.buy}); toast('Куплено!'); await refreshMenu(); } catch(e){ toast(e.message); } });
  } else if (view === 'deck') {
    const deck = p.deck || [];
    const cardOf = cid => cardsData ? cardsData.find(x => x.id === cid) : null;
    const mini = cid => { const c = cardOf(cid); return c; };
    // карточка колоды: иконка + имя + статы, как в бою
    const deckDeckCard = (cid, i) => {
      const c = mini(cid) || {name:cid, type:'creature', attack:0, health:0, cost:0, desc:'', legendary:false};
      const stats = c.type === 'creature'
        ? `<span>⚔ ${c.attack}</span><span>♥ ${c.health}</span>`
        : `<span>✦</span><span>${c.cost} ☕</span>`;
      return `<button class="card unit ready" data-remove="${i}" ${infoAttr(c)} title="${esc(c.desc||'')}" aria-label="${esc(c.name)}"><span class="art">${icon(c.id)}</span><span class="name">${esc(c.name)}</span><span class="unit-status">&nbsp;</span><span class="stats">${stats}</span></button>`;
    };
    // доступная карта
    const poolCard = cid => {
      const c = mini(cid) || {name:cid, type:'creature', attack:0, health:0, cost:0, desc:'', legendary:false};
      const stats = c.type === 'creature'
        ? `<span>⚔ ${c.attack}</span><span>♥ ${c.health}</span>`
        : `<span>✦</span><span>${c.cost} ☕</span>`;
      return `<button class="card unit ${deck.filter(x=>x===cid).length>=2?'unavailable':'ready'}" data-add="${esc(cid)}" ${infoAttr(c)} title="${esc(c.desc||'')}" aria-label="${esc(c.name)}"><span class="art">${icon(c.id)}</span><span class="name">${esc(c.name)}</span><span class="unit-status">&nbsp;</span><span class="stats">${stats}</span></button>`;
    };
    app.innerHTML = `<section class="lobby"><span class="eyebrow">Моя колода</span><h1>${deck.length}/15 карт</h1>${back}<div class="deck-field"><div class="deck-box"><h2>Ваша колода</h2><div class="deck-grid" id="deck-grid">${deck.map(deckDeckCard).join('') || '<p class="muted">Колода пуста</p>'}</div></div><button id="save-deck" class="secondary">Сохранить колоду</button></div><div class="deck-box"><h2>Доступные карты <span class="muted">· ${deckCandidates.length}</span></h2><div class="deck-pool" id="deck-pool">${deckCandidates.map(poolCard).join('') || '<p class="muted">Нет доступных карт</p>'}</div></div></section>`;
    document.querySelectorAll('[data-add]').forEach(el => el.onclick = async () => { cardsData = null; try { await api('/api/deck', {op:'add', card:el.dataset.add}); await refreshMenu(); } catch(e){ toast(e.message); } });
    document.querySelectorAll('[data-remove]').forEach(el => el.onclick = async () => { try { await api('/api/deck', {op:'remove', index:Number(el.dataset.remove)}); await refreshMenu(); } catch(e){ toast(e.message); } });
    document.querySelector('#save-deck').addEventListener('click', async () => { cardsData = null; try { const r = await api('/api/deck', {op:'save'}); toast('Колода сохранена'); await refreshMenu(); } catch(e){ toast(e.message); } });
  } else if (view === 'cards') {
    app.innerHTML = `<section class="lobby"><span class="eyebrow">Все карты</span><h1>Каталог.</h1>${back}<div class="cards-grid">${cardsData.map(c => `<div class="panel card-tile" ${infoAttr(c)}><span class="art">${icon(c.id)}</span><div class="name"><b>${esc(c.name)}</b>${c.legendary?' ⭐':''}${c.owned?` <span class="pill">×${c.count}</span>`:' <span class="muted">—нет</span>'}</div><div class="unit-status">${c.type==='creature'?`⚔ ${c.attack} / ♥ ${c.health}`:'✨ Заклинание'} · ${c.cost} ☕</div><p class="muted tiny">${esc(c.desc||'')}</p></div>`).join('')}</div></section>`;
  } else if (view === 'rating') {
    try {
      const rows = (await api('/api/rating')).slice(0, 20);
      const medals = ['🥇','🥈','🥉'];
      app.innerHTML = `<section class="lobby"><span class="eyebrow">Рейтинг</span><h1>Лидеры офиса.</h1>${back}<div class="panels"><ul class="log">${rows.map((x,i)=>`<li><b>${medals[i]||(i+1)+'.'} ${esc(x.name)}</b> — ${x.wins} побед, 🪙 ${x.coins}${String(x.name)===String(p.name)?' · вы':''}</li>`).join('') || '<li class="muted">Пока нет игроков.</li>'}</ul></div></section>`;
    } catch(e) { toast(e.message); return; }
  }
  bindMenuNav();
  document.querySelector('[data-view-back]')?.addEventListener('click', () => { view='lobby'; cardsData=null; deckCandidates=null; render(); });
  document.querySelectorAll('[data-view]').forEach(el => {});
}
async function refreshMenu() { state = await api('/api/menu'); cardsData = (view==='shop') ? await api('/api/cards') : cardsData; renderMenu(); }
function cardName(cid) {
  if (cardsData) { const c = cardsData.find(x => x.id === cid); if (c) return c.name; }
  return cid;
}
function canTarget(side, index) {
  if (!selection) return false;
  if (selection.kind === 'attack') return side === 'opponent' && selection.targets.includes(index === 'hero' ? 'hero' : String(index));
  const own = ['хил_цель','сокращение'].includes(selection.status);
  return side === (own ? 'me' : 'opponent') && selection.targets.includes(index === 'hero' ? (own ? 'hero_self' : 'hero_opp') : String(index));
}
function hero(side, player) {
  return `<div class="hero-row ${canTarget(side,'hero') ? 'target' : ''}" ${canTarget(side,'hero') ? `role="button" tabindex="0" data-target="${side}:hero" aria-label="Выбрать героя ${esc(player.name)}"` : ''}><div class="hero-info"><span class="hero-face">${side === 'me' ? '🧑‍💼' : '👤'}</span><div><div class="hero-name">${esc(player.name)}${side === 'me' ? ' · вы' : ''}</div><div class="hero-label">${esc(player.hero)}</div></div></div><div class="resources"><span class="resource stress" title="Стресс">♥ ${player.stress}/20</span><span class="resource coffee" title="Кофе">☕ ${player.coffee}/10</span></div></div>`;
}
function unitMarkup(side, unit) {
  const target = canTarget(side, unit.index), active = side === 'me' && unit.targets.length > 0;
  const tags = [unit.frozen ? '🧊 Заморожен' : '', unit.deadline != null ? `💣 Взрыв через ${unit.deadline}` : '', unit.stunned || unit.asleep ? '💤 Спит' : '', unit.attacked ? 'Уже атаковал' : '', unit.status === 'таунт' || unit.status === 'супер_таунт' ? '🛡 Защита' : ''].filter(Boolean);
  const info = {id:unit.card, name:unit.name, type:'creature', attack:unit.attack, hp:unit.hp, max_hp:unit.max_hp, status:unit.status, desc:unit.desc, deadline:unit.deadline, frozen:unit.frozen};
  return `<button class="card unit ${target ? 'target' : ''} ${active ? 'ready' : ''} ${selection?.kind === 'attack' && selection.index === unit.index && side === 'me' ? 'selected' : ''}" ${target ? `data-target="${side}:${unit.index}"` : `data-unit="${side}:${unit.index}"`} ${infoAttr(info)} title="${esc(unit.desc)}" aria-label="${esc(unit.name)}, атака ${unit.attack}, здоровье ${unit.hp}"><span class="art">${icon(unit.card)}</span>${unit.deadline != null ? `<span class="deadline-chip">💣 ${unit.deadline}</span>` : ''}<span class="name">${esc(unit.name)}</span><span class="unit-status">${esc(tags.join(' · '))}</span><span class="stats"><span>⚔ ${unit.attack}</span><span>♥ ${unit.hp}</span></span></button>`;
}
function cardMarkup(card) {
  const info = {id:card.id, name:card.name, type:card.type, cost:card.cost, attack:card.attack, health:card.health, status:card.status, desc:card.desc, legendary:card.legendary};
  return `<button class="card ${card.type === 'spell' ? 'spell' : ''} ${card.playable ? 'ready' : 'unavailable'} ${selection?.kind === 'cast' && selection.index === card.index ? 'selected' : ''}" data-card="${card.index}" ${infoAttr(info)} aria-label="${esc(card.name)}, ${card.cost} кофе"><span class="cost">${card.cost}</span><span class="art">${icon(card.id)}</span><span class="name">${esc(card.name)}</span><span class="desc">${esc(card.desc)}</span><span class="stats">${card.type === 'creature' ? `<span>⚔ ${card.attack}</span><span>♥ ${card.health}</span>` : '<span>✦ Заклинание</span>'}</span></button>`;
}
function renderGame(r) {
  const ended = r.phase === 'finished';
  const heroLabel = r.hero_info?.type === 'passive' ? 'Пассивная способность' : `Герой · ${r.hero_info?.active_cost ?? 2} ☕ / +${r.hero_info?.active_amount ?? 3} ♥`;
  app.innerHTML = `<section class="game"><div class="game-heading"><div><span class="eyebrow">Офисный Гвинт</span><h1>${ended ? 'Партия завершена' : 'Перерыв затянулся.'}</h1></div><span class="pill">Комната <span class="code">${esc(r.code)}</span></span></div>${ended ? `<div class="result"><h2>${r.won ? 'Победа! 🏆' : 'В этот раз — за коллегой.'}</h2><p>${r.won ? '+20 монет. Отличная работа команды.' : 'Новая партия — новый шанс.'}</p><button id="back-lobby">В игровую</button></div>` : ''}<div class="game-layout"><section class="table" aria-label="Игровой стол">${hero('opponent',r.opponent)}<div class="board" aria-label="Существа соперника">${r.opponent.board.map(u => unitMarkup('opponent',u)).join('') || '<span class="empty-board">Соперник ещё никого не вызвал</span>'}</div><div class="divider"><span class="turn-label ${r.my_turn && !ended ? '' : 'wait'}">${ended ? 'КОНЕЦ ПАРТИИ' : r.my_turn ? (r.skip ? 'ПРОПУСК ХОДА · ПОКУР' : 'ВАШ ХОД') : 'ХОД СОПЕРНИКА'}</span></div><div class="board" aria-label="Ваши существа">${r.me.board.map(u => unitMarkup('me',u)).join('') || '<span class="empty-board">Ваша команда появится здесь</span>'}</div>${hero('me',r.me)}${selection ? `<div class="action-hint"><span>${selection.kind === 'attack' ? 'Выберите цель атаки' : 'Выберите подсвеченную цель'}</span><button id="cancel-selection" class="ghost">Отмена</button></div>` : ''}</section><aside class="sidebar"><section class="panel"><h2>${r.my_turn ? 'Ваше решение' : 'Ход коллеги'}</h2><button class="end-turn" id="end" ${!r.my_turn || ended ? 'disabled' : ''}>Завершить ход</button><button class="secondary hero-button" id="hero" ${!r.hero_ready || ended ? 'disabled' : ''}>${esc(heroLabel)}</button><button class="ghost hero-button" id="concede" ${ended ? 'disabled' : ''}>Сдаться</button></section><section class="panel"><h2>За столом</h2><p class="muted tiny">В вашей колоде: ${r.me.deck_count}<br>Карт у соперника: ${r.opponent.hand_count}</p><p class="muted tiny">${r.skip ? '«Покур»: завершите ход, чтобы продолжить игру.' : 'Нажмите карту, чтобы разыграть её. Для атаки выберите своё существо, затем цель.'}</p></section><section class="panel log-panel"><h2>Последние события</h2><ul class="log">${[...r.log].reverse().slice(0,8).map(line => `<li>${esc(line)}</li>`).join('') || '<li>Партия начинается.</li>'}</ul></section></aside><section class="hand-area"><div class="hand-title"><h2>Ваша рука <span class="muted">· ${r.hand.length}</span></h2><span class="muted">${r.my_turn && !ended ? 'Карты с золотой рамкой доступны' : 'Планируйте следующий ход'}</span></div><div class="hand">${r.hand.map(cardMarkup).join('') || '<p class="muted">Карт в руке пока нет.</p>'}</div></section></div></section>`;
  const action = data => mutate('/api/action', {version:r.version,...data});
  document.querySelector('#end').onclick = () => action({action:'end'});
  document.querySelector('#hero').onclick = () => action({action:'hero'});
  document.querySelector('#concede').onclick = () => document.querySelector('#confirm').showModal();
  document.querySelector('#back-lobby')?.addEventListener('click', () => mutate('/api/leave'));
  document.querySelector('#cancel-selection')?.addEventListener('click', () => {selection=null; render();});
  document.querySelectorAll('[data-card]').forEach(el => el.onclick = () => {
    const card = r.hand[Number(el.dataset.card)];
    if (!card.playable) { window.GameSound.play("error"); toast(card.reason); return; }
    if (card.targeted) {
      if (!card.targets.length) {window.GameSound.play('error');toast('На поле нет подходящей цели.');return;}
      selection = {kind:'cast',index:card.index,status:card.status,targets:card.targets}; render();
    } else { selection=null; action({action:'play',index:card.index}); }
  });
  document.querySelectorAll('[data-unit]').forEach(el => el.onclick = () => {
    const [side, index] = el.dataset.unit.split(':'); const unit=r[side].board[Number(index)];
    if (side !== 'me' || !unit.targets.length) {toast(unit.desc);return;}
    selection = {kind:'attack', index:unit.index, targets:unit.targets}; render();
  });
  document.querySelectorAll('[data-target]').forEach(el => {
    const trigger = () => {
      if (!selection) return;
      const [side,index] = el.dataset.target.split(':');
      const target = index !== 'hero' ? index : selection.kind === 'attack' ? 'hero' : side === 'me' ? 'hero_self' : 'hero_opp';
      const picked = selection; selection=null;
      action({action:picked.kind,index:picked.index,target});
    };
    el.onclick=trigger; if (el.tagName !== 'BUTTON') el.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();trigger();}};
  });
}
document.querySelector('#confirm').addEventListener('close', event => {
  if (event.target.returnValue === 'concede' && state?.room) mutate('/api/action', {version:state.room.version,action:'concede'});
});
document.addEventListener('visibilitychange', () => {if(!document.hidden) refresh();});
window.addEventListener('online', refresh);

// ---- Подробное описание карт (долгое нажатие) ----
function showCardInfo(c) {
  if (!c) return;
  const status = c.status ? (c.status === 'таунт'||c.status==='супер_таунт'?'🛡 ':'') : '';
  const legendary = c.legendary ? ' ⭐' : '';
  const body = document.querySelector('#cardinfo-body');
  const stats = c.type === 'creature'
    ? `<span>⚔ ${c.attack}</span><span>♥ ${c.hp ?? c.max_hp ?? c.health}</span>`
    : `<span>${c.cost} ☕</span>`;
  body.innerHTML = `
    <div class="ci-art">${icon(c.id)}</div>
    <div class="ci-name"><b>${esc(c.name)}</b>${legendary}</div>
    <div class="ci-type">${c.type === 'creature' ? 'Существо' : 'Заклинание'} · ${c.cost} ☕</div>
    <div class="ci-stats">${stats}</div>
    <div class="ci-desc">${esc(c.desc || '')}</div>`;
  document.querySelector('#cardinfo').showModal();
  document.querySelector('#cardinfo').scrollTop = 0;
}
// Глобальное долгое нажатие на карты
let lpTimer = null, lpEl = null, lpStarted = false;
document.addEventListener('pointerdown', e => {
  const card = e.target.closest('[data-info]');
  if (!card) return;
  lpEl = card; lpStarted = false;
  lpTimer = setTimeout(() => {
    lpStarted = true;
    try { showCardInfo(JSON.parse(card.dataset.info)); } catch(_) {}
  }, 420);
});
document.addEventListener('pointerup', () => { clearTimeout(lpTimer); lpTimer=null; lpEl=null; });
document.addEventListener('pointercancel', () => { clearTimeout(lpTimer); lpTimer=null; lpEl=null; });
// если долгое нажатие сработало — не давать обычному клику выполниться
document.addEventListener('click', e => {
  if (lpStarted) { e.stopPropagation(); e.preventDefault(); lpStarted = false; }
}, true);
async function start() {
  try {
    config = await api('/api/config');
    if (!config.local) {
      await new Promise((resolve,reject) => {const script=document.createElement('script');script.src='https://telegram.org/js/telegram-web-app.js';script.onload=resolve;script.onerror=reject;document.head.append(script);});
      const tg = window.Telegram?.WebApp;
      if (!tg?.initData) {showLogin();return;}
      tg.ready(); tg.expand();
      const data=await api('/api/auth/telegram',{init_data:tg.initData}); token=data.token;localStorage.setItem(storageKey,token);accept(data);
    } else if (token) await refresh(); else showLogin();
    setConnection(true);
  } catch(error) { if(config) showLogin(error.message); else {app.innerHTML='<section class="login panel"><h1>Нет связи</h1><p class="muted">Проверьте, запущен ли сервер игры, и обновите страницу.</p></section>';} }
  setInterval(() => {if(!document.hidden) refresh();},1500);
}
start();

