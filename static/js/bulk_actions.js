// The bar of bulk actions of « Mon corpus » (#287): says how many rows are checked,
// shows the box that checks them all, and disables the buttons of the bar while none
// is checked (they stay in place). Without this script the bar works as well: the
// server says when nothing is checked.
(function () {
    "use strict";

    const form = document.querySelector("[data-bulk-actions]");
    if (!form) {
        return;
    }
    const rows = Array.from(document.querySelectorAll(`[data-bulk-row][form="${form.id}"]`));
    const all = document.querySelector("[data-bulk-all]");
    const count = form.querySelector("[data-bulk-count]");
    const buttons = form.querySelectorAll("button");

    function checkedCount() {
        return rows.filter((row) => row.checked).length;
    }

    function describe(checked) {
        if (checked === 0) {
            return "Aucune publication cochée";
        }
        if (checked === 1) {
            return "1 publication cochée :";
        }
        return `${checked} publications cochées :`;
    }

    function update() {
        const checked = checkedCount();
        count.textContent = describe(checked);
        buttons.forEach((button) => {
            button.disabled = checked === 0;
        });
        if (all) {
            all.checked = checked > 0 && checked === rows.length;
            all.indeterminate = checked > 0 && checked < rows.length;
            all.disabled = rows.length === 0;
        }
    }

    if (all) {
        all.hidden = false;
        all.addEventListener("change", () => {
            rows.forEach((row) => {
                row.checked = all.checked;
            });
            update();
        });
    }
    rows.forEach((row) => row.addEventListener("change", update));
    // Back from the history, the browser may restore the boxes checked.
    window.addEventListener("pageshow", update);
    update();
})();
