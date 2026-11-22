// The selected nodes of the image of a large graph (#453): those clicked in the image or
// checked in the list of all the nodes, kept lit with their links (image_highlight.js).
// Listed above that list, in the order of their selection: a click on a name centres the
// view on its node, its link leads to its page, « × » takes it out of the selection, and
// « Tout désélectionner » empties it.

const numbers = new Intl.NumberFormat("fr-FR");

export function createSelection(box, nodes, actions) {
    const parts = {
        count: box.querySelector("[data-selection-count]"),
        empty: box.querySelector("[data-selection-empty]"),
        list: box.querySelector("[data-selection-list]"),
        template: box.querySelector("[data-selection-row]"),
        clear: box.querySelector("[data-selection-clear] button"),
    };
    const selected = new Set();
    const listeners = [];

    function set(index, on) {
        if (index === null || on === selected.has(index)) {
            return;
        }
        if (on) {
            selected.add(index);
        } else {
            selected.delete(index);
        }
        listeners.forEach((listener) => listener(index, on));
        render();
        if (on) {
            parts.list.scrollTop = parts.list.scrollHeight;
        }
    }

    function render() {
        const count = selected.size;
        parts.count.textContent = `(${numbers.format(count)})`;
        parts.empty.hidden = count > 0;
        parts.list.hidden = count === 0;
        parts.clear.disabled = count === 0;
        parts.list.replaceChildren(...[...selected].map(row));
    }

    function row(index) {
        const item = parts.template.content.firstElementChild.cloneNode(true);
        const { label, url } = nodes[index];
        item.dataset.node = index;
        const name = item.querySelector("[data-selection-centre]");
        name.textContent = label;
        name.title = `Centrer la vue sur ${label}`;
        labelled(item.querySelector("[data-selection-link] a"), `Voir sa page : ${label}`).href = url;
        labelled(item.querySelector("[data-selection-remove] button"), `Retirer de la sélection : ${label}`);
        return item;
    }

    listenRows(parts.list, actions, (index) => set(index, false));
    parts.clear.addEventListener("click", () => [...selected].forEach((index) => set(index, false)));
    render();

    return {
        has: (index) => selected.has(index),
        set,
        toggle: (index) => set(index, !selected.has(index)),
        // Called with the node and whether it is now selected.
        onChange: (listener) => listeners.push(listener),
    };
}

function labelled(element, label) {
    element.setAttribute("aria-label", label);
    element.title = label;
    return element;
}

// Hover, centre and remove, delegated: the rows are drawn again at each change.
function listenRows(list, actions, remove) {
    const indexOf = (target) => {
        const item = target.closest("[data-node]");
        return item ? Number(item.dataset.node) : null;
    };
    list.addEventListener("pointerover", (event) => actions.hover(indexOf(event.target)));
    list.addEventListener("pointerleave", () => actions.hover(null));
    list.addEventListener("click", (event) => {
        const index = indexOf(event.target);
        if (index === null) {
            return;
        }
        if (event.target.closest("[data-selection-centre]")) {
            actions.centre(index);
        } else if (event.target.closest("[data-selection-remove]")) {
            remove(index);
            actions.hover(null);
        }
    });
}
