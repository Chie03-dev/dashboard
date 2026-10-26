async function fetchJSON(url){ const r=await fetch(url); if(!r.ok) throw new Error(r.statusText); return r.json(); }
function esc(s){
  return String(s||'').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function skeletonLines(el, n){
  el.innerHTML = Array.from({length:n}).map(()=>'<div class="skeleton skeleton--line"></div>').join('');
}
function empty(el, msg){
  const tag = el.tagName === 'UL' ? 'li' : 'div';
  el.innerHTML = `<${tag} class="empty">${esc(msg)}</${tag}>`;
}
async function loadDev(){
  skeletonLines(document.getElementById('dev'), 6);
  let items=[];
  try { items=await fetchJSON('/api/dev'); } catch(e){ items=[]; }
  const el=document.getElementById('dev');
  el.innerHTML='';
  if(!items.length){ empty(el,'No news items'); return; }
  for(const it of items){
    const li=document.createElement('li');
    li.className='feed__item';
    li.innerHTML=`<a href="${esc(it.url||'#')}" target="_blank" rel="noopener">${esc(it.title)}</a> <span class="badge">${esc(it.source||'')}</span>`;
    el.appendChild(li);
  }
}
loadDev();
