async function fetchDOIData(doiList) {
    try {
        const response = await fetch('http://localhost:8000/data', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(doiData)
        });

        const data = await response.json();

        if (data.status === "success") {
            let fetchInputList = data.input_list;
            let fetchReferencesList = data.references_list;
            let fetchCrossrefData = data.crossref_data;

            console.log(data);

            return [fetchInputList, fetchReferencesList, fetchCrossrefData];
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

async function main() {
    var response = await fetchDOIData(doiData);
    var inputList = response[0];
    var referencesList = response[1];
    var crossrefData = response[2];

    for (const input of inputList) {
        var li = document.createElement('li');
        li.innerText = input;
        HTMLInput.appendChild(li);
    }

    for (const ref of referencesList) {
        var li = document.createElement('li');
        li.innerText = ref;
        HTMLReferences.appendChild(li);
    }

    console.log(crossrefData);
}

var doiData = [
    "10.1109/TASC.2023.3260779"
];

const HTMLInput = document.getElementById("json_visualizer_input");
const HTMLReferences = document.getElementById("json_visualizer_references");

window.onload = () => {
    main();
};
