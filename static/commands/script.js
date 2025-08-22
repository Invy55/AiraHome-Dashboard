// Build command list
function buildCommandList(commandArray) {
    const commandList = document.getElementById("commandList");
    commandList.innerHTML = ""; // reset if re-used
    commandArray.forEach(command => {
        const li = document.createElement("li");
        li.textContent = command;
        commandList.appendChild(li);
    });
}

// Build form fields
function buildFormFields(fieldArray) {
    const fieldsBox = document.getElementById("fieldsBox");
    fieldsBox.innerHTML = ""; // reset if re-used
    fieldArray.forEach((field, i) => {
        const div = document.createElement("div");
        div.className = "form-group";
        const label = document.createElement("label");
        label.textContent = field["name"].replace(/_/g, " ") + ":";
        label.setAttribute("for", "field" + i);
        const input = document.createElement("input");
        input.type = "text";
        input.id = "field" + i;
        div.appendChild(label);
        div.appendChild(input);
        fieldsBox.appendChild(div);
    });
}

// Dropdown logic
const dropdown = document.getElementById("dropdown");
const commandInput = document.getElementById("commandInput");
let items = [];
let activeIndex = -1;

commandInput.addEventListener("focus", () => {
    dropdown.classList.add("show");
    filterList();
});

commandInput.addEventListener("input", filterList);

// Prevent invalid values: reset if not in list (case-insensitive)
commandInput.addEventListener("blur", () => {
    const val = commandInput.value.trim();
    const commands = items.map(item => item.textContent);
    const match = commands.find(command => command.toLowerCase() === val.toLowerCase());
    if (!match) {
        commandInput.value = "";
    } else {
        commandInput.value = match; // normalize casing
        commandChosen(commandInput.value);
    }
});

function filterList() {
    const filter = commandInput.value.toLowerCase();
    let visibleItems = Array.from(document.querySelectorAll("#commandList li"));
    let anyVisible = false;
    visibleItems.forEach(item => {
        if (item.textContent.toLowerCase().includes(filter)) {
            item.style.display = "";
            anyVisible = true;
        } else {
            item.style.display = "none";
        }
        item.classList.remove("active");
    });
    items = visibleItems; // update global items
    activeIndex = -1;
    if (!anyVisible) dropdown.classList.remove("show");
    else dropdown.classList.add("show");
}

// Item click
document.getElementById("commandList").addEventListener("click", (e) => {
    if (e.target.tagName === "LI") {
        commandInput.value = e.target.textContent;
        dropdown.classList.remove("show");
        commandChosen(commandInput.value);
    }
});

// Keyboard navigation
commandInput.addEventListener("keydown", (e) => {
    const visibleItems = items.filter(item => item.style.display !== "none");
    if (!visibleItems.length) return;

    if (e.key === "ArrowDown") {
        e.preventDefault();
        activeIndex = (activeIndex + 1) % visibleItems.length;
        setActive(visibleItems);
    } else if (e.key === "ArrowUp") {
        e.preventDefault();
        activeIndex = (activeIndex - 1 + visibleItems.length) % visibleItems.length;
        setActive(visibleItems);
    } else if (e.key === "Enter") {
        e.preventDefault();
        if (activeIndex >= 0) {
            commandInput.value = visibleItems[activeIndex].textContent;
        } else {
            commandInput.value = visibleItems[0].textContent;
        }
        dropdown.classList.remove("show");
        commandChosen(commandInput.value);
        
    } else if (e.key === "Escape") {
        dropdown.classList.remove("show");
    }
});

function setActive(visibleItems) {
    visibleItems.forEach(item => item.classList.remove("active"));
    if (activeIndex >= 0) {
        visibleItems[activeIndex].classList.add("active");
    }
}

document.addEventListener("click", (e) => {
    if (!dropdown.contains(e.target)) {
        dropdown.classList.remove("show");
    }
});

