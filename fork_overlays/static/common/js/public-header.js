function ensureImageEditNav(container) {
  if (!container) return;

  const existing = container.querySelector('a[data-nav="/image-edit"]');
  if (existing) return;

  const voiceLink = container.querySelector('a[data-nav="/voice"]');
  const videoLink = container.querySelector('a[data-nav="/video"]');
  const anchor = voiceLink || videoLink;
  if (!anchor || !anchor.parentElement) return;

  const link = document.createElement("a");
  link.href = "/image-edit";
  link.className = "nav-link text-sm";
  link.setAttribute("data-nav", "/image-edit");
  link.setAttribute("data-i18n", "nav.imageEdit");
  link.textContent = "Edit 图像编辑";

  if (voiceLink && voiceLink.parentElement === anchor.parentElement) {
    anchor.parentElement.insertBefore(link, voiceLink);
    return;
  }

  anchor.parentElement.appendChild(link);
}

async function loadPublicHeader() {
  const container = document.getElementById("app-header");
  if (!container) return;

  try {
    const res = await fetch("/static/common/html/public-header.html?v=1.5.5");
    if (!res.ok) return;

    container.innerHTML = await res.text();
    ensureImageEditNav(container);

    const logoutBtn = container.querySelector("#public-logout-btn");
    if (logoutBtn) {
      logoutBtn.classList.add("hidden");
      try {
        const verify = await fetch("/v1/public/verify", { method: "GET" });
        if (verify.status === 401) {
          logoutBtn.classList.remove("hidden");
        }
      } catch (e) {
        // Ignore verification errors and keep it hidden.
      }
    }

    if (window.I18n) {
      I18n.applyToDOM(container);
      const toggle = container.querySelector("#lang-toggle");
      if (toggle) toggle.textContent = I18n.getLang() === "zh" ? "EN" : "中";
    }

    const path = window.location.pathname;
    const links = container.querySelectorAll("a[data-nav]");
    links.forEach((link) => {
      const target = link.getAttribute("data-nav") || "";
      if (target && path.startsWith(target)) {
        link.classList.add("active");
      }
    });
  } catch (e) {
    // Fail silently to avoid breaking page load.
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", loadPublicHeader);
} else {
  loadPublicHeader();
}
