const input = document.getElementById('modelInput');
const status = document.getElementById('settingsStatus');
input.value = localStorage.getItem('chatModel') || '';
document.getElementById('saveSettings').addEventListener('click', () => {
  localStorage.setItem('chatModel', input.value.trim());
  status.textContent = 'Saved';
});
