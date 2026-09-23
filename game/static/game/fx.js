// Visual/audio effects shared by the pack opening and the collection.
window.FX = (() => {
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let canvas, ctx, particles = [], running = false, audio;

  function init(c) {
    canvas = c;
    ctx = c.getContext('2d');
    resize();
    addEventListener('resize', resize);
  }

  function resize() {
    const dpr = devicePixelRatio || 1;
    canvas.width = innerWidth * dpr;
    canvas.height = innerHeight * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function burst(x, y, color, count = 60, speed = 8, angle = null) {
    if (reduced || !ctx) return;
    for (let i = 0; i < count; i++) {
      const a = angle === null ? Math.random() * Math.PI * 2 : angle + (Math.random() - 0.5);
      const v = speed * (0.3 + Math.random());
      particles.push({
        x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life: 1,
        decay: 0.008 + Math.random() * 0.02, size: 1.5 + Math.random() * 3.5,
        color, streak: Math.random() < 0.35,
      });
    }
    if (!running) { running = true; requestAnimationFrame(tick); }
  }

  function tick() {
    ctx.clearRect(0, 0, innerWidth, innerHeight);
    ctx.globalCompositeOperation = 'lighter'; // overlapping sparks add up to white-hot
    particles = particles.filter(p => p.life > 0);
    for (const p of particles) {
      p.x += p.vx; p.y += p.vy; p.vy += 0.12; p.vx *= 0.985; p.life -= p.decay;
      ctx.globalAlpha = Math.max(p.life, 0);
      ctx.fillStyle = p.color;
      if (p.streak) {
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(Math.atan2(p.vy, p.vx));
        ctx.fillRect(-p.size * 3, -p.size / 4, p.size * 6, p.size / 2);
        ctx.restore();
      } else {
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size * p.life, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    ctx.globalAlpha = 1;
    if (particles.length) requestAnimationFrame(tick); else running = false;
  }

  function flash(color = '#fff', ms = 300) {
    if (reduced) return;
    const d = document.createElement('div');
    d.className = 'fx-flash';
    d.style.background = color;
    document.body.append(d);
    d.animate([{ opacity: 0.85 }, { opacity: 0 }], { duration: ms, easing: 'ease-out' }).finished.then(() => d.remove());
  }

  function shake(el, px = 8, ms = 400) {
    if (reduced) return Promise.resolve();
    const frames = [];
    for (let i = 0; i < 10; i++) {
      frames.push({ transform: `translate(${(Math.random() - 0.5) * 2 * px}px, ${(Math.random() - 0.5) * 2 * px}px)` });
    }
    frames.push({ transform: 'none' });
    return el.animate(frames, { duration: ms }).finished;
  }

  // --- Sound: tiny Web Audio synth, no files to load ---
  function tone(freq, dur, type = 'sine', gain = 0.12, when = 0, slideTo = null) {
    audio ??= new AudioContext();
    const t = audio.currentTime + when, o = audio.createOscillator(), g = audio.createGain();
    o.type = type;
    o.frequency.setValueAtTime(freq, t);
    if (slideTo) o.frequency.exponentialRampToValueAtTime(slideTo, t + dur);
    g.gain.setValueAtTime(gain, t);
    g.gain.exponentialRampToValueAtTime(0.001, t + dur);
    o.connect(g).connect(audio.destination);
    o.start(t);
    o.stop(t + dur);
  }

  function noise(dur, gain = 0.25) {
    audio ??= new AudioContext();
    const len = Math.floor(audio.sampleRate * dur), buf = audio.createBuffer(1, len, audio.sampleRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < len; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / len);
    const src = audio.createBufferSource(), filter = audio.createBiquadFilter(), g = audio.createGain();
    filter.type = 'bandpass';
    filter.frequency.setValueAtTime(3000, audio.currentTime);
    filter.frequency.exponentialRampToValueAtTime(600, audio.currentTime + dur);
    g.gain.value = gain;
    src.buffer = buf;
    src.connect(filter).connect(g).connect(audio.destination);
    src.start();
  }

  const chord = (notes, type, gap, dur) => notes.forEach((f, i) => tone(f, dur, type, 0.1, i * gap));
  const sounds = {
    tear: () => noise(0.4),
    flip: () => tone(420, 0.09, 'triangle', 0.08, 0, 900),
    charge: () => tone(160, 0.9, 'sawtooth', 0.04, 0, 900),
    rare: () => chord([523, 659, 784], 'sine', 0.07, 0.5),
    epic: () => chord([523, 659, 784, 1047], 'triangle', 0.08, 0.7),
    legendary: () => { tone(70, 1.4, 'sawtooth', 0.1, 0, 35); chord([523, 659, 784, 1047, 1319, 1568], 'sine', 0.09, 1.2); },
  };

  function sound(name) {
    try { sounds[name]?.(); } catch { /* audio unavailable: stay silent */ }
  }

  function tilt(el) {
    const vars = ['--rx', '--ry', '--mx', '--my', '--hyp'];
    el.addEventListener('pointermove', e => {
      const r = el.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width, py = (e.clientY - r.top) / r.height;
      el.style.setProperty('--rx', `${(0.5 - py) * 20}deg`);
      el.style.setProperty('--ry', `${(px - 0.5) * 24}deg`);
      el.style.setProperty('--mx', `${px * 100}%`);
      el.style.setProperty('--my', `${py * 100}%`);
      el.style.setProperty('--hyp', Math.min(1, Math.hypot(px - 0.5, py - 0.5) * 2).toFixed(3));
    });
    el.addEventListener('pointerleave', () => vars.forEach(v => el.style.removeProperty(v)));
  }

  return { reduced, init, burst, flash, shake, sound, tilt };
})();
