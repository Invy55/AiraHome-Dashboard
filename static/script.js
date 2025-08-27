// load the SVG view
let view;
window.addEventListener('load', function() {
    svg = document.getElementById('view');
    view = svg.getSVGDocument();
    if (view) {
        // Create a <style> element
        const styleElement = document.createElement('style');
        styleElement.textContent = `
            @import url('styles.css');
        `;

        // Append the <style> element to the <svg> root
        view.documentElement.appendChild(styleElement);
        console.log('CSS imported into the SVG.');
    } else {
        console.error('Failed to load the SVG document.');
    }

    // Initial setup: hide all dynamic elements
    // - Hide battery low indicators by default
    showObject('zone_1_low_battery', false);
    showObject('zone_2_low_battery', false);
    // - Hide all zones by default
    showObject('zone_1', false);
    showObject('zone_2', false);
    showObject('zone', false);
    // - Hide all zone pipes by default
    showObject('zone_1_delivery', false);
    showObject('zone_1_return', false);
    showObject('zone_2_delivery', false);
    showObject('zone_2_return', false);
    showObject('zone_delivery', false);
    showObject('zone_return', false);
    // - Hide cold/hot indicators by default
    showObject('zone_1_cold', false);
    showObject('zone_1_hot', false);
    showObject('zone_2_cold', false);
    showObject('zone_2_hot', false);
    showObject('zone_cold', false);
    showObject('zone_hot', false);
    // - Hide online and error status by default
    showObject('online_status', false);
    showObject('error_status', false);

    // Load data from GET data param
    let params, data;
    try {
        params = new URLSearchParams(document.location.search);
        data = JSON.parse(params.get("data") ? params.get("data") : "{}")
        if (!data || Object.keys(data).length == 0 || params.get("data") === "{\"\":{}}") {
            console.warn('No data provided in the URL parameters.');
            // done -> tell grafana
            window.parent.postMessage({ action: window.location.href, value: 1 }, document.referrer);
            return;
        }
        console.log('Data loaded from URL parameters:', data);
    } catch (error) {
        console.error('Error parsing data from URL parameters:', error);
        // done -> tell grafana
        window.parent.postMessage({ action: window.location.href, value: 1 }, document.referrer);
        return;
    }

    // Update SVG elements based on the data
    addPulse('online_status');
    // Heatpump active state, allowed states:
    //   PUMP_ACTIVE_STATE_UNSPECIFIED
    //   PUMP_ACTIVE_STATE_IDLE
    //   PUMP_ACTIVE_STATE_HEATING
    //   PUMP_ACTIVE_STATE_COOLING
    //   PUMP_ACTIVE_STATE_DHW
    //   PUMP_ACTIVE_STATE_ANTI_LEGIONELLA
    //   PUMP_ACTIVE_STATE_DEFROSTING
    switch (data['heat_pump']['pump_active_state']) {
        case "PUMP_ACTIVE_STATE_UNSPECIFIED":
        case "PUMP_ACTIVE_STATE_IDLE":
            // case heatpump is idle
            // everithing is default
            break;
        case "PUMP_ACTIVE_STATE_HEATING":
            // case heatpump is heating
            setPipeColor('heatpump_delivery', 'hot');
            setPipeColor('heatpump_return', 'cold');
            spinHeatpumpBlades(true);
            break;
        case "PUMP_ACTIVE_STATE_COOLING":
            // case heatpump is cooling
            setPipeColor('heatpump_delivery', 'cold');
            setPipeColor('heatpump_return', 'hot');
            spinHeatpumpBlades(true);
            break;
        case "PUMP_ACTIVE_STATE_DHW":
            // case heatpump is heating water
            setPipeColor('heatpump_delivery', 'hot');
            setPipeColor('heatpump_return', 'cold');
            spinHeatpumpBlades(true);
            setPipeColor('water_heater_delivery', 'hot');
            setPipeColor('water_heater_return', 'cold');
            setActive('water_heater_hot', true);
            break;

        default:
            break;
    }

    // Update temperatures
    updateSVGText('outside_temperature', data['heat_pump']['current_outdoor_temperature'] || '--');
    updateSVGText('water_heater_cur_temperature', data['water_heater']['current_hot_water_temperature'] || '--');
    updateSVGText('water_heater_tar_temperature', data['water_heater']['target_hot_water_temperature'] || '--');
    // Zone detection (single or dual)
    // if thermostat_2 exists, we have two zones
    let zones = ["zone"];
    if (data.hasOwnProperty("thermostat_2")) {
        // two zones
        showObject('zone_1', true);
        showObject('zone_2', true);
        showObject('zone_1_delivery', true);
        showObject('zone_1_return', true);
        showObject('zone_2_delivery', true);
        showObject('zone_2_return', true);
        zones = ["zone_1", "zone_2"];
    } else {
        // single zone
        showObject('zone', true);
        showObject('zone_delivery', true);
        showObject('zone_return', true);
    }
    // Update zone data
    zones.forEach(zone => {
        let thermostat = `thermostat_${zone === 'zone' ? '1' : zone.split('_')[1]}`;
        // Zone temperatures and humidity
        console.log(`${zone}_humidity`);
        updateSVGText(`${zone}_humidity`, data[thermostat]['humidity'] || '--');
        updateSVGText(`${zone}_cur_temperature`, data[thermostat]['actual_temperature'] || '--');
        updateSVGText(`${zone}_tar_temperature`, '--');
        // Zone pump status
        switch(data[thermostat]['current_pump_mode_state']) {
            case "PUMP_MODE_STATE_UNSPECIFIED":
            case "PUMP_MODE_STATE_IDLE":
                // case thermostat is off
                break;
            case "PUMP_MODE_STATE_HEATING":
                // case thermostat is heating
                setActive('zone_1_hot', true);
                setPipeColor(`${zone}_delivery`, 'hot');
                setPipeColor(`${zone}_return`, 'cold');
                break;
            case "PUMP_MODE_STATE_COOLING":
                // case thermostat is cooling
                setActive(`${zone}_cold`, true);
                setPipeColor(`${zone}_delivery`, 'cold');
                setPipeColor(`${zone}_return`, 'hot');
                break;
            default:
                console.warn(`Unknown pump mode state for thermostat 1: ${data[thermostat]['current_pump_mode_state']}`);
        }
        // Zone low battery warning
        showObject(`${zone}_low_battery`, data[thermostat]['warning_low_battery_level'] === 'true' || false);
    });

    // Online and error status
    if(data.hasOwnProperty("error"))
    showObject('error_status', data['error']['active'] === 'true' || false);

    // done -> tell grafana
    window.parent.postMessage({ action: window.location.href, value: 1 }, document.referrer);
});

