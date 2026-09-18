
// getAPIHeaders() lives in includes/auth.js, loaded ahead of this file.

const submitPromptButton = document.getElementById('submit_prompt');
submitPromptButton.onclick = () => {
  pushPromt2Backend();
};

const saveContentButton = document.getElementById('save_content');
saveContentButton.onclick = () => {
  saveContent2Backend();
};

let content_save = []

function updateContentSave(id, value) {
  var existingField = content_save.find(function (item) {
    return item.id == id;
  });

  if (existingField) {
    // Update the existing field's value
    existingField.value = value;
  } else {
    // Add new field to the array
    content_save.push({ id: id, value: value });
  }
}

function createContentFields(fieldNames, old_fields) {
  // Assuming you have a container element in your HTML with the ID 'content_fields'
  const content_fields = document.getElementById('content_fields');


  // save current field values
  // content_save = (typeof content_save != 'undefined' && content_save instanceof Array) ? content_save : []
  old_fields.forEach(function (id) {
    var field = document.getElementById("field_" + id);
    if (field) {
      updateContentSave(id, field.value)
    }
  });
  content_fields.textContent = '';
  fieldNames.forEach(function (fieldName) {

    if (fieldName != "Content") {
      const content_container = document.createElement('div');
      const label = document.createElement('label');
      label.textContent = fieldName + ': ';
      const input = document.createElement('textarea');
      input.id = "field_" + fieldName;
      content_container.appendChild(label);
      content_container.appendChild(input);
      content_fields.appendChild(content_container);
      document.getElementById("field_" + fieldName).value = content_save.find(item => item.id == fieldName) ? content_save.find(item => item.id == fieldName).value : null;
      content_fields.appendChild(document.createElement('br'));
    }
  });
}

function extractBracedStrings(str) {
  const results = [];
  let braceCount = 0;
  let startIndex = -1;

  for (let i = 0; i < str.length; i++) {
    if (str[i] === '{') {
      if (braceCount === 0) {
        startIndex = i + 1;
      }
      braceCount++;
    } else if (str[i] === '}') {
      braceCount--;
      if (braceCount === 0 && startIndex !== -1) {
        const found_field = str.substring(startIndex, i);
        if (!results.includes(found_field)) {
          results.push(found_field);
        }
        startIndex = -1;
      }
    }
  }

  return results;
}

function substitutePlaceholder(template, name, value) {
  // split/join, not String.replace: replace() with a string pattern substitutes
  // only the FIRST match - a template using {Topic} twice would send one literal
  // {Topic} to the model - and treats $&, $`, $' and $$ in the *value* as
  // replacement patterns, so a field value or draft containing them would be
  // corrupted on its way out.
  return template.split("{" + name + "}").join(value);
}

function assemblePrompt(templateText, liveContentHtml) {
  // Shared by both write paths. They diverged once already (finding 2) because
  // this loop was copy-pasted into each of them.
  //
  // Assigns the cross-file current_fields global on the way through:
  // prompt-window.js reads it back as old_fields when the user switches template,
  // to carry field values across.
  current_fields = extractBracedStrings(templateText);
  let prompt = templateText;

  current_fields.forEach(function (id) {
    const field = document.getElementById("field_" + id);
    if (field) {
      prompt = substitutePlaceholder(prompt, id, field.value);
      updateContentSave(id, field.value);
    } else if (id == "Content") {
      // {Content} has no textarea - it is filled from the editor body itself.
      prompt = substitutePlaceholder(prompt, id, liveContentHtml);
    }
  });

  return prompt;
}

