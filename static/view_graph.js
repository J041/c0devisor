function toggleTabs(side) {
  var tabs = document.querySelector("." + side + "-tabs");
  var middleTabs = document.querySelector(".middle-tabs");

  tabs.classList.toggle("collapsed");

  // If either left or right tabs are collapsed, expand the middle tab
  if (
    document.querySelector(".left-tabs.collapsed") ||
    document.querySelector(".right-tabs.collapsed")
  ) {
    middleTabs.style.width = "100%";
  } else {
    middleTabs.style.width = "80%"; // Default width when both left and right tabs are expanded
  }
}


// Function to apply SVG Pan Zoom to the SVG document
function applySvgPanZoom() {
  // Access the SVG document inside the <iframe>
  var svgFrame = document.getElementById("svgFrame");
  var svgDoc = svgFrame.contentDocument;

  // Check if SVG document is loaded
  if (svgDoc) {
    // Apply SVG Pan Zoom to the SVG document
    var svgElement = svgDoc.querySelector("svg");
    if (svgElement) {
      svgPanZoom(svgElement, {
        zoomEnabled: true,
        controlIconsEnabled: true,
        // You can add more options as needed
      });
    }
  }
}

// Call the function when the iframe is loaded
document.getElementById("svgFrame").onload = function () {
  applySvgPanZoom();
};

var active_querykeys = {};
const html_parser = new DOMParser();
// regenerate current function being viewed
async function regenerate_graph(event) {
  let response
  if (event && (event.target.tagName == "INPUT")) {
    var filename_querykey;
    filename_querykey = event.target.dataset.querykey.split('/');

    if (event.target.checked) {
      // Generate security form graph
      taint_selected = document.getElementById(filename_querykey[1]+"-taint-count");
      active_querykeys[filename_querykey[1]] = taint_selected.value;
    }
    else if (!event.target.checked) {
      delete active_querykeys[filename_querykey[1]];
    }
  }
  let folder = window.location.pathname.split('/') // /view_graph/<folder>/funcidORsubmit_security_form
    folder.length = 3;
    folder = folder.join('/')
  if (Object.keys(active_querykeys).length > 0) {
    let security_form = new FormData()
    security_form.append("activeKeys", JSON.stringify(active_querykeys));
    response = await fetch(`${$SCRIPT_ROOT}${folder}/security_view`, {
      method: 'POST',
      body: security_form
    });
  }
  else {
    response = await fetch(`${$SCRIPT_ROOT}${folder}/${active_func_id}/regenerate`, {
      method: "GET",
    });
  }
  if (response.status == 200) {
    var object = document.getElementById("svgFrame");
    // object.data = object.data
    await response.text()
      .then((data) => {
        docu = html_parser.parseFromString(data, "text/html");
        var refreshed_graph = docu.getElementById("svgFrame");
        object.data = refreshed_graph.data;
      })
  }
  // Flash
};




function searchFunctionNames() {
  var input, filter, functionNames, a, i, txtValue;
  input = document.getElementById('functionSearch');
  filter = input.value.toUpperCase();
  functionNames = document.getElementsByClassName('wrap-word');
  if (filter == "") {
    for (i = 0; i < functionNames.length; i++) {
      a = functionNames[i];
      txtValue = a.textContent || a.innerText;
      functionNames[i].style.display = '';
    }
    return
  }
  for (i = 0; i < functionNames.length; i++) {
    a = functionNames[i];
    txtValue = a.textContent || a.innerText;
    if (txtValue.toUpperCase().indexOf(filter) > -1) {
      functionNames[i].style.display = 'block';
    } else {
      functionNames[i].style.display = 'none';
    }
  }
}

// Security Forms ------------------------
// Auto set source file when source function is selected
function autofill_file() {
  var function_selector = document.getElementById('sourceInput3');
  var file_selector = document.getElementById('sourceInput4');
  var optgroups = function_selector.getElementsByTagName('optgroup');
  for (var i = 0; i < optgroups.length; i++) {
    var options = optgroups[i].getElementsByTagName('option');

    for (var j = 0; j < options.length; j++) {
      if (options[j].selected) { // check if options is selected
        file_selector.value = optgroups[i].getAttribute('label');
      }
    }
  }

}
// Filter source function dropdown list when  source file is selected
function filter_functions() {
  var function_selector = document.getElementById('sourceInput3');
  var selected_file = document.getElementById('sourceInput4').value;
  var optgroups = function_selector.getElementsByTagName('optgroup');
  for (var i = 0; i < optgroups.length; i++) {
    if (selected_file == "" || selected_file == optgroups[i].getAttribute('label')) {
      optgroups[i].disabled = false;
      optgroups[i].style = 'display: block;';
    }
    else {
      optgroups[i].disabled = true;
      optgroups[i].style = 'display: none;';
    }
  }
}

// Collapsible Tab
var coll = document.getElementsByClassName("collapsible");
var i;

