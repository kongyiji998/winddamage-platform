(() => {
  const menu = document.querySelector('.inspection-menu');
  const toggle = menu.querySelector('summary');

  document.addEventListener('click', event => {
    if (!menu.open) return;
    if (!menu.contains(event.target)) {
      menu.open = false;
      return;
    }

    const link = event.target.closest('a');
    if (!link) return;
    if (link.hasAttribute('aria-current') && !event.ctrlKey && !event.metaKey &&
        !event.shiftKey && !event.altKey) {
      event.preventDefault();
    }
    menu.open = false;
    toggle.focus({preventScroll:true});
  });
  menu.addEventListener('focusout', event => {
    if (!menu.contains(event.relatedTarget)) menu.open = false;
  });
  menu.addEventListener('keydown', event => {
    if (event.key === 'Escape' && menu.open) {
      event.preventDefault();
      event.stopPropagation();
      menu.open = false;
      toggle.focus();
    }
  });
  window.addEventListener('blur', () => { menu.open = false; });
  window.addEventListener('hashchange', () => { menu.open = false; });
})();
