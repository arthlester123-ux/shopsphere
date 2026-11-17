document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.querySelector(".menu-toggle");
  const nav = document.querySelector(".nav-links");
  if (toggle && nav) toggle.addEventListener("click", () => {
    const open = nav.classList.toggle("open");
    toggle.setAttribute("aria-expanded", String(open));
  });

  // Reveal sections as they enter the viewport.
  const revealItems = document.querySelectorAll("[data-reveal]");
  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver((entries, obs) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          obs.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08 });
    revealItems.forEach(item => observer.observe(item));
  } else revealItems.forEach(item => item.classList.add("is-visible"));

  // Sort and switch the catalogue layout without reloading the page.
  const grid = document.getElementById("productGrid");
  const sort = document.getElementById("productSort");
  if (grid && sort) sort.addEventListener("change", () => {
    const cards = [...grid.querySelectorAll(".product-card")];
    const mode = sort.value;
    cards.sort((a, b) => {
      if (mode === "price-low") return Number(a.dataset.price) - Number(b.dataset.price);
      if (mode === "price-high") return Number(b.dataset.price) - Number(a.dataset.price);
      if (mode === "name") return a.dataset.name.localeCompare(b.dataset.name);
      return Number(a.dataset.index) - Number(b.dataset.index);
    });
    cards.forEach((card, index) => {
      card.style.animationDelay = `${Math.min(index * 35, 280)}ms`;
      grid.appendChild(card);
    });
  });
  document.querySelectorAll(".view-button").forEach(button => button.addEventListener("click", () => {
    document.querySelectorAll(".view-button").forEach(item => item.classList.toggle("active", item === button));
    if (grid) grid.classList.toggle("list-view", button.dataset.view === "list");
  }));

  // Wishlist is a lightweight browser-side convenience for this demo storefront.
  const saved = new Set(JSON.parse(localStorage.getItem("shopsphere-wishlist") || "[]"));
  document.querySelectorAll("[data-favorite]").forEach(button => {
    const id = button.dataset.favorite;
    const sync = () => {
      const active = saved.has(id);
      button.classList.toggle("is-favorite", active);
      button.setAttribute("aria-pressed", String(active));
      button.textContent = active ? "♥" : "♡";
    };
    sync();
    button.addEventListener("click", () => {
      saved.has(id) ? saved.delete(id) : saved.add(id);
      localStorage.setItem("shopsphere-wishlist", JSON.stringify([...saved]));
      sync();
      showToast(saved.has(id) ? "Saved to your favorites" : "Removed from favorites");
    });
  });

  const modal = document.getElementById("quickView");
  if (!modal) return;
  const dialog = modal.querySelector(".quick-view-dialog");
  const closeButton = modal.querySelector(".quick-view-close");
  const image = document.getElementById("quickViewImage");
  const fallback = document.getElementById("quickViewFallback");
  const name = document.getElementById("quickViewName");
  const category = document.getElementById("quickViewCategory");
  const price = document.getElementById("quickViewPrice");
  const description = document.getElementById("quickViewDescription");
  const stock = document.getElementById("quickViewStock");
  const stockDot = document.getElementById("quickViewStockDot");
  const quantity = document.getElementById("quickViewQuantity");
  const cartForm = document.getElementById("quickViewCartForm");
  const addButton = document.getElementById("quickViewAdd");
  const moreLink = document.getElementById("quickViewMore");
  const loginLink = document.getElementById("quickViewLogin");
  let lastFocused = null;
  let closeTimer = null;

  function openModal(trigger) {
    if (closeTimer) clearTimeout(closeTimer);
    lastFocused = trigger;
    const data = trigger.dataset;
    name.textContent = data.name || "Product";
    category.textContent = data.category || "PRODUCT";
    price.textContent = data.price || "";
    description.textContent = data.description || "No additional description is available.";
    const available = Number(data.stock || 0);
    stock.textContent = available > 0 ? `${available} available in stock` : "Currently unavailable";
    stock.classList.toggle("is-out", available <= 0);
    stockDot.classList.toggle("stock-dot-out", available <= 0);
    quantity.max = String(Math.max(1, available));
    quantity.value = "1";
    cartForm.action = data.cartUrl || "";
    moreLink.href = data.detailsUrl || "#";
    image.alt = data.name || "Product image";
    image.style.display = "none";
    image.removeAttribute("src");
    fallback.textContent = (data.name || "S").charAt(0).toUpperCase();
    fallback.style.display = "grid";
    if (data.image) {
      image.onload = () => { image.style.display = "block"; fallback.style.display = "none"; };
      image.onerror = () => { image.style.display = "none"; fallback.style.display = "grid"; };
      image.src = data.image;
    }
    const canBuy = available > 0 && data.authenticated === "true";
    cartForm.hidden = !canBuy;
    loginLink.style.display = available > 0 && data.authenticated !== "true" ? "inline-flex" : "none";
    addButton.disabled = !canBuy;
    modal.inert = false;
    modal.setAttribute("aria-hidden", "false");
    document.body.classList.add("modal-open");
    // Two animation frames ensure the closed state is painted before opening.
    modal.classList.remove("is-closing");
    requestAnimationFrame(() => requestAnimationFrame(() => {
      modal.classList.add("is-open");
      closeButton.focus({ preventScroll: true });
    }));
  }

  function closeModal() {
    if (!modal.classList.contains("is-open")) return;
    modal.classList.remove("is-open");
    modal.classList.add("is-closing");
    modal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("modal-open");
    closeTimer = window.setTimeout(() => {
      modal.inert = true;
      modal.classList.remove("is-closing");
      if (lastFocused && document.contains(lastFocused)) lastFocused.focus({ preventScroll: true });
    }, 360);
  }

  document.querySelectorAll(".quick-view-trigger").forEach(trigger => trigger.addEventListener("click", () => openModal(trigger)));
  closeButton.addEventListener("click", closeModal);
  modal.addEventListener("click", event => { if (event.target === modal) closeModal(); });
  document.addEventListener("keydown", event => {
    if (!modal.classList.contains("is-open")) return;
    if (event.key === "Escape") closeModal();
    if (event.key === "Tab") {
      const focusable = [...dialog.querySelectorAll('a[href],button:not([disabled]),input:not([disabled])')].filter(el => !el.hidden && el.offsetParent !== null);
      if (!focusable.length) return;
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });

  document.querySelectorAll("[data-quantity]").forEach(button => button.addEventListener("click", () => {
    const current = Number(quantity.value || 1);
    const max = Number(quantity.max || 99);
    quantity.value = String(button.dataset.quantity === "plus" ? Math.min(max, current + 1) : Math.max(1, current - 1));
  }));
  quantity.addEventListener("change", () => {
    const max = Number(quantity.max || 99);
    quantity.value = String(Math.min(max, Math.max(1, Number(quantity.value || 1))));
  });
});

function showToast(message) {
  const region = document.getElementById("toastRegion");
  if (!region) return;
  const toast = document.createElement("div");
  toast.className = "shop-toast";
  toast.textContent = message;
  region.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add("is-visible"));
  window.setTimeout(() => {
    toast.classList.remove("is-visible");
    window.setTimeout(() => toast.remove(), 260);
  }, 2200);
}
