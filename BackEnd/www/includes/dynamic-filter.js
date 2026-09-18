
let dropdownCounter = 0;

// Parse items and group by key
function locolPromptFilterParseItems(items) {
    const groups = {
        'default': [] // For items without key:value format
    };
    
    items.forEach(item => {
        if (item.includes(':')) {
            const [key, value] = item.split(':', 2);
            if (!groups[key]) {
                groups[key] = [];
            }
            groups[key].push(value);
        } else {
            groups['default'].push(item);
        }
    });
    
    return groups;
}

// Generate all dropdowns
function locolPromptFilterGenerateDropdowns(items) {
    const container = document.getElementById('locol-prompt-filter-dropdownsContainer');
    container.innerHTML = ''
    const groups = locolPromptFilterParseItems(items);
    
    // Reset counter
    dropdownCounter = 0;
    
    // Create dropdown for items without keys first (if any exist)
    if (groups['default'].length > 0) {
        locolPromptFilterCreateDropdown('default', 'General Items', groups['default'], container);
    }
    
    // Create dropdowns for each key
    Object.keys(groups).forEach(key => {
        if (key !== 'default' && groups[key].length > 0) {
            locolPromptFilterCreateDropdown(key, key.charAt(0).toUpperCase() + key.slice(1), groups[key], container);
        }
    });
}

// Create a single dropdown
function locolPromptFilterCreateDropdown(key, title, items, container) {
    const dropdownId = `locol-prompt-filter-dropdown-${dropdownCounter}`;
    
    const dropdownContainer = document.createElement('div');
    dropdownContainer.className = 'locol-prompt-filter-dropdown-container';
    
    const dropdownTitle = document.createElement('div');
    dropdownTitle.className = 'locol-prompt-filter-dropdown-title';
    dropdownTitle.textContent = title;
    
    const dropdown = document.createElement('div');
    dropdown.className = 'locol-prompt-filter-dropdown';
    
    const button = document.createElement('button');
    button.className = 'locol-prompt-filter-dropdown-button';
    button.textContent = `Select ${title} ▼`;
    button.onclick = () => locolPromptFilterToggleDropdown(dropdownId);
    
    const content = document.createElement('div');
    content.className = 'locol-prompt-filter-dropdown-content';
    content.id = dropdownId;
    
    // Create checkboxes for this dropdown
    items.forEach((item, index) => {
        const checkboxItem = document.createElement('div');
        checkboxItem.className = 'locol-prompt-filter-checkbox-item';
        
        const checkboxId = `locol-prompt-filter-checkbox-${key}-${index}`;

        // Built with DOM APIs rather than innerHTML: item and key are tag strings
        // that come back from the prompt config, so interpolating them into markup
        // would let a tag inject HTML.
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.id = checkboxId;
        checkbox.value = item;
        checkbox.dataset.group = key;
        checkbox.addEventListener('change', locolPromptFilterUpdateSelected);

        const checkboxLabel = document.createElement('label');
        checkboxLabel.htmlFor = checkboxId;
        checkboxLabel.textContent = item;

        checkboxItem.append(checkbox, checkboxLabel);

        content.appendChild(checkboxItem);
    });
    
    dropdown.appendChild(button);
    dropdown.appendChild(content);
    dropdownContainer.appendChild(dropdownTitle);
    dropdownContainer.appendChild(dropdown);
    container.appendChild(dropdownContainer);
    
    dropdownCounter++;
}

// Toggle specific dropdown visibility
function locolPromptFilterToggleDropdown(dropdownId) {
    const content = document.getElementById(dropdownId);
    
    if (!content) {
        console.error('Dropdown element not found:', dropdownId);
        return;
    }
    
    // Close other dropdowns
    document.querySelectorAll('.locol-prompt-filter-dropdown-content').forEach(dropdown => {
        if (dropdown.id !== dropdownId) {
            dropdown.classList.remove('locol-prompt-filter-show');
        }
    });
    
    content.classList.toggle('locol-prompt-filter-show');
}

// Update selected items display
function locolPromptFilterUpdateSelected() {
    const checkboxes = document.querySelectorAll('input[type="checkbox"]');
    const selectedByGroup = {};
    
    checkboxes.forEach(checkbox => {
        if (checkbox.checked) {
            const group = checkbox.getAttribute('data-group');
            if (!selectedByGroup[group]) {
                selectedByGroup[group] = [];
            }
            selectedByGroup[group].push(checkbox.value);
        }
    });
    
    const selectedDiv = document.getElementById('locol-prompt-filter-selectedItems');
    if (!selectedDiv) {
        console.error('Selected items display element not found');
        return;
    }
    
    let displayText = '';
    
    if (Object.keys(selectedByGroup).length === 0) {
        displayText = 'None selected';
    } else {
        const groupTexts = [];
        Object.keys(selectedByGroup).forEach(group => {
            const groupTitle = group === 'default' ? 'General' : group;
            groupTexts.push(`${groupTitle}: ${selectedByGroup[group].join(', ')}`);
        });
        displayText = groupTexts.join(' | ');
    }
    
    selectedDiv.textContent = displayText;
    displayPrompts = filterByTags(promptArray, selectedByGroup) 
    refreshFilteredPromptList(displayPrompts)
}

// Close dropdown when clicking outside
document.addEventListener('click', function(event) {
    // Check if the click is outside any dropdown
    const isDropdownButton = event.target.closest('.locol-prompt-filter-dropdown-button');
    const isDropdownContent = event.target.closest('.locol-prompt-filter-dropdown-content');
    
    // If clicked outside both button and content, close all dropdowns
    if (!isDropdownButton && !isDropdownContent) {
        const dropdowns = document.querySelectorAll('.locol-prompt-filter-dropdown-content');
        dropdowns.forEach(dropdown => {
            dropdown.classList.remove('locol-prompt-filter-show');
        });
    }
});

function filterByTags(promptArray, tags) {
    const matchingRows = [];
    
    // Build search criteria from tags object
    const searchCriteria = [];
    
    // Add default tags (search for exact string match)
    if (tags.default && Array.isArray(tags.default)) {
        tags.default.forEach(tag => {
            searchCriteria.push(tag);
        });
    }
    
    // Add non-default tags (search for key:value format)
    Object.keys(tags).forEach(key => {
        if (key !== 'default' && Array.isArray(tags[key])) {
            tags[key].forEach(value => {
                searchCriteria.push(`${key}:${value}`);
            });
        }
    });
    
    // Filter promptArray based on search criteria
    promptArray.forEach(item => {
        searchArray = JSON.parse(item.tag_array)
            // Check if any tag in tag_string matches any search criteria
            const hasMatch = searchArray.some(tag => 
                searchCriteria.includes(tag)
            );
            
            if (hasMatch) {
                matchingRows.push(item);
            }
    });
    
    return matchingRows;
}