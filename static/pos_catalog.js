// pos_catalog.js
console.log("POS_CATALOG_INV3B_SEGMENTED");

export function createPosCatalog(deps) {
  let activeCategoryId = "all";
  let activeSearchTerm = "";
  const {
    getCategories,
    getProducts,
    addToCart,
    canAddToCart,
    usesLegacyStock,
    usesStocksApi,
    getProductCategoryName,
    getStockLabel
  } = deps;

  function isServiceProduct(product) {
    return String(product?.product_type || "physical").toLowerCase() === "service";
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function getCategoryDepth(category, categoriesMap) {
    let depth = 0;

    let currentParentId = category.parent_id;

    while (currentParentId != null) {
      const parent = categoriesMap.get(currentParentId);

      if (!parent) {
        break;
      }

      depth += 1;
      currentParentId = parent.parent_id;

      // safety anti-loop
      if (depth > 20) {
        break;
      }
    }

    return depth;
  }

  function buildCategoryChildrenMap(categories) {
    const map = new Map();

    categories.forEach(category => {
      const parentId =
        category.parent_id != null
          ? Number(category.parent_id)
          : null;

      if (!map.has(parentId)) {
        map.set(parentId, []);
      }

      map.get(parentId).push(category);
    });

    return map;
  }

  function collectDescendantCategoryIds(
    categoryId,
    childrenMap,
    result = new Set()
  ) {
    result.add(Number(categoryId));

    const children =
      childrenMap.get(Number(categoryId)) || [];

    children.forEach(child => {
      collectDescendantCategoryIds(
        child.id,
        childrenMap,
        result
      );
    });

    return result;
  }

  function getIndentedCategoryLabel(
    category,
    categoriesMap
  ) {
    const depth = getCategoryDepth(
      category,
      categoriesMap
    );

    return `${"— ".repeat(depth)}${category.name || ""}`;
  }

  function renderCategories() {
    const categories = getCategories();
    const container = document.getElementById("categoriesContainer");
    if (!container) return;

    container.innerHTML = "";

    const allBtn = document.createElement("button");
    allBtn.className = "category-btn active";
    allBtn.textContent = "Todas";
    allBtn.dataset.category = "all";
    allBtn.addEventListener("click", () => filterByCategory("all", allBtn));
    container.appendChild(allBtn);

const categoriesMap = new Map(
  categories.map(cat => [
    Number(cat.id),
    cat
  ])
);

const childrenMap =
  buildCategoryChildrenMap(categories);

function renderBranch(parentId = null) {
  const branch =
    [...(childrenMap.get(parentId) || [])]
      .sort((a, b) => {
        const sortA = Number(a.sort_order || 0);
        const sortB = Number(b.sort_order || 0);

        if (sortA !== sortB) {
          return sortA - sortB;
        }

        return String(a.name || "")
          .localeCompare(
            String(b.name || "")
          );
      });

  branch.forEach(category => {
      const btn = document.createElement("button");
      btn.className = "category-btn";
      btn.textContent =
      getIndentedCategoryLabel(
        category,
        categoriesMap
      );
      btn.dataset.category = category.id;
      btn.addEventListener("click", () => filterByCategory(category.id, btn));
      container.appendChild(btn);

        renderBranch(category.id);
      });
    }

    renderBranch(null);
  }

  function renderProducts(filteredProducts = null) {
    const products = getProducts();
    const rows = filteredProducts || products;

    const grid = document.getElementById("productsGrid");
    if (!grid) return;

    grid.innerHTML = "";

    if (!rows || rows.length === 0) {
      grid.innerHTML = `<div class="loading-box">No hay productos disponibles.</div>`;
      return;
    }

    rows.forEach(product => {
      const card = document.createElement("div");
      const isService = isServiceProduct(product);
      const disabled = !canAddToCart(product);
      const outOfStock = product.sellable_now !== true && !isService;
      const salePrice = Number(product.sale_price || 0);
      const categoryNameValue = getProductCategoryName(product);
      const stockLabel = getStockLabel(product);

      card.className = [
        "product-card",
        disabled ? "product-card-disabled" : "",
        outOfStock ? "product-card-out-of-stock" : "",
        isService ? "product-card-service" : "",
        !disabled ? "product-card-clickable" : ""
      ].filter(Boolean).join(" ");

      if (!disabled) {
        card.addEventListener("click", async () => {
          try {
            // consulta backend en tiempo real
            const freshProducts = await window.POS_API.fetchProducts();

            const fresh = (freshProducts || []).find(
              p => String(p.id) === String(product.id)
            );

            if (!fresh) {
              alert("El producto ya no está disponible.");
              return;
            }

            const isService = String(fresh?.product_type || "physical").toLowerCase() === "service";

            if (!isService && fresh.sellable_now !== true) {
              alert("El producto ya no tiene inventario disponible.");
              return;
            }

            addToCart(product.id);

          } catch (error) {
            console.error("Error validando inventario:", error);
            alert("No se pudo validar el inventario en tiempo real.");
          }
        });
      }

      const overlay = outOfStock
        ? `<div class="product-overlay-ribbon">SIN INVENTARIO</div>`
        : "";

      const topStatus = isService
        ? `<span class="product-status-chip product-status-chip-service">Servicio</span>`
        : outOfStock
          ? `<span class="product-status-chip product-status-chip-danger">Agotado</span>`
          : `<span class="product-status-chip product-status-chip-ok">Disponible</span>`;

      const categoryLine = categoryNameValue
        ? `<div class="product-subtitle">${escapeHtml(categoryNameValue)}</div>`
        : `<div class="product-subtitle product-subtitle-empty">Sin categoría</div>`;

      const stockBlock = isService
        ? `
          <div class="product-footer-row">
            <span class="product-footer-label">Tipo</span>
            <span class="product-footer-value">Servicio</span>
          </div>
        `
        : `
          <div class="product-footer-row">
            <span class="product-footer-label">Inventario</span>
            <span class="product-footer-value ${outOfStock ? "product-footer-value-danger" : ""}">
              ${escapeHtml(stockLabel)}
            </span>
          </div>
        `;

      card.innerHTML = `
        ${overlay}
        <div class="product-card-top">
          <div class="product-card-head">
            <div class="product-name" title="${escapeHtml(product.name)}">${escapeHtml(product.name)}</div>
            ${categoryLine}
          </div>
          <div class="product-card-status">
            ${topStatus}
          </div>
        </div>

        <div class="product-price-block">
          <div class="product-price-label">Precio</div>
          <div class="product-price">$${salePrice.toFixed(2)}</div>
        </div>

        <div class="product-card-footer">
          ${stockBlock}
        </div>
      `;

      grid.appendChild(card);
    });
  }

  function filterByCategory(categoryId, clickedBtn = null) {
    activeCategoryId = categoryId;
    const categories = getCategories();
    const products = getProducts();

    document.querySelectorAll(".category-btn").forEach(btn => {
      btn.classList.remove("active");
    });

    if (clickedBtn) {
      clickedBtn.classList.add("active");
    }

    if (categoryId === "all") {
      renderProducts(products);
      return;
    }

  const selectedCategory = categories.find(
      c => String(c.id) === String(categoryId)
    );

    if (!selectedCategory) {
      renderProducts(products);
      return;
    }

    const childrenMap =
      buildCategoryChildrenMap(
        categories
      );

    const descendantIds =
      [...collectDescendantCategoryIds(
        categoryId,
        childrenMap
      )]
      .map(id => String(id));

    const filtered = products.filter(product => {
      if (product.category_id == null) {
        return false;
      }

      return descendantIds.includes(
        String(product.category_id)
      );
    });

    renderProducts(filtered);
  }

  function setupSearch() {
    const searchInput = document.getElementById("searchInput");
    if (!searchInput) return;

    searchInput.addEventListener("input", function (e) {
      const products = getProducts();
      const searchTerm = e.target.value.toLowerCase().trim();
      activeSearchTerm = searchTerm;

      if (!searchTerm) {
        renderProducts(products);
        return;
      }

      const filtered = products.filter(p =>
        String(p.name || "").toLowerCase().includes(searchTerm) ||
        String(p.sku || "").toLowerCase().includes(searchTerm) ||
        String(getProductCategoryName(p) || "").toLowerCase().includes(searchTerm)
      );

      renderProducts(filtered);
    });
  }

  function showCatalogLoadError() {
    const grid = document.getElementById("productsGrid");
    if (!grid) return;

    grid.innerHTML = `
      <div class="error-box">
        No se pudo cargar el catálogo principal.<br>
        Revisa consola y logs del contenedor.
      </div>
    `;
  }

  function restoreCatalogState() {

    const products = getProducts();

    let rows = [...products];

    // búsqueda persistente
    if (activeSearchTerm) {
      rows = rows.filter(p =>
        String(p.name || "").toLowerCase().includes(activeSearchTerm) ||
        String(p.sku || "").toLowerCase().includes(activeSearchTerm) ||
        String(getProductCategoryName(p) || "").toLowerCase().includes(activeSearchTerm)
      );
    }

    // categoría persistente
    if (activeCategoryId !== "all") {

      const categories = getCategories();

      const childrenMap =
        buildCategoryChildrenMap(categories);

      const descendantIds =
        [...collectDescendantCategoryIds(
          activeCategoryId,
          childrenMap
        )]
        .map(id => String(id));

      rows = rows.filter(product => {
        if (product.category_id == null) {
          return false;
        }

        return descendantIds.includes(
          String(product.category_id)
        );
      });
    }

    renderProducts(rows);

    // restaurar botón activo
    document.querySelectorAll(".category-btn").forEach(btn => {
      btn.classList.remove("active");

      if (String(btn.dataset.category) === String(activeCategoryId)) {
        btn.classList.add("active");
      }
    });
  }
  
  return {
    renderCategories,
    renderProducts,
    filterByCategory,
    setupSearch,
    showCatalogLoadError,
    restoreCatalogState
  };
}