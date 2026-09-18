class Dropdown {
  constructor(containerId,refreshFunction,refreshSelection,initialEntries,readOnly=false ) {
    this.container = document.getElementById(containerId);
    this.entries = initialEntries;
    this.selectedEntry = null;
    this.refreshFunction = refreshFunction;
    this.refreshSelection = refreshSelection;
    this.selectedParent = null;
    this.readOnly = readOnly;

    this.init();
  }

  init() {
    this.singleEntryDiv = document.createElement('div');
    this.singleEntryDiv.classList.add('locol-single-entry');
    this.singleEntryDiv.textContent = 'None';
    this.singleEntryDiv.addEventListener('click', () => this.toggleDisplay());
    this.container.appendChild(this.singleEntryDiv);

    this.scrollableContainer = document.createElement('div');
    this.scrollableContainer.classList.add('locol-scrollable-container');
    this.container.appendChild(this.scrollableContainer);

    this.addFieldContainer = document.createElement('div');
    this.addFieldContainer.classList.add('locol-add-field-container');
    const inputField = document.createElement('input');
    inputField.type = 'text';
    inputField.placeholder = 'Enter new entry';
    this.addFieldContainer.appendChild(inputField);

    const addButton = document.createElement('button');
    addButton.textContent = 'Add';
    this.addFieldContainer.appendChild(addButton);
    addButton.addEventListener('click', () => {
      const newEntryText = inputField.value.trim();
      if (newEntryText) {
        const newEntry = {id: generateUUIDv7(), name: newEntryText,parent: this.selectedParent };
        this.entries.push(newEntry);
        this.addEntry(newEntry);
        this.refreshFunction(this.entries);
        inputField.value = '';
        this.addFieldContainer.style.display = 'none';
      }
    });

    this.scrollableContainer.appendChild(this.addFieldContainer);
    

    const addSelectionButton = document.createElement('div');
    addSelectionButton.classList.add('locol-add-entry');
    addSelectionButton.textContent = '+ Add Selection';
    addSelectionButton.addEventListener('click', () => {
      this.addFieldContainer.style.display = 'block';
      inputField.focus();
    });
    if (!this.readOnly) {
    this.scrollableContainer.appendChild(addSelectionButton);
    }

    this.entries.forEach(entry => this.addEntry(entry));
  }

  refreshDropdown(selectedParent,entries) {
    this.entries = entries;
    this.selectedParent = selectedParent;
    // Clear the scrollable container except for the "Add Selection" section
    this.scrollableContainer.innerHTML = '';
    this.scrollableContainer.appendChild(this.addFieldContainer);

    const addSelectionButton = document.createElement('div');
    addSelectionButton.classList.add('locol-add-entry');
    addSelectionButton.textContent = '+ Add Selection';
    addSelectionButton.addEventListener('click', () => {
      this.addFieldContainer.style.display = 'block';
    });
        this.scrollableContainer.appendChild(addSelectionButton);
  

    // Repopulate the dropdown list from this.entries
    this.entries.forEach(entry => this.addEntry(entry));

    this.scrollableContainer.addEventListener("keydown", function (event) {
      // Deliberately no logging here - this fires on every keystroke typed into
      // the dropdown, including anything the user types into the add-entry field.
      if (event.key === "Escape") {
        this.toggleDisplay();
      }
    })
  }

  toggleDisplay() {
    const isVisible = this.scrollableContainer.style.display === 'block';
    this.scrollableContainer.style.display = isVisible ? 'none' : 'block';
    this.singleEntryDiv.style.display = isVisible ? 'block' : 'none';
  }

  addEntry(entryObject) {
    const entryContainerDiv = document.createElement('div');
    entryContainerDiv.classList.add('locol-entry-container');

    const entryDiv = document.createElement('div');
    entryDiv.textContent = entryObject.name;
    entryDiv.classList.add('locol-entry');
    entryDiv.addEventListener('click', () => {
      this.updateSelectedEntry(entryObject,entryObject.id);
      this.toggleDisplay();
    });

    const renameIcon = this.createIcon('✏️', () => this.renameEntry(entryObject, entryDiv, entryContainerDiv));
    const deleteIcon = this.createIcon('🗑️', () => this.deleteEntry(entryObject, entryContainerDiv));

    entryContainerDiv.appendChild(entryDiv);

    if (!this.readOnly) {
      entryContainerDiv.appendChild(renameIcon);
      entryContainerDiv.appendChild(deleteIcon);
    }

    this.scrollableContainer.appendChild(entryContainerDiv);
  }

  updateSelectedEntry(entryObj,parent) {
    this.selectedEntry = entryObj.id;
    this.singleEntryDiv.textContent = entryObj.name;

    Array.from(this.scrollableContainer.querySelectorAll('.locol-entry')).forEach(entry => {
      entry.classList.remove('selected');
      if (entry.textContent == entryObj.name) {
        entry.classList.add('selected');
      }
    });
    this.refreshSelection(parent);
    refreshScreenContent();
  }

  selectSpecificEntry(entryObj) {
    // Log identifiers only - entryObj and this.entries carry the full record for
    // every row in the dropdown.
    console.log(`Attempting to select entry ${entryObj.id} of ${this.entries.length} available`);

    // Find the entry in the current entries
    const foundEntry = this.entries.find(entry => entry.id === entryObj.id);
    if (foundEntry) {
      console.log(`Found entry ${foundEntry.id} in dropdown`);
      // Use the same logic as a normal click - pass the entry id as the second parameter
      this.updateSelectedEntry(foundEntry, foundEntry.id);
      // Hide the dropdown after selection (same as toggleDisplay)
      this.scrollableContainer.style.display = 'none';
      this.addFieldContainer.style.display = 'none';
    } else {
      console.error(`Entry with id ${entryObj.id} not found in dropdown entries`);
    }
  }

  updateSelectedLLM(llmId) {
    const entryObj = this.entries.find((llm) => llm.id == llmId);
    if (!entryObj) {
      // A history row can name an LLM that no longer exists in the dropdown (deleted
      // through the Config Manager, or trimmed out of llm.yaml). Dereferencing .id here
      // used to throw and abort whatever was mid-flight - including the channel selection
      // in setLLMAndChannelSelections(), which runs updateSelectedLLM before setting the
      // channel and so would leave the screen unable to load any content at all.
      console.warn(`LLM with id '${llmId}' is not in the dropdown; leaving the current selection unchanged.`);
      return;
    }
    this.selectedEntry = entryObj.id;
    this.singleEntryDiv.textContent = entryObj.name;
    Array.from(this.scrollableContainer.querySelectorAll('.locol-entry')).forEach(entry => {
      entry.classList.remove('selected');
      if (entry.textContent == entryObj.name) {
        entry.classList.add('selected');
      }
    });
  }

  renameEntry(entryObject, entryDiv, entryContainerDiv) {
    const renameInput = document.createElement('input');
    renameInput.type = 'text';
    renameInput.value = entryObject.name;

    const saveButton = document.createElement('button');
    saveButton.textContent = 'Save';

    entryContainerDiv.innerHTML = '';
    entryContainerDiv.appendChild(renameInput);
    entryContainerDiv.appendChild(saveButton);

    saveButton.addEventListener('click', () => {
      const newText = renameInput.value.trim();
      if (newText) {
        entryObject.name = newText;
        entryDiv.textContent = newText;
        // selectedEntry holds an *id* (see updateSelectedEntry). Comparing it to
        // .name never matched, so renaming the selected entry used to leave the
        // collapsed label showing the old name. Only the label needs updating -
        // updateSelectedEntry() would fire refreshSelection() and
        // refreshScreenContent(), a full reload cascade, and nothing has moved.
        if (this.selectedEntry === entryObject.id) {
          this.singleEntryDiv.textContent = newText;
        }
        this.refreshFunction(this.entries);
        entryContainerDiv.innerHTML = '';
        entryContainerDiv.appendChild(entryDiv);
        entryContainerDiv.appendChild(this.createIcon('✏️', () => this.renameEntry(entryObject, entryDiv, entryContainerDiv)));
        entryContainerDiv.appendChild(this.createIcon('🗑️', () => this.deleteEntry(entryObject, entryContainerDiv)));
      }
    });
  }

  deleteEntry(entryObject, entryContainerDiv) {
    if (confirm(`Are you sure you want to delete "${entryObject.name}"?`)) {
      entryContainerDiv.remove();
      const index = this.entries.indexOf(entryObject);
      if (index > -1) {
        this.entries.splice(index, 1);
      }
      // Same id-vs-name mistake as renameEntry, and this branch was doubly broken:
      // `Null` (capital N) is not a JavaScript global, so had it ever fired it
      // would have thrown a ReferenceError. Clear the selection the way
      // clearLLMAndChannelSelections() does. The dependent dropdowns are left as
      // they are on purpose - running the cascade with no parent would
      // fetch('/api/get-items/null').
      if (this.selectedEntry === entryObject.id) {
        this.selectedEntry = null;
        this.singleEntryDiv.textContent = 'None';
      }
      this.refreshFunction(this.entries);
    }
  }

  createIcon(iconText, onClickHandler) {
    const icon = document.createElement('span');
    icon.textContent = iconText;
    icon.classList.add('locol-action-icon');
    icon.addEventListener('click', onClickHandler);
    return icon;
  }

}

function generateUUIDv7() {
  const timestamp = Date.now(); // Current time in milliseconds since Unix epoch
  const timeHex = timestamp.toString(16).padStart(12, '0'); // Convert to hex and pad

  const random = crypto.getRandomValues(new Uint8Array(10)); // Generate 10 random bytes
  const randomHex = Array.from(random)
      .map(byte => byte.toString(16).padStart(2, '0'))
      .join('');

  // Construct UUIDv7 format:
  // time_high | version | random
  const uuid = `${timeHex.slice(0, 8)}-${timeHex.slice(8)}-7${randomHex.slice(0, 3)}-${(parseInt(randomHex.slice(3, 5), 16) & 0x3f | 0x80).toString(16).padStart(2, '0')}${randomHex.slice(5, 8)}-${randomHex.slice(8)}`;

  return uuid;
}