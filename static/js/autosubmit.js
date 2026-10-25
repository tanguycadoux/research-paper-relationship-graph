// Forms sent as soon as one of their lists changes (the reading status, #164): their
// button is hidden. Without this script the button stays, and sends the form.
(function () {
    "use strict";

    document.querySelectorAll("[data-autosubmit]").forEach((form) => {
        form.querySelectorAll("[data-autosubmit-button]").forEach((button) => {
            button.hidden = true;
        });
        form.addEventListener("change", () => form.requestSubmit());
    });
})();
