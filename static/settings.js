(function(){
  const $ = (id) => document.getElementById(id);
  const DP = window.DP || {};
  const get = DP.get || function(k){ try { return localStorage.getItem(k); } catch(e){ return null; } };
  const set = DP.set || function(k,v){ try { localStorage.setItem(k,v); } catch(e){} };
  const remove = DP.remove || function(k){ try { localStorage.removeItem(k); } catch(e){} };

  let storageAvailable = true;
  try { localStorage.setItem('__t', '1'); localStorage.removeItem('__t'); } catch (e) { storageAvailable = false; }

  const widgets = [
    {id:'w-games', label:'Free Games'},
    {id:'w-deals', label:'Discounts'},
    {id:'w-news', label:'Game News'},
    {id:'w-digest', label:'Daily Digest'},
    {id:'w-wishlist', label:'Wishlist'},
    {id:'w-weather', label:'Weather'},
    {id:'w-youtube', label:'YouTube'},
    {id:'w-email', label:'Email'},
    {id:'w-steam', label:'Steam'},
    {id:'w-chat', label:'Chat'},
  ];

  function load() {
    if (!storageAvailable) {
      $('settingsStatus').textContent = 'localStorage unavailable; using server env defaults.';
      return;
    }
    $('baseUrlInput').value = get('llmBaseUrl') || '';
    $('apiKeyInput').value = get('llmApiKey') || '';
    $('modelInput').value = get('llmModel') || get('chatModel') || '';
    $('temperatureInput').value = get('llmTemperature') || '';
    $('maxTokensInput').value = get('llmMaxTokens') || '';
    $('systemPromptInput').value = get('systemPrompt') || '';
    $('requestTimeoutInput').value = get('requestTimeout') || '';
    $('weatherLatInput').value = get('weatherLat') || '';
    $('weatherLonInput').value = get('weatherLon') || '';
    $('themeInput').value = get('theme') || 'dark';
    $('compactnessInput').value = get('compactness') || 'comfortable';
    $('widgetHeightInput').value = get('widgetHeight') || '';
    $('reducedMotionInput').checked = get('reducedMotion') === 'true';
    $('defaultGameSortInput').value = get('defaultGameSort') || 'created';
    $('defaultGameCatInput').value = get('defaultGameCat') || '';

    const hidden = DP.getJSON ? DP.getJSON('hiddenWidgets', []) : (function(){ try { return JSON.parse(get('hiddenWidgets')||'[]'); } catch(e){ return []; } })();
    const box = $('widgetVisibility');
    box.innerHTML = '';
    widgets.forEach(w => {
      const lbl = document.createElement('label');
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.dataset.widget = w.id;
      cb.checked = !hidden.includes(w.id);
      lbl.appendChild(cb);
      lbl.appendChild(document.createTextNode(' ' + w.label));
      box.appendChild(lbl);
    });
  }

  function collectHidden() {
    const hidden = [];
    document.querySelectorAll('#widgetVisibility input[type="checkbox"]').forEach(cb => {
      if (!cb.checked) hidden.push(cb.dataset.widget);
    });
    return hidden;
  }

  function save() {
    if (!storageAvailable) {
      $('settingsStatus').textContent = 'Cannot save: localStorage unavailable.';
      return;
    }
    set('llmBaseUrl', $('baseUrlInput').value.trim());
    set('llmApiKey', $('apiKeyInput').value.trim());
    set('llmModel', $('modelInput').value.trim());
    set('chatModel', $('modelInput').value.trim());
    set('llmTemperature', $('temperatureInput').value.trim());
    set('llmMaxTokens', $('maxTokensInput').value.trim());
    set('systemPrompt', $('systemPromptInput').value.trim());
    set('requestTimeout', $('requestTimeoutInput').value.trim());
    set('weatherLat', $('weatherLatInput').value.trim());
    set('weatherLon', $('weatherLonInput').value.trim());
    set('theme', $('themeInput').value);
    set('compactness', $('compactnessInput').value);
    set('widgetHeight', $('widgetHeightInput').value.trim());
    set('reducedMotion', $('reducedMotionInput').checked ? 'true' : 'false');
    set('defaultGameSort', $('defaultGameSortInput').value);
    set('defaultGameCat', $('defaultGameCatInput').value.trim());
    set('hiddenWidgets', JSON.stringify(collectHidden()));
    if (DP.applyAll) DP.applyAll();
    $('settingsStatus').textContent = 'Saved';
  }

  async function testConnection() {
    const result = $('testResult');
    result.textContent = 'Testing...';
    try {
      const payload = {
        base_url: $('baseUrlInput').value.trim() || undefined,
        api_key: $('apiKeyInput').value.trim() || undefined,
        model: $('modelInput').value.trim() || undefined,
      };
      const r = await fetch('/api/llm/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.assign({ prompt: 'Reply with OK.' }, payload)),
      });
      const data = await r.json();
      if (data.ok) {
        result.textContent = 'Success: ' + (data.model || '') + ' (' + data.latency_ms + ' ms)';
      } else {
        result.textContent = 'Failed: ' + (data.error || r.statusText);
      }
    } catch (e) {
      result.textContent = 'Failed: ' + e.message;
    }
  }

  function exportSettings() {
    const data = {};
    const keys = ['llmBaseUrl','llmApiKey','llmModel','chatModel','llmTemperature','llmMaxTokens','systemPrompt','requestTimeout','weatherLat','weatherLon','theme','compactness','widgetHeight','reducedMotion','defaultGameSort','defaultGameCat','hiddenWidgets'];
    keys.forEach(k => { const v = get(k); if (v !== null) data[k] = v; });
    const blob = new Blob([JSON.stringify(data, null, 2)], {type:'application/json'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'dashboard-settings.json';
    a.click();
    URL.revokeObjectURL(url);
    $('dataStatus').textContent = 'Exported';
  }

  function importSettings(file) {
    const reader = new FileReader();
    reader.onload = function(e) {
      try {
        const data = JSON.parse(e.target.result);
        Object.keys(data).forEach(k => set(k, data[k]));
        load();
        if (DP.applyAll) DP.applyAll();
        $('dataStatus').textContent = 'Imported';
      } catch (err) {
        $('dataStatus').textContent = 'Import failed: ' + err.message;
      }
    };
    reader.readAsText(file);
  }

  function resetSettings() {
    const keys = ['llmBaseUrl','llmApiKey','llmModel','chatModel','llmTemperature','llmMaxTokens','systemPrompt','requestTimeout','weatherLat','weatherLon','theme','compactness','widgetHeight','reducedMotion','defaultGameSort','defaultGameCat','hiddenWidgets'];
    keys.forEach(k => remove(k));
    load();
    if (DP.applyAll) DP.applyAll();
    $('settingsStatus').textContent = 'Reset to defaults';
    $('dataStatus').textContent = 'Reset complete';
  }

  // wire
  $('saveSettings').addEventListener('click', save);
  $('testSettings').addEventListener('click', testConnection);
  $('clearChatHistory').addEventListener('click', function(){
    set('clearChatHistory', 'true');
    $('settingsStatus').textContent = 'Chat history will clear on next dashboard load';
  });
  $('exportSettings').addEventListener('click', exportSettings);
  $('importSettings').addEventListener('click', function(){ $('importFile').click(); });
  $('importFile').addEventListener('change', function(e){
    if (e.target.files && e.target.files[0]) importSettings(e.target.files[0]);
    e.target.value = '';
  });
  $('resetSettings').addEventListener('click', resetSettings);

  load();
  if (DP.applyAll) DP.applyAll();
})();
