(() => {
  const key = 'spotlight-site-appearance';
  const root = document.documentElement;
  let saved;
  try { saved = localStorage.getItem(key); } catch {}
  const preferred = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  root.dataset.appearance = saved === 'dark' || saved === 'light' ? saved : preferred;
  function sync() {
    document.querySelectorAll('[data-appearance-choice]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.appearanceChoice === root.dataset.appearance));
    });
  }
  document.addEventListener('DOMContentLoaded', () => {
    sync();
    document.querySelectorAll('[data-appearance-choice]').forEach(button => button.addEventListener('click', () => {
      root.dataset.appearance = button.dataset.appearanceChoice;
      try { localStorage.setItem(key, root.dataset.appearance); } catch {}
      sync();
    }));
  });
})();
