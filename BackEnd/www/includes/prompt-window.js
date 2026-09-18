
let prompt_template


// function to create entries
//
/*function createPromptEntries() {
  jsonData.forEach((entry) => {
    const entryContainer = document.getElementById('entryContainer');
    const entryDiv = document.createElement('div');
    entryDiv.textContent = entry.name;
    entryDiv.classList.add('entry');
    entryDiv.id = entry.id;

    // Add click event listener to each entry
    entryDiv.addEventListener('click', () => selectPromptEntry(entryDiv));

    entryContainer.appendChild(entryDiv);
  });
}*/

// Function to handle selection
function selectPromptEntry(entryDiv) {
  const promptEditor = document.getElementById('prompt-editor');
  // Remove 'selected' class from all entries
  const allEntries = document.querySelectorAll('.entry');
  allEntries.forEach(entry => entry.classList.remove('selected'));

  if (entryDiv) {
    // Add 'selected' class to clicked entry
    entryDiv.classList.add('selected');
    prompt_template = entryDiv;
    promptEditor.content = entryDiv.template;
    //selectedItemDisplay.textContent = `Selected Item: ${entryDiv.id}  ${entryDiv.textContent} ${entryDiv.template} `;
    current_fields = (typeof current_fields != 'undefined' && current_fields instanceof Array) ? current_fields : [];
    let old_fields = current_fields;
    current_fields = extractBracedStrings(entryDiv.template)
    createContentFields(current_fields, old_fields);
    adjustMainHeight()
  }

}

function findPromptById(targetId) {
  // Locate the parent DIV
  const parent = document.getElementById("entryContainer");
  // Get all child DIVs within the parent
  const childDivs = parent.getElementsByTagName('div');
  // Loop through child DIVs to find the one with the matching ID
  for (const child of childDivs) {
    if (child.id === targetId) {
      return child; // Return the matching DOM element
    }
  }

  console.log(`Child with ID '${targetId}' not found.`);
  return null; // Return null if no match found
}



