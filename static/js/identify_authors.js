// The authors of « Sans identifiant » on the identification page (#259): a list in signing
// order instead of the text field « un auteur par ligne », which the list keeps filled, so
// the form sends the same text with or without this script. Authors of the base are
// suggested while typing (name or ORCID), and « Nom, Prénom » adds a new author.
(function () {
    "use strict";

    const editor = document.querySelector("[data-author-editor]");
    if (!editor) {
        return;
    }
    const DELAY = 250; // ms of pause in the typing before asking the server
    const MIN_LENGTH = 2;

    const textarea = editor.querySelector("[data-author-lines] textarea");
    const rich = editor.querySelector("[data-author-rich]");
    const list = rich.querySelector("[data-author-list]");
    const empty = rich.querySelector("[data-author-empty]");
    const input = rich.querySelector("[data-author-search]");
    const listbox = rich.querySelector("[role=listbox]");
    const status = rich.querySelector("[data-author-status]");
    const proposal = rich.querySelector("[data-author-proposal]");
    const itemTemplate = editor.querySelector("template[data-author-item]");
    const optionTemplate = editor.querySelector("template[data-author-option]");
    const entries = JSON.parse(document.getElementById("author-entries").textContent);

    let options = [];
    let active = -1;
    let timer = null;
    let controller = null;

    function detail(entry) {
        const parts = [];
        if (entry.orcid) {
            parts.push(entry.orcid);
        }
        if (entry.publications !== undefined && entry.publications !== null) {
            const count = Number(entry.publications);
            parts.push(`${count} publication${count > 1 ? "s" : ""}`);
        }
        return parts.join(" · ");
    }

    function announce(text) {
        status.textContent = text;
    }

    // The list, and the text field the form sends.

    function render() {
        list.replaceChildren(...entries.map(item));
        empty.hidden = entries.length > 0;
        textarea.value = entries.map((entry) => entry.line).join("\n");
    }

    function item(entry, index) {
        const li = itemTemplate.content.firstElementChild.cloneNode(true);
        li.querySelector("[data-rank]").textContent = `${index + 1}.`;
        li.querySelector("[data-name]").textContent = entry.name;
        li.querySelector("[data-detail]").textContent = detail(entry);
        li.querySelector("[data-existing]").hidden = !entry.id;
        li.querySelector("[data-new]").hidden = Boolean(entry.id);
        for (const wrapper of li.querySelectorAll("[data-move]")) {
            const step = Number(wrapper.dataset.move);
            const button = wrapper.querySelector("button");
            const target = index + step;
            button.disabled = target < 0 || target >= entries.length;
            label(button, entry);
            button.addEventListener("click", () => move(index, step));
        }
        const remover = li.querySelector("[data-remove] button");
        label(remover, entry);
        remover.addEventListener("click", () => remove(index));
        return li;
    }

    function label(button, entry) {
        const text = `${button.getAttribute("aria-label")} ${entry.name}`;
        button.setAttribute("aria-label", text);
        button.title = text;
    }

    function move(index, step) {
        const target = index + step;
        [entries[index], entries[target]] = [entries[target], entries[index]];
        render();
        // The focus follows the author, on the same button when it can still be used.
        const li = list.children[target];
        const same = li.querySelector(`[data-move="${step}"] button`);
        const other = li.querySelector(`[data-move="${-step}"] button`);
        (same.disabled ? other : same).focus();
        announce(`${entries[target].name} : rang ${target + 1}.`);
    }

    function remove(index) {
        const [removed] = entries.splice(index, 1);
        render();
        const next = list.children[Math.min(index, entries.length - 1)];
        (next ? next.querySelector("[data-remove] button") : input).focus();
        announce(`${removed.name} retiré de la liste.`);
    }

    function add(entry) {
        if (entry.id && entries.some((other) => other.id === entry.id)) {
            announce(`${entry.name} est déjà dans la liste.`);
            return;
        }
        entries.push(entry);
        render();
        announce(`${entry.name} ajouté, rang ${entries.length}.`);
    }

    // A new author, typed « Nom, Prénom » (the first name is optional): its line, or null.
    function newAuthorLine(text) {
        const parts = text.split(",").map((part) => part.split(/\s+/).filter(Boolean).join(" "));
        if (parts.length > 2 || !parts[0]) {
            return null;
        }
        return parts[1] ? `${parts[0]}, ${parts[1]}` : parts[0];
    }

    // Suggestions while typing.

    async function search() {
        const text = input.value.trim();
        let found = [];
        if (text.length >= MIN_LENGTH) {
            if (controller) {
                controller.abort();
            }
            controller = new AbortController();
            const url = `${editor.dataset.suggestUrl}?q=${encodeURIComponent(text)}`;
            try {
                const response = await fetch(url, {
                    signal: controller.signal,
                    headers: { Accept: "application/json" },
                });
                if (response.ok) {
                    found = (await response.json()).results;
                }
            } catch (error) {
                if (error.name === "AbortError") {
                    return;
                }
            }
        }
        if (input.value.trim() !== text) {
            return;
        }
        const chosen = new Set(entries.filter((entry) => entry.id).map((entry) => entry.id));
        options = found
            .filter((author) => !chosen.has(author.id))
            .map((author) => ({ ...author, line: `#${author.id}` }));
        const line = newAuthorLine(text);
        if (line) {
            options.push({ id: null, name: line, line: line, typed: true });
        }
        show();
    }

    function show() {
        active = -1;
        listbox.replaceChildren(...options.map(option));
        listbox.hidden = options.length === 0;
        input.setAttribute("aria-expanded", String(options.length > 0));
        input.removeAttribute("aria-activedescendant");
    }

    function option(entry, index) {
        const li = optionTemplate.content.firstElementChild.cloneNode(true);
        li.id = `author-search-option-${index}`;
        li.querySelector("[data-name]").textContent = entry.typed
            ? `Nouvel auteur : ${entry.name}`
            : entry.name;
        li.querySelector("[data-detail]").textContent = entry.typed ? "" : detail(entry);
        li.addEventListener("pointerdown", (event) => event.preventDefault());
        li.addEventListener("click", () => choose(index));
        return li;
    }

    function close() {
        options = [];
        show();
    }

    function highlight(index) {
        active = index;
        [...listbox.children].forEach((li, position) => {
            li.setAttribute("aria-selected", String(position === index));
        });
        const current = listbox.children[index];
        input.setAttribute("aria-activedescendant", current.id);
        current.scrollIntoView({ block: "nearest" });
    }

    function choose(index) {
        const { typed, ...entry } = options[index];
        add(entry);
        input.value = "";
        close();
        input.focus();
    }

    function onKey(event) {
        const count = options.length;
        if (event.key === "ArrowDown" && count) {
            event.preventDefault();
            highlight((active + 1) % count);
        } else if (event.key === "ArrowUp" && count) {
            event.preventDefault();
            highlight((active - 1 + count) % count);
        } else if (event.key === "Enter") {
            // Never the whole form from this field: Enter adds the highlighted author.
            event.preventDefault();
            if (active >= 0) {
                choose(active);
            }
        } else if (event.key === "Escape" && count) {
            event.preventDefault();
            close();
        }
    }

    input.addEventListener("input", () => {
        clearTimeout(timer);
        timer = setTimeout(search, DELAY);
    });
    input.addEventListener("keydown", onKey);
    input.addEventListener("blur", close);

    // The first author cited by the reference, to confirm.

    if (proposal) {
        proposal.hidden = entries.length > 0;
        for (const choice of proposal.querySelectorAll("[data-author-choice]")) {
            choice.querySelector("button").addEventListener("click", () => {
                const { id, name, orcid, publications, line } = choice.dataset;
                add(id ? { id: Number(id), name, orcid, publications, line } : { id: null, name, line });
                proposal.hidden = true;
                input.focus();
            });
        }
        proposal.querySelector("[data-author-dismiss] button").addEventListener("click", () => {
            proposal.hidden = true;
            input.focus();
        });
    }

    editor.querySelector("[data-author-lines]").hidden = true;
    rich.hidden = false;
    render();
})();
