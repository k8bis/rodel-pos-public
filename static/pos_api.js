//console.log("POS_API_INV3B_SEGMENTED");

export function createPosApi() {
  const NAV = window.RODELSOFT_NAV || {};
  const POSCFG = window.POS_CONFIG || {};

  const APP_BASE_PATH =
    NAV.APP_HOME_URL ||
    POSCFG.APP_BASE_PATH ||
    "/pos";

  const APP_MENU_URL =
    NAV.APP_MENU_URL ||
    POSCFG.APP_MENU_URL ||
    "/";

  const LOGOUT_URL =
    NAV.LOGOUT_URL ||
    POSCFG.LOGOUT_URL ||
    `${APP_BASE_PATH}/logout`;

  const LOGIN_FALLBACK_URL =
    NAV.LOGIN_FALLBACK_URL ||
    POSCFG.LOGOUT_REDIRECT_URL ||
    POSCFG.LOGIN_FALLBACK_URL ||
    "/";

  const currentUrl = new URL(window.location.href);
  const APP_ID = currentUrl.searchParams.get("app_id");
  const CLIENT_ID = currentUrl.searchParams.get("client_id");

  const CONTEXT_QUERY = new URLSearchParams();
  if (APP_ID) CONTEXT_QUERY.set("app_id", APP_ID);
  if (CLIENT_ID) CONTEXT_QUERY.set("client_id", CLIENT_ID);

  const CONTEXT_SUFFIX = CONTEXT_QUERY.toString() ? `?${CONTEXT_QUERY.toString()}` : "";

  const API_BASE = `${APP_BASE_PATH}/api`;
  const SESSION_CHECK_URL = `${APP_BASE_PATH}/session-check${CONTEXT_SUFFIX}`;
  const CATALOG_SETTINGS_URL = `${API_BASE}/catalog-settings${CONTEXT_SUFFIX}`;
  const CATEGORIES_URL = `${API_BASE}/categories${CONTEXT_SUFFIX}`;
  const PRODUCTS_URL = `${API_BASE}/products${CONTEXT_SUFFIX}`;
  const SALES_URL = `${API_BASE}/sales${CONTEXT_SUFFIX}`;
  const CATALOG_ITEMS_URL = `${API_BASE}/catalog-items${CONTEXT_SUFFIX}`;
  const POS_PRICES_URL = `${API_BASE}/pos-prices${CONTEXT_SUFFIX}`;
  const POS_SETTINGS_URL = `${API_BASE}/pos-settings${CONTEXT_SUFFIX}`;
  const MAINTENANCE_PRODUCTS_URL = `${API_BASE}/maintenance/products${CONTEXT_SUFFIX}`;
  const SALE_PRODUCTS_URL = `${API_BASE}/sale-products${CONTEXT_SUFFIX}`;
  const POS_CUSTOMERS_URL = `${API_BASE}/pos-customers${CONTEXT_SUFFIX}`;

  function redirectToLogin() {
    window.location.replace(LOGIN_FALLBACK_URL);
  }

  async function handleApiResponse(response, endpointName = "API") {
    if (response.redirected) {
      console.warn(`${endpointName} respondió con redirect. Redirigiendo al login...`);
      redirectToLogin();
      throw new Error("Sesión expirada o inválida");
    }

    if (response.status === 401) {
      console.warn(`${endpointName} respondió 401. Redirigiendo al login...`);
      redirectToLogin();
      throw new Error("Sesión expirada o inválida");
    }

    return response;
  }

  async function fetchJson(url, endpointName = "API") {
    const raw = await fetch(url, {
      credentials: "same-origin",
      cache: "no-store",
      redirect: "follow"
    });

    const res = await handleApiResponse(raw, endpointName);

    if (!res.ok) {
      const txt = await res.text();
      throw new Error(`${endpointName} HTTP ${res.status}: ${txt}`);
    }

    return res.json();
  }

  async function validateSessionOrRedirect() {
    try {
      const response = await fetch(SESSION_CHECK_URL, {
        method: "GET",
        credentials: "same-origin",
        cache: "no-store",
        redirect: "follow"
      });

      if (response.redirected || !response.ok) {
        redirectToLogin();
        return false;
      }

      return true;
    } catch (error) {
      console.error("Error validando sesión:", error);
      redirectToLogin();
      return false;
    }
  }

  async function loadCatalogSettings() {
    try {
      return await fetchJson(CATALOG_SETTINGS_URL, "catalog-settings");
    } catch (error) {
      console.error("No se pudo cargar catalog-settings:", error);
      return {
        catalog_source: "pos",
        allow_manual_create: false,
        allow_price_edit: true,
        allow_status_toggle: true
      };
    }
  }

  async function getPosSettings() {
    return fetchJson(POS_SETTINGS_URL, "pos-settings");
  }

    async function savePosSettings(data) {
    const responseRaw = await fetch(POS_SETTINGS_URL, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json"
      },
      credentials: "same-origin",
      cache: "no-store",
      redirect: "follow",
      body: JSON.stringify(data || {})
    });

    const response = await handleApiResponse(responseRaw, "save-pos-settings");
    const rawText = await response.text();

    let result;
    try {
      result = rawText ? JSON.parse(rawText) : {};
    } catch {
      result = { detail: rawText || "Respuesta no JSON del servidor" };
    }

    return { response, result };
  }

  
  async function fetchCategories() {
    return fetchJson(CATEGORIES_URL, "categories");
  }

  async function fetchProducts() {
    // Catálogo principal de venta:
    // SOLO artículos activos en pos_prices, enriquecidos con existencia según origen
    return fetchJson(SALE_PRODUCTS_URL, "sale-products");
  }

  async function fetchMaintenanceProducts() {
    return fetchJson(MAINTENANCE_PRODUCTS_URL, "maintenance-products");
  }

  async function fetchCatalogItems() {
    return fetchJson(CATALOG_ITEMS_URL, "catalog-items");
  }

  async function fetchPosPrices() {
    return fetchJson(POS_PRICES_URL, "pos-prices");
  }

  async function createSale(payload) {
    const responseRaw = await fetch(SALES_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      credentials: "same-origin",
      cache: "no-store",
      redirect: "follow",
      body: JSON.stringify(payload)
    });

    const response = await handleApiResponse(responseRaw, "sales");
    const rawText = await response.text();

    let result;
    try {
      result = rawText ? JSON.parse(rawText) : {};
    } catch {
      result = { detail: rawText || "Respuesta no JSON del servidor" };
    }

    return { response, result };
  }

  async function fetchSaleByTicket(saleNumber) {
    const safeTicket = encodeURIComponent(String(saleNumber || "").trim());
    const url = `${API_BASE}/sales/by-ticket/${safeTicket}${CONTEXT_SUFFIX}`;

    return fetchJson(url, "sale-by-ticket");
  }

  async function fetchSalesRetries() {
    const url = `${API_BASE}/sales/retries${CONTEXT_SUFFIX}`;
    return fetchJson(url, "sales-retries");
  }

  async function cancelSale(saleId, payload) {
    const url = `${API_BASE.replace(CONTEXT_SUFFIX, "")}/sales/${saleId}/cancel${CONTEXT_SUFFIX}`;

    const responseRaw = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      credentials: "same-origin",
      cache: "no-store",
      redirect: "follow",
      body: JSON.stringify(payload || {})
    });

    const response = await handleApiResponse(responseRaw, "cancel-sale");
    const rawText = await response.text();

    let result;
    try {
      result = rawText ? JSON.parse(rawText) : {};
    } catch {
      result = { detail: rawText || "Respuesta no JSON del servidor" };
    }

    return { response, result };
  }

  async function fetchSalePrintContext(saleId) {
    const url = `${API_BASE.replace(CONTEXT_SUFFIX, "")}/sales/${saleId}/print-context${CONTEXT_SUFFIX}`;
    return fetchJson(url, "sale-print-context");
  }

  async function fetchSalePrintData(saleId) {
    const url = `${API_BASE.replace(CONTEXT_SUFFIX, "")}/sales/${saleId}/print-data${CONTEXT_SUFFIX}`;
    return fetchJson(url, "sale-print-data");
  }

  async function saveSalePrintData(saleId, payload) {
    const url = `${API_BASE.replace(CONTEXT_SUFFIX, "")}/sales/${saleId}/print-data${CONTEXT_SUFFIX}`;

    const responseRaw = await fetch(url, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json"
      },
      credentials: "same-origin",
      cache: "no-store",
      redirect: "follow",
      body: JSON.stringify(payload || {})
    });

    const response = await handleApiResponse(responseRaw, "save-sale-print-data");
    const rawText = await response.text();

    let result;
    try {
      result = rawText ? JSON.parse(rawText) : {};
    } catch {
      result = { detail: rawText || "Respuesta no JSON del servidor" };
    }

    return { response, result };
  }

  async function openSalePrintWindow(saleId) {
    const safeSaleId = Number(saleId || 0);

    if (!safeSaleId) {
      throw new Error("saleId inválido para impresión.");
    }

    const url = `${APP_BASE_PATH}/pos/api/sales/${safeSaleId}/print-html${CONTEXT_SUFFIX}`;

    const win = window.open(url, "_blank");

    if (!win) {
      throw new Error("El navegador bloqueó la ventana de impresión. Permite popups para esta app.");
    }

    return true;
  }

  async function applyStocksSale(payload) {
    const url = `${API_BASE}/integrations/pos/sales-apply${CONTEXT_SUFFIX}`;

    const responseRaw = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      credentials: "same-origin",
      cache: "no-store",
      redirect: "follow",
      body: JSON.stringify(payload)
    });

    const response = await handleApiResponse(responseRaw, "integrations-pos-sales-apply");
    const rawText = await response.text();

    let result;
    try {
      result = rawText ? JSON.parse(rawText) : {};
    } catch {
      result = { detail: rawText || "Respuesta no JSON del servidor" };
    }

    return { response, result };
  }
  
  async function createCategory(payload) {
    const responseRaw = await fetch(CATEGORIES_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      credentials: "same-origin",
      cache: "no-store",
      redirect: "follow",
      body: JSON.stringify(payload)
    });

    const response = await handleApiResponse(responseRaw, "create-category");
    const rawText = await response.text();

    let result;
    try {
      result = rawText ? JSON.parse(rawText) : {};
    } catch {
      result = { detail: rawText || "Respuesta no JSON del servidor" };
    }

    return { response, result };
  }

  async function updateCategory(categoryId, payload) {
    const url = `${API_BASE}/categories/${categoryId}${CONTEXT_SUFFIX}`;

    const responseRaw = await fetch(url, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json"
      },
      credentials: "same-origin",
      cache: "no-store",
      redirect: "follow",
      body: JSON.stringify(payload)
    });

    const response = await handleApiResponse(responseRaw, "update-category");
    const rawText = await response.text();

    let result;
    try {
      result = rawText ? JSON.parse(rawText) : {};
    } catch {
      result = { detail: rawText || "Respuesta no JSON del servidor" };
    }

    return { response, result };
  }

  async function createProduct(payload) {
    const responseRaw = await fetch(PRODUCTS_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      credentials: "same-origin",
      cache: "no-store",
      redirect: "follow",
      body: JSON.stringify(payload)
    });

    const response = await handleApiResponse(responseRaw, "create-product");
    const rawText = await response.text();

    let result;
    try {
      result = rawText ? JSON.parse(rawText) : {};
    } catch {
      result = { detail: rawText || "Respuesta no JSON del servidor" };
    }

    return { response, result };
  }

  async function updateProduct(productId, payload) {
    const url = `${API_BASE}/products/${productId}${CONTEXT_SUFFIX}`;

    const responseRaw = await fetch(url, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json"
      },
      credentials: "same-origin",
      cache: "no-store",
      redirect: "follow",
      body: JSON.stringify(payload)
    });

    const response = await handleApiResponse(responseRaw, "update-product");
    const rawText = await response.text();

    let result;
    try {
      result = rawText ? JSON.parse(rawText) : {};
    } catch {
      result = { detail: rawText || "Respuesta no JSON del servidor" };
    }

    return { response, result };
  }

  async function createMaintenanceProduct(payload) {
    const responseRaw = await fetch(MAINTENANCE_PRODUCTS_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      credentials: "same-origin",
      cache: "no-store",
      redirect: "follow",
      body: JSON.stringify(payload)
    });

    const response = await handleApiResponse(responseRaw, "create-maintenance-product");
    const rawText = await response.text();

    let result;
    try {
      result = rawText ? JSON.parse(rawText) : {};
    } catch {
      result = { detail: rawText || "Respuesta no JSON del servidor" };
    }

    return { response, result };
  }

  async function updateMaintenanceProduct(productId, payload) {
    const url = `${API_BASE}/maintenance/products/${productId}${CONTEXT_SUFFIX}`;

    const responseRaw = await fetch(url, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json"
      },
      credentials: "same-origin",
      cache: "no-store",
      redirect: "follow",
      body: JSON.stringify(payload)
    });

    const response = await handleApiResponse(responseRaw, "update-maintenance-product");
    const rawText = await response.text();

    let result;
    try {
      result = rawText ? JSON.parse(rawText) : {};
    } catch {
      result = { detail: rawText || "Respuesta no JSON del servidor" };
    }

    return { response, result };
  }

  async function savePosPrice({ editingId, payload }) {
    const url = editingId
      ? `${API_BASE}/pos-prices/${editingId}${CONTEXT_SUFFIX}`
      : POS_PRICES_URL;

    const method = editingId ? "PUT" : "POST";

    const responseRaw = await fetch(url, {
      method,
      headers: {
        "Content-Type": "application/json"
      },
      credentials: "same-origin",
      cache: "no-store",
      redirect: "follow",
      body: JSON.stringify(payload)
    });

    const response = await handleApiResponse(
      responseRaw,
      method === "POST" ? "create-pos-price" : "update-pos-price"
    );

    const rawText = await response.text();

    let result;
    try {
      result = rawText ? JSON.parse(rawText) : {};
    } catch {
      result = { detail: rawText || "Respuesta no JSON del servidor" };
    }

    return { response, result, method };
  }

  async function doLogout() {
    try {
      await fetch(LOGOUT_URL, {
        method: "POST",
        credentials: "include",
        cache: "no-store",
        redirect: "follow"
      });
    } catch (error) {
      console.warn("Error ejecutando logout centralizado:", error);
    }

    window.location.replace(LOGIN_FALLBACK_URL);
  }

  async function fetchPosCustomers({ search = "", includeInactive = false } = {}) {
    const params = new URLSearchParams();

    const safeSearch = String(search || "").trim();
    if (safeSearch) {
      params.set("search", safeSearch);
    }

    if (includeInactive) {
      params.set("include_inactive", "true");
    }

    const qs = params.toString();
    const separator = POS_CUSTOMERS_URL.includes("?") ? "&" : "?";
    const url = qs ? `${POS_CUSTOMERS_URL}${separator}${qs}` : POS_CUSTOMERS_URL;

    return fetchJson(url, "pos-customers");
  }

  async function savePosCustomer({ editingId, payload }) {
    const url = editingId
      ? `${API_BASE}/pos-customers/${editingId}${CONTEXT_SUFFIX}`
      : POS_CUSTOMERS_URL;

    const method = editingId ? "PUT" : "POST";

    const responseRaw = await fetch(url, {
      method,
      headers: {
        "Content-Type": "application/json"
      },
      credentials: "same-origin",
      cache: "no-store",
      redirect: "follow",
      body: JSON.stringify(payload || {})
    });

    const response = await handleApiResponse(
      responseRaw,
      method === "POST" ? "create-pos-customer" : "update-pos-customer"
    );

    const rawText = await response.text();

    let result;
    try {
      result = rawText ? JSON.parse(rawText) : {};
    } catch {
      result = { detail: rawText || "Respuesta no JSON del servidor" };
    }

    return { response, result, method };
  }

  return {
    APP_BASE_PATH,
    APP_MENU_URL,
    LOGOUT_URL,
    LOGIN_FALLBACK_URL,
    APP_ID,
    CLIENT_ID,
    API_BASE,
    CONTEXT_SUFFIX,
    SESSION_CHECK_URL,
    CATALOG_SETTINGS_URL,
    CATEGORIES_URL,
    PRODUCTS_URL,
    SALES_URL,
    CATALOG_ITEMS_URL,
    POS_PRICES_URL,
    POS_SETTINGS_URL,
    MAINTENANCE_PRODUCTS_URL,
    SALE_PRODUCTS_URL,
    POS_CUSTOMERS_URL,
    fetchMaintenanceProducts,
    redirectToLogin,
    handleApiResponse,
    fetchJson,
    validateSessionOrRedirect,
    loadCatalogSettings,
    fetchCategories,
    fetchProducts,
    fetchCatalogItems,
    fetchPosPrices,
    createSale,
    createCategory,
    updateCategory,
    createProduct,
    updateProduct,
    createMaintenanceProduct,
    updateMaintenanceProduct,
    savePosPrice,
    doLogout,
    getPosSettings,
    savePosSettings,
    applyStocksSale,
    fetchSaleByTicket,
    cancelSale,
    fetchSalesRetries,
    fetchPosCustomers,
    savePosCustomer,
    fetchSalePrintContext,
    fetchSalePrintData,
    saveSalePrintData,
    openSalePrintWindow,
  };
}