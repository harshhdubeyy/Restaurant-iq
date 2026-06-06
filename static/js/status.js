/* ═══════════════════════════════════════════════════════════════════
   LUME — status.js
   Polls /api/order-status/:id and updates the wait page live.
   ═══════════════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  const ORDER_ID  = window.LUME_ORDER_ID;
  const POLL_MS   = 8000; // poll every 8 s

  /* ── DOM refs ──────────────────────────────────────────────────── */
  const titleEl    = document.getElementById('statusTitle');
  const copyEl     = document.getElementById('statusCopy');
  const etaEl      = document.getElementById('etaNumber');
  const progressEl = document.getElementById('progressFill');
  const itemsEl    = document.getElementById('orderItems');
  const modelEl    = document.getElementById('modelSource');
  const menuLink   = document.getElementById('menuLink');
  const assistLink = document.getElementById('assistantLink');

  /* ── Status → UI map ───────────────────────────────────────────── */
  const STATUS_MAP = {
    Pending: {
      title:    'Order Received',
      copy:     'Your order has been placed and is waiting to be picked up by the kitchen.',
      progress: '15%',
      step:     0
    },
    Preparing: {
      title:    'Being Prepared',
      copy:     'The kitchen is actively working on your meal. Sit tight!',
      progress: '50%',
      step:     1
    },
    Ready: {
      title:    'Ready to Serve',
      copy:     'Your order is ready! A server will bring it to your table shortly.',
      progress: '85%',
      step:     2
    },
    Completed: {
      title:    'Order Served',
      copy:     'Enjoy your meal! We hope you love every bite.',
      progress: '100%',
      step:     3
    }
  };

  /* ── Update step indicators ────────────────────────────────────── */
  function updateSteps(statusKey) {
    const steps = document.querySelectorAll('.step');
    const current = STATUS_MAP[statusKey]?.step ?? 0;
    steps.forEach((el, i) => {
      el.classList.remove('active', 'done');
      if (i < current)  el.classList.add('done');
      if (i === current) el.classList.add('active');
    });
  }

  /* ── Render order items ────────────────────────────────────────── */
  function renderItems(items) {
    if (!itemsEl || !items || items.length === 0) return;
    itemsEl.innerHTML = items.map(item => `
      <div class="order-row">
        <div style="display:flex;align-items:center;gap:12px;flex:1;min-width:0">
          ${item.image
            ? `<img src="${item.image}" alt="${item.name}"
                    style="width:44px;height:44px;border-radius:10px;object-fit:cover;flex-shrink:0">`
            : ''}
          <div>
            <div style="font-size:14px;font-weight:500;color:var(--text)">${item.name}</div>
            ${item.category ? `<div style="font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em">${item.category}</div>` : ''}
          </div>
        </div>
        <div style="font-family:var(--font-mono);font-size:14px;font-weight:500;color:var(--primary);white-space:nowrap">
          ₹${(item.price || 0).toLocaleString('en-IN')}
        </div>
      </div>
    `).join('');
  }

  /* ── Apply fetched order data to the page ──────────────────────── */
  function applyOrder(order) {
    const status = order.status || 'Pending';
    const map    = STATUS_MAP[status] || STATUS_MAP.Pending;

    /* Title & copy */
    if (titleEl) titleEl.textContent = map.title;
    if (copyEl)  copyEl.textContent  = map.copy;

    /* ETA */
    if (etaEl) etaEl.textContent = order.eta ?? '--';

    /* Progress bar */
    if (progressEl) progressEl.style.width = map.progress;

    /* Steps */
    updateSteps(status);

    /* Items */
    renderItems(order.items);

    /* Model metadata */
    if (modelEl && order.ml) {
      const m = order.ml;
      modelEl.textContent = `ML model: ${m.wait_model || 'wait_time'} · predicted at ${m.predicted_at || '—'}`;
    }

    /* Update nav links with real table_id */
    if (order.table_id) {
      if (menuLink)   menuLink.href   = `/table/${order.table_id}`;
      if (assistLink) assistLink.href = `/assistant/${order.table_id}`;
    }

    /* Change document title */
    document.title = `Lume | ${map.title} — Order #${order.id}`;
  }

  /* ── Fetch ─────────────────────────────────────────────────────── */
  async function fetchStatus() {
    if (!ORDER_ID) return;
    try {
      const res   = await fetch(`/api/order-status/${ORDER_ID}`);
      if (!res.ok) throw new Error('Not found');
      const order = await res.json();
      applyOrder(order);

      /* Stop polling once completed */
      if (order.status === 'Completed') clearInterval(poller);
    } catch (err) {
      if (titleEl) titleEl.textContent = 'Order not found';
      if (copyEl)  copyEl.textContent  = `Could not load order #${ORDER_ID}. Check the link and try again.`;
      clearInterval(poller);
    }
  }

  /* ── Bootstrap ─────────────────────────────────────────────────── */
  fetchStatus();                       // immediate first call
  const poller = setInterval(fetchStatus, POLL_MS);
})();
