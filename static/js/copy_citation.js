// The « Copier » buttons of the citation panel (#286). A formatted citation is copied as
// HTML, which keeps its italics in a word processor, and as plain text; the BibTeX entry
// as plain text. Without this script, or without clipboard access, the buttons stay
// hidden: the text remains selectable.
(function () {
    "use strict";

    if (!navigator.clipboard) {
        return;
    }

    function copy(source) {
        if (source.tagName === "PRE") {
            // The BibTeX entry wraps to the panel (#413): its text, not its lines on screen.
            return navigator.clipboard.writeText(source.textContent.trim());
        }
        const text = source.innerText.trim();
        if (!window.ClipboardItem) {
            return navigator.clipboard.writeText(text);
        }
        return navigator.clipboard.write([
            new ClipboardItem({
                "text/html": new Blob([source.innerHTML.trim()], { type: "text/html" }),
                "text/plain": new Blob([text], { type: "text/plain" }),
            }),
        ]);
    }

    function say(status, message) {
        status.textContent = message;
        clearTimeout(status.timeout);
        status.timeout = setTimeout(() => {
            status.textContent = "";
        }, 2500);
    }

    document.querySelectorAll("[data-copy]").forEach((wrapper) => {
        const source = document.getElementById(wrapper.dataset.copy);
        const status = wrapper.querySelector("[data-copy-status]");
        wrapper.hidden = false;
        wrapper.querySelector("button").addEventListener("click", () => {
            copy(source).then(
                () => say(status, "Copié"),
                () => say(status, "Copie impossible : sélectionnez le texte"),
            );
        });
    });
})();
