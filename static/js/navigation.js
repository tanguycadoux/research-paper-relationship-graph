// Menus of the navigation on a small screen (#207). The browser keeps one open at a
// time (details with the same name); a click outside or Escape closes it. Without this
// script, a menu simply closes with its own button.
(function () {
    "use strict";

    const menus = [...document.querySelectorAll("[data-nav-menu]")];

    document.addEventListener("click", (event) => {
        for (const menu of menus) {
            if (menu.open && !menu.contains(event.target)) {
                menu.open = false;
            }
        }
    });

    document.addEventListener("keydown", (event) => {
        const open = menus.find((menu) => menu.open);
        if (event.key === "Escape" && open) {
            open.open = false;
            open.querySelector("summary").focus();
        }
    });
})();
