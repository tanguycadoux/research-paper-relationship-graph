// The image of a large graph is computed in the background (#328): the page asks every
// 2 s whether it is ready, and reloads once, then, to offer it. Without this script,
// a reload by hand does the same.
(function () {
    "use strict";

    const status = document.querySelector("[data-graph-image-status]");
    if (!status) {
        return;
    }
    const url = status.dataset.graphImageStatus;
    const timer = setInterval(async () => {
        try {
            const response = await fetch(url, { headers: { Accept: "application/json" } });
            const state = await response.json();
            if (!state.pending) {
                clearInterval(timer);
                window.location.reload();
            }
        } catch {
            // The server may restart: ask again at the next tick.
        }
    }, 2000);
})();
