// Wait for the DOM content to be fully loaded
document.addEventListener('DOMContentLoaded', function () {
    // Get the ul element containing running tasks
    const ulElement = document.getElementById('running-tasks-dropdown');
    // Count the number of tasks
    const numTasks = ulElement.getElementsByTagName('li').length;
    // Update the task counter display
    document.getElementById('task-counter').textContent = numTasks;

    // Hide the ulElement if it contains no li elements
    if (numTasks.length === 0) {
        ulElement.style.display = "none";
    }
});

// Retrieve pending tasks from localStorage or initialize an empty object
var keys = JSON.parse(window.localStorage.getItem("pendingTasks"))
if (!keys) {
    keys = {};
}

// Get the container for displaying running tasks
const working_tasks = document.getElementById("running-tasks-dropdown");

// Set the interval for polling server for task status
var pollInterval = 10000; //ms

// Iterate over pending tasks and display them
let taskNumber = 1; // Initialize a counter for task numbers
for (const [key, task_name] of Object.entries(keys)) {
    let new_task_name = document.createElement("li");
    // Append task number to the task name
    new_task_name.innerHTML = `${taskNumber}. ${task_name}`;
    new_task_name.id = key;
    working_tasks.appendChild(new_task_name);
    taskNumber++;

    // Start polling status for each task
    new Promise(resolve => pollStatus(key, resolve));
}

// Function to poll task status from the server
async function pollStatus(key, resolve) {
    // Fetch status update from server
    update = await fetch(`/status/${key}`, {
        method: "GET",
    });

    // Adjust the polling interval (example formula)
    pollInterval = 2.718281828 * (pollInterval ** 0.5772156649);
    
    // If task is completed
    if (update.status == 201) {
        // Get all processing tasks
        keys = JSON.parse(window.localStorage.getItem("pendingTasks"));
        
        // Mark completed task visually
        let completed_task = document.getElementById(`process-${key}`);
        if (completed_task) {
            completed_task.className += " completed";
        }
        


        // Add process counter circle
        const ulElement = document.getElementById('running-tasks-dropdown');
        const numTasks = ulElement.getElementsByTagName('li').length;
        document.getElementById('task-counter').textContent = numTasks;
        
        // Update task in uploaded files table
        let new_folder = JSON.parse(await update.text());
        if (typeof window.updateCompletedTaskInTable === "function") {
            updateCompletedTaskInTable(key, new_folder);
        }
        

        // alert
        flash_alert(`<b>• ${keys[key]} completed!</b>`, "completed", false);

        // location.reload();
        // Update local storage
        delete keys[key]
        window.localStorage.setItem("pendingTasks", JSON.stringify(keys));
        // Resolve with the response text
        resolve(new_folder);

    }
    else if (update.status == 410 || update.status == 404) {
        // Get all processing tasks
        keys = JSON.parse(window.localStorage.getItem("pendingTasks"));
        
        // Mark completed task visually
        let failed_task = document.getElementById(`process-${key}`);
        if (failed_task) {
            failed_task.className += " failed";
        }
        

        // Add process counter circle
        const ulElement = document.getElementById('running-tasks-dropdown');
        const numTasks = ulElement.getElementsByTagName('li').length;
        document.getElementById('task-counter').textContent = numTasks;
        
        // Remove process from uploaded files table 
        if (typeof window.updateCompletedTaskInTable === "function") {
            updateCompletedTaskInTable(key, undefined);
        }

        // alert
        let error_msg = JSON.parse(await update.text())["message"];
        flash_alert(`${keys[key]} failed</br>Error: ${error_msg}`, "failed", false);

        // location.reload();
        
        // Update local storage
        delete keys[key]
        window.localStorage.setItem("pendingTasks", JSON.stringify(keys));
        // Resolve with the response text
        resolve(error_msg);
    }
    else {
        // Continue polling
        setTimeout(() => pollStatus(key, resolve), pollInterval);
    };
}

// Define a global variable for the root URL
const $SCRIPT_ROOT = (window.location.port)? 
            `${window.location.protocol}//${window.location.hostname}:${window.location.port}`
            : `${window.location.protocol}//${window.location.hostname}`


// Function to display flash alerts
function flash_alert(message, category, clean) {
    if (typeof (clean) === "undefined") clean = true;
    if (clean) {
        remove_alerts();
    }
    var htmlString = 
        `<div class="alert ${category}" id="alert${taskNumber}">\
            <div class="alert-header">\
                <strong>Task Progress</strong>\
                <small>: Just Now</small>\
                    <span class="close" aria-hidden="true" onclick="remove_alerts(${taskNumber})">×</span>\
            </div>\
            <div class="alert-body">${message}</div>\
        </div>`;
    taskNumber++;
    let alert_list = document.getElementById("alerts");
    alert_list.innerHTML = htmlString + alert_list.innerHTML;
    alert_list.style.display = "block";
}

// Function to remove alerts
function remove_alerts(alertNumber) {
    if (!alertNumber) {
        let alert_list = document.getElementById("alerts");
        alert_list.innerHTML = "";
        return;
    }
    let alert_remove = document.getElementById(`alert${alertNumber}`);
    console.log(alert_remove);
    alert_remove.remove();
    return;
}

// Function to asynchronously post data
async function async_post(link, upload_id) {
    let post_url;
    if (link) {
        post_url = `${$SCRIPT_ROOT}/${link}`;
    }
    else {
        post_url = `${$SCRIPT_ROOT}/upload`;
    }
    console.log(post_url);
    if (upload_id) {
        file = document.getElementById(upload_id);
    }
    // Display info flash alert
    // Create a FormData object for file upload
    let upload_file = new FormData();
    
    upload_file.append("file", file.files[0]);
    // Send POST request for file upload
    const response_promise = fetch(post_url, {
        method: "POST",
        body: upload_file
    });
    // Await the response
    const response = await response_promise.then(r => r);
    if (response.status === 202) {
        // Extract the key from the response
        let key = await response.text();

        // Update pending tasks and local storage
        keys[key] = `${file.files[0].name}`;
        window.localStorage.setItem("pendingTasks", JSON.stringify(keys));
        // Add the task to the list
        let new_task_name = document.createElement("li")
        new_task_name.innerHTML = `${taskNumber}. ${keys[key]}`; // Append task number to the task name
        new_task_name.id = `process-${key}`;
        working_tasks.appendChild(new_task_name);

        // Add process counter circle
        const ulElement = document.getElementById('running-tasks-dropdown');
        const numTasks = ulElement.getElementsByTagName('li').length;
        document.getElementById('task-counter').textContent = numTasks;
        // location.reload();
        addPendingTasksToTable(key);

        // If upload successful, start polling task status
        // processing
        new Promise(resolve => pollStatus(key, resolve));
        window.location.href = window.location.href;
    }
    else {
        // Display error flash alert
        flash_alert("File upload failed", "failed");
    }

    // Await the resolution of the polling promise

}
