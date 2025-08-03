
const params = new URLSearchParams(window.location.search);
const pubId = params.get("id");

if (pubId) {
    fetch(`/get_publication?id=${pubId}`)
    .then(res => res.json())
    .then(data => renderPublication(data));
}

function renderPublication(data) {
    let titleNode = document.getElementById("publication_title");
    let dateNode = document.getElementById("publication_date");
    let DOINode = document.getElementById("publication_doi");
    let authorsNode = document.getElementById("publication_authors");

    let isoDate = data.published
    let humanReadable;
    if (/^\d{4}$/.test(isoDate)) {
        // Year only
        humanReadable = isoDate;
    } else if (/^\d{4}-\d{2}$/.test(isoDate)) {
        // Year and month
        const date = new Date(isoDate);
        humanReadable = date.toLocaleDateString(undefined, {
            year: 'numeric',
            month: 'long'
        });
    } else if (/^\d{4}-\d{2}-\d{2}$/.test(isoDate)) {
        // Full date
        const date = new Date(isoDate);
        humanReadable = date.toLocaleDateString(undefined, {
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        });
    } else {
        // Fallback for invalid format
        humanReadable = isoDate;
    }

    titleNode.innerText = data.title;
    dateNode.dateTime = data.published;
    dateNode.innerText = humanReadable;
    DOINode.innerText = data.doi;
    authorsNode.innerText = data.authors.join(', ');
}
