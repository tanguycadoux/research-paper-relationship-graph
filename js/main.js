function sendDOIData() {
    const doiData = [
        "10.1109/TASC.2023.3260779"
    ];

    fetch('http://localhost:8000/data', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(doiData)
    })
    .then(res => res.json())
    .then(response => {
        console.log("Server response:", response);
    })
    .catch(err => {
        console.error("Error sending data:", err);
    });
}

window.onload = () => {
    sendDOIData();
};
