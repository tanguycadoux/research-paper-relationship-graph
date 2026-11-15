// Progress of the requests in the queue (#379): the toast asks every 2.5 s how many of
// the user's publications are fetched, and says when it is over; the page of a
// publication or of an author (#380) still to fetch reloads once its data is there.
// Without this script, a reload by hand shows the same state.
(function () {
    "use strict";

    const INTERVAL = 2500;
    const DONE_DELAY = 6000;
    const toast = document.querySelector("[data-fetch-progress-toast]");
    const pending = document.querySelector(
        "[data-fetch-pending-publication], [data-fetch-pending-author]",
    );
    if (!toast && !pending) {
        return;
    }
    const url = (toast || pending).dataset.fetchProgress;
    let since = toast ? toast.dataset.fetchSince : "";

    function query() {
        const params = new URLSearchParams();
        if (since) {
            params.set("since", since);
        }
        if (pending && pending.dataset.fetchPendingPublication) {
            params.set("publication", pending.dataset.fetchPendingPublication);
        }
        if (pending && pending.dataset.fetchPendingAuthor) {
            params.set("author", pending.dataset.fetchPendingAuthor);
        }
        return `${url}?${params}`;
    }

    function show(state) {
        if (!toast) {
            return;
        }
        if (state.text) {
            toast.querySelector("[data-fetch-progress-text]").textContent = state.text;
        }
        since = state.since || since;
        if (!state.active) {
            toast.querySelector("svg").classList.remove("motion-safe:animate-spin");
            setTimeout(() => toast.remove(), DONE_DELAY);
        }
    }

    const timer = setInterval(async () => {
        try {
            const response = await fetch(query(), { headers: { Accept: "application/json" } });
            const state = await response.json();
            if (pending && (state.publication_pending === false || state.author_pending === false)) {
                clearInterval(timer);
                window.location.reload();
                return;
            }
            show(state);
            if (!state.active && !pending) {
                clearInterval(timer);
            }
        } catch {
            // The server may restart: ask again at the next tick.
        }
    }, INTERVAL);
})();
