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

function readJSONFile(file) {
    if (!file) {
        console.warn('No file selected');
        return;
    }

    const reader = new FileReader();

    reader.onload = function (e) {
        try {
            parsed_input_json = JSON.parse(e.target.result);
        } catch (err) {
            console.error('Error parsing JSON:', err);
        }
    };

    reader.onerror = function (e) {
        console.error('File read error:', e.target.error);
    };

    reader.readAsText(file);
}

function displayList(parsed_json, html_wrapper_id) {
    const html_wrapper = document.getElementById(html_wrapper_id);

    html_wrapper.innerHTML = "";
    while (html_wrapper.lastElementChild) {
        html_wrapper.removeChild(html_wrapper.lastElementChild);
    }

    for (const paper of parsed_json) {
        var div = document.createElement('div');
        const doi = paper.message.DOI;
        const title = paper.message.title[0];
        const date_array = paper.message.created["date-parts"][0];
        div.id = doi;
        div.innerHTML = title + ", " + doi + ", " + date_array[0] + '/' + date_array[1] + '/' + date_array[2];
        html_wrapper.appendChild(div);
    }
}

async function getPaperMetadata(doi) {
    const url = `https://api.crossref.org/works/${doi}`;

    try {
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }

        const data = await response.json();
        return data;
    } catch (error) {
        console.error('There was a problem fetching the paper metadata:', error);
    }
}

async function getPaperMetadataFromDOIList(list) {
    let return_list = [];

    for (const doi of list) {
        return_list.push(await getPaperMetadata(doi));
    }

    return return_list;
}

function citationPlot(papers_list) {
    const plot_svg = document.getElementById("citation_plot_svg");
    const plot_dates_div = document.getElementById("citation_plot_dates");

    resizeToParent(plot_svg);
    plot_svg.parentElement.setAttribute("style", `width: ${plot_svg.clientWidth}px`);
    plot_svg.setAttribute("height", 300);
    const svg_bbox = plot_svg.getBoundingClientRect();
    const max_line_height = 20;

    var years = new Set([]);
    for (const paper of papers_list) {
        years.add(paper.date_parts[0]);
    }

    const min_year = Math.min(...Array.from(years));
    const max_year = Math.max(...Array.from(years));
    for (let i = min_year; i < max_year + 2; i++) {
        years.add(i);
    }

    const years_array = Array.from(years);
    years_array.sort();

    var years_timestamps = [];
    for (const year of years_array) {
        let dateObject = new Date(String(year));
        years_timestamps.push(dateObject.getTime());
    }

    const min_year_timestamp = Math.min(...years_timestamps) - 31536000000 / 2;
    const max_year_timestamp = Math.max(...years_timestamps) + 31536000000 / 2;
    for (let i = 0; i < years_array.length; i++) {
        const year = years_array[i];
        const year_timestamp = years_timestamps[i];

        const line_xpos = (year_timestamp - min_year_timestamp) / (max_year_timestamp - min_year_timestamp) * svg_bbox.width;
        var line_height = max_line_height;
        var line_class = 'date-tick date-tick-';

        if (year % 5) {
            line_height = max_line_height / 2;
            line_class += 1;
        }
        else {
            line_class += 0;
        }

        const line_ypos_1 = svg_bbox.height - line_height;
        const line_ypos_2 = svg_bbox.height;

        plot_svg.appendChild(
            svgLine(
                line_xpos, line_ypos_1,
                line_xpos, line_ypos_2,
                `date-tick-${year}`, line_class
            )
        );

        const year_p = document.createElement('p');
        year_p.innerText = year;

        plot_dates_div.appendChild(year_p);
    }

    const box_size = 20;
    const min_y = box_size;
    const max_y = svg_bbox.height - box_size;
    for (const [i, paper] of papers_list.entries()) {
        const xpos = (paper.timestamp - min_year_timestamp) / (max_year_timestamp - min_year_timestamp) * svg_bbox.width;
        const ypos = min_y + (max_y - min_y) * i / (papers_list.length - 1);

        plot_svg.appendChild(svgCenteredText(i, xpos, ypos, `paper_svg_display_text-${paper.DOI}`, "paper_svg_display_text"));
        plot_svg.appendChild(svgCenteredRect(xpos, ypos, box_size, box_size, `paper_svg_display_rect-${paper.DOI}`, "paper_svg_display_rect"));
    }
}

