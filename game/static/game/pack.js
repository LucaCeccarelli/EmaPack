(() => {
  const $ = id => document.getElementById(id);
  const stage = $('stage'), packWrap = $('packWrap'), pack = $('pack'), tearLine = $('tearLine');
  const hint = $('hint'), timer = $('timer'), reveal = $('reveal'), summary = $('summary'), skipBtn = $('skip');
  const csrf = stage.querySelector('[name=csrfmiddlewaretoken]').value;
  const COLOR = { 1: '#dfe5f5', 2: '#3ddc84', 3: '#3aa0ff', 4: '#b35cff', 5: '#ffb800' };
  const SOUND = { 3: 'rare', 4: 'epic', 5: 'legendary' };
  const TEAR_DONE = 0.75; // fraction of the pack width to drag

  FX.init($('fx'));
  let nextPackAt = stage.dataset.nextPackAt ? new Date(stage.dataset.nextPackAt) : null;
  let busy = false, request = null, skip = false, pendingTap = null, message = '';
  const dur = ms => (FX.reduced || skip ? 0 : ms);
  const wait = ms => new Promise(r => setTimeout(r, dur(ms)));

  // ---------- Countdown ----------
  function ready() {
    const left = nextPackAt ? nextPackAt - Date.now() : 0;
    pack.classList.toggle('locked', left > 0 && !busy);
    pack.setAttribute('aria-disabled', String(left > 0));
    hint.hidden = left > 0 || busy;
    let text;
    if (message) {
      text = message;
    } else if (left <= 0) {
      text = 'A pack is ready!';
    } else {
      const s = Math.ceil(left / 1000);
      text = `Next pack in ${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
    }
    if (timer.textContent !== text) timer.textContent = text;
    return left <= 0;
  }
  setInterval(ready, 250);
  ready();

  // ---------- Request (sent on first touch, reused if the tear is abandoned and retried) ----------
  function fetchPack() {
    return request ??= fetch(stage.dataset.openUrl, { method: 'POST', headers: { 'X-CSRFToken': csrf } })
      .then(async r => {
        const data = await r.json().catch(() => ({
          error: r.redirected ? 'Your session expired. Please log in again.' : 'Something went wrong. Try again.',
        }));
        if (!r.ok || !data.cards) throw data;
        return data;
      });
  }

  // ---------- Tear (drag across the pack) ----------
  let tearFrom = null, torn = 0;
  pack.addEventListener('pointerdown', e => {
    FX.unlock();
    message = '';
    if (busy || !ready()) return;
    tearFrom = e.clientX;
    torn = 0;
    pack.setPointerCapture(e.pointerId);
    fetchPack().catch(() => {}); // errors are handled when the tear finishes
  });
  pack.addEventListener('pointermove', e => {
    if (tearFrom === null || busy) return;
    torn = Math.max(torn, Math.abs(e.clientX - tearFrom) / pack.offsetWidth);
    tearLine.style.setProperty('--p', Math.min(torn / TEAR_DONE, 1));
    const r = pack.getBoundingClientRect();
    if (Math.random() < 0.6) FX.burst(e.clientX, r.top + r.height * 0.14, '#fff6c0', 4, 3);
    if (torn >= TEAR_DONE) finishTear();
  });
  pack.addEventListener('pointerup', () => {
    if (!busy) { tearFrom = null; tearLine.style.setProperty('--p', 0); }
  });
  pack.addEventListener('keydown', e => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    FX.unlock();
    message = '';
    if (!busy && ready()) {
      e.preventDefault();
      finishTear();
    }
  });

  async function finishTear() {
    if (busy) return;
    busy = true;
    tearFrom = null;
    hint.hidden = true;
    const r = pack.getBoundingClientRect();
    FX.sound('tear');
    FX.flash('#fff', 250);
    pack.classList.add('torn');
    FX.burst(r.left + r.width / 2, r.top + r.height * 0.14, '#fff3b0', 90, 10, -Math.PI / 2);
    let data;
    try {
      data = await fetchPack();
    } catch (err) {
      return fail(err);
    }
    nextPackAt = new Date(data.next_pack_at);
    const cards = buildStack(data.cards); // images start loading during the tease
    await wait(600);
    // Tease: the pack glows the color of its best card, and rumbles if it's Epic or better.
    const best = Math.max(...data.cards.map(c => c.rarity));
    pack.style.setProperty('--glow', COLOR[best]);
    pack.classList.add('glowing');
    if (best >= 4) { FX.sound('charge'); await FX.shake(packWrap, best === 5 ? 14 : 8, 900); }
    else await wait(500);
    await revealAll(data.cards, cards);
  }

  function fail(err) {
    if (err && err.next_pack_at) nextPackAt = new Date(err.next_pack_at);
    message = (err && err.error) || 'Could not open the pack. Try again.';
    reset();
  }

  // ---------- Reveal ----------
  function buildStack(cards) {
    reveal.innerHTML = '';
    return cards.map((c, i) => {
      const el = document.createElement('div');
      el.className = `flip rarity-${c.slug}`;
      el.style.zIndex = cards.length - i; // first card on top; the best one is last
      el.style.visibility = 'hidden';
      el.innerHTML = `<div class="flip-inner"><div class="flip-face flip-back"><div class="card-back"><span>KOMI</span></div></div>`
        + `<div class="flip-face flip-front">${c.html}</div></div>`;
      el.querySelectorAll('img').forEach(img => { img.loading = 'eager'; });
      reveal.append(el);
      return el;
    });
  }

  const nextTap = () => (skip ? Promise.resolve() : new Promise(res => { pendingTap = res; }));
  function tap() { const res = pendingTap; pendingTap = null; res?.(); }
  reveal.addEventListener('click', tap);
  addEventListener('keydown', e => {
    if (pendingTap && ['Enter', ' ', 'ArrowRight'].includes(e.key)) { e.preventDefault(); tap(); }
  });
  skipBtn.addEventListener('click', () => { skip = true; tap(); });

  async function revealAll(cards, els) {
    reveal.hidden = false;
    skipBtn.hidden = false;
    packWrap.animate([{ transform: 'none', opacity: 1 }, { transform: 'translateY(60vh) rotate(8deg)', opacity: 0 }],
      { duration: dur(600), easing: 'cubic-bezier(.5,0,.75,0)', fill: 'forwards' });
    await Promise.all(els.map((el, i) => {
      el.style.visibility = '';
      return el.animate(
        [{ transform: 'translateY(60vh) scale(.5)', opacity: 0 },
         { transform: `translateY(${i * -3}px) rotate(${(i - 2) * 1.5}deg)`, opacity: 1 }],
        { duration: dur(700), delay: dur(i * 90), easing: 'cubic-bezier(.2,1.4,.4,1)', fill: 'both' }).finished;
    }));
    for (const [i, c] of cards.entries()) {
      await nextTap();
      await flip(els[i], c);
      await nextTap();
      await flyAway(els[i], i);
    }
    showSummary(cards);
  }

  async function flip(el, c) {
    const inner = el.querySelector('.flip-inner'), card = el.querySelector('.card');
    if (c.rarity >= 3 && !skip) { // anticipation: the aura builds, better cards tremble harder
      el.classList.add('charging');
      FX.sound('charge');
      if (c.rarity === 5) { stage.classList.add('dim', 'rays'); await wait(700); }
      await FX.shake(inner, c.rarity * 2, 300 + c.rarity * 150);
    }
    FX.sound('flip');
    const ms = c.rarity === 5 ? 1400 : c.rarity >= 3 ? 800 : 450;
    await inner.animate(
      [{ transform: 'rotateY(0)' }, { transform: 'rotateY(200deg) scale(1.1)', offset: 0.7 }, { transform: 'rotateY(180deg)' }],
      { duration: dur(ms), easing: 'cubic-bezier(.3,.7,.3,1)', fill: 'forwards' }).finished;
    el.classList.remove('charging');
    el.classList.add('revealed');
    if (c.is_new) el.insertAdjacentHTML('beforeend', '<span class="new-badge">NEW!</span>');
    FX.tilt(card);
    if (skip) return;

    const r = el.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
    const color = COLOR[c.rarity];
    if (c.rarity >= 2) FX.burst(x, y, color, 25 * c.rarity, 3 + c.rarity * 2);
    if (c.rarity >= 3) {
      FX.sound(SOUND[c.rarity]);
      FX.flash(color, 120 * c.rarity);
      // light sweeps across the foil once
      card.animate([{ '--mx': '0%', '--my': '0%', '--hyp': 1 }, { '--mx': '100%', '--my': '100%', '--hyp': 0 }],
        { duration: 1200, easing: 'ease-in-out' });
    }
    if (c.rarity >= 4) FX.shake(reveal, (c.rarity - 3) * 10, 500);
    if (c.rarity === 5) {
      for (let k = 0; k < 4; k++) setTimeout(() => {
        FX.burst(0, innerHeight, '#ffd700', 50, 16, -Math.PI / 3);
        FX.burst(innerWidth, innerHeight, '#fff2a8', 50, 16, -2 * Math.PI / 3);
      }, k * 250);
    }
  }

  function flyAway(el, i) {
    stage.classList.remove('dim', 'rays');
    const side = i % 2 ? 1 : -1;
    return el.animate(
      [{ opacity: 1 }, { transform: `translate(${side * 110}vw, -15vh) rotate(${side * 30}deg)`, opacity: 0 }],
      { duration: dur(450), easing: 'cubic-bezier(.5,0,.75,0)', fill: 'forwards' }).finished;
  }

  // ---------- Summary ----------
  function showSummary(cards) {
    stage.classList.remove('dim', 'rays');
    reveal.hidden = true;
    skipBtn.hidden = true;
    const box = $('summaryCards');
    box.innerHTML = '';
    cards.forEach((c, i) => {
      const item = document.createElement('div');
      item.className = 'summary-item';
      item.innerHTML = c.html + (c.is_new ? '<span class="new-badge">NEW!</span>' : '');
      box.append(item);
      FX.tilt(item.querySelector('.card'));
      item.animate([{ transform: 'translateY(40px) scale(.8)', opacity: 0 }, { transform: 'none', opacity: 1 }],
        { duration: dur(400), delay: dur(i * 90), easing: 'cubic-bezier(.2,1.4,.4,1)', fill: 'backwards' });
    });
    summary.hidden = false;
  }

  function reset() {
    busy = false;
    skip = false;
    request = null;
    pendingTap = null;
    summary.hidden = true;
    reveal.hidden = true;
    skipBtn.hidden = true;
    stage.classList.remove('dim', 'rays');
    packWrap.getAnimations().forEach(a => a.cancel());
    pack.classList.remove('torn', 'glowing');
    tearLine.style.setProperty('--p', 0);
    ready();
  }
  $('again').addEventListener('click', () => { message = ''; reset(); });
})();
