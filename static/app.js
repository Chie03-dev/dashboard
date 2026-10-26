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

function updateViewAll(id, total){
  const el=document.getElementById(id);
  if(!el) return;
  el.textContent = total>2 ? `View all ${total} →` : 'View all →';
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
  try {
    allGames=await fetchJSON('/api/games');
  } catch(e){ allGames=[]; }
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
  if(!sorted.length){ empty(el,'No free games yet'); updateViewAll('gamesViewAll', 0); return; }
  // render preview
  for(const g of sorted.slice(0,2)){
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
  updateViewAll('gamesViewAll', sorted.length);
}

async function loadDev(){
  let items=[];
  try { items=await fetchJSON('/api/dev'); } catch(e){ items=[]; }
  const el=document.getElementById('dev');
  el.innerHTML='';
  if(!items.length){ empty(el,'No news items'); updateViewAll('newsViewAll', 0); return; }
  for(const it of items.slice(0,5)){
    const li=document.createElement('li');
    li.className='feed__item';
    li.innerHTML=`<a href="${esc(it.url||'#')}" target="_blank" rel="noopener">${esc(it.title)}</a> <span class="badge">${esc(it.source||'')}</span>`;
    el.appendChild(li);
  }
  updateViewAll('newsViewAll', items.length);
}

async function loadDeals(){
  let items=[];
  try { items=await fetchJSON('/api/deals'); } catch(e){ items=[]; }
  const el=document.getElementById('deals');
  el.innerHTML='';
  if(!items.length){ empty(el,'No deals available'); updateViewAll('dealsViewAll', 0); return; }
  for(const d of items.slice(0,2)){
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
  updateViewAll('dealsViewAll', items.length);
}

async function loadWeather(){
  try {
    const w=await fetchJSON('/api/weather');
    const code=w.code!=null?` · code ${esc(w.code)}`:'';
    document.getElementById('weather').innerHTML = w.temperature!=null
      ? `<div class="weather__temp">${esc(w.temperature)}°C</div><div class="weather__meta">Wind ${esc(w.wind)} km/h${code}</div>`
      : '<div class="empty">Unavailable</div>';
  } catch(e){
    document.getElementById('weather').innerHTML='<div class="empty">Unavailable</div>';
  }
}
async function loadDigest(){
  try {
    const d=await fetchJSON('/api/digest');
    document.getElementById('digest').textContent=d.text||'';
  } catch(e){
    document.getElementById('digest').textContent='Unable to load digest.';
  }
}

async function loadWishlist(){
  let items=[];
  try { items=await fetchJSON('/api/wishlist'); } catch(e){ items=[]; }
  const el=document.getElementById('wishlist');
  el.innerHTML='';
  if(!items.length){ empty(el,'No wishlist items'); return; }
  for(const it of items){
    const li=document.createElement('li');
    li.className='list__item';
    li.innerHTML=`<span>${esc(it.name)}</span> <button data-id="${esc(it.id)}" class="btn btn--ghost wishDel" type="button" aria-label="Remove ${esc(it.name)}">×</button>`;
    el.appendChild(li);
  }
  el.querySelectorAll('.wishDel').forEach(b=>b.addEventListener('click',async e=>{
    await fetch('/api/wishlist/'+encodeURIComponent(e.currentTarget.dataset.id),{method:'DELETE'});
    await loadWishlist();
  }));
}

async function refresh(){
  const btn=document.getElementById('refresh');
  btn.disabled=true;
  try {
    await fetch('/api/refresh',{method:'POST'});
    await Promise.all([loadGames(),loadDev(),loadDigest(),loadWishlist(),loadDeals(),loadWeather()]);
  } finally { btn.disabled=false; }
}

document.getElementById('refresh').addEventListener('click',refresh);
document.getElementById('gameSort').addEventListener('change',renderGames);
document.getElementById('catFilter').addEventListener('change',renderGames);
document.getElementById('wishAdd').addEventListener('click',addWish);
document.getElementById('wishInput').addEventListener('keydown',e=>{ if(e.key==='Enter') addWish(); });

async function addWish(){
  const input=document.getElementById('wishInput');
  const v=input.value.trim();
  if(!v) return;
  await fetch('/api/wishlist',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:v})});
  input.value='';
  await loadWishlist();
}

Promise.all([loadGames(),loadDev(),loadDigest(),loadWishlist(),loadDeals(),loadWeather()]);
const chatMessages=[];
function appendChat(role, text){
  const log=document.getElementById('chatLog');
  if(!log) return;
  const div=document.createElement('div');
  div.className='chat-msg chat-msg--'+role;
  div.textContent=text;
  log.appendChild(div);
  log.scrollTop=log.scrollHeight;
}
async function sendChat(){
  const input=document.getElementById('chatInput');
  const btn=document.getElementById('chatSend');
  const v=input.value.trim();
  if(!v) return;
  input.value='';
  appendChat('user', v);
  chatMessages.push({role:'user', content:v});
  btn.disabled=true;
  try {
    const r=await fetch('/api/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({messages:chatMessages, model: localStorage.getItem('chatModel') || undefined})});
    const data=await r.json();
    if(!r.ok) throw new Error(data.detail||r.statusText);
    const reply=data.reply||'No response';
    appendChat('assistant', reply);
    chatMessages.push({role:'assistant', content:reply});
  } catch(e){
    appendChat('assistant', 'Error: '+e.message);
  } finally {
    btn.disabled=false;
  }
}
const chatSendBtn=document.getElementById('chatSend');
if(chatSendBtn){ chatSendBtn.addEventListener('click', sendChat); }
const chatInputEl=document.getElementById('chatInput');
if(chatInputEl){ chatInputEl.addEventListener('keydown', e=>{ if(e.key==='Enter') sendChat(); }); }
