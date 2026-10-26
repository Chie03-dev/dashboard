async function fetchJSON(url){ const r=await fetch(url); if(!r.ok) throw new Error(r.statusText); return r.json(); }
function esc(s){
  return String(s||'').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function skeletonCards(el, n){
  el.innerHTML = Array.from({length:n}).map(()=>'<div class="card skeleton skeleton--card"></div>').join('');
}
function empty(el, msg){
  const tag = el.tagName === 'UL' ? 'li' : 'div';
  el.innerHTML = `<${tag} class="empty">${esc(msg)}</${tag}>`;
}
function imgTag(src, alt){
  if(!src) return '';
  return `<div class="thumb"><img src="${esc(src)}" alt="${esc(alt||'')}" decoding="async" onerror="this.parentElement.classList.add('thumb--broken')" /></div>`;
}
async function loadDeals(){
  skeletonCards(document.getElementById('deals'), 6);
  let items=[];
  try { items=await fetchJSON('/api/deals'); } catch(e){ items=[]; }
  const el=document.getElementById('deals');
  el.innerHTML='';
  if(!items.length){ empty(el,'No deals available'); return; }
  for(const d of items){
    const card=document.createElement('article');
    card.className='card';
    const pct=Math.round(d.savings||0);
    card.innerHTML=`${imgTag(d.thumb,d.title)}
      <div class="card__body">
        <h3>${esc(d.title)}</h3>
        <div class="meta">$${esc(d.salePrice)} <span class="strike">$${esc(d.normalPrice)}</span></div>
        <div class="card__foot">
          ${pct?`<span class="chip chip--accent">${pct}% off</span>`:''}
          <a class="link" href="${esc(d.url||'#')}" target="_blank" rel="noopener">Open</a>
        </div>
      </div>`;
    el.appendChild(card);
  }
}
loadDeals();
