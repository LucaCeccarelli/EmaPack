(() => {
  const root = document.getElementById('battle');
  const $ = id => document.getElementById(id);
  const d = root.dataset;
  const csrf = root.querySelector('[name=csrfmiddlewaretoken]').value;
  const fmt = (msg, vars) => msg.replace(/\{(\w+)\}/g, (_, k) => vars[k]);
  const stat = key => root.getAttribute(`data-stat-${key}`);
  const POLL_MS = 1500;
  let state = null, shown = '', seenRounds = null, timer = null, poller = null, leftAt = 0, busy = false;
  const PICK = Number(d.pickSeconds);

  function showError(text) { $('error').textContent = text || ''; $('error').hidden = !text; }

  // A pending battle has no board: poll until it starts (or disappears), then reload into the right page.
  const pending = !$('hand');

  async function load(res) {
    if (res.status === 404) { location.href = d.battlesUrl; throw new Error('gone'); }
    return res.json();
  }

  async function poll() {
    try {
      apply(await load(await fetch(d.stateUrl, { headers: { Accept: 'application/json' } })));
      showError('');
    } catch (e) { if (e.message !== 'gone') showError(d.msgError); }
  }

  function side(s, label) {
    return `<div class="reveal-side"><span class="muted">${label}</span>${s.html}<strong class="reveal-value">${s.value}</strong></div>`;
  }

  function entry(h, latest) {
    return `<div class="reveal result-${h.result}${latest ? ' latest' : ''}">
      <p>${fmt(d.msgRound, { n: h.number })} · ${stat(h.stat)} · <strong>${d[`msg${h.result[0].toUpperCase()}${h.result.slice(1)}`]}</strong></p>
      <div class="reveal-pair">${side(h.you, d.msgYou)}${side(h.opponent, state.opponent)}</div></div>`;
  }

  function apply(s) {
    state = s;
    leftAt = performance.now(); // seconds_left is server-computed; count down from when it arrived
    if (pending) { if (s.status !== 'pending') location.reload(); return; }
    const r = s.round;
    $('score').textContent = `${d.msgYou} ${s.score.you} – ${s.score.opponent} ${s.opponent}`;
    $('stat').textContent = r ? `${fmt(d.msgRound, { n: r.number })} · ${stat(r.stat)}` : '';
    $('left').textContent = r ? fmt(d.msgCardsLeft, { name: s.opponent, n: s.opponent_cards_left }) : '';
    const they = fmt(d.msgTheyPicked, { name: s.opponent });
    $('status').textContent = !r ? '' : r.you_picked ? fmt(d.msgYouPicked, { name: s.opponent })
      : r.opponent_picked ? `${they} · ${d.msgPick}` : d.msgPick;

    // Re-render the hand only when it changes, so hovering/tapping isn't interrupted by polls.
    const key = JSON.stringify([s.hand.map(c => c.id), r && r.number, r && r.you_picked]);
    if (key !== shown) {
      shown = key;
      $('hand').innerHTML = s.hand.map(c => `<button type="button" class="hand-card" data-id="${c.id}" ${r && !r.you_picked ? '' : 'disabled'}>${c.html}</button>`).join('');
    }

    // The newest resolved round is shown big (once per new round); all rounds stay in the history below.
    const grew = seenRounds !== null && s.history.length > seenRounds;
    seenRounds = s.history.length;
    const last = s.history[s.history.length - 1];
    if (grew || (last && !$('reveal').innerHTML)) $('reveal').innerHTML = entry(last, true);
    $('historyTitle').hidden = s.history.length < 2;
    $('history').innerHTML = s.history.slice(0, -1).reverse().map(h => entry(h)).join('');

    $('result').hidden = !s.result;
    if (s.result) {
      const rec = s.record;
      $('result').innerHTML = `${{ win: d.msgWon, loss: d.msgLost, draw: d.msgTied }[s.result]}<br>
        <a class="btn small" href="${d.battlesUrl}">${d.msgBack}${rec ? ` · ${d.msgRecord}: ${rec.wins}-${rec.losses}-${rec.draws}` : ''}</a>`;
      $('timer').textContent = '';
      clearInterval(timer); timer = null;
      clearInterval(poller); poller = null;
      return;
    }
    tick();
  }

  function tick() {
    if (!state || !state.round) return;
    const left = Math.max(0, Math.ceil(state.round.seconds_left - (performance.now() - leftAt) / 1000));
    // Between rounds the new round already exists but its timer hasn't started: show the reveal, hold the hand.
    const waiting = left > PICK;
    $('timer').textContent = waiting ? '' : fmt(d.msgTime, { s: left });
    document.querySelectorAll('.hand-card').forEach(b => { b.disabled = waiting || state.round.you_picked || busy; });
  }

  $('hand')?.addEventListener('click', async e => {
    const btn = e.target.closest('.hand-card');
    if (!btn || btn.disabled || !state.round) return;
    const round = state.round.number; // the round the player was looking at, so a late click can't land in the next one
    busy = true;
    document.querySelectorAll('.hand-card').forEach(b => { b.disabled = true; });
    const body = new URLSearchParams({ card: btn.dataset.id, round });
    try {
      const res = await fetch(d.playUrl, { method: 'POST', headers: { 'X-CSRFToken': csrf }, body });
      const data = await load(res);
      busy = false;
      if (res.ok) { showError(''); apply(data); } else { showError(data.error || d.msgError); shown = ''; if (data.state) apply(data.state); else apply(state); }
    } catch (err) { busy = false; shown = ''; apply(state); if (err.message !== 'gone') showError(d.msgError); }
  });

  poll();
  poller = setInterval(poll, POLL_MS);
  timer = setInterval(tick, 250);
})();
