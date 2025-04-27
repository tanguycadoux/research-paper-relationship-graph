class Reference {
    constructor(title, date_parts, DOI, URL, ref, xCenter = 0, yCenter = 0, index = 0, size = 0) {
        this.title = title;
        this.date_parts = date_parts;
        this.DOI = DOI;
        this.URL = URL;
        this.ref = ref;

        const [year, month = 1, day = 1] = this.date_parts;
        const date = new Date(year, month - 1, day);
        this.timestamp = date.getTime();
    }

    renderBox(group) {
        var rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        var text = document.createElementNS('http://www.w3.org/2000/svg', 'text');

        rect.setAttribute('x', this.xCenter - this.size / 2);
        rect.setAttribute('y', this.yCenter - this.size / 2);
        rect.setAttribute('rx', 5);
        rect.setAttribute('ry', 5);
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

    renderLine(group, height) {
        var line = document.createElementNS('http://www.w3.org/2000/svg', 'line');

        line.setAttribute('x1', this.xCenter);
        line.setAttribute('y1', this.yCenter + this.size / 2);
        line.setAttribute('x2', this.xCenter);
        line.setAttribute('y2', height);
        line.setAttribute('class', 'paper_svg_display_line')

        group.appendChild(line);
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
        line.setAttribute('class', `date-tick date-tick-${this.level}`);

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
        var input_add_remove = document.createElement('input');
        var input_checkbox = document.createElement('input');
        var p_title = document.createElement('p');
        var p_doi = document.createElement('p');
        var p_id = document.createElement('p');
        var label = document.createElement('label');

        input_add_remove.type = 'button';

        p_id.innerText = `[${index}]`;

        p_title.innerText = `${paper.title}`;

        p_doi.innerText = `DOI: ${paper.DOI}`;
        p_doi.className = "doi_text_render";

        input_checkbox.type = 'checkbox';
        input_checkbox.className = "hidden_checkbox";
        input_checkbox.id = `checkbox_${paper.DOI}`;

        label.htmlFor = `checkbox_${paper.DOI}`;
        label.className = "reference_text_render";
        label.id = `user_reference_${paper.DOI}`;

        label.appendChild(p_id);
        label.appendChild(p_title);
        label.appendChild(p_doi);

        li.appendChild(input_add_remove);
        li.appendChild(input_checkbox);
        li.appendChild(label);

        if (userInputDOIList.includes(paper.DOI)) {
            input_add_remove.value = '-';
            input_add_remove.className = 'remove_button';
            input_add_remove.onclick = () => {
                removeDOI(paper.DOI);
            };
            HTMLInput.appendChild(li);
            label.onclick = () => {
                let selected_source_divider = document.getElementById("selected_source_divider");
                let user_sources_divider = document.getElementById("user_sources_divider");

                selected_source_divider.style.display = "block";
                user_sources_divider.style.gridColumn = "1";
            };
        } else {
            input_add_remove.value = '+';
            input_add_remove.className = 'add_button';
            input_add_remove.onclick = () => {
                addDOI(paper.DOI);
            };
            HTMLReferences.appendChild(li);
        }
    }
}

function drawTimescale() {
    const tickHeight = 20;
    const width = svgCanvas.getBoundingClientRect().width;

    const xCenterList = references.map(ref => ref.xCenter);
    const minXCenter = Math.min(...xCenterList);
    const maxXCenter = Math.max(...xCenterList);
    const timestampList = references.map(ref => ref.timestamp);
    const minTimestamp = Math.min(...timestampList);
    const maxTimestamp = Math.max(...timestampList);
    const minTimestampBorder = mapTo(0, minXCenter, maxXCenter, minTimestamp, maxTimestamp);
    const maxTimestampBorder = mapTo(width, minXCenter, maxXCenter, minTimestamp, maxTimestamp);
    const minTickYear = new Date(minTimestampBorder).getFullYear() + 1;
    const maxTickYear = new Date(maxTimestampBorder).getFullYear();

    var tickYears = [];
    for (let i = minTickYear; i < maxTickYear + 1; i++) {
        tickYears.push(i);
    }

    var ticks = [];
    const minYearTimestamp = new Date(String(Math.min(...tickYears))).getTime();
    const maxYearTimestamp = new Date(String(Math.max(...tickYears))).getTime();
    for (const year of tickYears) {
        var level = 0;
        if (year % 5) {
            level = 1;
        }

        const yearTimestamp = new Date(String(year)).getTime();
        const xPos = mapTo(yearTimestamp, minTimestampBorder, maxTimestampBorder, 0, width);
        ticks.push(new Tick(year, xPos, tickHeight, level));
    }

    clearHTMLContent(svgTimescaleGroup);
    
    var line = document.createElementNS('http://www.w3.org/2000/svg', 'line');

    line.setAttribute('x1', 0);
    line.setAttribute('y1', 0);
    line.setAttribute('x2', width);
    line.setAttribute('y2', 0);
    line.setAttribute('class', 'timescale-horizontal-line');

    svgTimescaleGroup.appendChild(line);

    for (const tick of ticks) {
        tick.render(svgTimescaleGroup);
    }

    return [minYearTimestamp, maxYearTimestamp];
}

function drawReferences() {
    const boxSize = 25;
    const pad = 5;
    const nbRef = references.length;
    const groupHeight = 2 * pad + boxSize * nbRef + pad * (nbRef - 1);
    const minYCenter = pad + boxSize / 2;
    const maxYCenter = groupHeight - (pad + boxSize / 2);

    svgCanvas.setAttribute("width", svgCanvas.parentElement.clientWidth);
    const svgWidth = svgCanvas.getBoundingClientRect().width;

    const timestampList = references.map(ref => ref.timestamp);
    const minTimestamp = Math.min(...timestampList);
    const maxTimestamp = Math.max(...timestampList);
    const minXCenter = pad + boxSize / 2;
    const maxXCenter = svgWidth - (pad + boxSize / 2);
    clearHTMLContent(svgReferencesGroup);
    for (const [i, ref] of references.entries()) {
        ref.xCenter = mapTo(ref.timestamp, minTimestamp, maxTimestamp, minXCenter, maxXCenter);
        ref.yCenter = minYCenter + (maxYCenter - minYCenter) * i / (nbRef - 1);
        ref.index = i;
        ref.size = boxSize;
        ref.renderLine(svgReferencesGroup, groupHeight);
    }
    for (const ref of references) {
        ref.renderBox(svgReferencesGroup);
    }

    return groupHeight;
}

function drawSVG() {
    let referencesGroupHeight = drawReferences();
    drawTimescale();

    let timescaleGroupHeight = svgTimescaleGroup.getBoundingClientRect().height;

    svgCanvas.setAttribute("height", referencesGroupHeight + timescaleGroupHeight);
    svgTimescaleGroup.setAttribute("transform", `translate(0, ${referencesGroupHeight})`);
}

function mapTo(number, inMin, inMax, outMin, outMax) {
    return (number - inMin) * (outMax - outMin) / (inMax - inMin) + outMin;
}

var userInputDOIList = [];
var references = [];

const HTMLDOIInput = document.getElementById("doiInput");
const HTMLInput = document.getElementById("json_visualizer_input");
const HTMLReferences = document.getElementById("json_visualizer_references");
const svgCanvas = document.getElementById("citation_plot_svg");
const svgTimescaleGroup = document.getElementById("timescale");
const svgReferencesGroup = document.getElementById("references_points");
