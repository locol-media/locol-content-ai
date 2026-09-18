
//new Dropdown('locol-item', [{ id: 'yyy1', item: 'Alpha' }, { id: 'yyy2', item: 'Beta' }, { id: 'yyy3',  item: 'Gamma' }]);

let projectDropdown
let itemDropdown
let channelDropdown
let llmDropdown
let promptArray

// getAPIHeaders() lives in includes/auth.js, loaded ahead of this file. So does
// the session token capture that used to happen here - by the time this runs the
// token is already in the cookie and stripped back out of the URL.

// Function to get the deep-link target from the URL
function getUrlParameters() {
    const urlParams = new URLSearchParams(window.location.search);

    return {
        project_id: urlParams.get('project_id'),
        item_id: urlParams.get('item_id')
    };
}

// Function to auto-select project and item from URL parameters
function autoSelectFromUrlParams(projectData, urlParams) {
    if (urlParams.project_id) {
        // Find project by ID
        const projectToSelect = projectData.find(project => project.id === urlParams.project_id);
        if (projectToSelect) {
            console.log(`Auto-selecting project: ${projectToSelect.name} (${projectToSelect.id})`);
            projectDropdown.selectSpecificEntry(projectToSelect);
            
            // If item_id is also provided, wait for items to load and then select
            if (urlParams.item_id) {
                // Set a flag to auto-select item after items are loaded
                window.autoSelectItemId = urlParams.item_id;
            }
        } else {
            console.warn(`Project with id ${urlParams.project_id} not found`);
        }
    }
}

// Process URL parameters on page load (including JWT)
const urlParams = getUrlParameters();

fetch('/api/get-projects/', {
    method: 'GET',
    headers: getAPIHeaders()
    }).then(res => res.json())
    .then(res => {
        projectDropdown = new Dropdown('locol-project',persistProjects,refreshItemDropdown,res);
        itemDropdown = new Dropdown('locol-item', persistItems,checkItemLLMChannelCombos, []);
        
        // Auto-select project and item from URL parameters
        if (urlParams.project_id || urlParams.item_id) {
            autoSelectFromUrlParams(res, urlParams);
        }
    }
    );

fetch('/api/get-channels/', {
  method: 'GET',
  headers: getAPIHeaders()
  }).then(res => res.json())
  .then(res => {
      channelDropdown = new Dropdown('locol-channel',doNothing, refreshPromptList, res,readOnly=true);
  }
  );

fetch('/api/get-llms/', {
  method: 'GET',
  headers: getAPIHeaders()
  }).then(res => res.json())
  .then(res => {
      llmDropdown = new Dropdown('locol-llm',doNothing, openSelectedLLM, res, readOnly=true);
  }
  );

  function openSelectedLLM(selected) {
    fetch(`/api/open-llm/${llmDropdown.selectedEntry}`, {
      method: 'GET',
      headers: getAPIHeaders()
      }).then(res => res.json())
      .then(res => {
          
      }
      );
  }

function persistProjects(jsonArray) {
  return persistDropdownList("persist-projects",jsonArray)
}
function persistItems(jsonArray) {
  return persistDropdownList("persist-items",jsonArray,projectDropdown.selectedEntry)
} 
function doNothing() {
  return 
} 

function persistDropdownList(dropdown,jsonArray,parent) {
  let parent_str = parent ? `?parent=${parent}` : ""
    return fetch(`/api/${dropdown}/${parent_str}`, {
      method: 'POST', // HTTP method
      headers: getAPIHeaders(),
      body: JSON.stringify(
        {
           "dropdownList":  jsonArray
        }
        
    ), // Convert the JSON array to a string
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json(); // Assuming the server returns a JSON response
      })
      .catch((error) => {
        console.error(`Error posting JSON array: ${error.message}`);
        throw error; // Re-throw the error for further handling
      });
  }
  
  function refreshItemDropdown(selected) {
    // Clear item, channel, and LLM selections when a new project is selected
    // Use setTimeout to ensure dropdowns are initialized
    setTimeout(() => {
      clearItemChannelLLMSelections();
    }, 100);
    
    fetch(`/api/get-items/${selected}`, {
      method: 'GET',
      headers: getAPIHeaders()
      }).then(res => res.json())
      .then(res => {
          // First refresh the dropdown with the new items
          itemDropdown.refreshDropdown(selected,res);
          
          // Auto-select item if autoSelectItemId is set
          if (window.autoSelectItemId) {
              const itemToSelect = res.find(item => item.id === window.autoSelectItemId);
              if (itemToSelect) {
                  console.log(`Auto-selecting item: ${itemToSelect.name} (${itemToSelect.id})`);
                  // Use longer timeout to ensure dropdown is fully refreshed and DOM updated
                  setTimeout(() => {
                      // Double-check that the item exists in the dropdown's entries
                      const dropdownItem = itemDropdown.entries.find(item => item.id === window.autoSelectItemId);
                      if (dropdownItem) {
                          itemDropdown.selectSpecificEntry(dropdownItem);
                          console.log(`Successfully auto-selected item: ${dropdownItem.name}`);
                      } else {
                          console.warn(`Item ${window.autoSelectItemId} not found in dropdown entries after refresh`);
                      }
                      // Clear the flag after use
                      window.autoSelectItemId = null;
                  }, 300);
              } else {
                  console.warn(`Item with id ${window.autoSelectItemId} not found in API response`);
                  window.autoSelectItemId = null;
              }
          }
      }
      );
  }

  function refreshPromptList(selected) {
    fetch(`/api/get-prompt-templates/${selected}`, {
      method: 'GET',
      headers: getAPIHeaders()
      }).then(res => res.json())
      .then(res => {
        promptArray = JSON.parse(res);
          // refresh prompt list
          refreshFilteredPromptList(promptArray)
          const tag_array = [...new Set(promptArray.flatMap(obj => JSON.parse(obj.tag_array)))]
            locolPromptFilterGenerateDropdowns(tag_array);
      }
      );
  }
  function refreshFilteredPromptList(currentArray) {
          // refresh prompt list
          const promptContainer = document.getElementById('entryContainer');
          promptContainer.innerHTML = '';
          currentArray.forEach((entry) => {
            const entryContainer = document.getElementById('entryContainer');
            const entryDiv = document.createElement('div');
            entryDiv.textContent = entry.name;
            entryDiv.classList.add('entry');
            entryDiv.id = entry.id;
            entryDiv.template = entry.template;     
            // Add click event listener to each entry
            entryDiv.addEventListener('click', () => selectPromptEntry(entryDiv));      
            entryContainer.appendChild(entryDiv);
          })
        }

