// Notifications (django.contrib.messages): close button, Escape key, and successes
// that fade out by themselves. Without this script they simply stay on the page.
(function () {
    "use strict";

    const AUTOHIDE_DELAY = 6000;

    function setUp(toast) {
        const close = () => toast.remove();
        const button = toast.querySelector("[data-toast-close]");
        button.hidden = false;
        button.addEventListener("click", close);
        toast.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                close();
            }
        });
        if (toast.hasAttribute("data-toast-autohide")) {
            autohide(toast, close);
        }
    }

    function autohide(toast, close) {
        // Paused while the pointer or the keyboard focus is on the toast.
        let timer = setTimeout(close, AUTOHIDE_DELAY);
        const pause = () => clearTimeout(timer);
        const resume = () => {
            timer = setTimeout(close, AUTOHIDE_DELAY);
        };
        toast.addEventListener("mouseenter", pause);
        toast.addEventListener("mouseleave", resume);
        toast.addEventListener("focusin", pause);
        toast.addEventListener("focusout", resume);
    }

    document.querySelectorAll("[data-toast]").forEach(setUp);
})();
