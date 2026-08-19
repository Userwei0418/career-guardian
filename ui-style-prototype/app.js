(() => {
  const screens = [...document.querySelectorAll(".screen")];
  const screenButtons = [...document.querySelectorAll("[data-screen-target]")];
  const navButtons = [...document.querySelectorAll(".domain-link[data-screen-target]")];
  const previewButtons = [...document.querySelectorAll(".preview-tabs [data-screen-target]")];
  const header = document.querySelector(".app-header");
  const menuButton = document.querySelector(".mobile-menu");
  const scrim = document.querySelector(".nav-scrim");
  const toast = document.querySelector(".toast");
  const dock = document.querySelector(".preview-dock");
  const dialog = document.querySelector(".detail-dialog");
  let toastTimer;

  function showToast(message) {
    clearTimeout(toastTimer);
    toast.textContent = message;
    toast.classList.add("is-visible");
    toastTimer = setTimeout(() => toast.classList.remove("is-visible"), 2400);
  }

  function closeMenu() {
    header.classList.remove("is-open");
    menuButton.setAttribute("aria-expanded", "false");
    scrim.hidden = true;
  }

  function showScreen(name) {
    screens.forEach((screen) => screen.classList.toggle("is-active", screen.dataset.screen === name));
    navButtons.forEach((button) => button.classList.toggle("is-active", button.dataset.screenTarget === name));
    previewButtons.forEach((button) => button.classList.toggle("is-active", button.dataset.screenTarget === name));
    closeMenu();
    window.scrollTo({ top: 0, behavior: "smooth" });
    history.replaceState(null, "", `#${name}`);
  }

  screenButtons.forEach((button) => button.addEventListener("click", () => showScreen(button.dataset.screenTarget)));
  document.querySelectorAll("[data-toast]").forEach((button) => button.addEventListener("click", () => showToast(button.dataset.toast)));
  document.querySelectorAll("[data-dialog-open]").forEach((button) => button.addEventListener("click", () => dialog.showModal()));

  document.querySelectorAll("[data-target-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      const tab = button.dataset.targetTab;
      document.querySelectorAll("[data-target-tab]").forEach((item) => item.classList.toggle("is-active", item === button));
      document.querySelectorAll("[data-target-panel]").forEach((panel) => panel.classList.toggle("is-active", panel.dataset.targetPanel === tab));
    });
  });
  document.querySelectorAll("[data-target-tab-jump]").forEach((button) => {
    button.addEventListener("click", () => document.querySelector(`[data-target-tab="${button.dataset.targetTabJump}"]`).click());
  });

  menuButton.addEventListener("click", () => {
    const open = !header.classList.contains("is-open");
    header.classList.toggle("is-open", open);
    menuButton.setAttribute("aria-expanded", String(open));
    scrim.hidden = !open;
  });
  scrim.addEventListener("click", closeMenu);
  document.querySelector(".dock-close").addEventListener("click", () => dock.classList.add("is-collapsed"));
  document.querySelector(".dock-open").addEventListener("click", () => dock.classList.remove("is-collapsed"));
  dialog.addEventListener("click", (event) => {
    const rect = dialog.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
  });

  const initial = location.hash.slice(1);
  showScreen(["today", "target", "interview", "decision"].includes(initial) ? initial : "today");
})();
