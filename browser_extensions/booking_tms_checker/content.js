(function () {
  const CONFIG = window.BookingTmsCheckerConfig || {};
  const DEFAULT_SERVER_BASE = CONFIG.defaultServerBase || 'https://192.168.10.4';
  const DEFAULT_SERVER_PORT = CONFIG.defaultServerPort || '8042';
  const STORAGE_KEY = 'bookingServerBase';

  if (document.getElementById('booking-tms-checker-host')) {
    return;
  }

  function normalizeBase(value) {
    const raw = String(value || '').trim() || DEFAULT_SERVER_BASE;
    const withScheme = /^[a-z][a-z0-9+.-]*:\/\//i.test(raw) ? raw : `https://${raw}`;
    try {
      const url = new URL(withScheme);
      if (!url.port && DEFAULT_SERVER_PORT) {
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

  function getServerBase() {
    return new Promise((resolve) => {
      if (
        typeof chrome === 'undefined' ||
        !chrome.storage ||
        !chrome.storage.local
      ) {
        resolve(normalizeBase(DEFAULT_SERVER_BASE));
        return;
      }
      chrome.storage.local.get({ [STORAGE_KEY]: DEFAULT_SERVER_BASE }, (items) => {
        resolve(normalizeBase(items[STORAGE_KEY]));
      });
    });
  }

  function setStatus(root, message, isError) {
    const status = root.querySelector('.booking-tms-status');
    if (!status) return;
    status.textContent = message || '';
    status.classList.toggle('is-error', Boolean(isError));
  }

  function render(serverBase) {
    const host = document.createElement('div');
    host.id = 'booking-tms-checker-host';

    const formAction = `${serverBase}/modules/booking/body-validation/extension-upload`;
    const safeServerBase = escapeHtml(serverBase);
    const safeFormAction = escapeHtml(formAction);
    host.innerHTML = `
      <form class="booking-tms-card" method="post" enctype="multipart/form-data" target="_blank" action="${safeFormAction}">
        <div class="booking-tms-head">
          <div class="booking-tms-title">
            <strong>Booking 质检</strong>
            <span title="${safeServerBase}">${safeServerBase}</span>
          </div>
          <button class="booking-tms-close" type="button" aria-label="关闭">×</button>
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
    const closeButton = host.querySelector('.booking-tms-close');
    const openButton = host.querySelector('.booking-tms-open');

    closeButton.addEventListener('click', () => {
      host.remove();
    });

    form.addEventListener('submit', (event) => {
      const file = fileInput.files && fileInput.files[0];
      if (!file) {
        event.preventDefault();
        setStatus(host, '请先选择 booking form。', true);
        return;
      }
      if (!file.name.toLowerCase().endsWith('.xlsx')) {
        event.preventDefault();
        setStatus(host, '当前只支持 .xlsx booking form。', true);
        fileInput.value = '';
        openButton.disabled = true;
        openButton.textContent = '先选择 booking form';
        return;
      }
      setStatus(host, `正在上传：${file.name}`, false);
      form.action = `${serverBase}/modules/booking/body-validation/extension-upload`;
      window.setTimeout(() => {
        setStatus(host, '已打开筛查结果页，可继续选择下一份 booking。', false);
        fileInput.value = '';
        openButton.disabled = true;
        openButton.textContent = '先选择 booking form';
      }, 800);
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

  getServerBase().then(render);
})();
