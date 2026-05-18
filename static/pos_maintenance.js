export function createPosMaintenance({
  api,
  getCategories,
  getMaintenanceProducts,
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
}) {
  const categoryModal = {};
  const categoryEditor = {};
  const productModal = {};
  const productEditor = {};

  let editingCategoryId = null;
  let editingProductId = null;

  const posConfigModal = {
    backdrop: null,
    form: null,
    companyDisplayName: null,
    ticketFooterText: null,
    catalogSource: null,
    catalogIntegrationUrl: null,
    submitBtn: null,
    title: null,
    saveBar: null,
    hint: null

  };

  const customerModal = {
    backdrop: null,
    title: null,
    filterInput: null,
    newBtn: null,
    listBody: null,
    selectionPanel: null,
    selectedSummary: null,
    attendedBy: null,
    salesNoteText: null,
    salesNoteExtraText: null,
    servicesLabel: null,
    ticketFooterText: null,
    paymentMethodLabel: null,
    continueBtn: null,
    cancelSelectionBtn: null
  };

  const customerEditor = {
    backdrop: null,
    title: null,
    form: null,
    submitBtn: null,
    saveBar: null,
    id: null,
    rfc: null,
    businessName: null,
    contactName: null,
    phone: null,
    email: null,
    address: null,
    postalCode: null,
    taxRegime: null,
    cfdiUse: null,
    isActive: null
  };

  let customerRows = [];
  let editingCustomerId = null;
  let customerManagerEventsBound = false;
  let customerSelectionMode = null;
  let customerSelectionState = {
    selectedCustomerId: null,
    selectedCustomerLabel: "",
    attendedBy: "",
    salesNoteText: "",
    salesNoteExtraText: "",
    servicesLabel: "",
    ticketFooterText: "",
    paymentMethodLabel: "Efectivo"
  };
  let customerSelectionResolver = null;


  function openModal(backdrop) {
    if (backdrop) backdrop.classList.add("show");
  }

  function closeModal(backdrop) {
    if (backdrop) backdrop.classList.remove("show");
  }

  function isReadonlyByRoleOrSource() {
    const readonlyBySource = isStocksSource() && !isPosSource();
    const readonlyByRole = !canManageCatalogs();
    return readonlyBySource || readonlyByRole;
  }

  function setupDomRefs() {
    // Category list modal
    categoryModal.backdrop = document.getElementById("categoryModalBackdrop");
    categoryModal.listBody = document.getElementById("categoryListBody");
    categoryModal.filterInput = document.getElementById("categoryFilterInput");
    categoryModal.newBtn = document.getElementById("newCategoryBtn");
    categoryModal.title = document.getElementById("categoryModalTitle");

    // Category editor
    categoryEditor.backdrop = document.getElementById("categoryEditorBackdrop");
    categoryEditor.form = document.getElementById("categoryForm");
    categoryEditor.title = document.getElementById("categoryEditorTitle");
    categoryEditor.name = document.getElementById("categoryName");
    categoryEditor.description = document.getElementById("categoryDescription");
    categoryEditor.color = document.getElementById("categoryColor");
    categoryEditor.parentId = document.getElementById("categoryParentId");
    categoryEditor.submitBtn = document.getElementById("categorySubmitBtn");

    // Product list modal
    productModal.backdrop = document.getElementById("productModalBackdrop");
    productModal.listBody = document.getElementById("productListBody");
    productModal.filterInput = document.getElementById("productFilterInput");
    productModal.newBtn = document.getElementById("newProductBtn");
    productModal.title = document.getElementById("productModalTitle");

    // Product editor
    productEditor.backdrop = document.getElementById("productEditorBackdrop");
    productEditor.form = document.getElementById("productForm");
    productEditor.title = document.getElementById("productEditorTitle");
    productEditor.submitBtn = document.getElementById("productSubmitBtn");
    productEditor.name = document.getElementById("productName");
    productEditor.description = document.getElementById("productDescription");
    productEditor.productType = document.getElementById("productType");
    productEditor.trackInventory = document.getElementById("trackInventory");
    productEditor.categoryId = document.getElementById("productCategoryId");
    productEditor.sku = document.getElementById("productSku");
    productEditor.barcode = document.getElementById("productBarcode");
    productEditor.costPrice = document.getElementById("productCostPrice");
    productEditor.stockQuantity = document.getElementById("productStockQuantity");
    productEditor.minStock = document.getElementById("productMinStock");
    productEditor.inventoryMode = document.getElementById("productInventoryMode");
    productEditor.stockItemId = document.getElementById("productStockItemId");
    productEditor.localInventorySection = document.getElementById("localInventorySection");
  }

  function ensurePosConfigModal() {
    if (posConfigModal.backdrop) return;

    const wrapper = document.createElement("div");
    wrapper.innerHTML = `
      <div class="rs-modal-backdrop" id="posConfigBackdrop">
        <div class="rs-modal-card rs-modal-card-lg">
          <div class="rs-modal-header">
            <h3 id="posConfigTitle">Configuración POS</h3>
            <button type="button" class="rs-modal-close" id="closePosConfigBtn">✕</button>
          </div>

          <form id="posConfigForm" class="rs-modal-form">
            <div class="rs-form-grid">
              <div class="rs-form-group">
                <label for="posCfgCompanyDisplayName">Nombre comercial mostrado</label>
                <input type="text" id="posCfgCompanyDisplayName" maxlength="200" />
              </div>
            </div>

            <div class="rs-poscfg-tabs">
              <button type="button" class="rs-btn rs-btn-primary" id="posCfgMainTabPrint">
                Personalización de Impresión
              </button>
              <button type="button" class="rs-btn rs-btn-secondary" id="posCfgMainTabCommercial">
                Configuración Comercial
              </button>
            </div>

            <div id="posCfgMainPanelPrint">
              <div class="rs-form-section">
                <div class="rs-form-section-title">Tipo de impresión</div>

                <div class="rs-form-grid rs-form-grid-3">
                  <div class="rs-form-group">
                    <label for="posCfgPrintDocumentType">Documento a imprimir</label>
                    <select id="posCfgPrintDocumentType">
                      <option value="ticket">Ticket</option>
                      <option value="sales_note">Nota de venta</option>
                    </select>
                  </div>

                  <div class="rs-form-group" id="posCfgTicketTemplateWrap">
                    <label for="posCfgTicketTemplateName">Template ticket</label>
                    <input
                      type="text"
                      id="posCfgTicketTemplateName"
                      maxlength="255"
                      placeholder="ticket_default.html"
                    />
                  </div>

                  <div class="rs-form-group" id="posCfgSalesNoteTemplateWrap">
                    <label for="posCfgSalesNoteTemplateName">Template nota</label>
                    <input
                      type="text"
                      id="posCfgSalesNoteTemplateName"
                      maxlength="255"
                      placeholder="sales_note_default.html"
                    />
                  </div>
                </div>
              </div>

              <div class="rs-form-section">
                <div class="rs-form-section-title">Textos de impresión</div>

                <div class="rs-form-grid rs-form-grid-2">
                  <div class="rs-form-group">
                    <label for="posCfgSalesNoteTextDefault">Texto principal</label>
                    <textarea id="posCfgSalesNoteTextDefault" rows="3"></textarea>
                  </div>

                  <div class="rs-form-group">
                    <label for="posCfgSalesNoteServicesLabel">Texto secundario</label>
                    <input
                      type="text"
                      id="posCfgSalesNoteServicesLabel"
                      maxlength="255"
                      placeholder="SERVICIOS"
                    />
                  </div>

                  <div class="rs-form-group" style="grid-column: 1 / -1;">
                    <label for="posCfgSalesNoteExtraText">Texto extra largo</label>
                    <textarea id="posCfgSalesNoteExtraText" rows="3"></textarea>
                  </div>

                  <div class="rs-form-group" style="grid-column: 1 / -1;">
                    <label for="posCfgTicketFooterText">Texto en pie</label>
                    <textarea id="posCfgTicketFooterText" rows="3"></textarea>
                  </div>
                </div>
              </div>
            </div>

            <div id="posCfgMainPanelCommercial">
              <div class="rs-form-section">
                <div class="rs-form-section-title">Datos Fiscales</div>

                <div class="rs-form-grid rs-form-grid-3">
                  <div class="rs-form-group">
                    <label for="posCfgDefaultTicketTaxRegime">Régimen fiscal</label>
                    <input
                      type="text"
                      id="posCfgDefaultTicketTaxRegime"
                      maxlength="10"
                      placeholder="616"
                    />
                  </div>

                  <div class="rs-form-group">
                    <label for="posCfgDefaultTicketCfdiUse">Uso de CFDI</label>
                    <input
                      type="text"
                      id="posCfgDefaultTicketCfdiUse"
                      maxlength="10"
                      placeholder="S01"
                    />
                  </div>

                  <div class="rs-form-group">
                    <label for="posCfgDefaultTaxPercent">IVA por defecto (%)</label>
                    <input type="number" id="posCfgDefaultTaxPercent" min="0" step="0.01" />
                  </div>
                </div>
              </div>

              <div class="rs-form-section">
                <div class="rs-form-section-title">Gestión de inventario</div>

                <div class="rs-form-grid rs-form-grid-2">
                  <div class="rs-form-group">
                    <label for="posCfgCatalogSource">App de inventario</label>
                    <select id="posCfgCatalogSource">
                      <option value="pos">POS</option>
                      <option value="stocks">Stocks</option>
                    </select>
                  </div>

                  <div class="rs-form-group">
                    <label for="posCfgCatalogIntegrationUrl">URL de Stocks</label>
                    <input
                      type="text"
                      id="posCfgCatalogIntegrationUrl"
                      maxlength="500"
                      placeholder="http://host:puerto/ext/rodel-stocks"
                    />
                    <small id="posCfgHint">
                      Obligatoria cuando la app de inventario es 'stocks'. Si falta, POS se bloqueará operativamente, pero esta pantalla seguirá accesible.
                    </small>
                  </div>
                </div>
              </div>
            </div>

            <div class="rs-modal-actions" id="posConfigSaveBar">
              <button type="button" class="rs-btn rs-btn-secondary" id="cancelPosConfigBtn">Cancelar</button>
              <button type="button" class="rs-btn rs-btn-primary" id="savePosConfigBtn">Guardar</button>
            </div>
          </form>
        </div>
      </div>
    `.trim();

    document.body.insertAdjacentElement("beforeend", wrapper.firstElementChild);

    posConfigModal.backdrop = document.getElementById("posConfigBackdrop");
    posConfigModal.form = document.getElementById("posConfigForm");
    posConfigModal.companyDisplayName = document.getElementById("posCfgCompanyDisplayName");
    posConfigModal.ticketFooterText = document.getElementById("posCfgTicketFooterText");
    posConfigModal.catalogSource = document.getElementById("posCfgCatalogSource");
    posConfigModal.catalogIntegrationUrl = document.getElementById("posCfgCatalogIntegrationUrl");
    posConfigModal.printDocumentType = document.getElementById("posCfgPrintDocumentType");
    posConfigModal.ticketTemplateName = document.getElementById("posCfgTicketTemplateName");
    posConfigModal.salesNoteTemplateName = document.getElementById("posCfgSalesNoteTemplateName");
    posConfigModal.defaultTaxPercent = document.getElementById("posCfgDefaultTaxPercent");
    posConfigModal.defaultTicketCfdiUse = document.getElementById("posCfgDefaultTicketCfdiUse");
    posConfigModal.defaultTicketTaxRegime = document.getElementById("posCfgDefaultTicketTaxRegime");
    posConfigModal.salesNoteTextDefault = document.getElementById("posCfgSalesNoteTextDefault");
    posConfigModal.salesNoteExtraText = document.getElementById("posCfgSalesNoteExtraText");
    posConfigModal.salesNoteServicesLabel = document.getElementById("posCfgSalesNoteServicesLabel");
    posConfigModal.submitBtn = document.getElementById("savePosConfigBtn");
    posConfigModal.title = document.getElementById("posConfigTitle");
    posConfigModal.saveBar = document.getElementById("posConfigSaveBar");
    posConfigModal.hint = document.getElementById("posCfgHint");

    posConfigModal.mainTabPrintBtn = document.getElementById("posCfgMainTabPrint");
    posConfigModal.mainTabCommercialBtn = document.getElementById("posCfgMainTabCommercial");
    posConfigModal.mainPanelPrint = document.getElementById("posCfgMainPanelPrint");
    posConfigModal.mainPanelCommercial = document.getElementById("posCfgMainPanelCommercial");

    posConfigModal.ticketTemplateWrap = document.getElementById("posCfgTicketTemplateWrap");
    posConfigModal.salesNoteTemplateWrap = document.getElementById("posCfgSalesNoteTemplateWrap");

    const closeBtn = document.getElementById("closePosConfigBtn");
    const cancelBtn = document.getElementById("cancelPosConfigBtn");

    if (closeBtn) {
      closeBtn.addEventListener("click", () => closeModal(posConfigModal.backdrop));
    }

    if (cancelBtn) {
      cancelBtn.addEventListener("click", () => closeModal(posConfigModal.backdrop));
    }

    if (posConfigModal.backdrop) {
      posConfigModal.backdrop.addEventListener("click", (e) => {
        if (e.target === posConfigModal.backdrop) {
          closeModal(posConfigModal.backdrop);
        }
      });
    }

    if (posConfigModal.mainTabPrintBtn) {
      posConfigModal.mainTabPrintBtn.addEventListener("click", () => {
        setPosConfigMainTab("print");
      });
    }

    if (posConfigModal.mainTabCommercialBtn) {
      posConfigModal.mainTabCommercialBtn.addEventListener("click", () => {
        setPosConfigMainTab("commercial");
      });
    }

    if (posConfigModal.printDocumentType) {
      posConfigModal.printDocumentType.addEventListener("change", () => {
        syncPosConfigPrintUi();
      });
    }
  }

  function setPosConfigMainTab(tab) {
    const isPrint = String(tab || "print").toLowerCase() !== "commercial";

    if (posConfigModal.mainPanelPrint) {
      posConfigModal.mainPanelPrint.style.display = isPrint ? "" : "none";
    }

    if (posConfigModal.mainPanelCommercial) {
      posConfigModal.mainPanelCommercial.style.display = isPrint ? "none" : "";
    }

    if (posConfigModal.mainTabPrintBtn) {
      posConfigModal.mainTabPrintBtn.classList.toggle("rs-btn-primary", isPrint);
      posConfigModal.mainTabPrintBtn.classList.toggle("rs-btn-secondary", !isPrint);
    }

    if (posConfigModal.mainTabCommercialBtn) {
      posConfigModal.mainTabCommercialBtn.classList.toggle("rs-btn-primary", !isPrint);
      posConfigModal.mainTabCommercialBtn.classList.toggle("rs-btn-secondary", isPrint);
    }
  }

  function syncPosConfigPrintUi() {
    const docType = String(posConfigModal.printDocumentType?.value || "ticket").toLowerCase();
    const isTicket = docType !== "sales_note";

    if (posConfigModal.ticketTemplateWrap) {
      posConfigModal.ticketTemplateWrap.style.display = isTicket ? "" : "none";
    }

    if (posConfigModal.salesNoteTemplateWrap) {
      posConfigModal.salesNoteTemplateWrap.style.display = isTicket ? "none" : "";
    }
  }


  function fillPosConfigForm(data = {}) {
    if (!posConfigModal.form) return;

    posConfigModal.companyDisplayName.value = data.company_display_name || "";
    posConfigModal.printDocumentType.value =
      String(data.print_document_type || "ticket").toLowerCase() === "sales_note"
        ? "sales_note"
        : "ticket";
    posConfigModal.ticketTemplateName.value = data.ticket_template_name || "ticket_default.html";
    posConfigModal.salesNoteTemplateName.value = data.sales_note_template_name || "sales_note_default.html";
    posConfigModal.defaultTaxPercent.value = data.default_tax_percent ?? 16;
    posConfigModal.defaultTicketCfdiUse.value = data.default_ticket_cfdi_use || "S01";
    posConfigModal.defaultTicketTaxRegime.value = data.default_ticket_tax_regime || "616";
    posConfigModal.ticketFooterText.value = data.ticket_footer_text || "";
    posConfigModal.salesNoteTextDefault.value = data.sales_note_text_default || "";
    posConfigModal.salesNoteExtraText.value = data.sales_note_extra_text || "";
    posConfigModal.salesNoteServicesLabel.value = data.sales_note_services_label || "";
    posConfigModal.catalogSource.value =
      String(data.catalog_source || "pos").toLowerCase() === "stocks" ? "stocks" : "pos";
    posConfigModal.catalogIntegrationUrl.value = data.catalog_integration_url || "";
    syncPosConfigPrintUi();
    setPosConfigMainTab("print");
  }

  function setPosConfigReadonly(readonly) {
    if (!posConfigModal.form) return;

    setReadonlyForFormFields(posConfigModal.form, !!readonly);
    setButtonVisibility(posConfigModal.submitBtn, !readonly);

    if (posConfigModal.saveBar) {
      posConfigModal.saveBar.style.justifyContent = readonly ? "flex-end" : "";
    }

    if (posConfigModal.mainTabPrintBtn) {
      posConfigModal.mainTabPrintBtn.disabled = !!readonly;
    }
    if (posConfigModal.mainTabCommercialBtn) {
      posConfigModal.mainTabCommercialBtn.disabled = !!readonly;
    }
  }

  async function openPosConfigManager({ readonly = true } = {}) {
    ensurePosConfigModal();

    try {
      const data = await api.getPosSettings();

      fillPosConfigForm(data);
      setPosConfigReadonly(readonly);

      if (posConfigModal.title) {
        posConfigModal.title.textContent = readonly
          ? "Configuración POS (solo lectura)"
          : "Configuración POS";
      }

      if (posConfigModal.submitBtn) {
        posConfigModal.submitBtn.onclick = async () => {
          if (readonly) return;

          const payload = {
            company_display_name: posConfigModal.companyDisplayName.value.trim() || null,
            print_document_type: posConfigModal.printDocumentType.value || "ticket",
            ticket_template_name: posConfigModal.ticketTemplateName.value.trim() || "ticket_default.html",
            sales_note_template_name: posConfigModal.salesNoteTemplateName.value.trim() || "sales_note_default.html",
            default_tax_percent: Number(posConfigModal.defaultTaxPercent.value || 16),
            default_ticket_cfdi_use: posConfigModal.defaultTicketCfdiUse.value.trim() || "S01",
            default_ticket_tax_regime: posConfigModal.defaultTicketTaxRegime.value.trim() || "616",
            ticket_footer_text: posConfigModal.ticketFooterText.value.trim() || null,
            sales_note_text_default: posConfigModal.salesNoteTextDefault.value.trim() || null,
            sales_note_extra_text: posConfigModal.salesNoteExtraText.value.trim() || null,
            sales_note_services_label: posConfigModal.salesNoteServicesLabel.value.trim() || null,
            catalog_source: posConfigModal.catalogSource.value,
            catalog_integration_url: posConfigModal.catalogIntegrationUrl.value.trim() || null,
          };

          try {
            posConfigModal.submitBtn.disabled = true;

            const { response, result } = await api.savePosSettings(payload);

            if (!response.ok) {
              throw new Error(result?.detail || "No se pudo guardar Configuración POS.");
            }

            closeModal(posConfigModal.backdrop);

            // MUY IMPORTANTE:
            // recargamos catálogo settings y re-evaluamos bloqueo global
            await loadData();

          } catch (err) {
            console.error("savePosSettings error:", err);
            alert(err.message || "No se pudo guardar Configuración POS.");
          } finally {
            posConfigModal.submitBtn.disabled = false;
          }
        };
      }

      openModal(posConfigModal.backdrop);
    } catch (err) {
      console.error("getPosSettings error:", err);
      alert(err.message || "No se pudo cargar Configuración POS.");
    }
  }
  
  function getCategoryDepth(category, categories = []) {
    if (!category || !category.parent_id) {
      return 0;
    }

    let depth = 0;
    let currentParentId = category.parent_id;

    while (currentParentId) {
      const parent = categories.find(
        (cat) => String(cat.id) === String(currentParentId)
      );

      if (!parent) {
        break;
      }

      depth += 1;
      currentParentId = parent.parent_id;
    }

    return depth;
  }

  function getIndentedCategoryLabel(category, categories = []) {
    const depth = getCategoryDepth(category, categories);
    //console.log("Category:", category.name, "Depth:", depth);
    if (depth <= 0) {
      return category.name || "";
    }

    return `${"·· ".repeat(depth)}${category.name || ""}`;
  }

  function getAvailableParentCategories(currentId = null) {
    const currentIdText =
      currentId != null
        ? String(currentId)
        : null;

    const categories = getCategories();

    return categories.filter(cat => {
      if (!cat || cat.id == null) {
        return false;
      }

      if (currentIdText && String(cat.id) === currentIdText) {
        return false;
      }

      return true;
    });
  }

  function populateParentCategorySelect(currentId = null, selectedParentId = null) {
    if (!categoryEditor.parentId) return;

    const categories = sortCategoriesTree(getCategories());

    categoryEditor.parentId.innerHTML = `
      <option value="">Sin categoría padre</option>
      ${categories.map(cat => `
        <option
          value="${cat.id}"
          ${String(selectedParentId || "") === String(cat.id) ? "selected" : ""}
        >
          ${escapeHtml(getIndentedCategoryLabel(cat, getCategories()))}
        </option>
      `).join("")}
    `;
  }

  function renderCategoryTable() {
    if (!categoryModal.listBody) return;

    const categories = sortCategoriesTree(getCategories());

    const canEdit = canManageCatalogs();
    const readonly = isReadonlyByRoleOrSource();
    const actionLabel = readonly ? "Ver" : "Editar";

    if (!categories.length) {
      categoryModal.listBody.innerHTML = `
        <tr>
          <td colspan="5" class="catalog-empty-row">No hay categorías registradas.</td>
        </tr>
      `;
      return;
    }

    categoryModal.listBody.innerHTML = categories.map(cat => `
      <tr>
        <td>${cat.id ?? ""}</td>
        <td>${escapeHtml(getIndentedCategoryLabel(cat, getCategories()))}</td>
        <td>${escapeHtml(cat.description || "")}</td>
        <td>
          <span class="color-chip" style="background:${escapeHtml(cat.color || "#2563eb")}"></span>
          ${escapeHtml(cat.color || "#2563eb")}
        </td>
        <td>
          ${canEdit ? `<button class="secondary-btn" data-category-edit="${cat.id}">${actionLabel}</button>` : ""}
        </td>
      </tr>
    `).join("");

    if (categoryModal.newBtn) {
      const readonly = isReadonlyByRoleOrSource();
      setButtonVisibility(categoryModal.newBtn, !readonly);
      categoryModal.newBtn.disabled = readonly;
    }
  }

  function sortCategoriesTree(categories = []) {
    const byParent = new Map();

    for (const category of categories) {
      const parentKey =
        category.parent_id != null
          ? String(category.parent_id)
          : "root";

      if (!byParent.has(parentKey)) {
        byParent.set(parentKey, []);
      }

      byParent.get(parentKey).push(category);
    }

    for (const items of byParent.values()) {
      items.sort((a, b) => {
        const orderA = Number(a.sort_order || 0);
        const orderB = Number(b.sort_order || 0);

        if (orderA !== orderB) {
          return orderA - orderB;
        }

        return String(a.name || "")
          .localeCompare(String(b.name || ""));
      });
    }

    const result = [];

    function appendChildren(parentId = null) {
      const key =
        parentId != null
          ? String(parentId)
          : "root";

      const children = byParent.get(key) || [];

      for (const child of children) {
        result.push(child);
        appendChildren(child.id);
      }
    }

    appendChildren(null);

    return result;
  }

  function renderProductRow(prod) {
    const canEdit = canManageCatalogs();
    const readonly = isReadonlyByRoleOrSource();
    const actionLabel = readonly ? "Ver" : "Editar";

    return `
      <tr>
        <td>${prod.id ?? ""}</td>
        <td>${escapeHtml(prod.name || "")}</td>
        <td>${escapeHtml(prod.category_name || "")}</td>
        <td>${escapeHtml(prod.sku || "")}</td>
        <td>${prod.sale_price != null ? `$${money(prod.sale_price)}` : "-"}</td>
        <td>${prod.stock_quantity != null ? Number(prod.stock_quantity) : 0}</td>
        <td>${prod.is_active === true ? "Activo" : prod.is_active === false ? "Inactivo" : "-"}</td>
        <td>
          ${canEdit ? `<button class="secondary-btn" data-product-edit="${prod.id}">${actionLabel}</button>` : ""}
        </td>
      </tr>
    `;
  }

  function renderProductTable() {
    if (!productModal.listBody) return;

    const products = getMaintenanceProducts();

    if (!products.length) {
      productModal.listBody.innerHTML = `
        <tr>
          <td colspan="8" class="catalog-empty-row">No hay productos registrados.</td>
        </tr>
      `;
      return;
    }

    productModal.listBody.innerHTML = products.map(renderProductRow).join("");

    if (productModal.newBtn) {
      const readonly = isReadonlyByRoleOrSource();
      setButtonVisibility(productModal.newBtn, !readonly);
      productModal.newBtn.disabled = readonly;
    }
  }

  function populateCategorySelect() {
    if (!productEditor.categoryId) return;

    const categories = sortCategoriesTree(getCategories());
    const currentValue = productEditor.categoryId.value;

    productEditor.categoryId.innerHTML = `
      <option value="">Seleccione categoría...</option>
      ${categories.map(cat => `
        <option value="${cat.id}">
          ${escapeHtml(getIndentedCategoryLabel(cat, getCategories()))}
        </option>
      `).join("")}
    `;

    if (currentValue) {
      productEditor.categoryId.value = currentValue;
    }
  }

  function isLocalInventoryMode() {
    return String(productEditor.inventoryMode?.value || "pos_legacy").toLowerCase() === "pos_legacy";
  }

  function syncProductInventoryUi() {
    const isLocal = isLocalInventoryMode();

    if (productEditor.localInventorySection) {
      productEditor.localInventorySection.classList.toggle("is-hidden", !isLocal);
    }

    if (productEditor.stockItemId) {
      productEditor.stockItemId.disabled = isLocal || isReadonlyByRoleOrSource();
      if (isLocal) {
        productEditor.stockItemId.value = "";
      }
    }

    if (productEditor.trackInventory) {
      if (!isLocal) {
        productEditor.trackInventory.checked = true;
      }
    }

    if (productEditor.productType) {
      const isService = String(productEditor.productType.value || "").toLowerCase() === "service";

      if (isService) {
        if (productEditor.trackInventory) {
          productEditor.trackInventory.checked = false;
        }
        if (productEditor.localInventorySection) {
          productEditor.localInventorySection.classList.add("is-hidden");
        }
      } else {
        if (isLocal && productEditor.localInventorySection) {
          productEditor.localInventorySection.classList.remove("is-hidden");
        }
      }
    }
  }

  function openCategoryManager() {
    renderCategoryTable();
    openModal(categoryModal.backdrop);
  }

  function openProductManager() {
    renderProductTable();
    populateCategorySelect();
    openModal(productModal.backdrop);
  }

  function resetCategoryForm() {
    editingCategoryId = null;
    if (categoryEditor.form) categoryEditor.form.reset();

    if (categoryEditor.parentId) {
      categoryEditor.parentId.value = "";
    }

    if (categoryEditor.color && !categoryEditor.color.value) {
      categoryEditor.color.value = "#2563eb";
    }
  }

  function resetProductForm() {
    editingProductId = null;
    if (productEditor.form) productEditor.form.reset();

    if (productEditor.productType) productEditor.productType.value = "physical";
    if (productEditor.inventoryMode) productEditor.inventoryMode.value = "pos_legacy";
    if (productEditor.trackInventory) productEditor.trackInventory.checked = true;
    if (productEditor.stockQuantity) productEditor.stockQuantity.value = "0";
    if (productEditor.minStock) productEditor.minStock.value = "0";
    if (productEditor.costPrice) productEditor.costPrice.value = "0";
    if (productEditor.stockItemId) productEditor.stockItemId.value = "";

    syncProductInventoryUi();
  }

  function openNewCategoryEditor() {
    const readonly = isReadonlyByRoleOrSource();
    if (readonly) return;

    resetCategoryForm(
      populateParentCategorySelect(null, null)
    );

    if (categoryEditor.title) {
      categoryEditor.title.textContent = "Nueva categoría";
    }
    if (categoryEditor.submitBtn) {
      categoryEditor.submitBtn.textContent = "Guardar categoría";
    }

    setReadonlyForFormFields(categoryEditor.form, readonly);
    setButtonVisibility(categoryEditor.submitBtn, !readonly);

    openModal(categoryEditor.backdrop);
  }

  function openEditCategoryEditor(categoryId) {
    const categories = getCategories();
    const category = categories.find(c => String(c.id) === String(categoryId));
    if (!category) return;

    editingCategoryId = category.id;

    const readonly = isReadonlyByRoleOrSource();

    if (categoryEditor.title) {
      categoryEditor.title.textContent = readonly ? "Ver categoría" : "Editar categoría";
    }
    if (categoryEditor.submitBtn) {
      categoryEditor.submitBtn.textContent = "Guardar categoría";
    }

    if (categoryEditor.name) categoryEditor.name.value = category.name || "";
    if (categoryEditor.description) categoryEditor.description.value = category.description || "";
    if (categoryEditor.color) categoryEditor.color.value = category.color || "#2563eb";

    populateParentCategorySelect(
      category.id,
      category.parent_id ?? null
    );

    setReadonlyForFormFields(categoryEditor.form, readonly);
    setButtonVisibility(categoryEditor.submitBtn, !readonly);

    openModal(categoryEditor.backdrop);
  }

  function openNewProductEditor() {
    const readonly = isReadonlyByRoleOrSource();
    if (readonly) return;

    resetProductForm();
    populateCategorySelect();

    if (productEditor.title) {
      productEditor.title.textContent = "Nuevo producto";
    }
    if (productEditor.submitBtn) {
      productEditor.submitBtn.textContent = "Guardar producto";
    }

    setReadonlyForFormFields(productEditor.form, readonly);
    if (productEditor.inventoryMode) {
      productEditor.inventoryMode.disabled = true;
    }

    setButtonVisibility(productEditor.submitBtn, !readonly);

    syncProductInventoryUi();
    openModal(productEditor.backdrop);
  }

  function openEditProductEditor(productId) {
    const products = getMaintenanceProducts();
    const product = products.find(p => String(p.id) === String(productId));
    if (!product) return;

    editingProductId = product.id;
    populateCategorySelect();

    const readonly = isReadonlyByRoleOrSource();

    if (productEditor.title) {
      productEditor.title.textContent = readonly ? "Ver producto" : "Editar producto";
    }
    if (productEditor.submitBtn) {
      productEditor.submitBtn.textContent = "Guardar producto";
    }

    if (productEditor.name) productEditor.name.value = product.name || "";
    if (productEditor.description) productEditor.description.value = product.description || "";
    if (productEditor.productType) productEditor.productType.value = product.product_type || "physical";
    if (productEditor.trackInventory) productEditor.trackInventory.checked = !!product.track_inventory;
    if (productEditor.categoryId) productEditor.categoryId.value = product.category_id ?? "";
    if (productEditor.sku) productEditor.sku.value = product.sku || "";
    if (productEditor.barcode) productEditor.barcode.value = product.barcode || "";
    if (productEditor.costPrice) productEditor.costPrice.value = Number(product.cost ?? 0);
    if (productEditor.stockQuantity) productEditor.stockQuantity.value = Number(product.stock_quantity ?? 0);
    if (productEditor.minStock) productEditor.minStock.value = Number(product.min_stock ?? 0);
    if (productEditor.inventoryMode) productEditor.inventoryMode.value = product.inventory_mode || "pos_legacy";
    if (productEditor.stockItemId) productEditor.stockItemId.value = product.stock_item_id ?? "";

    setReadonlyForFormFields(productEditor.form, readonly);
    if (productEditor.inventoryMode) {
      productEditor.inventoryMode.disabled = true;
    }

    setButtonVisibility(productEditor.submitBtn, !readonly);

    syncProductInventoryUi();
    openModal(productEditor.backdrop);
  }

  async function submitCategoryForm(e) {
    e.preventDefault();

    const readonly = isReadonlyByRoleOrSource();
    if (readonly) return;

    const payload = {
      name: categoryEditor.name?.value?.trim() || "",
      description: categoryEditor.description?.value?.trim() || "",
      color: categoryEditor.color?.value || "#2563eb",

      parent_id:
        categoryEditor.parentId?.value
          ? Number(categoryEditor.parentId.value)
          : null,

      sort_order: 0
    };

    if (!payload.name) {
      alert("El nombre de la categoría es obligatorio.");
      return;
    }

    try {
      if (editingCategoryId) {
        await api.updateCategory(editingCategoryId, payload);
      } else {
        await api.createCategory(payload);
      }

      closeModal(categoryEditor.backdrop);
      await loadData();
      renderCategoryTable();
      populateCategorySelect();
    } catch (error) {
      console.error("Error guardando categoría:", error);
      alert(error?.message || "No se pudo guardar la categoría.");
    }
  }

  async function submitProductForm(e) {
    e.preventDefault();

    const readonly = isReadonlyByRoleOrSource();
    if (readonly) return;

    const inventoryMode = productEditor.inventoryMode?.value || "pos_legacy";
    const isLocal = String(inventoryMode).toLowerCase() === "pos_legacy";
    const isService = String(productEditor.productType?.value || "").toLowerCase() === "service";

    const payload = {
      name: productEditor.name?.value?.trim() || "",
      description: productEditor.description?.value?.trim() || "",
      product_type: productEditor.productType?.value || "physical",
      track_inventory: isService ? false : !!productEditor.trackInventory?.checked,
      category_id: productEditor.categoryId?.value ? Number(productEditor.categoryId.value) : null,
      sku: productEditor.sku?.value?.trim() || null,
      barcode: productEditor.barcode?.value?.trim() || null,
      cost: isLocal && !isService ? Number(productEditor.costPrice?.value || 0) : 0,
      sale_price: 0,
      stock_quantity: isLocal && !isService ? Number(productEditor.stockQuantity?.value || 0) : 0,
      min_stock: isLocal && !isService ? Number(productEditor.minStock?.value || 0) : 0,
      inventory_mode: inventoryMode,
      stock_item_id: !isLocal && productEditor.stockItemId?.value
        ? Number(productEditor.stockItemId.value)
        : null
    };

    if (!payload.name) {
      alert("El nombre del producto es obligatorio.");
      return;
    }

    try {
      let apiResult;

      if (editingProductId) {
        apiResult = await api.updateMaintenanceProduct(editingProductId, payload);
      } else {
        apiResult = await api.createMaintenanceProduct(payload);
      }

      if (apiResult?.response && !apiResult?.response?.ok) {
        const detail =
          apiResult?.result?.detail ||
          apiResult?.result?.message ||
          "No se pudo guardar el producto.";
        throw new Error(detail);
      }

      closeModal(productEditor.backdrop);
      await loadData();
      renderProductTable();
    } catch (error) {
      console.error("Error guardando producto:", error);
      alert(error?.message || "No se pudo guardar el producto.");
    }
  }

  function setupMaintenanceActions() {
    if (categoryModal.newBtn) {
      categoryModal.newBtn.addEventListener("click", () => {
        openNewCategoryEditor();
      });
    }

    if (productModal.newBtn) {
      productModal.newBtn.addEventListener("click", () => {
        openNewProductEditor();
      });
    }

    if (categoryEditor.form) {
      categoryEditor.form.addEventListener("submit", submitCategoryForm);
    }

    if (productEditor.form) {
      productEditor.form.addEventListener("submit", submitProductForm);
    }

    if (productEditor.inventoryMode) {
      productEditor.inventoryMode.addEventListener("change", syncProductInventoryUi);
    }

    if (productEditor.productType) {
      productEditor.productType.addEventListener("change", syncProductInventoryUi);
    }

    if (categoryModal.listBody) {
      categoryModal.listBody.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-category-edit]");
        if (!btn) return;
        openEditCategoryEditor(btn.dataset.categoryEdit);
      });
    }

    if (productModal.listBody) {
      productModal.listBody.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-product-edit]");
        if (!btn) return;
        openEditProductEditor(btn.dataset.productEdit);
      });
    }

    if (categoryModal.filterInput) {
      categoryModal.filterInput.addEventListener("input", () => {
        const term = String(categoryModal.filterInput.value || "").toLowerCase().trim();
        const categories = getCategories();
        const canEdit = canManageCatalogs();

        if (!term) {
          renderCategoryTable();
          return;
        }

        const filtered = categories.filter(cat =>
          String(cat.category_path || cat.name || "")
            .toLowerCase()
            .includes(term) 
        );

        if (!filtered.length) {
          categoryModal.listBody.innerHTML = `
            <tr>
              <td colspan="5" class="catalog-empty-row">Sin resultados.</td>
            </tr>
          `;
          return;
        }

        categoryModal.listBody.innerHTML = filtered.map(cat => `
          <tr>
            <td>${cat.id ?? ""}</td>
            <td>${escapeHtml(getIndentedCategoryLabel(cat, getCategories()))}</td>
            <td>${escapeHtml(cat.description || "")}</td>
            <td>
              <span class="color-chip" style="background:${escapeHtml(cat.color || "#2563eb")}"></span>
              ${escapeHtml(cat.color || "#2563eb")}
            </td>
            <td>
              ${canEdit ? `<button class="secondary-btn" data-category-edit="${cat.id}">Editar</button>` : ""}
            </td>
          </tr>
        `).join("");
      });
    }

    if (productModal.filterInput) {
      productModal.filterInput.addEventListener("input", () => {
        const term = String(productModal.filterInput.value || "").toLowerCase().trim();
        const products = getMaintenanceProducts();

        if (!term) {
          renderProductTable();
          return;
        }

        const filtered = products.filter(prod =>
          String(prod.name || "").toLowerCase().includes(term) ||
          String(prod.sku || "").toLowerCase().includes(term) ||
          String(prod.category_name || "").toLowerCase().includes(term)
        );

        if (!filtered.length) {
          productModal.listBody.innerHTML = `
            <tr>
              <td colspan="8" class="catalog-empty-row">Sin resultados.</td>
            </tr>
          `;
          return;
        }

        productModal.listBody.innerHTML = filtered.map(renderProductRow).join("");
      });
    }
  }

  function ensureCustomerManagerModal() {
    if (customerModal.backdrop) return;

    const wrapper = document.createElement("div");
    wrapper.innerHTML = `
      <div class="rs-modal-backdrop" id="customerModalBackdrop">
        <div class="rs-modal-card rs-modal-card-xl">
          <div class="rs-modal-header">
            <h3 id="customerModalTitle">Clientes POS</h3>
            <button type="button" class="rs-modal-close" id="closeCustomerModalBtn">✕</button>
          </div>

          <div class="rs-modal-form">
            <div class="catalog-toolbar">
              <input
                type="text"
                id="customerFilterInput"
                class="search-input"
                placeholder="Buscar por RFC, razón social o contacto"
              />
              <button type="button" class="action-btn" id="newCustomerBtn">
                Nuevo cliente
              </button>
            </div>

            <div class="catalog-table-wrap">
              <table class="catalog-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>RFC</th>
                    <th>Razón social</th>
                    <th>Contacto</th>
                    <th>Teléfono</th>
                    <th>Email</th>
                    <th>Estado</th>
                    <th>Acciones</th>
                  </tr>
                </thead>
                <tbody id="customerListBody">
                  <tr>
                    <td colspan="8" class="catalog-empty-row">Cargando...</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div id="customerSelectionPanel" class="rs-form-section" style="display:none; margin-top: 16px;">
              <div class="rs-form-section-title">Datos de impresión de nota</div>

              <div class="rs-form-grid rs-form-grid-2">
                <div class="rs-form-group" style="grid-column: 1 / -1;">
                  <label>Cliente seleccionado</label>
                  <div id="customerSelectedSummary" class="rs-inline-readonly">
                    Cliente no seleccionado.
                  </div>
                </div>

                <div class="rs-form-group">
                  <label for="customerSelectionAttendedBy">Atendió</label>
                  <input type="text" id="customerSelectionAttendedBy" maxlength="255" />
                </div>

                <div class="rs-form-group">
                  <label for="customerSelectionPaymentMethodLabel">Método de pago</label>
                  <input type="text" id="customerSelectionPaymentMethodLabel" maxlength="100" />
                </div>

                <div class="rs-form-group" style="grid-column: 1 / -1;">
                  <label for="customerSelectionSalesNoteText">Texto principal</label>
                  <textarea id="customerSelectionSalesNoteText" rows="3"></textarea>
                </div>
              </div>

              <div class="rs-modal-actions" style="margin-top: 16px;">
                <button type="button" class="rs-btn rs-btn-secondary" id="cancelCustomerSelectionBtn">
                  Cancelar
                </button>
                <button type="button" class="rs-btn rs-btn-primary" id="continueCustomerSelectionBtn">
                  Usar cliente
                </button>
              </div>
            </div>

          </div>
        </div>
      </div>
    `.trim();

    document.body.insertAdjacentElement("beforeend", wrapper.firstElementChild);

    customerModal.backdrop = document.getElementById("customerModalBackdrop");
    customerModal.title = document.getElementById("customerModalTitle");
    customerModal.filterInput = document.getElementById("customerFilterInput");
    customerModal.newBtn = document.getElementById("newCustomerBtn");
    customerModal.listBody = document.getElementById("customerListBody");
    customerModal.selectionPanel = document.getElementById("customerSelectionPanel");
    customerModal.selectedSummary = document.getElementById("customerSelectedSummary");
    customerModal.attendedBy = document.getElementById("customerSelectionAttendedBy");
    customerModal.salesNoteText = document.getElementById("customerSelectionSalesNoteText");
    customerModal.salesNoteExtraText = document.getElementById("customerSelectionSalesNoteExtraText");
    customerModal.servicesLabel = document.getElementById("customerSelectionServicesLabel");
    customerModal.ticketFooterText = document.getElementById("customerSelectionTicketFooterText");
    customerModal.paymentMethodLabel = document.getElementById("customerSelectionPaymentMethodLabel");
    customerModal.continueBtn = document.getElementById("continueCustomerSelectionBtn");
    customerModal.cancelSelectionBtn = document.getElementById("cancelCustomerSelectionBtn");

    const closeBtn = document.getElementById("closeCustomerModalBtn");

    if (closeBtn) {
      closeBtn.addEventListener("click", () => {
        closeCustomerManagerModal(true);
      });
    }

    if (customerModal.backdrop) {
      customerModal.backdrop.addEventListener("click", (e) => {
        if (e.target === customerModal.backdrop) {
          closeCustomerManagerModal(true);
        }
      });
    }
  }

  function bindCustomerManagerEvents() {
    if (customerManagerEventsBound) return;
    if (!customerModal.backdrop) return;

    if (customerModal.newBtn) {
      customerModal.newBtn.addEventListener("click", () => {
        openNewCustomerEditor();
      });
    }

    if (customerModal.listBody) {
      customerModal.listBody.addEventListener("click", (e) => {
        const selectBtn = e.target.closest("[data-customer-select]");
        if (selectBtn && isCustomerSelectionMode()) {
          selectCustomerForSalesNote(selectBtn.dataset.customerSelect);
          return;
        }

        const btn = e.target.closest("[data-customer-edit]");
        if (!btn) return;

        openEditCustomerEditor(btn.dataset.customerEdit);
      });
    }

    if (customerModal.filterInput) {
      customerModal.filterInput.addEventListener("input", () => {
        const term = String(customerModal.filterInput.value || "").toLowerCase().trim();

        if (!term) {
          renderCustomerTable();
          return;
        }

        const filtered = customerRows.filter(row =>
          String(row?.rfc || "").toLowerCase().includes(term) ||
          String(row?.business_name || "").toLowerCase().includes(term) ||
          String(row?.contact_name || "").toLowerCase().includes(term)
        );

        renderCustomerTable(filtered);
      });
    }

    if (customerModal.continueBtn) {
      customerModal.continueBtn.addEventListener("click", () => {
        try {
          const result = buildCustomerSelectionResult();
          resolveAndCloseCustomerSelection(result);
          closeCustomerManagerModal(false);
        } catch (error) {
          alert(error?.message || "No se pudo continuar.");
        }
      });
    }

    if (customerModal.cancelSelectionBtn) {
      customerModal.cancelSelectionBtn.addEventListener("click", () => {
        closeCustomerManagerModal(true);
      });
    }

    bindCustomerSelectionFieldSync();
    customerManagerEventsBound = true;
  }


  function isCustomerSelectionMode() {
    return customerSelectionMode === "sales_note_select";
  }

  function resetCustomerSelectionState() {
    customerSelectionMode = null;
    customerSelectionState = {
      selectedCustomerId: null,
      selectedCustomerLabel: "",
      attendedBy: "",
      salesNoteText: "",
      salesNoteExtraText: "",
      servicesLabel: "",
      ticketFooterText: "",
      paymentMethodLabel: "Efectivo"
    };
    customerSelectionResolver = null;
  }

  function fillCustomerSelectionForm(state = {}) {
    customerSelectionState = {
      selectedCustomerId: state.selectedCustomerId ?? null,
      selectedCustomerLabel: state.selectedCustomerLabel || "",
      attendedBy: state.attendedBy || "",
      salesNoteText: state.salesNoteText || "",
      salesNoteExtraText: "",
      servicesLabel: "",
      ticketFooterText: "",
      paymentMethodLabel: state.paymentMethodLabel || "Efectivo"
    };

    if (customerModal.attendedBy) {
      customerModal.attendedBy.value = customerSelectionState.attendedBy;
    }
    if (customerModal.salesNoteText) {
      customerModal.salesNoteText.value = customerSelectionState.salesNoteText;
    }
    if (customerModal.paymentMethodLabel) {
      customerModal.paymentMethodLabel.value = customerSelectionState.paymentMethodLabel;
    }

    syncCustomerSelectionSummary();
  }


  function bindCustomerSelectionFieldSync() {
    const bindValue = (el, key) => {
      if (!el) return;
      el.addEventListener("input", () => {
        customerSelectionState[key] = String(el.value || "");
      });
    };

    bindValue(customerModal.attendedBy, "attendedBy");
    bindValue(customerModal.salesNoteText, "salesNoteText");
    bindValue(customerModal.paymentMethodLabel, "paymentMethodLabel");
  }


  function syncCustomerSelectionSummary() {
    if (!customerModal.selectedSummary) return;

    if (customerSelectionState.selectedCustomerId) {
      customerModal.selectedSummary.textContent =
        customerSelectionState.selectedCustomerLabel ||
        `Cliente #${customerSelectionState.selectedCustomerId}`;
    } else {
      customerModal.selectedSummary.textContent = "Cliente no seleccionado.";
    }
  }

  function setCustomerManagerModeUi() {
    const selection = isCustomerSelectionMode();

    if (customerModal.selectionPanel) {
      customerModal.selectionPanel.style.display = selection ? "" : "none";
    }

    if (customerModal.newBtn) {
      customerModal.newBtn.style.display = "";
      customerModal.newBtn.disabled = false;
    }

    if (customerModal.title) {
      customerModal.title.textContent = selection
        ? "Seleccionar cliente para nota de venta"
        : "Información de clientes";
    }
  }

  function selectCustomerForSalesNote(customerId) {
    const row = customerRows.find(item => String(item?.id) === String(customerId));
    if (!row) {
      alert("Cliente no encontrado.");
      return;
    }

    if (row.is_active !== true) {
      alert("No se puede seleccionar un cliente inactivo.");
      return;
    }

    customerSelectionState.selectedCustomerId = row.id;
    customerSelectionState.selectedCustomerLabel =
      row.business_name || row.contact_name || row.rfc || `#${row.id}`;

    syncCustomerSelectionSummary();
  }

  function resolveAndCloseCustomerSelection(payload) {
    if (typeof customerSelectionResolver === "function") {
      const resolver = customerSelectionResolver;
      customerSelectionResolver = null;
      resolver(payload);
    }

    resetCustomerSelectionState();
  }

  function closeCustomerManagerModal(cancelSelection = false) {
    const wasSelectionMode = isCustomerSelectionMode();

    if (cancelSelection && wasSelectionMode) {
      resolveAndCloseCustomerSelection(null);
    } else if (!wasSelectionMode) {
      resetCustomerSelectionState();
    }

    if (customerModal.backdrop) {
      customerModal.backdrop.classList.remove("show");
    }
  }

  function buildCustomerSelectionResult() {
    const attendedBy = String(customerModal.attendedBy?.value || "").trim();
    const salesNoteText = String(customerModal.salesNoteText?.value || "").trim();
    const paymentMethodLabel = String(customerModal.paymentMethodLabel?.value || "").trim() || "Efectivo";

    if (!customerSelectionState.selectedCustomerId) {
      throw new Error("Debe seleccionar un cliente activo.");
    }

    return {
      customer_id: customerSelectionState.selectedCustomerId,
      customer_label: customerSelectionState.selectedCustomerLabel || "",
      attended_by: attendedBy,
      sales_note_text: salesNoteText,
      sales_note_extra_text: "",
      services_label: "",
      ticket_footer_text: "",
      payment_method_label: paymentMethodLabel
    };
  }

  function ensureCustomerEditorModal() {
    if (customerEditor.backdrop) return;

    const wrapper = document.createElement("div");
    wrapper.innerHTML = `
      <div class="rs-modal-backdrop" id="customerEditorBackdrop">
        <div class="rs-modal-card rs-modal-card-lg">
          <div class="rs-modal-header">
            <h3 id="customerEditorTitle">Cliente POS</h3>
            <button type="button" class="rs-modal-close" id="closeCustomerEditorBtn">✕</button>
          </div>

          <form id="customerEditorForm" class="rs-modal-form">
            <div class="rs-form-section">
              <div class="rs-form-section-title">Datos fiscales</div>

              <div class="rs-form-grid rs-form-grid-2">
                <div class="rs-form-group">
                  <label for="customerRfc">RFC</label>
                  <input type="text" id="customerRfc" maxlength="20" required />
                </div>

                <div class="rs-form-group">
                  <label for="customerBusinessName">Razón social / nombre</label>
                  <input type="text" id="customerBusinessName" maxlength="255" required />
                </div>

                <div class="rs-form-group">
                  <label for="customerTaxRegime">Régimen fiscal</label>
                  <input type="text" id="customerTaxRegime" maxlength="10" />
                </div>

                <div class="rs-form-group">
                  <label for="customerCfdiUse">Uso CFDI</label>
                  <input type="text" id="customerCfdiUse" maxlength="10" />
                </div>

                <div class="rs-form-group">
                  <label for="customerPostalCode">Código postal</label>
                  <input type="text" id="customerPostalCode" maxlength="20" />
                </div>

                <div class="rs-form-group rs-checkbox-group rs-checkbox-group-inline">
                  <label class="rs-checkbox-label">
                    <input type="checkbox" id="customerIsActive" checked />
                    <span>Activo</span>
                  </label>
                </div>
              </div>
            </div>

            <div class="rs-form-section">
              <div class="rs-form-section-title">Contacto</div>

              <div class="rs-form-grid rs-form-grid-2">
                <div class="rs-form-group">
                  <label for="customerContactName">Contacto</label>
                  <input type="text" id="customerContactName" maxlength="255" />
                </div>

                <div class="rs-form-group">
                  <label for="customerPhone">Teléfono</label>
                  <input type="text" id="customerPhone" maxlength="50" />
                </div>

                <div class="rs-form-group" style="grid-column: 1 / -1;">
                  <label for="customerEmail">Email</label>
                  <input type="email" id="customerEmail" maxlength="255" />
                </div>
              </div>
            </div>

            <div class="rs-form-section">
              <div class="rs-form-section-title">Dirección</div>

              <div class="rs-form-grid">
                <div class="rs-form-group">
                  <label for="customerAddress">Dirección</label>
                  <textarea id="customerAddress" rows="3"></textarea>
                </div>
              </div>
            </div>

            <div class="rs-modal-actions" id="customerEditorSaveBar">
              <button type="button" class="rs-btn rs-btn-secondary" id="cancelCustomerEditorBtn">Cancelar</button>
              <button type="submit" class="rs-btn rs-btn-primary" id="saveCustomerBtn">Guardar</button>
            </div>
          </form>
        </div>
      </div>
    `.trim();

    document.body.insertAdjacentElement("beforeend", wrapper.firstElementChild);

    customerEditor.backdrop = document.getElementById("customerEditorBackdrop");
    customerEditor.title = document.getElementById("customerEditorTitle");
    customerEditor.form = document.getElementById("customerEditorForm");
    customerEditor.submitBtn = document.getElementById("saveCustomerBtn");
    customerEditor.saveBar = document.getElementById("customerEditorSaveBar");
    customerEditor.rfc = document.getElementById("customerRfc");
    customerEditor.businessName = document.getElementById("customerBusinessName");
    customerEditor.contactName = document.getElementById("customerContactName");
    customerEditor.phone = document.getElementById("customerPhone");
    customerEditor.email = document.getElementById("customerEmail");
    customerEditor.address = document.getElementById("customerAddress");
    customerEditor.postalCode = document.getElementById("customerPostalCode");
    customerEditor.taxRegime = document.getElementById("customerTaxRegime");
    customerEditor.cfdiUse = document.getElementById("customerCfdiUse");
    customerEditor.isActive = document.getElementById("customerIsActive");

    const closeBtn = document.getElementById("closeCustomerEditorBtn");
    const cancelBtn = document.getElementById("cancelCustomerEditorBtn");

    if (closeBtn) {
      closeBtn.addEventListener("click", () => {
        closeCustomerEditorModal();
      });
    }

    if (cancelBtn) {
      cancelBtn.addEventListener("click", () => {
        closeCustomerEditorModal();
      });
    }

    if (customerEditor.backdrop) {
      customerEditor.backdrop.addEventListener("click", (e) => {
        if (e.target === customerEditor.backdrop) {
          closeCustomerEditorModal();
        }
      });
    }

    if (customerEditor.form) {
      customerEditor.form.addEventListener("submit", submitCustomerForm);
    }
  }

  function closeCustomerEditorModal() {
    if (customerEditor.backdrop) {
      customerEditor.backdrop.classList.remove("show");
    }
  }

  function renderCustomerTable(rows = null) {
    ensureCustomerManagerModal();

    if (!customerModal.listBody) return;

    const list = Array.isArray(rows) ? rows : customerRows;
    const canEdit = canManageCatalogs();
    const selection = isCustomerSelectionMode();

    if (!Array.isArray(list) || !list.length) {
      customerModal.listBody.innerHTML = `
        <tr>
          <td colspan="8" class="catalog-empty-row">Sin customers registrados.</td>
        </tr>
      `;
      return;
    }

    customerModal.listBody.innerHTML = list.map(row => {
      const active = row?.is_active === true;
      const selected = selection && String(customerSelectionState.selectedCustomerId ?? "") === String(row?.id ?? "");

      let actionHtml = "";

      if (selection) {
        if (active) {
          actionHtml = `
            <button
              type="button"
              class="secondary-btn"
              data-customer-select="${row.id}"
            >
              ${selected ? "Cliente seleccionado" : "Seleccionar"}
            </button>
          `;
        } else {
          actionHtml = `<span class="status-badge status-inactive">No seleccionable</span>`;
        }
      } else if (canEdit) {
        actionHtml = `<button type="button" class="secondary-btn" data-customer-edit="${row.id}">Editar</button>`;
      }

      return `
        <tr ${selected ? 'class="row-selected"' : ""}>
          <td>${row?.id ?? ""}</td>
          <td>${escapeHtml(row?.rfc || "")}</td>
          <td>${escapeHtml(row?.business_name || "")}</td>
          <td>${escapeHtml(row?.contact_name || "")}</td>
          <td>${escapeHtml(row?.phone || "")}</td>
          <td>${escapeHtml(row?.email || "")}</td>
          <td>
            <span class="status-badge ${active ? "status-active" : "status-inactive"}">
              ${active ? "Activo" : "Inactivo"}
            </span>
          </td>
          <td>${actionHtml}</td>
        </tr>
      `;
    }).join("");

    setCustomerManagerModeUi();
    syncCustomerSelectionSummary();
  }

  function fillCustomerForm(data = {}) {
    if (!customerEditor.form) return;

    customerEditor.rfc.value = data.rfc || "";
    customerEditor.businessName.value = data.business_name || "";
    customerEditor.contactName.value = data.contact_name || "";
    customerEditor.phone.value = data.phone || "";
    customerEditor.email.value = data.email || "";
    customerEditor.address.value = data.address || "";
    customerEditor.postalCode.value = data.postal_code || "";
    customerEditor.taxRegime.value = data.tax_regime || "";
    customerEditor.cfdiUse.value = data.cfdi_use || "";
    customerEditor.isActive.checked = data.is_active !== false;
  }

  function buildCustomerPayload() {
    return {
      rfc: String(customerEditor.rfc?.value || "").trim().toUpperCase(),
      business_name: String(customerEditor.businessName?.value || "").trim(),
      contact_name: String(customerEditor.contactName?.value || "").trim() || null,
      phone: String(customerEditor.phone?.value || "").trim() || null,
      email: String(customerEditor.email?.value || "").trim() || null,
      address: String(customerEditor.address?.value || "").trim() || null,
      postal_code: String(customerEditor.postalCode?.value || "").trim() || null,
      tax_regime: String(customerEditor.taxRegime?.value || "").trim() || null,
      cfdi_use: String(customerEditor.cfdiUse?.value || "").trim() || null,
      is_active: !!customerEditor.isActive?.checked
    };
  }

  async function loadCustomersAndRender() {
    customerRows = await api.fetchPosCustomers({ includeInactive: true });
    renderCustomerTable();
  }

  function openNewCustomerEditor() {
    ensureCustomerEditorModal();
    editingCustomerId = null;

    if (customerEditor.title) {
      customerEditor.title.textContent = "Información de Nuevo Cliente";
    }

    fillCustomerForm({
      is_active: true
    });

    customerEditor.backdrop.classList.add("show");
  }

  function openEditCustomerEditor(customerId) {
    ensureCustomerEditorModal();

    const row = customerRows.find(item => String(item?.id) === String(customerId));
    if (!row) {
      alert("Cliente no encontrado.");
      return;
    }

    editingCustomerId = row.id;

    if (customerEditor.title) {
      customerEditor.title.textContent = `Editar Información de Cliente #${row.id}`;
    }

    fillCustomerForm(row);
    customerEditor.backdrop.classList.add("show");
  }

  async function submitCustomerForm(e) {
    e.preventDefault();

    if (!customerEditor.form) return;

    const payload = buildCustomerPayload();

    if (!payload.rfc) {
      alert("RFC es obligatorio.");
      return;
    }

    if (!payload.business_name) {
      alert("Razón social / nombre es obligatorio.");
      return;
    }

    if (customerEditor.submitBtn) {
      customerEditor.submitBtn.disabled = true;
    }

    try {
      const { response, result } = await api.savePosCustomer({
        editingId: editingCustomerId,
        payload
      });

      if (!response.ok) {
        throw new Error(result?.detail || "No se pudo guardar el Cliente.");
      }

      closeCustomerEditorModal();
      await loadCustomersAndRender();

      if (isCustomerSelectionMode()) {
        const savedId = result?.id ?? editingCustomerId;
        if (savedId != null) {
          selectCustomerForSalesNote(savedId);
        }
      }
    } catch (error) {
      console.error("Error guardando Cliente:", error);
      alert(error?.message || "No se pudo guardar el Cliente.");
    } finally {
      if (customerEditor.submitBtn) {
        customerEditor.submitBtn.disabled = false;
      }
    }
  }

  async function openCustomerManager() {
    ensureCustomerManagerModal();
    ensureCustomerEditorModal();
    bindCustomerManagerEvents();
    resetCustomerSelectionState();
    customerSelectionMode = null;

    if (customerModal.title) {
      customerModal.title.textContent = "Información de clientes";
    }

    if (customerModal.filterInput) {
      customerModal.filterInput.value = "";
    }

    customerModal.backdrop.classList.add("show");

    try {
      await loadCustomersAndRender();
    } catch (error) {
      console.error("Error cargando customers:", error);

      if (customerModal.listBody) {
        customerModal.listBody.innerHTML = `
          <tr>
            <td colspan="8" class="catalog-empty-row">
              ${escapeHtml(error?.message || "No se pudieron cargar los customers.")}
            </td>
          </tr>
        `;
      }
    }
  }

  async function openCustomerManagerForSalesNote({
    selectedCustomerId = null,
    attendedBy = "",
    salesNoteText = "",
    salesNoteExtraText = "",
    servicesLabel = "",
    ticketFooterText = "",
    paymentMethodLabel = "Efectivo"
  } = {}) {
    ensureCustomerManagerModal();
    ensureCustomerEditorModal();
    bindCustomerManagerEvents();

    if (customerModal.filterInput) {
      customerModal.filterInput.value = "";
    }

    customerSelectionMode = "sales_note_select";

    customerModal.backdrop.classList.add("show");

    try {
      await loadCustomersAndRender();

      let selectedCustomerLabel = "";
      if (selectedCustomerId != null) {
        const existing = customerRows.find(item => String(item?.id) === String(selectedCustomerId));
        if (existing) {
          selectedCustomerLabel =
            existing.business_name || existing.contact_name || existing.rfc || `#${existing.id}`;
        }
      }

      fillCustomerSelectionForm({
        selectedCustomerId,
        selectedCustomerLabel,
        attendedBy,
        salesNoteText,
        salesNoteExtraText,
        servicesLabel,
        ticketFooterText,
        paymentMethodLabel
      });

      renderCustomerTable();

      return await new Promise((resolve) => {
        customerSelectionResolver = resolve;
      });
    } catch (error) {
      resolveAndCloseCustomerSelection(null);
      customerModal.backdrop.classList.remove("show");
      throw error;
    }
  }

  return {
    setupDomRefs,
    setupMaintenanceActions,
    openCategoryManager,
    openProductManager,
    openCustomerManager,
    openCustomerManagerForSalesNote,
    renderCategoryTable,
    renderProductTable,
    renderCustomerTable,
    populateCategorySelect,
    openPosConfigManager
  };
}
