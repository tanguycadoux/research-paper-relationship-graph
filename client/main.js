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

    renderPublicationsTable(publications, publicationsTable);
    renderPublicationsTable(references,   referencesTable);
}

function renderPublicationsTable(publications, table){
    console.log(table)
    clearHTMLContent(table);

    // Table definition
    let tableHeader = document.createElement('thead');
    let tableBody   = document.createElement('tbody');

    table.appendChild(tableHeader);
    table.appendChild(tableBody);

    // Header
    let headRow      = document.createElement('tr');
    let headInfoCol  = document.createElement('th');
    let headTitleCol = document.createElement('th');
    let headDOICol   = document.createElement('th');
    let headDateCol  = document.createElement('th');

    headTitleCol.innerText = "Title";
    headDOICol.innerText   = "DOI";
    headDateCol.innerText  = "Date";

    headRow.appendChild(headInfoCol);
    headRow.appendChild(headTitleCol);
    headRow.appendChild(headDOICol);
    headRow.appendChild(headDateCol);
    tableHeader.appendChild(headRow);

    for (const pub of publications) {
        let anchor = document.createElement('a');

        let row       = document.createElement('tr');
        let infoCell  = document.createElement('td');
        let titleCell = document.createElement('td');
        let DOICell   = document.createElement('td');
        let dateCell  = document.createElement('td');

        row.appendChild(infoCell);
        row.appendChild(titleCell);
        row.appendChild(DOICell);
        row.appendChild(dateCell);
        
        if (pub.title != null) {
            anchor.innerText = pub.title;
            anchor.href = "/publication.html?id=" + pub.id;
            titleCell.appendChild(anchor);
        }
        if (pub.doi == null) {
            infoCell.innerText = "/!\\";
        }
        else{
            infoCell.innerText = "+";
            DOICell.innerHTML = pub.doi;
        }
        if (pub.published != null) {
            dateCell.innerHTML = pub.published;
        }
        
        tableBody.appendChild(row);
    }
}


const publicationsTable = document.getElementById('publications_table');
const referencesTable   = document.getElementById('references_table');

window.onload = async (event) => {
    await updatePublicationsAndReferencesList();
}
