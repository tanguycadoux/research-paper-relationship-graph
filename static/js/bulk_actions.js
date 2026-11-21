// The bars of bulk actions (#287, #408), each above its list: says how many rows are
// checked, shows the box that checks them all, and disables the buttons of the bar
// while none is checked (they stay in place). Several bars can share a page: the rows
// and the box « Tout cocher » of a bar name its form (form="…", data-bulk-all="…").
// A bar marked data-bulk-collapsible (#410) is folded into its first line, which then
// says what checking does, until a first row is checked: it unfolds for good, and its
// buttons are disabled again rather than hidden if the rows are unchecked.
// Without this script the bars work as well, unfolded: the server says when nothing is
// checked.
(function () {
    "use strict";

    function describe(checked) {
        if (checked === 0) {
            return "Aucune publication cochée";
        }
        if (checked === 1) {
            return "1 publication cochée :";
        }
        return `${checked} publications cochées :`;
    }

    function setUp(form) {
        const rows = Array.from(document.querySelectorAll(`[data-bulk-row][form="${form.id}"]`));
        const all = document.querySelector(`[data-bulk-all="${form.id}"]`);
        const count = form.querySelector("[data-bulk-count]");
        const buttons = form.querySelectorAll("button");
        const more = form.querySelector("[data-bulk-more]");
        const hint = form.dataset.bulkCollapsible;
        let folded = hint !== undefined;

        function fold(checked) {
            folded = folded && checked === 0;
            more.hidden = folded;
            form.toggleAttribute("data-bulk-folded", folded);
        }

        function update() {
            const checked = rows.filter((row) => row.checked).length;
            fold(checked);
            count.textContent = folded ? hint : describe(checked);
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
    }

    document.querySelectorAll("[data-bulk-actions]").forEach(setUp);
})();
