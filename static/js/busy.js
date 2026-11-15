// Busy buttons (#339): a form sent to the server may wait for the sources (Crossref,
// DataCite, OpenAlex, ORCID…) from 1 to 10 s. Once it is sent, its submit buttons are
// disabled, against a second click, and the one clicked turns its icon into a spinner.
// Without this script nothing changes: the form is sent as before.
(function () {
    "use strict";

    const SPINNER =
        '<svg data-busy-spinner class="size-[1.25em] shrink-0 animate-spin" viewBox="0 0 24 24" ' +
        'fill="none" aria-hidden="true"><circle cx="12" cy="12" r="9" stroke="currentColor" ' +
        'stroke-width="3" class="opacity-25"></circle><path d="M21 12a9 9 0 0 0-9-9" ' +
        'stroke="currentColor" stroke-width="3" stroke-linecap="round"></path></svg>';

    function busy(form, submitter) {
        const buttons = form.querySelectorAll('button[type="submit"], button:not([type])');
        // After the submission has read the clicked button's name and value (« à lire »).
        setTimeout(() => {
            buttons.forEach((button) => {
                if (!button.disabled) {
                    button.disabled = true;
                    button.dataset.busyDisabled = "";
                }
            });
        });
        if (!submitter) {
            return;
        }
        submitter.setAttribute("aria-busy", "true");
        // An SVG has no hidden property: the attribute, which the base styles hide.
        const icon = submitter.querySelector("svg");
        if (icon) {
            icon.setAttribute("hidden", "");
        }
        submitter.insertAdjacentHTML("afterbegin", SPINNER);
    }

    function restore() {
        document.querySelectorAll("[data-busy-spinner]").forEach((spinner) => {
            const button = spinner.closest("button");
            spinner.remove();
            button.removeAttribute("aria-busy");
            const icon = button.querySelector("svg");
            if (icon) {
                icon.removeAttribute("hidden");
            }
        });
        // Only the buttons disabled here: the page may disable others (a useless control
        // stays in place, disabled).
        document.querySelectorAll("[data-busy-disabled]").forEach((button) => {
            button.disabled = false;
            delete button.dataset.busyDisabled;
        });
    }

    document.addEventListener("submit", (event) => {
        const form = event.target;
        if (event.defaultPrevented || form.method.toLowerCase() !== "post") {
            return;
        }
        busy(form, event.submitter);
    });
    // Back to the page from the history: its buttons work again.
    window.addEventListener("pageshow", (event) => {
        if (event.persisted) {
            restore();
        }
    });
})();