for (i = 0; i < coll.length; i++) {
  coll[i].addEventListener("click", function () {
    this.classList.toggle("active");
    var content = this.nextElementSibling;
    if (content.style.maxHeight) {
      content.style.maxHeight = null;
    } else {
      content.style.maxHeight = content.scrollHeight + "px";
    }
  });
}


var leftTabsDivs = document.querySelectorAll('.left-tabs div p');

leftTabsDivs.forEach(function(div) {
  div.addEventListener('click', function() {
    // Toggle the 'active' class on the clicked div
    this.parentElement.classList.toggle('active');
    nested_dir = this.parentElement.getElementsByTagName("div");
    for (var i = 0; i < nested_dir.length; i++) {
      nested_dir[i].classList.remove("active");
    };
  });
});


// Add stuff that needs to be reset on load/reload here
window.onload = function () {
  for (var i = 0; i < coll.length; i++) {
    checkboxs = coll[i].getElementsByTagName("INPUT")
    for (var j = 0; j < checkboxs.length; j++) {
      checkboxs[j].checked = false;
    }
  }
  // Focus the left bar to the current active element
  const active_func = document.getElementsByClassName("active-tab") || [undefined];
  if (active_func[0]) {
    const left_tab = document.getElementsByClassName("left-tabs")[0];
    left_tab.scrollTop = active_func[0].offsetTop - left_tab.offsetTop;
  }
}

function exportQuery(key) {
  // Retrieve values from input fields
  var valuesToExport = {
    sourceInput1: document.getElementById('OldsourceInput1-' + key).value,
    sourceInput2: document.getElementById('OldsourceInput2-' + key).value,
    sourceInput3: document.getElementById('OldsourceInput3-' + key).value,
    sourceInput4: document.getElementById('OldsourceInput4-' + key).value,
    sourceInput5: document.getElementById('OldsourceInput5-' + key).value,
    sourceInput6: document.getElementById('OldsourceInput6-' + key).value
  };

  // Remove ".php" extension if present in sourceInput4
  if (valuesToExport.sourceInput4.endsWith('.php')) {
    valuesToExport.sourceInput4 = valuesToExport.sourceInput4.slice(0, -4);
  }

  // Convert values to JSON
  var jsonString = JSON.stringify(valuesToExport);

  // Create a Blob containing the JSON data
  var blob = new Blob([jsonString], { type: 'application/json' });

  // Create a link element
  var a = document.createElement('a');
  a.href = window.URL.createObjectURL(blob);

  a.download = 'exported_data_' + key + '.json'; // Set the filename for the downloaded file

  // Append the link to the document body and trigger a click event to start the download
  document.body.appendChild(a);
  a.click();

  // Clean up by removing the link from the document body
  document.body.removeChild(a);
}

// Function to handle file import
document.getElementById('importButton').addEventListener('click', function () {
  document.getElementById('importFile').click();
});

// Function to handle file selection
document.getElementById('importFile').addEventListener('change', function (event) {
  const file = event.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = function (e) {
    try {
      const importedData = JSON.parse(e.target.result);
      // Process imported data
      // Example: Fill form fields with imported data
      document.getElementById('sourceInput1').value = importedData.sourceInput1;
      document.getElementById('sourceInput2').value = importedData.sourceInput2;
      document.getElementById('sourceInput3').value = importedData.sourceInput3;
      document.getElementById('sourceInput4').value = importedData.sourceInput4;
      document.getElementById('sinkInput').value = importedData.sourceInput5;
      document.getElementById('sanitizationInput').value = importedData.sourceInput6;
      console.log(typeof importedData.sourceInput4)
      console.log(importedData.sourceInput4)
    } catch (error) {
      console.error('Error parsing JSON file:', error);
    }
  };
  reader.readAsText(file);
});

// Get all input fields
const inputs = document.querySelectorAll('.form-control');

// Add event listener to each input field
inputs.forEach(input => {
    input.addEventListener('input', function() {
        // Update localStorage with the input's value
        localStorage.setItem(input.id, input.value);
    });
});

// Populate input fields with values from localStorage on page load
window.addEventListener('load', function() {
    inputs.forEach(input => {
        const storedValue = localStorage.getItem(input.id);
        if (storedValue) {
            input.value = storedValue;
        }
    });
});

function submitForm() {
  const form = document.getElementById('securityForm');
  const formData = new FormData(form);

  fetch(form.action, {
      method: form.method,
      body: formData
  })
  .then(response => {
      if (response.ok) {
          // alert('Form submitted successfully!');
          clearForm();
      } else {
          throw new Error('Form submission failed');
      }
  })
  .catch(error => {
      console.error('Error submitting form:', error);
  });
}

function clearForm() {
  // alert('Form submitted successfully!');
  // Get all input fields
  const inputs = document.querySelectorAll('.form-control');

  // Clear the value of each input field
  inputs.forEach(input => {
      input.value = '';
      localStorage.removeItem(input.id); // Clear the corresponding localStorage value
  });
}