// Send button
function sendAction() {
    const command = commandInput.value.trim();
    const urlParams = new URLSearchParams(window.location.search);
    const heatpump_id = urlParams.get("heatpump_id");

    if (!command || !heatpump_id) {
        console.error("Command or heatpump_id is missing.");
        return;
    }

    const fieldsBox = document.getElementById("fieldsBox");
    const inputs = fieldsBox.querySelectorAll("input");
    const fieldValues = {};
    inputs.forEach((input, i) => {
        const label = fieldsBox.querySelector(`label[for="${input.id}"]`);
        if (label) {
            const fieldName = label.textContent.slice(0, -1).replace(/ /g, "_"); // remove colon and replace spaces
            fieldValues[fieldName] = input.value.trim();
        }
    });

    // Construct query string from fieldValues
    fieldValues["heatpump_id"] = heatpump_id; // add heatpump_id to params
    const queryParams = new URLSearchParams(fieldValues).toString();
    const url = `../api/command/${encodeURIComponent(command)}?${queryParams}`;

    // Send GET request
    fetch(url)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log("Ping command response:", data);
            streamResponse(data);
        })
        .catch(error => {
            console.error("Error fetching Ping command:", error);
        });

    console.log("Sending command:", command, "with fields:", fieldValues, "and heatpump_id:", heatpump_id);
}

function streamResponse(data) {
    const command_id = data["command_id"]["value"];
    const queryParams = new URLSearchParams({"command_id": command_id}).toString();
    const url = `../api/progress/?${queryParams}`;
    const outputBox = document.getElementById("outputBox");

    // Clear the output box before streaming
    outputBox.textContent = "";

    fetch(url)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            const reader = response.body.getReader();
            const decoder = new TextDecoder("utf-8");

            function readStream() {
                reader.read().then(({ done, value }) => {
                    if (done) {
                        console.log("Stream ended.");
                        lastCommand = ""; // reset lastCommand to allow re-selection
                        return;
                    }
                    const text = decoder.decode(value);
                    outputBox.textContent += processOutput(text); // Append streamed text to the output box
                    
                    // Auto-scroll to the bottom
                    outputBox.scrollTop = outputBox.scrollHeight;

                    readStream(); // Continue reading the stream
                }).catch(error => {
                    console.error("Error reading stream:", error);
                });
            }

            readStream(); // Start reading the stream
        })
        .catch(error => {
            console.error("Error fetching stream response:", error);
        });
}

let processedLines = new Set(); // Use a Set to track unique lines

function processOutput(output) {
    const lines = output.split("\n"); // Split the output into individual lines
    let newLines = "";

    lines.forEach(line => {
        if (!processedLines.has(line) && line) { // Check if the line has already been processed
            processedLines.add(line); // Add the line to the Set
            let linejson;
            let outline;
            let cleanedjson;
            try {
                console.log("Processing line:", line);
                linejson = JSON.parse(line.trim())["command_progress"];
                if (linejson.hasOwnProperty("time")) {
                    cleanedjson = { ...linejson };
                    console.log("Cleaning JSON:", cleanedjson);
                    delete cleanedjson["time"];
                    delete cleanedjson["command_id"];
                    delete cleanedjson["aws_iot_received_time"];
                    console.log("Cleaned JSON:", cleanedjson);
                    outline = `${linejson["time"]}: ${JSON.stringify(cleanedjson)}`;
                    console.log("Outline with time:", outline);
                } else {
                    if (linejson.hasOwnProperty("command_id")) {
                        delete linejson["command_id"];
                    }
                    outline = JSON.stringify(linejson);
                }
            } catch (e) {
                // Not JSON, keep original line
                console.error("Error parsing line as JSON:", e);
            }
            newLines += `${outline}\n\n`; // Append the new line using template literals
        }
    });

    return newLines; // Return only the new lines
}

// Obtain command list from api
function getCommands() {
    fetch("../api/get_commands")
        .then(response => response.json())
        .then(data => {
            buildCommandList(data["commands"]);	
            items = Array.from(document.querySelectorAll("#commandList li")); // update items
        })
        .catch(error => console.error("Error fetching commands:", error));
}

// Obtain fields for a command from api
function getFields(command) {
    if (!command) {
        buildFormFields([]); // clear fields if no command
        return;
    }
    fetch("../api/get_command_fields/" + encodeURIComponent(command))
        .then(response => response.json())
        .then(data => {
            buildFormFields(data["fields"]);
        })
        .catch(error => console.error("Error fetching fields:", error));
}

var lastCommand = "";

function commandChosen(command) {
    if (command === lastCommand) return; // ignore if already chosen
    lastCommand = command; // store the last chosen command
    getFields(command); // fetch fields for the selected command
    console.log("Command chosen:", command);
    document.getElementById("sendButton").focus()
}

// Run builders on page load
window.addEventListener("load", () => {
    getCommands();
    //buildFormFields(fields);
    items = Array.from(document.querySelectorAll("#commandList li")); // update items

    // Clear search input on soft reload
    commandInput.value = "";

    // done -> tell grafana
    window.parent.postMessage({ action: window.location.href, value: 1 }, document.referrer);
});
