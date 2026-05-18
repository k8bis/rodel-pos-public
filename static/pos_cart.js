// pos_cart.js
//console.log("POS_CART_INV3B_SEGMENTED");

export function createPosCart(deps) {
  const {
    getProducts,
    isService,
    usesStocksApi,
    usesLegacyStock,
    getNumericStock,
    canAddToCart,
    getBlockReason,
    loadData,
    api
  } = deps;

  let cart = {};

  function getCart() {
    return cart;
  }

  function resetCart() {
    cart = {};
    renderCart();
  }

  function addToCart(productId) {
    const products = getProducts();
    const product = products.find(p => String(p.id) === String(productId));
    if (!product) return;

    if (!canAddToCart(product)) {
      alert(getBlockReason(product));
      return;
    }

    const existingQty = cart[productId]?.quantity || 0;
    const nextQty = existingQty + 1;

    if (cart[productId]) {
      cart[productId].quantity = nextQty;
    } else {
      cart[productId] = { ...product, quantity: 1 };
    }

    renderCart();
  }

  function updateQuantity(productId, newQuantity) {
    if (newQuantity <= 0) {
      delete cart[productId];
    } else if (cart[productId]) {
      const products = getProducts();
      const product = products.find(p => String(p.id) === String(productId)) || cart[productId];

      cart[productId].quantity = newQuantity;
    }

    renderCart();
  }

function renderCart() {
  const container = document.getElementById("cartItems");
  const totalEl = document.getElementById("cartTotal");

  if (!container || !totalEl) return;

  container.innerHTML = "";
  let total = 0;

  const items = Object.values(cart);

  if (items.length === 0) {
    container.innerHTML = `<div class="empty-cart">El carrito está vacío.</div>`;
    totalEl.textContent = "Total: $0.00";
    return;
  }

  items.forEach(item => {
    const itemTotal = Number(item.sale_price) * item.quantity;
    total += itemTotal;

    const inventoryHint = isService(item)
      ? "Servicio"
      : (usesStocksApi(item)
          ? `Stocks API${item.stock_item_id ? ` · Item #${item.stock_item_id}` : ""}`
          : "POS Legacy");

    const itemEl = document.createElement("div");
    itemEl.className = "cart-item";

    itemEl.innerHTML = `
      <div class="cart-item-main">
        <div class="cart-item-head">
          <div class="cart-item-name" title="${item.name}">${item.name}</div>
          <button
            type="button"
            class="cart-remove-btn"
            onclick="updateQuantity(${item.id}, 0)"
            title="Eliminar del carrito"
            aria-label="Eliminar ${item.name} del carrito"
          >
            ✕
          </button>
        </div>

        <div class="cart-item-unit-price">
          $${Number(item.sale_price).toFixed(2)} c/u
        </div>

        <div class="cart-item-meta">${inventoryHint}</div>
      </div>

      <div class="cart-item-side">
        <div class="quantity-controls">
          <button
            type="button"
            class="quantity-btn"
            onclick="updateQuantity(${item.id}, ${item.quantity - 1})"
            aria-label="Disminuir cantidad de ${item.name}"
          >
            −
          </button>

          <span class="quantity-value">${item.quantity}</span>

          <button
            type="button"
            class="quantity-btn"
            onclick="updateQuantity(${item.id}, ${item.quantity + 1})"
            aria-label="Aumentar cantidad de ${item.name}"
          >
            +
          </button>
        </div>

        <div class="cart-item-total">$${itemTotal.toFixed(2)}</div>
      </div>
    `;

    container.appendChild(itemEl);
  });

  totalEl.textContent = `Total: $${total.toFixed(2)}`;
}

  function buildCheckoutPayload() {
    const items = Object.values(cart);

    return {
      items: items.map(item => ({
        pos_price_id: item.id,
        quantity: item.quantity
      })),
      payment_method: "cash",
      notes: "Venta generada desde POS web"
    };
  }

  async function submitCheckout() {
    const items = Object.values(cart);

    if (items.length === 0) {
      return {
        ok: false,
        response: null,
        result: { detail: "El carrito está vacío." },
        payload: null
      };
    }

    const payload = buildCheckoutPayload();
    // 🔴 VALIDACIÓN FINAL DE INVENTARIO (BUG P5)
    const latestProducts = getProducts();

    const latestMap = {};
    for (const p of (latestProducts || [])) {
      latestMap[String(p.id)] = p;
    }

    for (const item of items) {
      const fresh = latestMap[String(item.id)];

      if (!fresh) {
        return {
          ok: false,
          response: null,
          result: { detail: `Producto ya no disponible: ${item.name}` },
          payload
        };
      }

      const isServiceItem = isService(fresh);

      if (!isServiceItem) {
        const stock = Number(fresh.stock_quantity || 0);

        if (stock < Number(item.quantity)) {
          return {
            ok: false,
            response: null,
            result: {
              detail: `Inventario insuficiente para ${item.name}. Disponible: ${stock}`
            },
            payload
          };
        }
      }
    }

    try {
      const { response, result } = await api.createSale(payload);

      return {
        ok: !!response?.ok,
        response,
        result,
        payload
      };
    } catch (error) {
      console.error("Error en submitCheckout:", error);

      if (String(error.message).includes("Sesión expirada o inválida")) {
        throw error;
      }

      return {
        ok: false,
        response: null,
        result: { detail: error?.message || "Error inesperado al procesar la venta." },
        payload
      };
    }
  }

  function clearCartAfterSuccessfulFlow() {
    cart = {};
    renderCart();
  }

  async function checkout() {
    const submit = await submitCheckout();

    if (!submit.ok) {
      const msg = submit?.result?.detail || `Error HTTP ${submit?.response?.status || "N/A"}`;
      alert(`No se pudo procesar la venta: ${msg}`);
      return submit;
    }

    alert(`Venta procesada correctamente. Folio: ${submit.result?.sale_number || submit.result?.id || "N/A"}`);

    clearCartAfterSuccessfulFlow();
    await loadData();

    return submit;
  }

    return {
    getCart,
    resetCart,
    addToCart,
    updateQuantity,
    renderCart,
    buildCheckoutPayload,
    submitCheckout,
    clearCartAfterSuccessfulFlow,
    checkout
  };
}