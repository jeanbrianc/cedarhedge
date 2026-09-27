'use strict';
const menuButton = document.querySelector('.menu-button');
const navigation = document.getElementById('navigation');
if (menuButton && navigation) {
  const setMenuOpen = (open, returnFocus = false) => {
    navigation.classList.toggle('is-open', open);
    menuButton.setAttribute('aria-expanded', String(open));
    menuButton.querySelector('span').textContent = open ? '−' : '+';
    if (returnFocus) menuButton.focus();
  };
  menuButton.addEventListener('click', () => setMenuOpen(menuButton.getAttribute('aria-expanded') !== 'true'));
  navigation.addEventListener('click', event => {
    if (event.target.closest('a')) setMenuOpen(false);
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && navigation.classList.contains('is-open')) setMenuOpen(false, true);
  });
  document.addEventListener('click', event => {
    if (!event.target.closest('.header-inner')) setMenuOpen(false);
  });
  window.matchMedia('(min-width: 801px)').addEventListener('change', () => setMenuOpen(false));
  menuButton.hidden = false;
  document.documentElement.classList.add('js');
}
const year = document.getElementById('year');
if (year) year.textContent = String(new Date().getFullYear());
