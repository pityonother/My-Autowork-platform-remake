const CONFIG = window.BookingTmsCheckerConfig || {};
const DEFAULT_SERVER_BASE = CONFIG.defaultServerBase || 'https://127.0.0.1';
const DEFAULT_SERVER_PORT = CONFIG.defaultServerPort || '8010';
const STORAGE_KEY = 'bookingServerBase';
const STORAGE_TOKEN_KEY = 'bookingAccessToken';

function normalizeBase(value) {
  const raw = String(value || '').trim() || DEFAULT_SERVER_BASE;
  const withScheme = /^[a-z][a-z0-9+.-]*:\/\//i.test(raw) ? raw : `https://${raw}`;
  const hasExplicitPort = /^[a-z][a-z0-9+.-]*:\/\/(?:\[[^\]]+\]|[^/:?#]+):\d+/i.test(withScheme);
  try {
    const url = new URL(withScheme);
    if (!url.port && DEFAULT_SERVER_PORT && !hasExplicitPort) {
      url.port = DEFAULT_SERVER_PORT;
    }
    return url.toString().replace(/\/+$/, '');
  } catch (_error) {
    return withScheme.replace(/\/+$/, '');
  }
}

const input = document.getElementById('server-base');
const tokenInput = document.getElementById('access-token');
const saveButton = document.getElementById('save');
const status = document.getElementById('status');

chrome.storage.local.get({ [STORAGE_KEY]: DEFAULT_SERVER_BASE, [STORAGE_TOKEN_KEY]: '' }, (items) => {
  input.value = normalizeBase(items[STORAGE_KEY]);
  tokenInput.value = String(items[STORAGE_TOKEN_KEY] || '');
});

saveButton.addEventListener('click', () => {
  const value = normalizeBase(input.value);
  if (!/^https?:\/\/[^/]+/i.test(value)) {
    status.textContent = '请输入完整地址，例如 https://127.0.0.1:8010';
    status.style.color = '#c2204a';
    return;
  }
  chrome.storage.local.set({ [STORAGE_KEY]: value, [STORAGE_TOKEN_KEY]: tokenInput.value.trim() }, () => {
    status.style.color = '#2f7f56';
    status.textContent = '已保存，刷新 TMS 页面后生效。';
  });
});
