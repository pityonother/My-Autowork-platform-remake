const CONFIG = window.BookingTmsCheckerConfig || {};
const DEFAULT_SERVER_BASE = CONFIG.defaultServerBase || 'https://192.168.10.205';
const STORAGE_KEY = 'bookingServerBase';

function normalizeBase(value) {
  const text = String(value || '').trim() || DEFAULT_SERVER_BASE;
  return text.replace(/\/+$/, '');
}

const input = document.getElementById('server-base');
const saveButton = document.getElementById('save');
const status = document.getElementById('status');

chrome.storage.local.get({ [STORAGE_KEY]: DEFAULT_SERVER_BASE }, (items) => {
  input.value = normalizeBase(items[STORAGE_KEY]);
});

saveButton.addEventListener('click', () => {
  const value = normalizeBase(input.value);
  if (!/^https?:\/\/[^/]+/i.test(value)) {
    status.textContent = '请输入完整地址，例如 https://192.168.10.205';
    status.style.color = '#c2204a';
    return;
  }
  chrome.storage.local.set({ [STORAGE_KEY]: value }, () => {
    status.style.color = '#2f7f56';
    status.textContent = '已保存，刷新 TMS 页面后生效。';
  });
});
