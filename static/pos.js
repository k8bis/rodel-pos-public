import { createPosApi } from "./pos_api.js";
import { createPosCart } from "./pos_cart.js";
import { createPosCatalog } from "./pos_catalog.js";
import { createPosMaintenance } from "./pos_maintenance.js";
import { createPosPrices } from "./pos_prices.js";

console.log("POS_JS_INV3B1_SECURITY_FINAL_V2");

const api = createPosApi();

window.POS_API = api;

/* =========================
   CONFIG / SEGURIDAD
========================= */
const POS_CONFIG = window.POS_CONFIG || {};

function getRole() {
  return String(POS_CONFIG.ROLE || "member").trim().toLowerCase();
}

function isSystemAdmin() {
  return POS_CONFIG.IS_SYSTEM_ADMIN === true;
}

function isAppClientAdmin() {
  return POS_CONFIG.IS_APP_CLIENT_ADMIN === true;
}

function isMember() {
  return POS_CONFIG.IS_MEMBER === true || (!isSystemAdmin() && !isAppClientAdmin());
}

function canManageCatalogs() {
  // v6.3 oficial: system_admin y app_client_admin pueden CRUD; member solo consulta
  return POS_CONFIG.CAN_MANAGE_CATALOGS === true || isSystemAdmin() || isAppClientAdmin();
}

function canViewPosConfig() {
  return POS_CONFIG.CAN_VIEW_POS_CONFIG === true || isSystemAdmin() || isAppClientAdmin();
}

function canEditPosConfig() {
  return POS_CONFIG.CAN_EDIT_POS_CONFIG === true || isSystemAdmin();
}

/* =========================
   ESTADO GLOBAL
========================= */
let categories = [];
let products = [];
let maintenanceProducts = [];
let catalogItems = [];
let posPrices = [];
let catalogSettings = {
  catalog_source: "pos",
  catalog_integration_url: null,
  stocks_service_configured: false,
  company_display_name: null
};

let cartModule = null;
let catalogModule = null;
let maintenanceModule = null;
let pricesModule = null;

let posBlocked = false;
let posBlockReason = "";

let pendingSalesNoteData = {
  customer_id: null,
  customer_label: "",
  attended_by: "",
  sales_note_text: "",
  sales_note_extra_text: "",
  services_label: "",
  ticket_footer_text: "",
  payment_method_label: "Efectivo"
};

let currentSaleId = null;

/* =========================
   HELPERS GENERALES
========================= */
function getCatalogSource() {
  return String(catalogSettings?.catalog_source || "pos").toLowerCase();
}

function isStocksSource() {
  return getCatalogSource() === "stocks";
}

function isPosSource() {
  return getCatalogSource() === "pos";
}

function getCatalogIntegrationUrl() {
  const raw = String(catalogSettings?.catalog_integration_url || "").trim();
  return raw || null;
}

function hasStocksServiceConfigured() {
  if (!isStocksSource()) return false;
  return !!getCatalogIntegrationUrl();
}

// inventory_mode queda como snapshot / histórico, NO como switch operativo
function normalizeInventoryMode(value) {
  return String(value || "").trim().toLowerCase();
}

function isService(product) {
  return String(product?.product_type || product?.type || "").toLowerCase() === "service";
}

function getNumericStock(product) {
  const n = Number(product?.stock_quantity ?? 0);
  return Number.isFinite(n) ? n : 0;
}

function canAddToCart(product) {
  if (posBlocked) return false;
  if (!product) return false;
  return product.sellable_now === true;
}

function getBlockReason(product) {
  if (!product) return "Producto inválido.";
  return product.disabled_reason || "Producto no disponible.";
}

function getProductCategoryName(product) {
  if (product?.category_name) return product.category_name;
  if (product?.category?.name) return product.category.name;

  const categoryId = product?.category_id;
  if (categoryId == null) return "";

  const category = categories.find(c => String(c.id) === String(categoryId));
  return category?.name || "";
}

function getProductBadges(product) {
  const badges = [];

  if (isService(product)) {
    badges.push({ label: "Servicio", className: "badge-service" });
  } else if (String(product?.catalog_source || "").toLowerCase() === "stocks") {
    badges.push({ label: "Stocks", className: "badge-stocks" });
  } else {
    badges.push({ label: "POS", className: "badge-pos" });
  }

  if (product.sellable_now !== true) {
    badges.push({ label: "No vendible", className: "badge-muted" });
  }

  return badges;
}

