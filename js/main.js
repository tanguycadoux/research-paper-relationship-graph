class Paper {
    constructor(title, datetime, date_parts, timestamp, DOI, URL, ref) {
        this.title = title;
        this.datetime = datetime;
        this.date_parts = date_parts;
        this.timestamp = timestamp;
        this.DOI = DOI;
        this.URL = URL;
        this.ref = ref;
    }
}

async function fetchDOIData(doiList) {
    try {
        const response = await fetch('http://localhost:8000/data', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(userInputDOIList)
        });

        const data = await response.json();

        if (data.status === "success") {
            let fetchReferencesList = data.references_list;
            let fetchCrossrefData = data.crossref_data;
            let fetchEntriesErrors = data.crossref_errors;

            console.log(data);

            return data;
        } else {
            console.error("Server returned error status:", data);
            return null;
        }
    }
    catch (err) {
        console.error("Error sending data:", err);
        return null;
    }
}

function clearHTMLContent(nodeDOM) {
    nodeDOM.innerHTML = "";
    while (nodeDOM.lastElementChild) {
        nodeDOM.removeChild(html_wrapper.lastElementChild);
    }
}

async function addDOI() {
    const addedDOI = HTMLDOIInput.value.toLowerCase();
    HTMLDOIInput.style.borderColor = "black";

    if (userInputDOIList.includes(addedDOI)) {
        console.log(`DOI ${addedDOI} already present`);
    } else {
        console.log("Adding DOI:", addedDOI);
        userInputDOIList.push(addedDOI);
    }
    console.log("DOI list:", userInputDOIList);

    var response = await fetchDOIData(userInputDOIList);
    var referencesList = response.references_list;
    var crossrefData = response.crossref_data;
    var crossrefErrors = response.crossref_errors;

    for (const error of crossrefErrors) {
        if (error.DOI == HTMLDOIInput.value.toLowerCase()) {
            HTMLDOIInput.style.borderColor = "red";
            for (let i = 0; i < userInputDOIList.length; i++) {
                if (error.DOI == userInputDOIList[i]) {
                    userInputDOIList.splice(i, 1);
                }
            }
        }
    }

    var allDOIList = [...new Set([...userInputDOIList, ...referencesList])];
    for (const doi of allDOIList) {
        for (const entry of crossrefData) {
            const m = entry.message;
            if (m.DOI == doi) {
                papers.push(
                    new Paper(
                        m.title[0], m.created["date-time"], m.created["date-parts"], m.created.timestamp,
                        m.DOI, m.URL, m.reference
                    )
                );
            }
        }
    }

    clearHTMLContent(HTMLInput);
    clearHTMLContent(HTMLReferences);
    for (const [index, paper] of papers.entries()) {
        var li = document.createElement('li');
        li.innerText = `[${index}] ${paper.title} (${paper.DOI})`;
        if (userInputDOIList.includes(paper.DOI)) {
            HTMLInput.appendChild(li);
        } else {
            HTMLReferences.appendChild(li);
        }
    }
}

var userInputDOIList = [];
var papers = [];

const HTMLDOIInput = document.getElementById("doiInput");
const HTMLInput = document.getElementById("json_visualizer_input");
const HTMLReferences = document.getElementById("json_visualizer_references");