// map ids from python to svg elements ids
let svgIds = {
    // outside
    'outside_temperature': 'tspan2407-0-1',
    'heatpump_blades': 'g949',
    'heatpump_delivery': 'g9960',
    'heatpump_return': 'g9964',
    // water heater
    'water_heater_cur_temperature': 'tspan2407',
    'water_heater_tar_temperature': 'tspan2407-0',
    'water_heater_delivery': 'g9984',
    'water_heater_return': 'g9988',
    'water_heater_hot': 'g11642-0',
    // zone 1
    'zone_1': 'g9595',
    'zone_1_humidity': 'tspan2407-7-0',
    'zone_1_cur_temperature': 'tspan2407-7-7',
    'zone_1_tar_temperature': 'tspan2407-7',
    'zone_1_delivery': 'g9968',
    'zone_1_return': 'g9972',
    'zone_1_low_battery': 'g30748',
    'zone_1_cold': 'g9598',
    'zone_1_hot': 'g6363-5-3-4',
    // zone 2
    'zone_2': 'g9559',
    'zone_2_humidity': 'tspan2407-7-0-1',
    'zone_2_cur_temperature': 'tspan2407-7-7-6',
    'zone_2_tar_temperature': 'tspan2407-7-8',
    'zone_2_delivery': 'g9980',
    'zone_2_return': 'g9976',
    'zone_2_low_battery': 'g30748-2',
    'zone_2_cold': 'g9531',
    'zone_2_hot': 'g6363-5-3-4-4',
    // zone
    'zone': 'g1479',
    'zone_humidity': 'tspan1459',
    'zone_cur_temperature': 'tspan1453',
    'zone_tar_temperature': 'tspan1447',
    'zone_delivery': 'g1653',
    'zone_return': 'g1647',
    'zone_low_battery': 'g1443',
    'zone_cold': 'g1477',
    'zone_hot': 'g1473',
    // online and error status
    'online_status': 'g3185',
    'error_status': 'g9849'
}

function updateSVGText(id, value) {
    if (view) {
        let element = view.getElementById(svgIds[id]);
        //console.log(`Updating SVG text for id: ${id}, value: ${value}`);
        //console.log(`Element found: ${element}`);
        if (element) {
            // Loop through child nodes to find the text node
            for (let i = 0; i < element.childNodes.length; i++) {
                //console.log(`Child node ${i}:`, element.childNodes[i]);
                if (element.childNodes[i].nodeType === Node.TEXT_NODE) {
                    element.childNodes[i].textContent = value;
                    //console.log(`Updated text node for id ${id} to value: ${value}`);
                    break; // Exit after updating the first text node
                }
            }
        } else {
            console.warn(`Element with id ${svgIds[id]} not found in SVG.`);
        }
    } else {
        console.warn('SVG document is not loaded yet.');
    }
}