function checkItemLLMChannelCombos(itemId) {
  if (!itemId) {
    // If no item selected, clear LLM and channel selections
    clearLLMAndChannelSelections();
    return;
  }
  
  fetch(`/api/check-item-llm-channel/${itemId}`, {
    method: 'GET',
    headers: getAPIHeaders()
  })
  .then(response => {
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    return response.json();
  })
  .then(data => {
    console.log(`LLM-Channel combinations for item: ${(data.combinations || []).length} found`);
    
    if (data.success && data.combinations && data.combinations.length === 1) {
      // Only one combination found, set both LLM and channel
      const combo = data.combinations[0];
      setLLMAndChannelSelections(combo.llm, combo.channel_id);
    } else {
      // Multiple combinations or no combinations, clear selections
      clearLLMAndChannelSelections();
    }
  })
  .catch(error => {
    console.error(`Error checking LLM-Channel combinations: ${error.message}`);
    clearLLMAndChannelSelections();
  });
}

function setLLMAndChannelSelections(llmId, channelId) {
  // Set LLM dropdown selection
  if (llmDropdown && llmId) {
    llmDropdown.updateSelectedLLM(llmId);
  }
  
  // Set Channel dropdown selection  
  if (channelDropdown && channelId) {
    const channelEntry = channelDropdown.entries.find(entry => entry.id === channelId);
    if (channelEntry) {
      channelDropdown.updateSelectedEntry(channelEntry, channelId);
    }
  }
  
  console.log(`Set LLM to: ${llmId}, Channel to: ${channelId}`);
}

function clearLLMAndChannelSelections() {
  // Clear LLM dropdown selection
  if (llmDropdown && llmDropdown.singleEntryDiv && llmDropdown.scrollableContainer) {
    llmDropdown.selectedEntry = null;
    llmDropdown.singleEntryDiv.textContent = 'None';
    // Remove selected class from all entries
    try {
      Array.from(llmDropdown.scrollableContainer.querySelectorAll('.locol-entry')).forEach(entry => {
        entry.classList.remove('selected');
      });
    } catch (e) {
      console.log('LLM dropdown not fully initialized yet');
    }
  }
  
  // Clear Channel dropdown selection
  if (channelDropdown && channelDropdown.singleEntryDiv && channelDropdown.scrollableContainer) {
    channelDropdown.selectedEntry = null;
    channelDropdown.singleEntryDiv.textContent = 'None';
    // Remove selected class from all entries
    try {
      Array.from(channelDropdown.scrollableContainer.querySelectorAll('.locol-entry')).forEach(entry => {
        entry.classList.remove('selected');
      });
    } catch (e) {
      console.log('Channel dropdown not fully initialized yet');
    }
  }
  
  console.log('Cleared LLM and Channel selections');
}

function clearItemChannelLLMSelections() {
  // Clear Item dropdown selection
  if (itemDropdown && itemDropdown.singleEntryDiv && itemDropdown.scrollableContainer) {
    itemDropdown.selectedEntry = null;
    itemDropdown.singleEntryDiv.textContent = 'None';
    // Remove selected class from all entries
    try {
      Array.from(itemDropdown.scrollableContainer.querySelectorAll('.locol-entry')).forEach(entry => {
        entry.classList.remove('selected');
      });
    } catch (e) {
      console.log('Item dropdown not fully initialized yet');
    }
  }
  
  // Clear LLM and Channel selections (reuse existing function)
  clearLLMAndChannelSelections();
  
  console.log('Cleared Item, LLM and Channel selections');
}