function pushPromt2Backend() {
  // fill out prmopt template
  // submit it
  const promptEditor = document.getElementById('prompt-editor');
  const liveContent = getLiveQuillContent('quill-editor');
  const liveContentHtml = getLiveQuillHtml('quill-editor');
  const prompt = assemblePrompt(promptEditor.innerText, liveContentHtml);

  let currentPanels = getPanelFractions();

  fetch('/api/llm-invoke/', {
    method: 'POST',
    headers: getAPIHeaders(),
    body: JSON.stringify({
      "project_id": projectDropdown.selectedEntry,
      "item_id": itemDropdown.selectedEntry,
      "channel_id": channelDropdown.selectedEntry,
      "prompt_id": prompt_template ? prompt_template.id : null,
      "content": liveContent,
      "fields": JSON.stringify(content_save),
      "llm": llmDropdown.selectedEntry,
      "prompt_template": getLiveQuillContent('prompt-editor'),
      "query": prompt,
      "panel_fractions": JSON.stringify(currentPanels),
      "rag_on_off": false
    })
  }).then(res => res.json())
    .then(res => {
      quillEditor.content = res.content
      appendHistoryDisplay(res.timestamp, quillEditor.content)
      setPanelFractions(currentPanels)
    });
}

function getLiveQuillInstance(customElementId) {
  // The .content Stencil prop is only ever set programmatically (e.g. after an
  // LLM response or history reload) and never reflects live typing, since
  // nothing writes editor state back into it on text-change. Everything that
  // needs what the user can actually see has to go to the Quill instance.
  const wrapper = document.getElementById(customElementId);
  const editorNode = wrapper && wrapper.querySelector('[quill-editor]');
  return (editorNode && Quill.find(editorNode)) || null;
}

function getLiveQuillContent(customElementId) {
  const quill = getLiveQuillInstance(customElementId);
  if (!quill) {
    const wrapper = document.getElementById(customElementId);
    return wrapper ? wrapper.content : ""; // fallback to the (possibly stale) prop
  }
  // getContents() returns a Delta instance; JSON.stringify(delta) serializes
  // to {"ops": [...]} (its own properties), not the bare [...] array that
  // html_to_delta()/appendHistoryDisplay()/the rest of this codebase expect.
  return JSON.stringify(quill.getContents().ops);
}

function getLiveQuillHtml(customElementId) {
  // For {Content}: the model is told to emit p/b/i/ul/h1/h2 and its reply comes
  // back through html_to_delta(), so feeding the draft in as HTML is what lets
  // bold/lists/headings survive an iterative "rewrite this shorter" round trip.
  const quill = getLiveQuillInstance(customElementId);
  if (!quill) {
    console.warn(`No Quill instance for #${customElementId}; sending empty {Content}`);
    return "";
  }
  // Defensive: getSemanticHTML() emitted &nbsp; for ordinary spaces in the
  // 2.0.0-rc.0 build this page used to load from a CDN, which left the model
  // reading entities instead of prose. The vendored 2.0.2 no longer does it, so
  // this is a no-op there - kept so a version change can't quietly reintroduce it.
  return quill.getSemanticHTML().replace(/&nbsp;/g, ' ');
}

function saveContent2Backend() {
  // Save current content to history without LLM invocation
  const promptEditor = document.getElementById('prompt-editor');
  const liveContent = getLiveQuillContent('quill-editor');
  const liveContentHtml = getLiveQuillHtml('quill-editor');
  const prompt = assemblePrompt(promptEditor.innerText, liveContentHtml);

  let currentPanels = getPanelFractions();

  fetch('/api/persist-content/', {
    method: 'POST',
    headers: getAPIHeaders(),
    body: JSON.stringify({
      "project_id": projectDropdown.selectedEntry,
      "item_id": itemDropdown.selectedEntry,
      "channel_id": channelDropdown.selectedEntry,
      "prompt_id": prompt_template ? prompt_template.id : null,
      "content": liveContent,
      "fields": JSON.stringify(content_save),
      "llm": llmDropdown.selectedEntry,
      "prompt_template": getLiveQuillContent('prompt-editor'),
      "query": prompt,
      "panel_fractions": JSON.stringify(currentPanels),
      "rag_on_off": false
    })
  }).then(res => res.json())
    .then(res => {
      appendHistoryDisplay(res.timestamp, liveContent)
      setPanelFractions(currentPanels)
    });
}

