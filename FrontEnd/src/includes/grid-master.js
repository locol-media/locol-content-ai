// DOM utils:
const el = (sel, par = document) => document.querySelector(sel);
const els = (sel, par = document) => document.querySelectorAll(sel);
const elNew = (tag, prop = {}) => Object.assign(document.createElement(tag), prop);

// Resizable
let isResizing = false;
const resizableGrid = (elParent, idx) => {

  const isVert = elParent.classList.contains("panes-v");
  const elsPanes = elParent.querySelectorAll(":scope > .pane");

  let fr = [...elsPanes].map(() => 1 / elsPanes.length);
  let elPaneCurr = null;
  let paneIndex = -1;
  let frStart = 0;

  const frToCSS = () => {
    elParent.style[isVert ? "grid-template-rows" : "grid-template-columns"] = fr.join("fr ") + "fr";
  };

  const pointerDown = (evt) => {
    if (isResizing || !evt.target.closest(".gutter")) return;
    isResizing = true;
    elPaneCurr = evt.currentTarget;
    fr = [...elsPanes].map((elPane) => isVert ? elPane.clientHeight / elParent.clientHeight : elPane.clientWidth / elParent.clientWidth);
    paneIndex = [...elsPanes].indexOf(elPaneCurr);
    frStart = fr[paneIndex];
    frNext = fr[paneIndex + 1];
    addEventListener("pointermove", pointerMove);
    addEventListener("pointerup", pointerUp);
  };

  const pointerMove = (evt) => {
    evt.preventDefault();
    const paneBCR = elPaneCurr.getBoundingClientRect();
    const parentSize = isVert ? elParent.clientHeight : elParent.clientWidth;
    const pointer = {
      x: Math.max(0, Math.min(evt.clientX - paneBCR.left, elParent.clientWidth)),
      y: Math.max(0, Math.min(evt.clientY - paneBCR.top, elParent.clientHeight))
    };
    const frRel = pointer[isVert ? "y" : "x"] / parentSize;
    const frDiff = frStart - frRel;
    fr[paneIndex] = Math.max(0.05, frRel);
    fr[paneIndex + 1] = Math.max(0.05, frNext + frDiff);
    frToCSS();
  };

  const pointerUp = (evt) => {
    removeEventListener("pointermove", pointerMove);
    removeEventListener("pointerup", pointerUp);
    isResizing = false;
    adjustMainHeight()
  };

  [...elsPanes].slice(0, -1).forEach((elPane, i) => {
    elPane.append(elNew("div", {
      className: "gutter"
    }));
    elPane.addEventListener("pointerdown", pointerDown);
  });
  frToCSS();
};

els(".panes").forEach(resizableGrid);

function getFractions(gridElement) {
  // Get computed styles of the grid container
  const computedStyle = window.getComputedStyle(gridElement);

  // Get the row sizes in pixels (computed)
  const isVert = gridElement.classList.contains("panes-v");
  const rowSizes = computedStyle.getPropertyValue(isVert ? "grid-template-rows" : "grid-template-columns")
    .split(" ")
    .map(size => {
      if (size.includes("px")) {
        return parseFloat(size); // Convert pixel values to numbers
      }
      return 0; // Ignore non-pixel values
    });

  // Calculate total fractionable space
  const totalSpace = rowSizes.reduce((sum, val) => sum + val, 0);

  // Convert pixel values to fractional values
  return rowSizes.map(size => (size / totalSpace).toFixed(2) + "fr");
}
function setFractions(gridElement, frValues) {
  // Join the fr values into a valid CSS string
  gridElement.style.gridTemplateRows = frValues.join(" ");
}

const panelElements = new Map();
panelElements.set('panel_main',document.getElementById('panel_main'));
panelElements.set('panel_left',document.getElementById('panel_left'));
panelElements.set('panel_right',document.getElementById('panel_right'));
panelElements.set('panel_prompt',document.getElementById('panel_prompt'));

function getPanelFractions() {
  let panelFractions = []
  for (let [key, element] of panelElements) {
    panelFractions.push( {
      panel: key,
      element: element,
      fractions: getFractions(element)
    })
  }
  return panelFractions
}

function setPanelFractions(panelFractions) {
  panelFractions.forEach(
    (panel) => {
      element = panelElements.get(panel.panel)
      setFractions(element, panel.fractions)
    }
  )
}