function getStockLabel(product) {
  if (isService(product)) return "Servicio · sin inventario";

  const source = String(product?.catalog_source || "").toLowerCase();

  if (source === "stocks") {
    const onHand = Number(product?.on_hand_qty ?? 0);
    const reserved = Number(product?.reserved_qty ?? 0);
    const stock = Number(product?.stock_quantity ?? 0);

    if (product.source_exists === false) {
      return "Sin existencia en origen Stocks";
    }

    return `Stock: ${stock}`;
  }

  return `Stock: ${getNumericStock(product)}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function money(value) {
  const n = Number(value || 0);
  return Number.isFinite(n) ? n.toFixed(2) : "0.00";
}

function openModal(backdropId) {
  const target = document.getElementById(backdropId);
  if (!target) return;

  document.querySelectorAll(".rs-modal-backdrop.show").forEach(el => {
    if (el !== target && !el.classList.contains("rs-modal-sublevel")) {
      el.classList.remove("show");
    }
  });

  target.dataset.justOpened = "true";
  target.classList.add("show");

  setTimeout(() => {
    delete target.dataset.justOpened;
  }, 50);
}

function closeModal(backdropId) {
  const el = document.getElementById(backdropId);
  if (el) el.classList.remove("show");
}

function closeAllMainModals() {
  closeModal("categoryModalBackdrop");
  closeModal("productModalBackdrop");
  closeModal("priceModalBackdrop");
  closeModal("saleDetailModalBackdrop");
  closeModal("salesOpsModalBackdrop");
}

async function closeSalesOpsModalAndRefresh() {
  closeModal("saleDetailModalBackdrop");
  closeModal("salesOpsModalBackdrop");
  await loadData();
}

function setReadonlyForFormFields(container, readonly) {
  if (!container) return;

  const fields = container.querySelectorAll("input, textarea, select");
  fields.forEach(field => {
    if (field.type === "checkbox" || field.type === "radio") {
      field.disabled = readonly;
    } else {
      field.disabled = readonly;
      if (readonly) {
        field.setAttribute("readonly", "readonly");
      } else {
        field.removeAttribute("readonly");
      }
    }
  });
}

function setButtonVisibility(el, visible) {
  if (!el) return;
  el.style.display = visible ? "" : "none";
}

function setHeaderTitle() {
  const titleEl = document.getElementById("posShellTitle");
  if (!titleEl) return;

  const catalogSource = String(catalogSettings?.catalog_source || "pos").toLowerCase();
  const modeLabel = catalogSource === "stocks" ? "Stocks" : "Local";

  titleEl.textContent = `RodelSoft POS (${modeLabel})`;
}

function getModeLabel() {
  const catalogSource = String(catalogSettings?.catalog_source || "pos").toLowerCase();
  return catalogSource === "stocks" ? "Stocks" : "Local";
}

function getModalTitle(baseTitle) {
  return `${baseTitle} (${getModeLabel()})`;
}

function shouldBlockPosByCatalogConfig() {
  return isStocksSource() && !hasStocksServiceConfigured();
}

function getPosBlockReason() {
  if (shouldBlockPosByCatalogConfig()) {
    return "POS bloqueado: el cliente está configurado con catálogo Stocks pero no tiene catalog_integration_url. No se puede operar hasta configurar el servicio.";
  }
  return "";
}

function setButtonDisabled(el, disabled) {
  if (!el) return;
  el.disabled = !!disabled;
  el.classList.toggle("is-disabled", !!disabled);
}

function showPosBlockedMessage() {
  const message = posBlockReason || getPosBlockReason();
  if (!message) return;

  const catalogGrid = document.getElementById("productsGrid");
  if (catalogGrid) {
    catalogGrid.innerHTML = `
      <div class="empty-state" style="max-width:100%; width:100%;">
        <strong>POS bloqueado</strong><br>
        <span>${escapeHtml(message)}</span>
      </div>
    `;
  }

  const cartItems = document.getElementById("cartItems");
  if (cartItems) {
    cartItems.innerHTML = `
      <div class="empty-state">
        POS bloqueado por configuración incompleta de Stocks.
      </div>
    `;
  }
}

function applyBlockedUiRules() {
  const refreshBtn = document.getElementById("refreshBtn");
  const checkoutBtn = document.getElementById("checkoutBtn");
  const salesHistoryBtn = document.getElementById("salesHistoryBtn");
  const catalogsMenuBtn = document.getElementById("catalogsMenuBtn");
  const manageCustomersBtn = document.getElementById("manageCustomersBtn");
  const manageCategoriesBtn = document.getElementById("manageCategoriesBtn");
  const manageProductsBtn = document.getElementById("manageProductsBtn");

  const blocked = !!posBlocked;

  setButtonDisabled(refreshBtn, false); // refrescar sí se permite
  setButtonDisabled(checkoutBtn, blocked);
  setButtonDisabled(salesHistoryBtn, blocked);
  setButtonDisabled(catalogsMenuBtn, blocked);
  setButtonDisabled(manageCategoriesBtn, blocked);
  setButtonDisabled(manageProductsBtn, blocked);
  setButtonDisabled(manageCustomersBtn, blocked);

  if (blocked) {
    if (checkoutBtn) {
      checkoutBtn.title = posBlockReason;
    }
    if (salesHistoryBtn) {
      salesHistoryBtn.title = posBlockReason;
    }
    if (catalogsMenuBtn) {
      catalogsMenuBtn.title = posBlockReason;
    }
    if (manageCategoriesBtn) {
      manageCategoriesBtn.title = posBlockReason;
    }
    if (manageProductsBtn) {
      manageProductsBtn.title = posBlockReason;
    }
    if (manageCustomersBtn) {
      manageCustomersBtn.title = posBlockReason;
    }
  }
}

function isSalesNoteMode() {
  return String(catalogSettings?.print_document_type || "ticket").trim().toLowerCase() === "sales_note";
}

function getLoggedUserDisplayName() {
  const candidates = [
    POS_CONFIG.USER_FULL_NAME,
    POS_CONFIG.USER_NAME,
    POS_CONFIG.USERNAME,
    POS_CONFIG.EMAIL
  ];

  for (const raw of candidates) {
    const value = String(raw || "").trim();
    if (value) return value;
  }

  return "";
}

function resetPendingSalesNoteData() {
  pendingSalesNoteData = {
    customer_id: catalogSettings?.default_customer_id || null,
    customer_label: catalogSettings?.default_customer_name || "",
    attended_by: getLoggedUserDisplayName(),
    sales_note_text: String(catalogSettings?.sales_note_text_default || "").trim(),
    sales_note_extra_text: String(catalogSettings?.sales_note_extra_text || "").trim(),
    services_label: String(catalogSettings?.sales_note_services_label || "").trim(),
    ticket_footer_text: String(catalogSettings?.ticket_footer_text || "").trim(),
    payment_method_label: "Efectivo"
  };
}

function updateSalesNoteAssignUi() {
  const section = document.getElementById("salesNoteAssignSection");
  const summary = document.getElementById("assignedCustomerSummary");
  const assignBtn = document.getElementById("assignCustomerBtn");

  const visible = isSalesNoteMode() && !posBlocked;

  if (section) {
    section.style.display = visible ? "" : "none";
  }

  if (assignBtn) {
    assignBtn.textContent = pendingSalesNoteData?.customer_id
      ? "👤 Cambiar de cliente"
      : "👤 Selecciona un cliente";
    assignBtn.disabled = !!posBlocked;
  }

  if (summary) {
    if (!visible) {
      summary.textContent = "";
      return;
    }

    if (pendingSalesNoteData?.customer_id) {
      summary.textContent = `Cliente asignado: ${pendingSalesNoteData.customer_label || `#${pendingSalesNoteData.customer_id}`}`;
    } else {
      summary.textContent = "Cliente no asignado.";
    }
  }
}

function buildSalePrintDataPayload() {
  const docType = String(catalogSettings?.print_document_type || "ticket").trim().toLowerCase();
  const isSalesNote = docType === "sales_note";

  const payload = {
    document_type: isSalesNote ? "sales_note" : "ticket",
    payment_method_label: pendingSalesNoteData?.payment_method_label || "Efectivo",
    ticket_footer_text:
      pendingSalesNoteData?.ticket_footer_text ||
      String(catalogSettings?.ticket_footer_text || "").trim() ||
      null,
    sales_note_extra_text:
      pendingSalesNoteData?.sales_note_extra_text ||
      String(catalogSettings?.sales_note_extra_text || "").trim() ||
      null,
    services_label:
      pendingSalesNoteData?.services_label ||
      String(catalogSettings?.sales_note_services_label || "").trim() ||
      null
  };

  if (isSalesNote) {
    payload.pos_customer_id = pendingSalesNoteData?.customer_id || null;
    payload.attended_by =
      String(pendingSalesNoteData?.attended_by || "").trim() ||
      getLoggedUserDisplayName() ||
      null;
    payload.sales_note_text =
      String(pendingSalesNoteData?.sales_note_text || "").trim() ||
      String(catalogSettings?.sales_note_text_default || "").trim() ||
      null;
  }

  return payload;
}

function validatePreCheckoutSalesNote() {
  if (!isSalesNoteMode()) {
    return { ok: true };
  }

  if (!pendingSalesNoteData?.customer_id) {
    return {
      ok: false,
      message: "Debe asignar un cliente antes de procesar una nota de venta."
    };
  }

  return { ok: true };
}

async function openAssignCustomerFlow() {
  if (posBlocked) {
    alert(posBlockReason);
    return;
  }

  if (!isSalesNoteMode()) {
    return;
  }

  if (!maintenanceModule || typeof maintenanceModule.openCustomerManagerForSalesNote !== "function") {
    alert("La selección de cliente para nota de venta no está disponible en esta compilación.");
    return;
  }

  try {
    const selected = await maintenanceModule.openCustomerManagerForSalesNote({
      selectedCustomerId: pendingSalesNoteData?.customer_id || null,
      attendedBy:
        String(pendingSalesNoteData?.attended_by || "").trim() ||
        getLoggedUserDisplayName(),
      salesNoteText:
        String(pendingSalesNoteData?.sales_note_text || "").trim() ||
        String(catalogSettings?.sales_note_text_default || "").trim(),
      salesNoteExtraText:
        String(pendingSalesNoteData?.sales_note_extra_text || "").trim() ||
        String(catalogSettings?.sales_note_extra_text || "").trim(),
      servicesLabel:
        String(pendingSalesNoteData?.services_label || "").trim() ||
        String(catalogSettings?.sales_note_services_label || "").trim(),
      ticketFooterText:
        String(pendingSalesNoteData?.ticket_footer_text || "").trim() ||
        String(catalogSettings?.ticket_footer_text || "").trim(),
      paymentMethodLabel:
        String(pendingSalesNoteData?.payment_method_label || "").trim() || "Efectivo"
    });

    if (!selected || !selected.customer_id) {
      return;
    }

    pendingSalesNoteData = {
      customer_id: selected.customer_id,
      customer_label: selected.customer_label || "",
      attended_by: String(selected.attended_by || "").trim(),
      sales_note_text: String(selected.sales_note_text || "").trim(),
      sales_note_extra_text: String(selected.sales_note_extra_text || "").trim(),
      services_label: String(selected.services_label || "").trim(),
      ticket_footer_text: String(selected.ticket_footer_text || "").trim(),
      payment_method_label: String(selected.payment_method_label || "Efectivo").trim() || "Efectivo"
    };

    updateSalesNoteAssignUi();
  } catch (error) {
    console.error("Error en asignación de customer para nota:", error);
    alert(error?.message || "No se pudo completar la asignación del cliente.");
  }
}

/* =========================
   CARGA DE DATOS
========================= */
async function loadData() {
  try {
    catalogSettings = await api.loadCatalogSettings();
    window.CATALOG_SETTINGS = catalogSettings; // para debug en consola
    setHeaderTitle();

    posBlocked = shouldBlockPosByCatalogConfig();
    posBlockReason = getPosBlockReason();

    if (posBlocked) {
      categories = [];
      products = [];
      maintenanceProducts = [];
      catalogItems = [];
      posPrices = [];

      if (catalogModule) {
        catalogModule.renderCategories();
        catalogModule.renderProducts([]);
      }

      if (cartModule) {
        cartModule.renderCart();
      }

      if (maintenanceModule) {
        maintenanceModule.renderCategoryTable();
        maintenanceModule.renderProductTable();
        maintenanceModule.populateCategorySelect();
      }

      if (pricesModule) {
        pricesModule.renderCommercialTable();
        pricesModule.populateCatalogItemSelect();
      }

      applyCatalogSourceUiRules();
      applyRoleUiRules();
      applyBlockedUiRules();
      resetPendingSalesNoteData();
      updateSalesNoteAssignUi();

      return;
    }

    const [catData, productData, maintenanceProductData, catalogItemsData, posPricesData] = await Promise.all([
      api.fetchCategories().catch(err => {
        console.error("fetchCategories error:", err);
        return [];
      }),
      api.fetchProducts().catch(err => {
        console.error("fetchProducts error:", err);
        return [];
      }),
      api.fetchMaintenanceProducts().catch(err => {
        console.error("fetchMaintenanceProducts error:", err);
        return [];
      }),
      api.fetchCatalogItems().catch(err => {
        console.error("fetchCatalogItems error:", err);
        return [];
      }),
      api.fetchPosPrices().catch(err => {
        console.error("fetchPosPrices error:", err);
        return [];
      })
    ]);

    categories = Array.isArray(catData) ? catData : [];
    products = Array.isArray(productData) ? productData : [];
    maintenanceProducts = Array.isArray(maintenanceProductData) ? maintenanceProductData : [];
    catalogItems = Array.isArray(catalogItemsData) ? catalogItemsData : [];
    posPrices = Array.isArray(posPricesData) ? posPricesData : [];

    if (catalogModule) {
      catalogModule.renderCategories();
      catalogModule.renderProducts(products);
    }

    if (cartModule) {
      cartModule.renderCart();
    }

    if (maintenanceModule) {
      maintenanceModule.renderCategoryTable();
      maintenanceModule.renderProductTable();
      maintenanceModule.populateCategorySelect();
    }

    if (pricesModule) {
      pricesModule.renderCommercialTable();
      pricesModule.populateCatalogItemSelect();
    }

    applyCatalogSourceUiRules();
    applyRoleUiRules();
    applyBlockedUiRules();

    resetPendingSalesNoteData();
    updateSalesNoteAssignUi();
  } catch (error) {
    console.error("Error cargando datos del POS:", error);

    if (String(error.message).includes("Sesión expirada o inválida")) {
      return;
    }

    if (catalogModule) {
      catalogModule.showCatalogLoadError();
    }
  }
}

/* =========================
   CATÁLOGO / CARRITO
========================= */
function bindCartGlobals() {
  window.updateQuantity = (productId, newQty) => {
    if (!cartModule) return;
    cartModule.updateQuantity(productId, newQty);
  };
}

/* =========================
   REGLAS UI
========================= */
function applyCatalogSourceUiRules() {
  const categoriesBtn = document.getElementById("manageCategoriesBtn");
  const productsBtn = document.getElementById("manageProductsBtn");
  const catalogsBtn = document.getElementById("catalogsMenuBtn");

  if (categoriesBtn) {
    categoriesBtn.title = isStocksSource()
      ? "Modo consulta (origen Stocks)"
      : "Mantenimiento de categorías POS";
  }

  if (productsBtn) {
    productsBtn.title = isStocksSource()
      ? "Modo consulta (origen Stocks)"
      : "Mantenimiento de productos POS";
  }

  if (catalogsBtn) {
    catalogsBtn.title = isStocksSource()
      ? "Catálogo comercial POS sobre items base de Stocks"
      : "Catálogo comercial POS";
  }
}

function applyRoleUiRules() {
  const posConfigMenuBtn = document.getElementById("posConfigMenuBtn");
  const manageCategoriesBtn = document.getElementById("manageCategoriesBtn");
  const manageProductsBtn = document.getElementById("manageProductsBtn");
  const catalogsMenuBtn = document.getElementById("catalogsMenuBtn");
  const manageCustomersBtn = document.getElementById("manageCustomersBtn");

  const posConfigMenuSection = document.getElementById("posConfigMenuSection");

  if (posConfigMenuSection) {
    setButtonVisibility(posConfigMenuSection, canViewPosConfig());
  } else if (posConfigMenuBtn) {
    setButtonVisibility(posConfigMenuBtn, canViewPosConfig());
  }

  if (manageCategoriesBtn) {
    manageCategoriesBtn.title = canManageCatalogs()
      ? (isStocksSource() ? "Modo consulta (origen Stocks)" : "Administrar categorías")
      : "Solo consulta";
  }

  if (manageProductsBtn) {
    manageProductsBtn.title = canManageCatalogs()
      ? (isStocksSource() ? "Modo consulta (origen Stocks)" : "Administrar productos")
      : "Solo consulta";
  }

  if (catalogsMenuBtn) {
    catalogsMenuBtn.title = canManageCatalogs()
      ? (isStocksSource()
          ? "Catálogo comercial POS sobre items base de Stocks"
          : "Administrar catálogo de precios")
      : "Solo consulta";
  }
  
  if (manageCustomersBtn) {
    manageCustomersBtn.title = "Catálogo operativo de clientes POS";
  }

}

/* =========================
   MENÚ / NAVEGACIÓN
========================= */
function setupUserMenu() {
  const userMenuBtn = document.getElementById("userMenuBtn");
  const userDropdown = document.getElementById("userDropdown");

  if (!userMenuBtn || !userDropdown) return;

  userMenuBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    userDropdown.classList.toggle("show");
  });

  document.addEventListener("click", (e) => {
    if (!userDropdown.contains(e.target) && e.target !== userMenuBtn) {
      userDropdown.classList.remove("show");
    }
  });

  userDropdown.addEventListener("click", (e) => {
    e.stopPropagation();
  });
}

function closeUserDropdown() {
  const userDropdown = document.getElementById("userDropdown");
  if (userDropdown) {
    userDropdown.classList.remove("show");
  }
}

function setupMenuActions() {
  const appsMenuBtn = document.getElementById("appsMenuBtn");
  const catalogsMenuBtn = document.getElementById("catalogsMenuBtn");
  const manageCustomersBtn = document.getElementById("manageCustomersBtn");
  const manageCategoriesBtn = document.getElementById("manageCategoriesBtn");
  const manageProductsBtn = document.getElementById("manageProductsBtn");
  const posConfigMenuBtn = document.getElementById("posConfigMenuBtn");
  const logoutBtn = document.getElementById("logoutBtn");

  if (appsMenuBtn) {
    appsMenuBtn.addEventListener("click", () => {
      closeUserDropdown();
      window.location.href = api.APP_MENU_URL;
    });
  }

  if (catalogsMenuBtn) {
    catalogsMenuBtn.addEventListener("click", () => {
      closeUserDropdown();

      if (posBlocked) {
        alert(posBlockReason);
        return;
      }

      if (pricesModule) pricesModule.openCommercialManager();
    });
  }

  if (manageCustomersBtn) {
    manageCustomersBtn.addEventListener("click", async () => {
      closeUserDropdown();

      if (posBlocked) {
        alert(posBlockReason);
        return;
      }

      if (!maintenanceModule || typeof maintenanceModule.openCustomerManager !== "function") {
        alert("Catálogo de customers no disponible en esta compilación.");
        return;
      }

      await maintenanceModule.openCustomerManager();
    });
  }

  if (manageCategoriesBtn) {
    manageCategoriesBtn.addEventListener("click", () => {
      closeUserDropdown();

      if (posBlocked) {
        alert(posBlockReason);
        return;
      }

      if (maintenanceModule) maintenanceModule.openCategoryManager();
    });
  }

  if (manageProductsBtn) {
    manageProductsBtn.addEventListener("click", () => {
      closeUserDropdown();

      if (posBlocked) {
        alert(posBlockReason);
        return;
      }

      if (maintenanceModule) maintenanceModule.openProductManager();
    });
  }

  if (posConfigMenuBtn) {
    posConfigMenuBtn.addEventListener("click", async () => {
      closeUserDropdown();

      if (!canViewPosConfig()) {
        return;
      }

      if (!maintenanceModule || typeof maintenanceModule.openPosConfigManager !== "function") {
        alert("Configuración POS no disponible en esta compilación.");
        return;
      }

      await maintenanceModule.openPosConfigManager({
        readonly: !canEditPosConfig()
      });
    });
  }

  if (logoutBtn) {
    logoutBtn.addEventListener("click", async () => {
      closeUserDropdown();
      await api.doLogout();
    });
  }
}

/* =========================
   EVENTOS UI
========================= */
function setupRefreshButton() {
  const refreshBtn = document.getElementById("refreshBtn");
  if (!refreshBtn) return;

  refreshBtn.addEventListener("click", async () => {
    await loadData();
  });
}

function setupAssignCustomerButton() {
  const assignBtn = document.getElementById("assignCustomerBtn");
  if (!assignBtn) return;

  assignBtn.addEventListener("click", async () => {
    await openAssignCustomerFlow();
  });
}

function setupCheckoutButton() {
  const checkoutBtn = document.getElementById("checkoutBtn");
  if (!checkoutBtn) return;

  checkoutBtn.addEventListener("click", async () => {
    if (posBlocked) {
      alert(posBlockReason);
      return;
    }

    if (!cartModule) return;

    const precheck = validatePreCheckoutSalesNote();
    if (!precheck.ok) {
      alert(precheck.message || "No se puede continuar.");
      return;
    }

    checkoutBtn.disabled = true;

    try {
      if (typeof cartModule.submitCheckout !== "function") {
        throw new Error("submitCheckout no disponible en cartModule.");
      }

      const submit = await cartModule.submitCheckout();

      if (!submit?.ok) {
        const msg = submit?.result?.detail || `Error HTTP ${submit?.response?.status || "N/A"}`;
        alert(`No se pudo procesar la venta: ${msg}`);
        return;
      }

      const saleId = submit?.result?.id;
      const saleNumber = submit?.result?.sale_number || saleId || "N/A";

      if (!saleId) {
        throw new Error("La venta se guardó pero no regresó ID.");
      }

      const printPayload = buildSalePrintDataPayload();
      const { response, result } = await api.saveSalePrintData(saleId, printPayload);

      if (!response?.ok) {
        throw new Error(result?.detail || `La venta ${saleNumber} se guardó, pero no se pudo guardar la información documental.`);
      }

      let printErrorMessage = "";

      try {
        if (typeof api.openSalePrintWindow === "function") {
          await api.openSalePrintWindow(saleId);
        } else {
          printErrorMessage = "La impresión no está disponible en esta compilación.";
        }
      } catch (printError) {
        console.error("Error abriendo impresión de venta:", printError);
        printErrorMessage = printError?.message || "No se pudo abrir la impresión automática.";
      }

      if (typeof cartModule.clearCartAfterSuccessfulFlow === "function") {
        cartModule.clearCartAfterSuccessfulFlow();
      }

      resetPendingSalesNoteData();
      updateSalesNoteAssignUi();

      await loadData();

      if (printErrorMessage) {
        alert(`Venta procesada correctamente. Folio: ${saleNumber}\n\nPero no se pudo abrir la impresión automática:\n${printErrorMessage}`);
      } else {
        alert(`Venta procesada correctamente. Folio: ${saleNumber}`);
      }
    } catch (error) {
      console.error("Error en checkout orquestado POS:", error);

      if (String(error.message).includes("Sesión expirada o inválida")) {
        return;
      }

      alert(error?.message || "No se pudo completar el flujo de venta.");
    } finally {
      checkoutBtn.disabled = false;
    }
  });
}

function setupSalesHistoryButton() {
  const salesHistoryBtn = document.getElementById("salesHistoryBtn");
  if (!salesHistoryBtn) return;

  const salesOpsModalTitle = document.getElementById("salesOpsModalTitle");
  const saleDetailModalTitle = document.getElementById("saleDetailModalTitle");

  const salesOpsSearchBtn = document.getElementById("salesOpsSearchBtn");
  const salesOpsTicketInput = document.getElementById("salesOpsTicketInput");

  const salesRetryListBody = document.getElementById("salesRetryListBody");

  const saleDetailStatus = document.getElementById("saleDetailStatus");
  const saleDetailNumber = document.getElementById("saleDetailNumber");
  const saleDetailSource = document.getElementById("saleDetailSource");
  const saleDetailSummary = document.getElementById("saleDetailSummary");
  const saleCancelReason = document.getElementById("saleCancelReason");
  const saleCancelBtn = document.getElementById("saleCancelBtn");
  const saleReprintBtn = document.getElementById("saleReprintBtn");

  function resetSaleDetail() {
    if (saleDetailStatus) saleDetailStatus.value = "Sin consultar";
    if (saleDetailNumber) saleDetailNumber.value = "";
    if (saleDetailSource) saleDetailSource.value = "";
    if (saleCancelReason) saleCancelReason.value = "";

    if (saleDetailSummary) {
      saleDetailSummary.innerHTML = `
        <div class="catalog-empty-row" style="border: none;">
          Busque un ticket para visualizar su detalle.
        </div>
      `;
    }

    if (saleCancelBtn) {
      saleCancelBtn.style.display = "none";
      saleCancelBtn.disabled = false;
    }
  }

  async function loadRetryTable() {
    if (!salesRetryListBody) return;

    salesRetryListBody.innerHTML = `
      <tr>
        <td colspan="6" class="catalog-empty-row">Cargando...</td>
      </tr>
    `;
    try {
      const result = await api.fetchSalesRetries();
      const items = result?.items || [];

      if (!items.length) {
        salesRetryListBody.innerHTML = `
          <tr>
            <td colspan="6" class="catalog-empty-row">
              Sin reintentos pendientes.
            </td>
          </tr>
        `;
        return;
      }

      salesRetryListBody.innerHTML = items.map(item => `
        <tr>
          <td>${item.sale_number}</td>
          <td>${item.retry_type_label}</td>
          <td>${item.origin_label}</td>
          <td>${item.last_message}</td>
          <td>${item.event_date}</td>
          <td>
            <button class="secondary-btn" data-retry-ticket="${item.sale_number}">
              Abrir
            </button>
          </td>
        </tr>
      `).join("");

    } catch (e) {
      salesRetryListBody.innerHTML = `
        <tr>
          <td colspan="6" class="catalog-empty-row">
            Error cargando reintentos
          </td>
        </tr>
      `;
    }
  }

  async function searchTicketAndOpenDetail() {
    const ticket = String(salesOpsTicketInput?.value || "").trim();
    if (!ticket) {
      alert("Debe capturar un número de ticket");
      return;
    }

    try {
      const sale = await api.fetchSaleByTicket(ticket);

      if (saleDetailNumber) {
        saleDetailNumber.value = sale.sale_number || ticket;
      }
      
      currentSaleId = sale.id || null;

      // =========================
      // CONTROL VISIBILIDAD CANCELACIÓN
      // =========================
      if (saleCancelBtn) {
        const status = String(sale?.status || "").toLowerCase();

        const isAdminUser = isSystemAdmin() || isAppClientAdmin();

        const canCancel =
          isAdminUser &&
          status !== "cancelled";

        saleCancelBtn.style.display = canCancel ? "" : "none";
      }

      if (saleDetailStatus) {
        const statusMap = {
          completed: "Completado",
          cancelled: "Cancelado",
          pending: "Pendiente",
          pending_inventory: "Pendiente por inventario",
        };
        saleDetailStatus.value = statusMap[sale.status] || sale.status || "N/A";
      }

      if (saleDetailSource) {
        const sourceMap = {
          stocks: "Stocks",
          pos: "POS"
        };
        saleDetailSource.value = sourceMap[sale.catalog_source_snapshot] || sale.catalog_source_snapshot || "N/A";
      }

      const itemsHtml = Array.isArray(sale?.items) && sale.items.length
        ? sale.items.map(item => {
            const qty = Number(item?.quantity || 0).toFixed(0);
            const name = escapeHtml(item?.product_name_snapshot || "Item");
            const kind = escapeHtml(item?.product_type_snapshot || "physical");
            return `<li>${name} — Cantidad: ${qty} — Tipo: ${kind}</li>`;
          }).join("")
        : "<li>Sin items</li>";

      if (saleDetailSummary) {
        saleDetailSummary.innerHTML = `
          <div><strong>Ticket:</strong> ${sale.sale_number}</div>
          <div><strong>Total:</strong> $${Number(sale.total_amount || 0).toFixed(2)}</div>
          <div><strong>Estado venta:</strong> ${sale.status}</div>
          <div><strong>Cancelado por:</strong> ${escapeHtml(sale?.cancelled_by || "-")}</div>
          <div><strong>Motivo cancelación:</strong> ${escapeHtml(sale?.cancellation_reason || "-")}</div>
          <div>
            <strong>Productos / Servicios:</strong>
            <ul style="margin:0.35rem 0 0 1.25rem; padding:0;">
              ${itemsHtml}
            </ul>
          </div>
        `;
      }

      // 🔴 abrir submodal correctamente
      const detailModal = document.getElementById("saleDetailModalBackdrop");
      if (detailModal) {

        // 🔴 mismo fix estructural
        ensureModalInBody("saleDetailModalBackdrop");

        // 🔴 cerrar otros subniveles
        document.querySelectorAll(".rs-modal-backdrop.show").forEach(el => {
          if (el !== detailModal) el.classList.remove("show");
        });

        detailModal.classList.add("show");
      }

    } catch (e) {
      alert("Error consultando ticket");
    }
  }

  

  // 🔴 BOTÓN HISTORIAL (AQUÍ ESTÁ EL FIX REAL)
  salesHistoryBtn.addEventListener("click", async (e) => {
    e.preventDefault();
    e.stopPropagation();

    const modal = document.getElementById("salesOpsModalBackdrop");
    if (!modal) return;

    // 🔴 mover a body (clave)
    ensureModalInBody("salesOpsModalBackdrop");

    // 🔴 cerrar otros
    document.querySelectorAll(".rs-modal-backdrop.show").forEach(el => {
      el.classList.remove("show");
    });

    // 🔴 abrir (patrón correcto)
    modal.classList.add("show");

    // 🔴 TU LÓGICA ORIGINAL
    if (salesOpsModalTitle) {
      salesOpsModalTitle.textContent = "Historial / Cancelación";
    }

    if (saleDetailModalTitle) {
      saleDetailModalTitle.textContent = "Detalle de ticket";
    }

    if (salesOpsTicketInput) {
      salesOpsTicketInput.value = "";
    }

    resetSaleDetail();
    await loadRetryTable();
  });

  if (salesOpsSearchBtn) {
    salesOpsSearchBtn.addEventListener("click", searchTicketAndOpenDetail);
  }

  if (saleReprintBtn) {
    console.log("saleReprintBtn SALE ID:", currentSaleId);
    saleReprintBtn.addEventListener("click", async () => {
      try {
        if (!currentSaleId) {
          alert("No hay venta seleccionada");
          return;
        }

        await api.openSalePrintWindow(currentSaleId);

      } catch (error) {
        console.error("Error en reimpresión:", error);
        alert(error.message || "No se pudo reimprimir");
      }
    });
  }

  if (saleCancelBtn) {
    saleCancelBtn.addEventListener("click", async () => {
      try {
        if (!currentSaleId) {
          alert("No hay venta seleccionada");
          return;
        }

        const reason = String(saleCancelReason?.value || "").trim();

        if (!reason) {
          alert("Debe capturar el motivo de cancelación");
          return;
        }

        const confirmCancel = confirm("¿Confirmas cancelar la venta?");
        if (!confirmCancel) return;

        const { response, result } = await api.cancelSale(currentSaleId, {
          reason
        });

        if (!response?.ok) {
          throw new Error(result?.detail || "Error al cancelar la venta");
        }

        alert("Venta cancelada correctamente");

        // refrescar UI
        await loadData();
        closeModal("saleDetailModalBackdrop");

      } catch (error) {
        console.error("Error cancelando venta:", error);
        alert(error.message || "No se pudo cancelar la venta");
      }
    });
  }
}

function setupModalClosers() {
  document.querySelectorAll("[data-close-modal]").forEach(btn => {
    btn.addEventListener("click", () => {
      closeAllMainModals();
    });
  });

  document.querySelectorAll("[data-close-category-editor]").forEach(btn => {
    btn.addEventListener("click", () => closeModal("categoryEditorBackdrop"));
  });

  document.querySelectorAll("[data-close-product-editor]").forEach(btn => {
    btn.addEventListener("click", () => closeModal("productEditorBackdrop"));
  });

  document.querySelectorAll("[data-close-price-editor]").forEach(btn => {
    btn.addEventListener("click", () => closeModal("priceEditorBackdrop"));
  });

  document.querySelectorAll(".rs-modal-backdrop").forEach(backdrop => {
    backdrop.addEventListener("click", async (e) => {

      if (e.target !== backdrop) return;

      const isJustOpened = backdrop.dataset.justOpened === "true";
      if (isJustOpened) return;

      const hasActiveSubmodal = document.querySelector(".rs-modal-sublevel.show");
      if (hasActiveSubmodal) return;

      backdrop.classList.remove("show");
    });
  });

  document.querySelectorAll("[data-close-sales-ops]").forEach(btn => {
    btn.addEventListener("click", async () => {
      await closeSalesOpsModalAndRefresh();
    });
  });

  document.querySelectorAll("[data-close-sale-detail]").forEach(btn => {
    btn.addEventListener("click", () => closeModal("saleDetailModalBackdrop"));
  });
}

function ensureModalInBody(modalId) {
  const modal = document.getElementById(modalId);
  if (!modal) return;

  if (modal.parentElement !== document.body) {
    document.body.appendChild(modal);
  }
}

/* =========================
   INIT
========================= */
async function initPos() {
  const ok = await api.validateSessionOrRedirect();
  if (!ok) return;

  cartModule = createPosCart({
    getProducts: () => products,
    isService,
    // compatibilidad: mantenemos nombres que otros módulos ya consumen,
    // pero los desligamos de inventory_mode como switch operativo
    usesStocksApi: () => isStocksSource(),
    usesLegacyStock: () => isPosSource(),
    getNumericStock,
    canAddToCart,
    getBlockReason,
    loadData,
    api
  });

  catalogModule = createPosCatalog({
    getCategories: () => categories,
    getProducts: () => products,
    addToCart: (productId) => cartModule.addToCart(productId),
    canAddToCart,
    usesLegacyStock: () => isPosSource(),
    usesStocksApi: () => isStocksSource(),
    getProductBadges,
    getProductCategoryName,
    getStockLabel
  });

  maintenanceModule = createPosMaintenance({
    api,
    getCategories: () => categories,
    getMaintenanceProducts: () => maintenanceProducts,
    getCatalogSource,
    isStocksSource,
    isPosSource,
    canManageCatalogs,
    canEditPosConfig,
    escapeHtml,
    money,
    setReadonlyForFormFields,
    setButtonVisibility,
    loadData
  });

  pricesModule = createPosPrices({
    api,
    getCatalogItems: () => catalogItems,
    getPosPrices: () => posPrices,
    getCatalogSource,
    isStocksSource,
    isPosSource,
    canManageCatalogs,
    escapeHtml,
    money,
    setButtonVisibility,
    loadData
  });

  if (maintenanceModule && typeof maintenanceModule.setupDomRefs === "function") {
    maintenanceModule.setupDomRefs();
  }

  if (pricesModule && typeof pricesModule.setupDomRefs === "function") {
    pricesModule.setupDomRefs();
  }

  bindCartGlobals();

  setupUserMenu();
  setupMenuActions();
  setupRefreshButton();
  
  // 🔴 BUG P5 — refresh automático
  setInterval(async () => {

    try {

      // NO refrescar si hay modales abiertos
      const openModal = document.querySelector(".rs-modal-backdrop.show");

      if (openModal) {
        return;
      }

      await loadData();

      if (
        catalogModule &&
        typeof catalogModule.restoreCatalogState === "function"
      ) {
        catalogModule.restoreCatalogState();
      }

    } catch (e) {
      console.warn("Auto refresh falló:", e);
    }

  }, 15000);


  setupAssignCustomerButton();
  setupCheckoutButton();
  setupSalesHistoryButton();
  setupModalClosers();

  if (maintenanceModule) {
    maintenanceModule.setupMaintenanceActions();
  }

  if (pricesModule) {
    pricesModule.setupPricesActions();
  }

  catalogModule.setupSearch();

  applyRoleUiRules();
  await loadData();
}

document.addEventListener("DOMContentLoaded", initPos);