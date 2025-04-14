class Reference {
    constructor(title, date_parts, DOI, URL, ref, xCenter = 0, yCenter = 0, index = 0, size = 0) {
        this.title = title;
        this.date_parts = date_parts;
        this.DOI = DOI;
        this.URL = URL;
        this.ref = ref;
    }

    render(group) {
        var rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        var text = document.createElementNS('http://www.w3.org/2000/svg', 'text');

        rect.setAttribute('x', this.xCenter - this.size / 2);
        rect.setAttribute('y', this.yCenter - this.size / 2);
        rect.setAttribute('width', this.size);
        rect.setAttribute('height', this.size);
        rect.setAttribute('class', 'paper_svg_display_rect');


        text.setAttribute('x', this.xCenter);
        text.setAttribute('y', this.yCenter);
        text.setAttribute('dominant-baseline', 'middle');
        text.setAttribute('text-anchor', 'middle');
        text.textContent = this.index;

        group.appendChild(rect);
        group.appendChild(text);
        
    }
}

class Tick {
    constructor(value, position = 0, length = 100, level = 0) {
        this.value = value;
        this.position = position;
        this.length = length;
        this.level = level;
    }

    render(group) {
        var line = document.createElementNS('http://www.w3.org/2000/svg', 'line');

        line.setAttribute('x1', this.position);
        line.setAttribute('y1', 0);
        line.setAttribute('x2', this.position);
        line.setAttribute('y2', this.length * (1 - this.level / 2));
        line.setAttribute('class', `date-tick date-tick-${this.level}`)

        group.appendChild(line);

        if (this.level == 0) {
            var text = document.createElementNS('http://www.w3.org/2000/svg', 'text');

            text.setAttribute('x', this.position);
            text.setAttribute('y', this.length + 5);
            text.setAttribute('dominant-baseline', 'hanging');
            text.setAttribute('text-anchor', 'middle');
            text.textContent = this.value;

            group.appendChild(text);
        }
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

async function removeDOI(doi) {
    for (let i = 0; i < userInputDOIList.length; i++) {
        if (doi == userInputDOIList[i]) {
            userInputDOIList.splice(i, 1);
        }
    }
    await updateDOI();
    drawSVG();
}

async function addDOI(doi) {
    if (doi === undefined) {
        doi = HTMLDOIInput.value.toLowerCase();
    }
    if (!(userInputDOIList.includes(doi))) {
        userInputDOIList.push(doi);
    }
    await updateDOI();
    drawSVG();
}

async function updateDOI() {
    HTMLDOIInput.style.borderColor = "black";

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

    references = [];
    var allDOIList = [...new Set([...userInputDOIList, ...referencesList])];
    for (const doi of allDOIList) {
        for (const entry of crossrefData) {
            const m = entry.message;
            if (m.DOI == doi) {
                references.push(
                    new Reference(
                        m.title[0], m.published["date-parts"][0],
                        m.DOI, m.URL, m.reference
                    )
                );
            }
        }
    }

    clearHTMLContent(HTMLInput);
    clearHTMLContent(HTMLReferences);
    for (const [index, paper] of references.entries()) {
        var li = document.createElement('li');
        var input = document.createElement('input');
        var p = document.createElement('p');

        input.type = 'button';
        p.innerText = `[${index}] ${paper.title} (${paper.DOI})`;

        li.appendChild(input);
        li.appendChild(p);
        if (userInputDOIList.includes(paper.DOI)) {
            input.value = '-';
            input.onclick = () => {
                removeDOI(paper.DOI);
            };
            HTMLInput.appendChild(li);
        } else {
            input.value = '+';
            input.onclick = () => {
                addDOI(paper.DOI);
            };
            HTMLReferences.appendChild(li);
        }
    }
}

function drawTimescale(width) {
    const tickHeight = 20;

    var years = new Set();
    for (const paper of references) {
        years.add(paper.date_parts[0]);
    }

    const minYear = Math.min(...Array.from(years));
    const maxYear = Math.max(...Array.from(years));
    for (let i = minYear; i < maxYear + 2; i++) {
        years.add(i);
    }

    const yearsArray = Array.from(years);
    yearsArray.sort();

    var ticks = [];
    const year_in_ms = 31536000000;
    const minYearTimestamp = new Date(String(Math.min(...yearsArray))).getTime() - year_in_ms / 2;
    const maxYearTimestamp = new Date(String(Math.max(...yearsArray))).getTime() + year_in_ms / 2;
    for (const year of yearsArray) {
        var level = 0;
        if (year % 5) {
            level = 1;
        }

        const yearTimestamp = new Date(String(year)).getTime();
        const xPos = (yearTimestamp - minYearTimestamp) / (maxYearTimestamp - minYearTimestamp) * width;
        ticks.push(new Tick(year, xPos, tickHeight, level));
    }

    clearHTMLContent(svgTimescaleGroup);
    for (const tick of ticks) {
        tick.render(svgTimescaleGroup);
    }

    return [minYearTimestamp, maxYearTimestamp];
}

function drawReferences(timestampMin, timestampMax) {
    const boxSize = 20;
    const groupHeight = boxSize + boxSize * references.length;
    const svgWidth = svgTimescaleGroup.getBoundingClientRect().width;
    const minYCenter = boxSize;
    const maxYCenter = groupHeight - boxSize;

    clearHTMLContent(svgReferencesGroup);
    for (const [i, ref] of references.entries()) {
        const [year, month = 1, day = 1] = ref.date_parts;
        const date = new Date(year, month - 1, day);
        const timestamp = date.getTime();

        ref.xCenter = (timestamp - timestampMin) / (timestampMax - timestampMin) * svgWidth;
        ref.yCenter = minYCenter + (maxYCenter - minYCenter) * i / (references.length - 1);
        ref.index = i;
        ref.size = boxSize;
        ref.render(svgReferencesGroup);
    }

    return groupHeight;
}

function drawSVG() {
    let timestampMinMax = drawTimescale(svgCanvas.getBoundingClientRect().width);
    let referencesGroupHeight = drawReferences(timestampMinMax[0], timestampMinMax[1]);

    let timescaleGroupHeight = svgTimescaleGroup.getBoundingClientRect().height;

    svgCanvas.setAttribute("height", referencesGroupHeight + timescaleGroupHeight);
    svgTimescaleGroup.setAttribute("transform", `translate(0, ${referencesGroupHeight})`);
}

var userInputDOIList = [];
var references = [];

const HTMLDOIInput = document.getElementById("doiInput");
const HTMLInput = document.getElementById("json_visualizer_input");
const HTMLReferences = document.getElementById("json_visualizer_references");
const svgCanvas = document.getElementById("citation_plot_svg");
const svgTimescaleGroup = document.getElementById("timescale");
const svgReferencesGroup = document.getElementById("references_points");
