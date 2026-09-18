introJs().setOptions({
  steps: [{
    title: 'Welcome',
    intro: `Welcome to Locol Content AI👋. The purpose of this app is to help you generate social marketing content.
    It helps you organize your Social Media AI projects across multiple social media channels, multiple AI servics, and keep a history of your interactions for reuse.
     `
  },
  {
    element: document.querySelector('#locol-project'),
    intro: 'Projects are used to organize your social media work. Click on the button to create new projects.'
  },
  {
    element: document.querySelector('#locol-item'),
    intro: 'Each Project contains a collection of social media items, whether they are blog posts, or smaller items for LinkedIn, Reddit, Facebook or others.'
  },
  {
    element: document.querySelector('#locol-channel'),
    intro: 'A default selection of channels have been created for you. You can add or edit channels in the <strong>channel</strong> folder.'
  },
  {
    element: document.querySelector('#locol-llm'),
    intro: 'You can define multiple AI LLMs. You just need to provide your key for each LLM in the files in the LLM folder (for now... LLM definition editor coming up).'
  },
  {
    element: document.querySelector('#locol_content'),
    intro: 'This is the main area for input into the LLM. LLM output is also placed here, for your edits and as input into the next interaction.'
  },
  {
    element: document.querySelector('#locol_history'),
    intro: 'The history window keeps track of your inputs into the LLMs and their outputs. You can scroll this window for previous work and reuse any material by copying and pasting into the content editor.'
  },  {
    element: document.querySelector('#prompt_window'),
    intro: 'This window contains a list of potential prompt templates that are valid for the channel you have selected. There is a wide range of prompts. Use the Filter buttons to find the right prompt for you right now.'
  },
  {
    element: document.querySelector('#prompt_editor_header'),
    intro: 'Select a prompt template from the prompt list and customize the prompt if needed. Otherwise use the prompt input area to fill in the information requested by the prompt.'
  },
  {
    element: document.querySelector('#prompt_input'),
    intro: 'Here you fill in the information that will customize the template to your needs.'
  },
  {
    element: document.querySelector('#submit_prompt'),
    intro: 'When you are ready, hit this button to submit your question to the LLM.'
  },
  {
    title: 'Farewell!',
    element: document.querySelector('.card__image'),
    intro: '<img src="https://images.unsplash.com/photo-1608096299210-db7e38487075?ixid=MXwxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHw%3D&ixlib=rb-1.2.1&auto=format&fit=crop&w=400&q=80" />'
  }]
}).start();