function svgLine(x1, y1, x2, y2, id, line_class) {
    var line = document.createElementNS('http://www.w3.org/2000/svg', 'line');

    line.setAttribute('x1', x1);
    line.setAttribute('y1', y1);
    line.setAttribute('x2', x2);
    line.setAttribute('y2', y2);
    line.setAttribute('id', id);
    line.setAttribute('class', line_class);

    return line;
}

function svgCenteredText(text, cx, cy, id, text_class) {
    var text_element = document.createElementNS('http://www.w3.org/2000/svg', 'text');

    text_element.setAttribute('x', cx);
    text_element.setAttribute('y', cy);
    text_element.setAttribute('id', id);
    text_element.setAttribute('class', text_class);
    text_element.setAttribute('dominant-baseline', 'middle');
    text_element.setAttribute('text-anchor', 'middle');
    text_element.textContent = text;

    return text_element;
}

function svgCenteredRect(cx, cy, width, height, id, rect_class) {
    var rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');

    rect.setAttribute('x', cx - width / 2);
    rect.setAttribute('y', cy - height / 2);
    rect.setAttribute('width', width);
    rect.setAttribute('height', height);
    rect.setAttribute('id', id);
    rect.setAttribute('class', rect_class);

    return rect;
}

function resizeToParent(element) {
    const parent_width = element.parentElement.clientWidth;
    element.setAttribute("width", parent_width);
}

function indexPapers(crossref_list) {
    for (const paper of crossref_list) {
        var indexed_papers_doi = [];
        for (const paper of indexed_papers_list) {
            indexed_papers_doi.push(paper.DOI);
        }

        if (!indexed_papers_doi.includes(paper.message.DOI)) {
            var references = [];
            for (const ref of paper.message.reference) {
                if ("DOI" in ref) {
                    references.push(ref.DOI);
                }
            }
            indexed_papers_list.push(
                new Paper(
                    paper.message.title[0], paper.message.created["date-time"], paper.message.created["date-parts"][0], paper.message.created.timestamp,
                    paper.message.DOI, paper.message.URL, references
                )
            );
        }
    }
}

async function fetchData(filename) {
    try {
        const response = await fetch(filename);
        if (!response.ok) throw new Error("HTTP error " + response.status);
        const data = await response.json();
        return data;
    } catch (err) {
        console.error("Fetch error:", err);
        return null;
    }
}

let input_file = null;
let parsed_input_json = null;
let indexed_papers_list = [];

document.getElementById('json_file').addEventListener('change', function (event) {
    input_file = event.target.files[0];
    readJSONFile(input_file);
});

document.getElementById('update_visualizer').addEventListener('click', function () {
    main();
});

async function main() {
    input_list = await getPaperMetadataFromDOIList(parsed_input_json);

    indexPapers(input_list);

    let source_list = [];
    for (const paper of indexed_papers_list) {
        for (const ref of paper.ref) {
            source_list.push(ref);
        }
    }
    displayList(input_list, "json_visualizer_input");
    source_list = await getPaperMetadataFromDOIList(source_list);
    displayList(source_list, "json_visualizer_sources");

    indexPapers(source_list);

    citationPlot(indexed_papers_list);
}
async function main2() {
    const input_doi_list = await fetchData('source\\input_papers.json');
    console.log("Input DOI list:", input_doi_list);

    let input_list = await getPaperMetadataFromDOIList(input_doi_list);
    console.log(input_list);
}

window.onload = () => {
    main2();
    console.log("main2()");
};
