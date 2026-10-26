async function fetchJSON(url){ const r=await fetch(url); if(!r.ok) throw new Error(r.statusText); return r.json(); }
function countdown(end){
  if(!end) return '';
  const t=new Date(end).getTime();
  if(isNaN(t)) return '';
  const diff=t-Date.now();
  if(diff<=0) return 'Expired';
  const h=Math.floor(diff/3600000);
  const m=Math.floor((diff%3600000)/60000);
  return `Ends in ${h}h ${m}m`;
}
function esc(s){
  return String(s||'').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function empty(el, msg){
  const tag = el.tagName === 'UL' ? 'li' : 'div';
  el.innerHTML = `<${tag} class="empty">${esc(msg)}</${tag}>`;
}
function imgTag(src, alt){
  if(!src) return '';
  return `<div class="thumb"><img src="${esc(src)}" alt="${esc(alt||'')}" decoding="async" onerror="this.parentElement.classList.add('thumb--broken')" /></div>`;
}

let allGames=[];
async function loadGames(){
  try { allGames=await fetchJSON('/api/games'); } catch(e){ allGames=[]; }
  const cats=[...new Set(allGames.map(g=>g.category).filter(Boolean))].sort();
  const sel=document.getElementById('catFilter');
  sel.innerHTML='<option value="">All</option>'+cats.map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join('');
  renderGames();
}
function renderGames(){
  const mode=document.getElementById('gameSort').value;
  const cat=document.getElementById('catFilter').value;
  const filtered=cat?allGames.filter(g=>g.category===cat):allGames;
  const sorted=[...filtered].sort((a,b)=>{
    if(mode==='platform') return String(a.platform||'').localeCompare(String(b.platform||''));
    if(mode==='end'){ const ta=a.end_date?new Date(a.end_date).getTime():Infinity; const tb=b.end_date?new Date(b.end_date).getTime():Infinity; return ta-tb; }
    if(mode==='title') return String(a.title||'').localeCompare(String(b.title||''));
    return new Date(b.created_at||0).getTime()-new Date(a.created_at||0).getTime();
  });
  const el=document.getElementById('games');
  el.innerHTML='';
  if(!sorted.length){ empty(el,'No free games yet'); return; }
  for(const g of sorted){
    const card=document.createElement('article');
    card.className='card';
    const cd=countdown(g.end_date);
    card.innerHTML=`${imgTag(g.thumbnail,g.title)}
      <div class="card__body">
        <h3>${esc(g.title)}</h3>
        <div class="meta">${esc(g.category||'Game')} · ${esc(g.platform||'')} · ${esc(g.source||'')}</div>
        <div class="card__foot">
          ${cd?`<span class="chip ${cd==='Expired'?'chip--muted':''}">${esc(cd)}</span>`:''}
          <a class="link" href="${esc(g.url||'#')}" target="_blank" rel="noopener">Open</a>
        </div>
      </div>`;
    el.appendChild(card);
  }
}
document.getElementById('gameSort').addEventListener('change',renderGames);
document.getElementById('catFilter').addEventListener('change',renderGames);
loadGames();
