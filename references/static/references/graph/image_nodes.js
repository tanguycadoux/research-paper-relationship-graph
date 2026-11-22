// The list of the nodes beside the image of a large graph (#453): searched without case
// nor accents, sorted by size or by name. Only the rows in sight are drawn (the graph of
// the authors has 9 500 nodes), placed at their rank in a list as tall as all of them.
// Hovering a row lights its node, checking it keeps it lit with its links, « Centrer »
// brings it to the middle of the view; hovering a node of the image shows its row.

// The height of a row, in pixels (h-11 of the row of the template).
const ROW = 44;
// Rows drawn above and below those in sight, for a smooth scroll.
const OVERSCAN = 6;
const collator = new Intl.Collator("fr", { sensitivity: "base", numeric: true });
// One formatter for all the rows: toLocaleString builds one at each call.
const numbers = new Intl.NumberFormat("fr-FR");

function fold(text) {
    return text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
}

export function createNodeList(panel, nodes, actions) {
    const parts = {
        search: panel.querySelector("[data-image-search]"),
        sort: panel.querySelector("[data-image-sort]"),
        count: panel.querySelector("[data-image-count]"),
        list: panel.querySelector("[data-image-list]"),
        rows: panel.querySelector("[data-image-rows]"),
        template: panel.querySelector("[data-image-row]"),
    };
    const keys = nodes.map((node) => fold(node.label));
    const orders = sortedOrders(nodes);
    const state = { shown: orders.size, active: null, checked: new Set(), frame: 0 };

    function filter() {
        const query = fold(parts.search.value.trim());
        const order = orders[parts.sort.value] ?? orders.size;
        state.shown = query ? order.filter((index) => keys[index].includes(query)) : order;
        parts.rows.style.height = `${state.shown.length * ROW}px`;
        parts.count.textContent = countText(state.shown.length, nodes.length, actions.nouns);
        parts.list.scrollTop = 0;
        render();
    }

    function render() {
        const { scrollTop, clientHeight } = parts.list;
        const first = Math.max(0, Math.floor(scrollTop / ROW) - OVERSCAN);
        const last = Math.min(state.shown.length, Math.ceil((scrollTop + clientHeight) / ROW) + OVERSCAN);
        const rows = state.shown.slice(first, last).map((index, k) => row(index, first + k));
        parts.rows.replaceChildren(...rows);
    }

    function row(index, position) {
        const item = parts.template.content.firstElementChild.cloneNode(true);
        fillRow(item, nodes[index], actions.nouns);
        item.style.top = `${position * ROW}px`;
        item.dataset.node = index;
        item.querySelector("[data-row-check]").checked = state.checked.has(index);
        item.toggleAttribute("data-checked", state.checked.has(index));
        item.toggleAttribute("data-active", index === state.active);
        return item;
    }

    // The row of a node hovered in the image: lit, and scrolled into sight.
    function reveal(index) {
        state.active = index;
        for (const item of parts.rows.children) {
            item.toggleAttribute("data-active", Number(item.dataset.node) === index);
        }
        const position = index === null ? -1 : state.shown.indexOf(index);
        const { scrollTop, clientHeight } = parts.list;
        if (position >= 0 && (position * ROW < scrollTop || (position + 1) * ROW > scrollTop + clientHeight)) {
            parts.list.scrollTop = position * ROW - (clientHeight - ROW) / 2;
        }
    }

    function toggle(index, on) {
        if (on) {
            state.checked.add(index);
        } else {
            state.checked.delete(index);
        }
        actions.check(index, on);
        render();
    }

    listenRows(parts, actions, toggle);
    parts.list.addEventListener("scroll", () => {
        cancelAnimationFrame(state.frame);
        state.frame = requestAnimationFrame(render);
    });
    parts.search.addEventListener("input", filter);
    parts.sort.addEventListener("change", filter);
    new ResizeObserver(render).observe(parts.list);
    filter();
    return { reveal };
}

// The ranks of the nodes, largest first (by name among equals), and by name.
function sortedOrders(nodes) {
    const ranks = nodes.map((_, index) => index);
    const byName = (a, b) => collator.compare(nodes[a].label, nodes[b].label);
    return {
        size: [...ranks].sort((a, b) => nodes[b].size - nodes[a].size || byName(a, b)),
        name: [...ranks].sort(byName),
    };
}

function fillRow(item, node, nouns) {
    const name = item.querySelector("[data-row-name]");
    name.href = node.url;
    name.textContent = node.label;
    name.title = node.label;
    item.querySelector("[data-row-size]").textContent = counted(node.size, nouns.size);
    item.querySelector("[data-row-check]").setAttribute("aria-label", `Garder en évidence : ${node.label}`);
    item.querySelector("[data-row-centre] button").setAttribute("aria-label", `Centrer : ${node.label}`);
}

// « 12 citations », « 1 citation » (0 and 1 in the singular, like pluralize_fr).
function counted(count, [singular, plural]) {
    return `${numbers.format(count)} ${count > 1 ? plural : singular}`;
}

function countText(shown, total, nouns) {
    if (shown === total) {
        return counted(total, nouns.node);
    }
    return `${numbers.format(shown)} sur ${counted(total, nouns.node)}`;
}

// Hover, check and « Centrer » of the rows, delegated: the rows come and go with the scroll.
function listenRows(parts, actions, toggle) {
    const indexOf = (target) => {
        const item = target.closest("[data-node]");
        return item ? Number(item.dataset.node) : null;
    };
    parts.rows.addEventListener("pointerover", (event) => actions.hover(indexOf(event.target)));
    parts.list.addEventListener("pointerleave", () => actions.hover(null));
    parts.rows.addEventListener("change", (event) => {
        if (event.target.matches("[data-row-check]")) {
            toggle(indexOf(event.target), event.target.checked);
        }
    });
    parts.rows.addEventListener("click", (event) => {
        if (event.target.closest("[data-row-centre]")) {
            actions.centre(indexOf(event.target));
        }
    });
}
