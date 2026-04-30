// pos_prices.js
export function createPosPrices({
  api,
  getCatalogItems,
  getPosPrices,
  getCatalogSource,
  isStocksSource,
  isPosSource,
  canManageCatalogs,
  escapeHtml,
  money,
  setButtonVisibility,
  loadData
}) {
  const priceModal = {};
  const priceEditor = {};

  let editingPriceId = null;

  function openModal(backdrop) {
    if (backdrop) backdrop.classList.add("show");
  }

  function closeModal(backdrop) {
    if (backdrop) backdrop.classList.remove("show");
  }

  function isReadonlyByRoleOrSource() {
    // Regla oficial:
    // El modal de precios NO es readonly por origen.
    // Solo la seguridad determina si puede crear/editar.
    return !canManageCatalogs();
  }

  function setupDomRefs() {
    priceModal.backdrop = document.getElementById("priceModalBackdrop");
    priceModal.listBody = document.getElementById("catalogCommercialListBody");
    priceModal.filterInput = document.getElementById("commercialFilterInput");
    priceModal.newBtn = document.getElementById("newCommercialBtn");
    priceModal.title = document.getElementById("priceModalTitle");

    priceEditor.backdrop = document.getElementById("priceEditorBackdrop");
    priceEditor.form = document.getElementById("priceForm");
    priceEditor.title = document.getElementById("priceEditorTitle");
    priceEditor.catalogItemSelect = document.getElementById("catalogItemSelect");
    priceEditor.salePrice = document.getElementById("catalogSalePrice");
    priceEditor.taxPercent = document.getElementById("catalogTaxPercent");
    priceEditor.isActive = document.getElementById("catalogIsActive");
    priceEditor.submitBtn = document.getElementById("priceSubmitBtn");
  }

  function renderCommercialTable() {
    if (!priceModal.listBody) return;

    const prices = getPosPrices();
    const canEdit = canManageCatalogs();

    if (!prices.length) {
      priceModal.listBody.innerHTML = `
        <tr>
          <td colspan="6" class="catalog-empty-row">No hay catálogo comercial registrado. Puede agregar artículos con el botón "Nuevo".</td>
        </tr>
      `;
      refreshNewCommercialButton();
      return;
    }

    priceModal.listBody.innerHTML = prices.map(item => {
      const productName = item.product_name || `Item comercial #${item.catalog_item_id ?? item.id ?? ""}`;
      const sku = item.sku || "";

      let sourceBadge = "";
      if (item.using_snapshot_fallback) {
        sourceBadge = `<div class="catalog-warning-text">Origen no disponible (usando referencia comercial)</div>`;
      } else if (item.product_missing) {
        sourceBadge = `<div class="catalog-warning-text">Artículo base no localizado</div>`;
      } else if (item.catalog_source === "stocks" && item.product_is_active === false) {
        sourceBadge = `<div class="catalog-warning-text">Artículo origen inactivo en Stocks</div>`;
      }

      return `
        <tr>
          <td>${item.id ?? ""}</td>
          <td>
            ${escapeHtml(productName)}
            ${sourceBadge}
          </td>
          <td>${escapeHtml(sku)}</td>
          <td>$${money(item.sale_price)}</td>
          <td>${item.is_active === false ? "Inactivo" : "Activo"}</td>
          <td>
            ${canEdit ? `<button class="secondary-btn" data-price-edit="${item.id}">Editar</button>` : ""}
          </td>
        </tr>
      `;
    }).join("");

    refreshNewCommercialButton();
  }

  function populateCatalogItemSelect(selectedItemId = null) {
    if (!priceEditor.catalogItemSelect) return;

    const availableItems = getAvailableCatalogItems(selectedItemId);

    priceEditor.catalogItemSelect.innerHTML = `
      <option value="">Seleccione item base...</option>
      ${availableItems.map(item => `
        <option value="${item.id}">
          ${escapeHtml(item.name || "")}${item.sku ? ` (${escapeHtml(item.sku)})` : ""}
        </option>
      `).join("")}
    `;

    if (selectedItemId !== null && selectedItemId !== undefined && selectedItemId !== "") {
      priceEditor.catalogItemSelect.value = String(selectedItemId);
    }
  }

  function getAvailableCatalogItems(selectedItemId = null) {
    const items = getCatalogItems();
    const prices = getPosPrices();
    const currentCatalogSource = String(getCatalogSource() || "pos").toLowerCase();

    const usedIds = new Set(
      prices
        .filter(price => String(price.catalog_source || "pos").toLowerCase() === currentCatalogSource)
        .map(price => Number(price.catalog_item_id))
        .filter(id => Number.isFinite(id) && id > 0)
    );

    return items.filter(item => {
      const itemId = Number(item.id);
      if (!Number.isFinite(itemId) || itemId <= 0) return false;

      if (selectedItemId !== null && itemId === Number(selectedItemId)) {
        return true;
      }

      return !usedIds.has(itemId);
    });
  }

  function refreshNewCommercialButton() {
    if (!priceModal.newBtn) return;

    const readonly = isReadonlyByRoleOrSource();
    const availableItems = getAvailableCatalogItems(null);
    const hasAvailableItems = availableItems.length > 0;

    setButtonVisibility(priceModal.newBtn, !readonly && hasAvailableItems);
    priceModal.newBtn.disabled = readonly || !hasAvailableItems;
    priceModal.newBtn.title = !hasAvailableItems
      ? "Todos los artículos disponibles ya están registrados en el catálogo comercial."
      : "";
  }

  function openCommercialManager() {
    renderCommercialTable();
    openModal(priceModal.backdrop);
  }

  function resetPriceForm() {
    editingPriceId = null;
    if (priceEditor.form) priceEditor.form.reset();
    if (priceEditor.salePrice) priceEditor.salePrice.value = "0";
    if (priceEditor.taxPercent) priceEditor.taxPercent.value = "16";
    if (priceEditor.isActive) priceEditor.isActive.checked = true;
  }

  function openNewPriceEditor() {
    const readonly = isReadonlyByRoleOrSource();

    if (readonly) return;

    resetPriceForm();
    populateCatalogItemSelect(null);

    const availableItems = getAvailableCatalogItems(null);
    if (!availableItems.length) {
      alert("Todos los artículos disponibles ya están registrados en el catálogo comercial.");
      return;
    }

    if (priceEditor.title) {
      priceEditor.title.textContent = "Nuevo precio comercial";
    }
    if (priceEditor.submitBtn) {
      priceEditor.submitBtn.textContent = "Guardar catálogo";
    }

    if (priceEditor.catalogItemSelect) {
      priceEditor.catalogItemSelect.disabled = false;
    }
    if (priceEditor.salePrice) {
      priceEditor.salePrice.disabled = false;
    }
    if (priceEditor.taxPercent) {
      priceEditor.taxPercent.disabled = false;
    }
    if (priceEditor.isActive) {
      priceEditor.isActive.disabled = false;
    }

    setButtonVisibility(priceEditor.submitBtn, true);

    openModal(priceEditor.backdrop);
  }

  function populateCatalogItemSelectForEdit(item) {
    if (!priceEditor.catalogItemSelect) return;

    const selectedId = item?.catalog_item_id ?? "";
    const productName = item?.product_name || "";
    const sku = item?.sku || "";

    priceEditor.catalogItemSelect.innerHTML = `
      <option value="${selectedId}">
        ${escapeHtml(productName)}${sku ? ` (${escapeHtml(sku)})` : ""}
      </option>
    `;

    priceEditor.catalogItemSelect.value = String(selectedId);
  }

  function openEditPriceEditor(priceId) {
    if (!canManageCatalogs()) return;

    const prices = getPosPrices();
    const item = prices.find(p => String(p.id) === String(priceId));
    if (!item) return;

    editingPriceId = item.id;
    const currentCatalogSource = String(item.catalog_source || getCatalogSource() || "pos").toLowerCase();
    const selectedItemId = item.catalog_item_id ?? null;

    // En edición NO debemos depender de que el item siga disponible en el selector de alta.
    // Construimos un option único con el item actual.
    if (priceEditor.catalogItemSelect) {
      const optionLabel = `${item.product_name || "Item"}${item.sku ? ` (${item.sku})` : ""}`;
      priceEditor.catalogItemSelect.innerHTML = `
        <option value="${selectedItemId ?? ""}">
          ${escapeHtml(optionLabel)}
        </option>
      `;
      priceEditor.catalogItemSelect.value = String(selectedItemId ?? "");
      priceEditor.catalogItemSelect.disabled = true;
    }

    if (priceEditor.title) {
      priceEditor.title.textContent = "Editar precio comercial";
    }
    if (priceEditor.submitBtn) {
      priceEditor.submitBtn.textContent = "Guardar catálogo";
    }

    if (priceEditor.salePrice) {
      priceEditor.salePrice.value = String(item.sale_price ?? 0);
      priceEditor.salePrice.disabled = false;
    }

    if (priceEditor.taxPercent) {
      priceEditor.taxPercent.value = String(item.tax_percent ?? 16);
      priceEditor.taxPercent.disabled = false;
    }

    if (priceEditor.isActive) {
      priceEditor.isActive.checked = item.is_active !== false;
      priceEditor.isActive.disabled = false;
    }

    setButtonVisibility(priceEditor.submitBtn, true);

    openModal(priceEditor.backdrop);
  }

  async function submitPriceForm(e) {
    e.preventDefault();

    const readonly = isReadonlyByRoleOrSource();
    if (readonly) return;

    const catalogItemId = priceEditor.catalogItemSelect?.value
      ? Number(priceEditor.catalogItemSelect.value)
      : null;

    const payload = {
      sale_price: Number(priceEditor.salePrice?.value || 0),
      tax_percent: Number(priceEditor.taxPercent?.value || 0),
      is_active: !!priceEditor.isActive?.checked
    };

    if (!editingPriceId) {
      const currentCatalogSource = String(getCatalogSource() || "pos").toLowerCase();

      if (!catalogItemId) {
        alert("Debe seleccionar un item base.");
        return;
      }

      payload.catalog_item_id = catalogItemId;
      payload.catalog_source = currentCatalogSource;
    }

    try {
      await api.savePosPrice({
        editingId: editingPriceId,
        payload
      });

      closeModal(priceEditor.backdrop);
      await loadData();
      renderCommercialTable();
      refreshNewCommercialButton();
    } catch (error) {
      console.error("Error guardando catálogo comercial:", error);
      alert(error?.message || "No se pudo guardar el catálogo comercial.");
    }
  }

  function setupPricesActions() {
    if (priceModal.newBtn) {
      priceModal.newBtn.addEventListener("click", () => {
        openNewPriceEditor();
      });
    }

    if (priceEditor.form) {
      priceEditor.form.addEventListener("submit", submitPriceForm);
    }

    if (priceModal.listBody) {
      priceModal.listBody.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-price-edit]");
        if (!btn) return;
        openEditPriceEditor(btn.dataset.priceEdit);
      });
    }

    if (priceModal.filterInput) {
      priceModal.filterInput.addEventListener("input", () => {
        const term = String(priceModal.filterInput.value || "").toLowerCase().trim();
        const prices = getPosPrices();

        if (!term) {
          renderCommercialTable();
          return;
        }

        const filtered = prices.filter(item => {
          const productName = item.product_name || "";
          const sku = item.sku || "";

          return (
            String(productName).toLowerCase().includes(term) ||
            String(sku).toLowerCase().includes(term)
          );
        });

        if (!filtered.length) {
          priceModal.listBody.innerHTML = `
            <tr>
              <td colspan="6" class="catalog-empty-row">Sin resultados.</td>
            </tr>
          `;
          return;
        }

        const canEdit = canManageCatalogs();

        priceModal.listBody.innerHTML = filtered.map(item => {
          const productName = item.product_name || `Item comercial #${item.catalog_item_id ?? item.id ?? ""}`;
          const sku = item.sku || "";

          let sourceBadge = "";
          if (item.using_snapshot_fallback) {
            sourceBadge = `<div class="catalog-warning-text">Origen no disponible (usando referencia comercial)</div>`;
          } else if (item.product_missing) {
            sourceBadge = `<div class="catalog-warning-text">Artículo base no localizado</div>`;
          } else if (item.catalog_source === "stocks" && item.product_is_active === false) {
            sourceBadge = `<div class="catalog-warning-text">Artículo origen inactivo en Stocks</div>`;
          }

          return `
            <tr>
              <td>${item.id ?? ""}</td>
              <td>
                ${escapeHtml(productName)}
                ${sourceBadge}
              </td>
              <td>${escapeHtml(sku)}</td>
              <td>$${money(item.sale_price)}</td>
              <td>${item.is_active === false ? "Inactivo" : "Activo"}</td>
              <td>
                ${canEdit ? `<button class="secondary-btn" data-price-edit="${item.id}">Editar</button>` : ""}
              </td>
            </tr>
          `;
        }).join("");
      });
    }
  }

  return {
    setupDomRefs,
    setupPricesActions,
    openCommercialManager,
    renderCommercialTable,
    populateCatalogItemSelect
  };
}