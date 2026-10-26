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

// Shared preference helpers and application
window.DP = window.DP || {};
(function(){
  const DP = window.DP;
  DP.get = function(k){ try { return localStorage.getItem(k); } catch(e){ return null; } };
  DP.set = function(k,v){ try { localStorage.setItem(k,v); } catch(e){} };
  DP.remove = function(k){ try { localStorage.removeItem(k); } catch(e){} };
  DP.getJSON = function(k, fallback){ try { const v=localStorage.getItem(k); return v?JSON.parse(v):fallback; } catch(e){ return fallback; } };
  DP.setJSON = function(k,v){ try { localStorage.setItem(k, JSON.stringify(v)); } catch(e){} };

  function applyTheme(){
    const t = DP.get('theme') || 'dark';
    document.body.setAttribute('data-theme', t);
  }
  function applyCompact(){
    const c = DP.get('compactness') || 'comfortable';
    document.body.classList.toggle('compact', c === 'compact');
  }
  function applyReducedMotion(){
    const r = DP.get('reducedMotion') === 'true';
    document.body.classList.toggle('reduce-motion', r);
  }
  function applyWidgetHeight(){
    const h = DP.get('widgetHeight');
    if (h) document.documentElement.style.setProperty('--widget-min-h', h + 'px');
    else document.documentElement.style.removeProperty('--widget-min-h');
  }
  function applyHiddenWidgets(){
    let hidden = [];
    try { hidden = JSON.parse(DP.get('hiddenWidgets') || '[]'); } catch(e){ hidden=[]; }
    hidden.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.style.display = 'none';
    });
  }
  function applyAll(){
    applyTheme();
    applyCompact();
    applyReducedMotion();
    applyWidgetHeight();
    applyHiddenWidgets();
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', applyAll);
  } else {
    applyAll();
  }
  DP.applyAll = applyAll;
  DP.applyTheme = applyTheme;
  DP.applyCompact = applyCompact;
  DP.applyReducedMotion = applyReducedMotion;
  DP.applyWidgetHeight = applyWidgetHeight;
  DP.applyHiddenWidgets = applyHiddenWidgets;
})();