function setPipeColor(id, color) {
    let availableColors = ['hot', 'cold', 'return'];
    if (!(availableColors.includes(color) || color === '')) {
        // If the color is not in the list, log an error and return
        console.error(`Invalid color: ${color}. Available colors are: ${availableColors.join(', ')}`);
        return;
    }
    if (view) {
        let element = view.getElementById(svgIds[id]);
        //console.log(`Setting pipe color for id: ${id}, color: ${color}`);
        if (element) {
            // if element is a group, we need to process all children
            let children = [];
            if (element.tagName === 'g') {
                children = element.children;
            } else if (element.tagName === 'path' || element.tagName === 'line') {
                children = [element];
            } else {
                console.warn(`Element with id ${svgIds[id]} is not a group or path/line.`);
                return;
            }
            
            for (let i = 0; i < children.length; i++) {
                // remove all classes from each child
                availableColors.forEach(c => {
                    children[i].classList.remove(`${c}-line`);
                    children[i].classList.remove(`${c}-head`);
                });
                
                // add class with given name to each child
                if (color !== '') {
                    // Check if the element has a fill style or attribute to understand if it's the arrow head or not
                    const hasFillInStyle = children[i].hasAttribute('style') && children[i].getAttribute('style').includes('fill');
                    const hasFillAttribute = children[i].hasAttribute('fill');

                    if (hasFillInStyle || hasFillAttribute) {
                        children[i].classList.add(`${color}-head`);
                    } else {
                        children[i].classList.add(`${color}-line`);
                    }
                    //console.log(`Set color ${color} for element with id ${svgIds[id]}.`);
                }
            }
        } else {
            console.warn(`Element with id ${svgIds[id]} not found in SVG.`);
        }
    } else {
        console.warn('SVG document is not loaded yet.');
    }
}

function spinHeatpumpBlades(enable) {
    if (view) {
        let blades = view.getElementById(svgIds['heatpump_blades']);
        if (blades) {
            // Add a class to trigger the CSS animation
            if (enable) {
                const origin = computeOrigin('heatpump_blades');
                if (origin) {
                    blades.classList.add('rotating');
                    blades.style.transformOrigin = `${origin.x}px ${origin.y}px`;
                } else {
                    console.warn(`Could not compute origin for element with id ${svgIds['heatpump_blades']}.`);
                }
                //console.log('Heatpump blades spinning.');
            } else {
                blades.classList.remove('rotating');
                //console.log('Heatpump blades stopped.');
            }
        } else {
            console.warn('Heatpump blades element not found in SVG.');
        }
    } else {
        console.warn('SVG document is not loaded yet.');
    }
}

function showObject(id, show) {
    if (view) {
        let element = view.getElementById(svgIds[id]);
        if (element) {
            element.style.display = show ? 'block' : 'none';
            //console.log(`Element with id ${id} is now ${show ? 'visible' : 'hidden'}.`);
        } else {
            console.warn(`Element with id ${id} not found in SVG.`);
        }
    } else {
        console.warn('SVG document is not loaded yet.');
    }
}

function setActive(id, active) {
    if (view) {
        let element = view.getElementById(svgIds[id]);
        if (element) {
            showObject(id, true); // Ensure the object is visible before setting active state
            // Determine the class name based on the id
            let className = id.includes('cold') ? 'active-blue' : 'active-orange';
            // if element is a group, we need to process all children
            let children = [];
            if (element.tagName === 'g') {
                children = element.children;
            } else if (element.tagName === 'path' || element.tagName === 'line') {
                children = [element];
            } else {
                console.warn(`Element with id ${svgIds[id]} is not a group or path/line.`);
                return;
            }
            for (let i = 0; i < children.length; i++) {
                if (active) {
                    children[i].classList.add(className);
                    //console.log(`Element with id ${id} is now active.`);
                } else {
                    children[i].classList.remove('active-orange', 'active-blue');
                    //console.log(`Element with id ${id} is no longer active.`);
                }
            }
        } else {
            console.warn(`Element with id ${id} not found in SVG.`);
        }
    } else {
        console.warn('SVG document is not loaded yet.');
    }
}

function addPulse(id) {
    if (view) {
        let element = view.getElementById(svgIds[id]);
        showObject(id, true); // Ensure the object is visible before adding pulse
        if (element) {
            const origin = computeOrigin(id);
            if (origin) {
                element.classList.add('pulse');
                element.style.transformOrigin = `${origin.x}px ${origin.y}px`;
            } else {
                console.warn(`Could not compute origin for element with id ${id}.`);
            }
            //console.log(`Element with id ${id} is pulsing.`);
        } else {
            console.warn(`Element with id ${id} not found in SVG.`);
        }
    } else {
        console.warn('SVG document is not loaded yet.');
    }
}

function computeOrigin(id) {
    if (view) {
        let element = view.getElementById(svgIds[id]);
        if (element) {
            let bbox = element.getBBox();
            let originX = bbox.x + bbox.width / 2;
            let originY = bbox.y + bbox.height / 2;
            return { x: originX, y: originY };
        } else {
            console.warn(`Element with id ${id} not found in SVG.`);
            return null;
        }
    } else {
        console.warn('SVG document is not loaded yet.');
        return null;
    }
}