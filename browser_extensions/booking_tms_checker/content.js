(function () {
  const CONFIG = window.BookingTmsCheckerConfig || {};
  const DEFAULT_SERVER_BASE = CONFIG.defaultServerBase || 'https://127.0.0.1';
  const DEFAULT_SERVER_PORT = CONFIG.defaultServerPort || '8010';
  const STORAGE_KEY = 'bookingServerBase';
  const STORAGE_TOKEN_KEY = 'bookingAccessToken';
  const HOST_ID = 'booking-tms-checker-host';
  const RUNTIME_KEY = '__bookingTmsCheckerRuntime';
  const RESTORE_DELAY_MS = 250;
  let renderPromise = null;
  let restoreTimer = null;

  if (
    window[RUNTIME_KEY] &&
    typeof window[RUNTIME_KEY].ensureHost === 'function'
  ) {
    void window[RUNTIME_KEY].ensureHost();
    return;
  }

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

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function buildUploadUrl(serverBase) {
    return new URL('/modules/booking/body-validation/extension-upload', serverBase).toString();
  }

  async function uploadBookingFile(serverBase, accessToken, file) {
    const formData = new FormData();
    formData.append('booking_file', file, file.name);
    const headers = { Accept: 'application/json' };
    if (accessToken) {
      headers['x-my-autowork-token'] = accessToken;
    }
    const response = await fetch(buildUploadUrl(serverBase), {
      method: 'POST',
      headers,
      body: formData,
      credentials: 'include',
    });
    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || `上传失败：HTTP ${response.status}`);
    }
    const payload = await response.json();
    if (!payload || !payload.url) {
      throw new Error('服务端没有返回筛查结果页面地址。');
    }
    return new URL(payload.url, serverBase).toString();
  }

  function getSettings() {
    return new Promise((resolve) => {
      if (
        typeof chrome === 'undefined' ||
        !chrome.storage ||
        !chrome.storage.local
      ) {
        resolve({ serverBase: normalizeBase(DEFAULT_SERVER_BASE), accessToken: '' });
        return;
      }
      chrome.storage.local.get({ [STORAGE_KEY]: DEFAULT_SERVER_BASE, [STORAGE_TOKEN_KEY]: '' }, (items) => {
        resolve({
          serverBase: normalizeBase(items[STORAGE_KEY]),
          accessToken: String(items[STORAGE_TOKEN_KEY] || '').trim(),
        });
      });
    });
  }

  function setStatus(root, message, isError) {
    const status = root.querySelector('.booking-tms-status');
    if (!status) return;
    status.textContent = message || '';
    status.classList.toggle('is-error', Boolean(isError));
  }

  function render(settings) {
    if (document.getElementById(HOST_ID)) {
      return;
    }
    const serverBase = settings.serverBase;
    const accessToken = settings.accessToken;
    const host = document.createElement('div');
    host.id = HOST_ID;

    const safeServerBase = escapeHtml(serverBase);
    host.innerHTML = `
      <form class="booking-tms-card">
        <div class="booking-tms-head">
          <div class="booking-tms-title">
            <strong>Booking 质检</strong>
            <span title="${safeServerBase}">${safeServerBase}</span>
          </div>
          <button class="booking-tms-collapse" type="button" aria-label="收起质检入口" aria-expanded="true">−</button>
        </div>
        <div class="booking-tms-body">
          <label class="booking-tms-upload">
            <input type="file" name="booking_file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" required>
            <span>选择 booking form 并筛查</span>
          </label>
          <button class="booking-tms-open" type="submit" disabled>先选择 booking form</button>
          <div class="booking-tms-status">选择 .xlsx 后会上传到服务端，并打开带筛查结果的页面。</div>
        </div>
      </form>
    `;

    const form = host.querySelector('form');
    const fileInput = host.querySelector('input[type="file"]');
    const collapseButton = host.querySelector('.booking-tms-collapse');
    const openButton = host.querySelector('.booking-tms-open');

    collapseButton.addEventListener('click', () => {
      const isCollapsed = host.classList.toggle('is-collapsed');
      collapseButton.textContent = isCollapsed ? '+' : '−';
      collapseButton.setAttribute('aria-expanded', String(!isCollapsed));
      collapseButton.setAttribute('aria-label', isCollapsed ? '展开质检入口' : '收起质检入口');
    });

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const file = fileInput.files && fileInput.files[0];
      if (!file) {
        setStatus(host, '请先选择 booking form。', true);
        return;
      }
      if (!file.name.toLowerCase().endsWith('.xlsx')) {
        setStatus(host, '当前只支持 .xlsx booking form。', true);
        fileInput.value = '';
        openButton.disabled = true;
        openButton.textContent = '先选择 booking form';
        return;
      }
      openButton.disabled = true;
      openButton.textContent = '正在上传...';
      setStatus(host, `正在上传：${file.name}`, false);
      try {
        const resultUrl = await uploadBookingFile(serverBase, accessToken, file);
        window.open(resultUrl, '_blank', 'noopener');
        setStatus(host, '已打开筛查结果页，可继续选择下一份 booking。', false);
        fileInput.value = '';
        openButton.textContent = '先选择 booking form';
      } catch (error) {
        openButton.disabled = false;
        openButton.textContent = '上传并打开筛查结果';
        setStatus(host, error && error.message ? error.message : '上传失败，请检查服务地址和 token。', true);
      }
    });

    fileInput.addEventListener('change', () => {
      const file = fileInput.files && fileInput.files[0];
      if (!file) {
        openButton.disabled = true;
        openButton.textContent = '先选择 booking form';
        return;
      }
      if (!file.name.toLowerCase().endsWith('.xlsx')) {
        setStatus(host, '当前只支持 .xlsx booking form。', true);
        fileInput.value = '';
        openButton.disabled = true;
        openButton.textContent = '先选择 booking form';
        return;
      }
      openButton.disabled = false;
      openButton.textContent = '上传并打开筛查结果';
      setStatus(host, `已选择：${file.name}，点击按钮开始筛查。`, false);
    });

    document.documentElement.appendChild(host);
  }

  function ensureHost() {
    if (document.getElementById(HOST_ID)) {
      return Promise.resolve();
    }
    if (renderPromise) {
      return renderPromise;
    }
    renderPromise = getSettings()
      .then((settings) => {
        if (!document.getElementById(HOST_ID)) {
          render(settings);
        }
      })
      .finally(() => {
        renderPromise = null;
      });
    return renderPromise;
  }

  function removedNodeContainsHost(node) {
    if (!node || node.nodeType !== 1) {
      return false;
    }
    if (node.id === HOST_ID) {
      return true;
    }
    return typeof node.querySelector === 'function' && Boolean(node.querySelector(`#${HOST_ID}`));
  }

  function scheduleHostRestore() {
    if (restoreTimer !== null) {
      return;
    }
    restoreTimer = window.setTimeout(() => {
      restoreTimer = null;
      void ensureHost();
    }, RESTORE_DELAY_MS);
  }

  const observer = new MutationObserver((mutations) => {
    if (document.getElementById(HOST_ID)) {
      return;
    }
    const hostWasRemoved = mutations.some((mutation) =>
      Array.from(mutation.removedNodes || []).some(removedNodeContainsHost)
    );
    if (hostWasRemoved) {
      scheduleHostRestore();
    }
  });

  window[RUNTIME_KEY] = Object.freeze({ ensureHost });
  observer.observe(document, { childList: true, subtree: true });
  void ensureHost();
})();
