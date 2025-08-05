window.onload = async (event) => {
    await updatePublicationsAndReferencesList();
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

    await updatePublicationsAndReferencesList();
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

async function getReferences() {
    try {
        const res = await fetch('/get_references');
        const data = await res.json();
        return data;
    } catch (err) {
        console.error('Error fetching publications:', err);
        return [];
    }
}

async function updatePublicationsAndReferencesList() {
    const publications = await getPublications();
    const references = await getReferences();

    let publications_list = document.getElementById('publications_list');
    let references_list = document.getElementById('references_list');

    console.log(references)

    clearHTMLContent(publications_list);
    clearHTMLContent(references_list);

    for (const publication of publications) {
        let listEntry = document.createElement('li');
        let anchor = document.createElement('a');

        let pubTitle = "Missing title";
        let pubDOI = "Missing DOI";

        if (publication.title != null) {
            pubTitle = publication.title;
        }
        if (publication.doi != null) {
            pubDOI = publication.doi;
        }
        anchor.innerText = pubTitle + ' - ' + pubDOI;
        anchor.href = "/publication.html?id=" + publication.id;

        listEntry.appendChild(anchor);
        publications_list.appendChild(listEntry);
    }
    for (const ref of references) {
        let list_entry = document.createElement('li');
        let anchor = document.createElement('a');

        let refTitle = "Missing title";
        let refDOI = "Missing DOI";

        if (ref.title != null) {
            refTitle = ref.title;
        }
        if (ref.doi != null) {
            refDOI = ref.doi;
        }
        anchor.innerText = refTitle + ' - ' + refDOI;
        anchor.href = "/publication.html?id=" + ref.id;

        list_entry.appendChild(anchor);
        references_list.appendChild(list_entry);
    }
}
