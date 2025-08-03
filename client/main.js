window.onload = async (event) => {
    await updateRenderPublicationsList();
}

function clearHTMLContent(nodeDOM) {
    nodeDOM.innerHTML = "";
    while (nodeDOM.lastElementChild) {
        nodeDOM.removeChild(html_wrapper.lastElementChild);
    }
}

async function addDOI(doi) {
    doi = document.getElementById('doi_input').value.toLowerCase();

    const response = await fetch('/add_publication', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            'doi': doi
        })
    });

    await updateRenderPublicationsList();
}

async function getPublications() {
    try {
        const res = await fetch('/get_publications');
        const data = await res.json();
        return data;
    } catch (err) {
        console.error('Error fetching publications:', err);
        return [];
    }
}

async function updateRenderPublicationsList() {
    const publications = await getPublications();

    let publications_list = document.getElementById('publications_list');

    clearHTMLContent(publications_list);

    for (const publication of publications) {
        let list_entry = document.createElement('li');
        let anchor = document.createElement('a');

        anchor.innerText = publication.title;
        anchor.href = "/publication.html?id=" + publication.id;

        list_entry.appendChild(anchor);
        publications_list.appendChild(list_entry);
    }
}
