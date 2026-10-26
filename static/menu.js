const menuToggle=document.getElementById('menuToggle');
const sideMenu=document.getElementById('sideMenu');
const menuOverlay=document.getElementById('menuOverlay');
const menuClose=document.getElementById('menuClose');
function openMenu(){
  if(!sideMenu) return;
  sideMenu.classList.add('is-open');
  sideMenu.setAttribute('aria-hidden','false');
  if(menuOverlay) menuOverlay.hidden=false;
  if(menuToggle) menuToggle.setAttribute('aria-expanded','true');
}
function closeMenu(){
  if(!sideMenu) return;
  sideMenu.classList.remove('is-open');
  sideMenu.setAttribute('aria-hidden','true');
  if(menuOverlay) menuOverlay.hidden=true;
  if(menuToggle) menuToggle.setAttribute('aria-expanded','false');
}
if(menuToggle) menuToggle.addEventListener('click', openMenu);
if(menuClose) menuClose.addEventListener('click', closeMenu);
if(menuOverlay) menuOverlay.addEventListener('click', closeMenu);
document.addEventListener('keydown', e=>{ if(e.key==='Escape') closeMenu(); });
