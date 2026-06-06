/* ═══════════════════════════════════════════════════════════════════
   LUME — cart.js
   Manages cart state, renders cart UI, handles place-order flow.
   ═══════════════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  /* ── State ─────────────────────────────────────────────────────── */
  let cart = []; // [{ name, price, image, category, qty }]

  /* ── DOM refs (resolved after DOMContentLoaded) ─────────────────── */
  let cartList, cartTotal, placeOrderBtn, bottomCart, bottomCount, bottomTotal, bottomOrderBtn;

  /* ── Helpers ───────────────────────────────────────────────────── */
  function totalItems()  { return cart.reduce((s, i) => s + i.qty, 0); }
  function totalPrice()  { return cart.reduce((s, i) => s + i.price * i.qty, 0); }
  function fmt(n)        { return '₹' + n.toLocaleString('en-IN'); }

  /* ── Find or add item ───────────────────────────────────────────── */
  function addItem(data) {
    const existing = cart.find(i => i.name === data.name);
    if (existing) {
      existing.qty++;
    } else {
      cart.push({ ...data, qty: 1 });
    }
    render();
  }

  function removeItem(name) {
    const idx = cart.findIndex(i => i.name === name);
    if (idx === -1) return;
    if (cart[idx].qty > 1) {
      cart[idx].qty--;
    } else {
      cart.splice(idx, 1);
    }
    render();
  }

  /* ── Render cart panel ──────────────────────────────────────────── */
  function render() {
    if (!cartList) return;

    /* Cart list */
    if (cart.length === 0) {
      cartList.innerHTML = '<p class="muted" style="padding:8px 0">Your cart is empty — add dishes from the menu above.</p>';
    } else {
      cartList.innerHTML = cart.map(item => `
        <div class="cart-item">
          <div style="display:flex;align-items:center;gap:12px;flex:1;min-width:0">
            ${item.image
              ? `<img src="${item.image}" alt="${item.name}"
                      style="width:44px;height:44px;border-radius:10px;object-fit:cover;flex-shrink:0">`
              : ''}
            <div style="min-width:0">
              <div style="font-size:14px;font-weight:500;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${item.name}</div>
              <div style="font-family:var(--font-mono);font-size:12px;color:var(--text-sec)">${fmt(item.price)}</div>
            </div>
          </div>
          <div class="qty-control">
            <button class="qty-button" data-action="remove" data-name="${item.name}" aria-label="Remove one">−</button>
            <span class="qty-value">${item.qty}</span>
            <button class="qty-button" data-action="add" data-item='${JSON.stringify({ name: item.name, price: item.price, image: item.image, category: item.category })}' aria-label="Add one">+</button>
          </div>
        </div>
      `).join('');
    }

    /* Totals */
    const total = totalPrice();
    const count = totalItems();
    cartTotal.textContent = fmt(total);
    placeOrderBtn.disabled = count === 0;

    /* Bottom bar */
    bottomCount.textContent = count + (count === 1 ? ' item' : ' items');
    bottomTotal.textContent = fmt(total);
    if (count > 0) {
      bottomCart.classList.add('visible');
    } else {
      bottomCart.classList.remove('visible');
    }
  }

  /* ── Place order with Razorpay Payment ─────────────────────────── */
  async function placeOrder() {
    if (cart.length === 0) return;

    const btn = placeOrderBtn;
    const origText = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Processing…';

    try {
      // Step 1: Create Razorpay order
      const orderRes = await fetch('/create-razorpay-order', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          items: cart.map(i => ({ name: i.name, price: i.price, image: i.image, category: i.category, qty: i.qty })),
          table_id: window.LUME_TABLE_ID || 5
        })
      });

      const orderData = await orderRes.json();

      if (!orderData.success) {
        alert(orderData.message || 'Could not create order. Please try again.');
        btn.disabled = false;
        btn.textContent = origText;
        return;
      }

      // Step 2: Open Razorpay checkout
      const options = {
        key: orderData.key_id,
        amount: orderData.amount,
        currency: orderData.currency,
        name: 'Lume Restaurant',
        description: 'Order Payment',
        order_id: orderData.razorpay_order_id,
        handler: async function (response) {
          // Step 3: Verify payment on backend
          btn.textContent = 'Verifying payment…';
          
          try {
            const verifyRes = await fetch('/verify-payment', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                razorpay_order_id: response.razorpay_order_id,
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_signature: response.razorpay_signature,
                items: cart.map(i => ({ name: i.name, price: i.price, image: i.image, category: i.category, qty: i.qty })),
                table_id: window.LUME_TABLE_ID || 5,
                order_id: orderData.order_id
              })
            });

            const verifyData = await verifyRes.json();

            if (verifyData.success) {
              cart = [];
              render();
              // Redirect to order status page
              window.location.href = '/order-status/' + verifyData.order_id;
            } else {
              alert(verifyData.message || 'Payment verification failed. Please contact support.');
              btn.disabled = false;
              btn.textContent = origText;
            }
          } catch (err) {
            console.error('Payment verification error:', err);
            alert('Payment verification failed. Please contact support with your payment ID.');
            btn.disabled = false;
            btn.textContent = origText;
          }
        },
        prefill: {
          name: 'Guest',
          email: 'guest@lume.restaurant',
          contact: '9999999999'
        },
        theme: {
          color: '#6366f1'
        },
        modal: {
          ondismiss: function() {
            // User closed the payment modal
            btn.disabled = false;
            btn.textContent = origText;
          }
        }
      };

      const razorpayInstance = new Razorpay(options);
      razorpayInstance.open();

    } catch (err) {
      console.error('Place order error:', err);
      alert('Network error — please check your connection.');
      btn.disabled = false;
      btn.textContent = origText;
    }
  }

  /* ── Init ───────────────────────────────────────────────────────── */
  document.addEventListener('DOMContentLoaded', () => {
    cartList      = document.getElementById('cartList');
    cartTotal     = document.getElementById('cartTotal');
    placeOrderBtn = document.getElementById('placeOrderBtn');
    bottomCart    = document.getElementById('bottomCart');
    bottomCount   = document.getElementById('bottomCartCount');
    bottomTotal   = document.getElementById('bottomCartTotal');
    bottomOrderBtn= document.getElementById('bottomOrderBtn');

    if (!cartList) return; // not on menu page

    render();

    /* Add-to-cart buttons (delegated — menu.js also fires these) */
    document.addEventListener('click', e => {
      /* Add button on dish card */
      const addBtn = e.target.closest('[data-add]');
      if (addBtn) {
        try {
          const data = JSON.parse(addBtn.dataset.add);
          addItem(data);
        } catch (_) {}
        return;
      }

      /* Qty +/- inside cart */
      const qtyBtn = e.target.closest('[data-action]');
      if (qtyBtn) {
        const action = qtyBtn.dataset.action;
        if (action === 'remove') {
          removeItem(qtyBtn.dataset.name);
        } else if (action === 'add') {
          try {
            const item = JSON.parse(qtyBtn.dataset.item);
            addItem(item);
          } catch (_) {}
        }
      }
    });

    /* Place order buttons */
    placeOrderBtn.addEventListener('click', placeOrder);
    if (bottomOrderBtn) bottomOrderBtn.addEventListener('click', placeOrder);
  });

  /* Expose for external use (e.g. assistant page quick-add) */
  window.LumeCart = { addItem, removeItem, getCart: () => cart };
})();
