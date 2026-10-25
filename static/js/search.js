// Ctrl+K, ⌘K on a Mac, puts the cursor in the search bar (#153). Where no bar is shown
// (header on a small screen), it opens the search page.
(function () {
    "use strict";

    const mac = /Mac|iPhone|iPad/.test(navigator.platform);
    if (mac) {
        for (const hint of document.querySelectorAll("[data-search-shortcut]")) {
            hint.textContent = "⌘ K";
        }
    }

    document.addEventListener("keydown", (event) => {
        const modifier = mac ? event.metaKey : event.ctrlKey;
        if (event.key.toLowerCase() !== "k" || !modifier || event.altKey || event.shiftKey) {
            return;
        }
        const input = [...document.querySelectorAll("[data-search-input]")].find(
            (element) => element.offsetParent !== null,
        );
        const link = document.querySelector("[data-search-link]");
        if (input) {
            event.preventDefault();
            input.focus();
            input.select();
        } else if (link) {
            event.preventDefault();
            window.location.href = link.dataset.searchLink;
        }
    });
})();
