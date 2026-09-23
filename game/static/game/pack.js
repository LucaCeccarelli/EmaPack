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
    hint.style.visibility = left > 0 || busy ? 'hidden' : ''; // keep its space so the pack never jumps
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

  // ---------- Pack tilt: it leans toward the pointer and catches the light ----------
  function tiltPack(e) {
    const r = pack.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width, py = (e.clientY - r.top) / r.height;
    pack.style.setProperty('--rx', `${(0.5 - py) * 14}deg`);
    pack.style.setProperty('--ry', `${(px - 0.5) * 18}deg`);
    pack.style.setProperty('--gx', `${px * 100}%`);
    pack.style.setProperty('--gy', `${py * 100}%`);
  }
  const untiltPack = () => ['--rx', '--ry', '--gx', '--gy'].forEach(v => pack.style.removeProperty(v));
  pack.addEventListener('pointerleave', () => { if (tearFrom === null) untiltPack(); });

  // ---------- Tear (drag across the pack, either direction) ----------
  let tearFrom = null, torn = 0, tearDir = 1;
  pack.addEventListener('pointerdown', e => {
    FX.unlock();
    message = '';
    if (busy || !ready()) return;
    tearFrom = e.clientX;
    torn = 0;
    pack.classList.add('tearing');
    pack.setPointerCapture(e.pointerId);
    fetchPack().catch(() => {}); // errors are handled when the tear finishes
  });
  pack.addEventListener('pointermove', e => {
    if (busy) return;
    tiltPack(e);
    if (tearFrom === null) return;
    const dx = e.clientX - tearFrom;
    if (Math.abs(dx) > 4) {
      tearDir = Math.sign(dx);
      pack.classList.toggle('tear-left', tearDir < 0); // the tear line grows from the side you started on
    }
    torn = Math.max(torn, Math.abs(dx) / pack.offsetWidth);
    tearLine.style.setProperty('--p', Math.min(torn / TEAR_DONE, 1));
    const r = pack.getBoundingClientRect();
    if (Math.random() < 0.6) FX.burst(e.clientX, r.top + r.height * 0.14, '#fff6c0', 4, 3);
    if (torn >= TEAR_DONE) finishTear();
  });
  const cancelTear = () => {
    if (busy) return;
    tearFrom = null;
    pack.classList.remove('tearing');
    tearLine.style.setProperty('--p', 0);
  };
  pack.addEventListener('pointerup', cancelTear);
  pack.addEventListener('pointercancel', cancelTear);
  pack.addEventListener('keydown', e => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    FX.unlock();
    message = '';
    if (!busy && ready()) {
      e.preventDefault();
      tearDir = 1;
      finishTear();
    }
  });

  async function finishTear() {
    if (busy) return;
    busy = true;
    tearFrom = null;
    hint.style.visibility = 'hidden';
    const r = pack.getBoundingClientRect();
    FX.sound('tear');
    FX.buzz(35);
    FX.flash('#fff', 250);
    pack.classList.remove('tearing');
    pack.style.setProperty('--dir', tearDir);
    untiltPack();
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
    reveal.innerHTML = '<p class="reveal-hint" id="revealHint" aria-live="polite"></p>';
    return cards.map((c, i) => {
      const el = document.createElement('div');
      el.className = `flip rarity-${c.slug}`;
      el.style.zIndex = cards.length - i; // first card on top; the best one is last
      el.style.visibility = 'hidden';
      el.innerHTML = `<div class="flip-inner"><div class="flip-face flip-back"><div class="card-back"><span>EMA</span></div></div>`
        + `<div class="flip-face flip-front">${c.html}</div></div>`;
      el.querySelectorAll('img').forEach(img => { img.loading = 'eager'; });
      reveal.append(el);
      return el;
    });
  }

  const nextTap = () => (skip ? Promise.resolve() : new Promise(res => { pendingTap = res; }));
  function tap() { const res = pendingTap; pendingTap = null; res?.(); }
  let suppressClick = false; // a swipe ends with a click event; don't count it twice
  reveal.addEventListener('click', () => { if (suppressClick) { suppressClick = false; return; } tap(); });
  reveal.addEventListener('pointerdown', () => { suppressClick = false; }, true);
  addEventListener('keydown', e => {
    if (pendingTap && ['Enter', ' ', 'ArrowRight'].includes(e.key)) { e.preventDefault(); tap(); }
  });
  skipBtn.addEventListener('click', () => { skip = true; tap(); });

  async function revealAll(cards, els) {
    reveal.hidden = false;
    skipBtn.hidden = false;
    // 1. Cards rise halfway out of the torn opening (hidden below its edge).
    // 2. The empty pack drops away completely.  3. Only then the cards settle, ready to open.
    const pr = pack.getBoundingClientRect();
    const fromY = pr.top + pr.height * 0.35 - innerHeight / 2, outY = fromY - 110;
    const edge = Math.max(0, innerHeight - (pr.top + pr.height * 0.15));
    reveal.style.clipPath = `inset(0 0 ${edge}px 0)`;
    await Promise.all(els.map((el, i) => {
      el.style.visibility = '';
      return el.animate(
        [{ transform: `translateY(${fromY}px) scale(.5)`, opacity: 0 },
         { transform: `translateY(${outY}px) scale(.62) rotate(${(i - 2) * 2}deg)`, opacity: 1 }],
        { duration: dur(650), delay: dur(i * 90), easing: 'cubic-bezier(.2,.8,.3,1)', fill: 'both' }).finished;
    }));
    const fall = { duration: dur(700), easing: 'cubic-bezier(.5,0,.75,0)', fill: 'forwards' };
    reveal.animate([{ clipPath: `inset(0 0 ${edge}px 0)` }, { clipPath: 'inset(0 0 0 0)' }], fall);
    await packWrap.animate([{ transform: 'none', opacity: 1 }, { transform: 'translateY(60vh) rotate(8deg)', opacity: 0 }], fall).finished;
    reveal.getAnimations().forEach(a => a.cancel());
    reveal.style.clipPath = '';
    await Promise.all(els.map((el, i) => el.animate(
      [{ transform: `translateY(${outY}px) scale(.62) rotate(${(i - 2) * 2}deg)` },
       { transform: `translateY(${i * -3}px) rotate(${(i - 2) * 1.5}deg)` }],
      { duration: dur(550), delay: dur(i * 40), easing: 'cubic-bezier(.3,1.3,.4,1)', fill: 'both' }).finished));
    const hintText = $('revealHint');
    for (const [i, c] of cards.entries()) {
      hintText.textContent = i === 0 ? 'Tap to reveal' : '';
      if (c.rarity >= 3) els[i].classList.add('hinting'); // Hearthstone-style: the back glows its rarity color
      await nextTap();
      await flip(els[i], c);
      hintText.textContent = i === 0 ? 'Swipe it away, or tap for the next card' : '';
      const dir = await swipeOrTap(els[i]);
      await flyAway(els[i], i, dir);
    }
    showSummary(cards);
  }

  async function flip(el, c) {
    const inner = el.querySelector('.flip-inner'), card = el.querySelector('.card');
    el.classList.remove('hinting');
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
      FX.buzz(c.rarity === 5 ? [60, 40, 60, 40, 160] : c.rarity === 4 ? [50, 30, 90] : 40);
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

  // Resolves with the throw direction (-1 / 1) once the revealed card is swiped far enough, or 0 on a tap.
  function swipeOrTap(el) {
    if (skip) return Promise.resolve(0);
    return new Promise(res => {
      let from = null, dx = 0, dy = 0;
      const done = dir => {
        el.onpointerdown = el.onpointermove = el.onpointerup = el.onpointercancel = null;
        pendingTap = null;
        res(dir);
      };
      pendingTap = () => done(0); // tap, Enter/→ and Skip still work
      el.onpointerdown = e => { from = [e.clientX, e.clientY]; el.setPointerCapture(e.pointerId); el.style.transition = 'none'; };
      el.onpointermove = e => {
        if (!from) return;
        dx = e.clientX - from[0]; dy = e.clientY - from[1];
        el.style.translate = `${dx}px ${dy}px`;
        el.style.rotate = `${dx / 14}deg`;
      };
      el.onpointerup = el.onpointercancel = () => {
        if (!from) return;
        from = null;
        if (Math.abs(dx) > 6 || Math.abs(dy) > 6) suppressClick = true;
        if (Math.abs(dx) > 90) return done(Math.sign(dx));
        el.style.transition = 'translate .35s cubic-bezier(.3,1.5,.5,1), rotate .35s'; // not far enough: spring back
        el.style.translate = el.style.rotate = '';
        dx = dy = 0;
      };
    });
  }

  function flyAway(el, i, dir = 0) {
    stage.classList.remove('dim', 'rays');
    const side = dir || (i % 2 ? 1 : -1);
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
    pack.classList.remove('torn', 'glowing', 'tearing', 'tear-left');
    pack.style.removeProperty('--glow');
    tearFrom = null;
    untiltPack();
    tearLine.style.setProperty('--p', 0);
    ready();
  }
  $('again').addEventListener('click', () => { message = ''; reset(); });
})();