function refreshScreenContent() {
  if (
    projectDropdown && projectDropdown.selectedEntry != null &&
    itemDropdown && itemDropdown.selectedEntry != null &&
    channelDropdown && channelDropdown.selectedEntry != null
  ) {
    fetch('/api/get-history/', {
      method: 'POST',
      headers: getAPIHeaders(),
      body: JSON.stringify(
        {
          "project_id": projectDropdown.selectedEntry,
          "item_id": itemDropdown.selectedEntry,
          "channel_id": channelDropdown.selectedEntry
        }

      )
    }).then(res => {
      if (!res.ok) {
        // Without this the error body falls through to the success path below:
        // {"detail": ...} has no .length, and `undefined != 0` is true, so the
        // handler would index res[0] and throw into a dangling promise - which
        // is how a failing endpoint used to present as two silently empty panes.
        throw new Error(`get-history failed: HTTP ${res.status} ${res.statusText}`);
      }
      return res.json();
    })
      .then(res => {
        if (!Array.isArray(res)) {
          // Log the shape, not the payload - a get-history body carries the
          // user's saved content.
          console.error(`get-history returned a non-array payload (${typeof res}); not restoring.`);
          return;
        }
        if (res.length === 0) {
          console.log('get-history returned no rows for this project/item/channel; nothing to restore.');
          return;
        }

        let history_data = res[0]

        // Populate both panes FIRST. Everything below is a best-effort restore,
        // and each step is isolated so one failure can't blank the panes.
        quillEditor.content = history_data.response
        quillView.content = ''
        for (let i = res.length - 1; i >= 0; i--) {
          appendHistoryDisplay(res[i].query_datetime, res[i].response)
        }

        // restore dynamic fields before restoring prompt
        try {
          content_save = history_data.fields ? JSON.parse(history_data.fields) : [];
        } catch (e) {
          console.warn(`Error parsing fields JSON, using empty array: ${e.message}`);
          content_save = [];
        }

        try {
          let promptSelected = findPromptById(history_data.prompt_id);
          if (promptSelected) {  // give it a second if the channel button has to be refreshed
            selectPromptEntry(promptSelected);
          } else {
            setTimeout(() => {
              try {
                selectPromptEntry(findPromptById(history_data.prompt_id));
              } catch (e) {
                console.warn(`Error restoring prompt template: ${e.message}`);
              }
            }, "1000");
          }
        } catch (e) {
          console.warn(`Error restoring prompt template: ${e.message}`);
        }

        // todo: retrieve grid panes from history_data.panel_fractions
        try {
          if (history_data.panel_fractions) {
            setPanelFractions(JSON.parse(history_data.panel_fractions));
          }
        } catch (e) {
          console.warn(`Error parsing panel_fractions JSON: ${e.message}`);
        }

        try {
          llmDropdown.updateSelectedLLM(history_data.llm)
        } catch (e) {
          console.warn(`Error restoring LLM selection: ${e.message}`);
        }
      })
      .catch(err => {
        console.error(`Error restoring screen content: ${err.message}`);
      });
  }
}

function appendHistoryDisplay(timestamp, content) {
  if (content != "") {
    let tail = (quillView.content == "") ? "]" : ("," + quillView.content.slice(1,-1) + "]")
    let history = `[{"insert": "\\n\\n------------------- ${timestamp} -------------------\\n\\n"},` + content.slice(1,-1) + tail
      quillView.content = history
  }

}


/*
const toggleBtn = document.getElementById("toggleBtn");
let ragOnOff = false;

toggleBtn.addEventListener("click", () => {
    ragOnOff = !ragOnOff;
    toggleBtn.classList.toggle("animate-button", ragOnOff);
    toggleBtn.textContent = ragOnOff ? "RAG on" : "RAG off";
});
*/
