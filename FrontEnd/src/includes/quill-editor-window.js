
// getAPIHeaders() lives in includes/auth.js, loaded ahead of this file.

const quillEditor = document.getElementById('quill-editor');
const quillView = document.getElementById('view');
const quillViewHTML = document.getElementById('htmlView');

function reset_data(data_type) {
  // Currently unreachable - every call site below is commented out. Returns the
  // parsed body so a future caller can use it, rather than dumping the response
  // to the console.
  return fetch(`/api/load-buttons/${data_type}`, {
    method: 'GET',
    headers: getAPIHeaders()
  }).then(res => res.json())
}

/*
const locol_buttons = document.getElementById('locol-set-buttons');
locol_buttons.onclick = () => {
  reset_data("buttons")
};

const locol_prompts = document.getElementById('locol-set-prompts');
locol_prompts.onclick = () => {
  reset_data("prompts")
};

const locol_kb = document.getElementById('locol-set-kb');
locol_kb.onclick = () => {
  reset_data("kb")
};*/

quillEditor.addEventListener('editorInit', event => {
  /*quillEditor.content = JSON.stringify({ ops: [{ insert: '' }] });
  quillView.content = JSON.stringify({ ops: [{ insert: '' }] });*/
  // Do NOT blank .content here. editorInit fires at the end of the component's
  // componentDidLoad (deferred another macrotask by a setTimeout), and that can't
  // run until Quill has downloaded from its CDN - while refreshScreenContent()
  // runs off a chain of fast same-origin API calls. When the API chain wins the
  // race, clearing here wiped the history that had just been loaded into both
  // panes. Both elements already declare content="" in index.html, so there is
  // nothing to clear.
  //
  // Instead, cover the opposite ordering: if the editor finished initialising
  // after the dropdown cascade already settled, re-apply the stored content.
  // refreshScreenContent() is self-guarding (it no-ops unless project, item and
  // channel are all selected), so this is safe whichever side wins.
  refreshScreenContent();
});

/*
quillEditor.addEventListener('editorChange', event => {
  console.log('editorChange', event.detail);
});

quillEditor.addEventListener('editorSelectionChange', event => {
  console.log('editorSelectionChange', event.detail);
});

quillEditor.addEventListener('editorFocus', event => {
  console.log('editorFocus', event.detail);
});

quillEditor.addEventListener('editorBlur', event => {
  console.log('editorBlur', event.detail);
});*/