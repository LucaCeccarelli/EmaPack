// Card editor: mirrors the form into the live preview card as the player types.
(() => {
  const form = document.getElementById('card-editor');
  const card = document.querySelector('#preview .card');
  const $ = sel => card.querySelector(sel);
  const field = name => form.elements[name];

  // Text: name, tagline, and the initial letter shown when there's no logo.
  const nameEl = $('.card-name'), taglineEl = $('.card-tagline');
  function updateText() {
    nameEl.textContent = field('name').value.trim() || 'Your card';
    taglineEl.textContent = field('tagline').value.trim();
    const initial = $('.card-logo span');
    if (initial) initial.textContent = nameEl.textContent[0].toUpperCase();
  }
  field('name').addEventListener('input', updateText);
  field('tagline').addEventListener('input', updateText);

  // Colors drive the card's gradient.
  function updateColors() {
    card.style.setProperty('--c1', field('primary_color').value);
    card.style.setProperty('--c2', field('secondary_color').value);
  }
  field('primary_color').addEventListener('input', updateColors);
  field('secondary_color').addEventListener('input', updateColors);

  // Images: shown from the local file, nothing is uploaded until the form is sent.
  function bindImage(name, boxSel, fallback) {
    const input = field(name), box = $(boxSel), label = input.closest('.upload');
    let url = null;
    input.addEventListener('change', () => {
      if (url) URL.revokeObjectURL(url);
      const file = input.files[0];
      url = file && file.type.startsWith('image/') ? URL.createObjectURL(file) : null;
      if (url) {
        const img = document.createElement('img');
        img.alt = '';
        img.src = url;
        box.replaceChildren(img);
      } else {
        box.replaceChildren(...fallback());
      }
      label.classList.toggle('has-file', !!url);
      label.style.setProperty('--thumb', url ? `url("${url}")` : 'none');
    });
  }
  bindImage('logo', '.card-logo', () => { const s = document.createElement('span'); s.textContent = nameEl.textContent[0].toUpperCase(); return [s]; });
  bindImage('banner', '.card-art', () => []);

  // Character counters next to the labels.
  form.querySelectorAll('.count').forEach(counter => {
    const input = document.getElementById(counter.dataset.for);
    const update = () => { counter.textContent = `${input.value.length}/${input.maxLength}`; };
    input.addEventListener('input', update);
    update();
  });

  // Preview-only rarity switch (the admin picks the real one).
  const rarityLabel = $('.card-rarity');
  document.querySelectorAll('.rarity-toggle button').forEach(btn => btn.addEventListener('click', () => {
    card.className = card.className.replace(/rarity-\w+/, `rarity-${btn.dataset.rarity}`);
    rarityLabel.textContent = btn.textContent;
    document.querySelectorAll('.rarity-toggle button').forEach(b => b.setAttribute('aria-pressed', String(b === btn)));
  }));

  updateText();
  updateColors();
  FX.tilt(card);
})();
