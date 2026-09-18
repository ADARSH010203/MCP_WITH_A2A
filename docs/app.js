const form = document.getElementById("task-form");
const endpointInput = document.getElementById("endpoint");
const sessionInput = document.getElementById("session-id");
const queryInput = document.getElementById("query");
const requestPreview = document.querySelector("#request-preview code");
const responsePreview = document.querySelector("#response-preview code");
const statusLabel = document.getElementById("playground-status");

function buildPayload() {
  return {
    jsonrpc: "2.0",
    id: "web-" + Date.now(),
    method: "tasks/send",
    params: {
      id: "web-" + Date.now(),
      sessionId: sessionInput.value.trim() || "web-demo-session",
      message: {
        role: "user",
        parts: [
          {
            type: "text",
            text: queryInput.value.trim()
          }
        ]
      },
      acceptedOutputModes: ["text"]
    }
  };
}

function refreshPreview() {
  const payload = buildPayload();
  requestPreview.textContent = JSON.stringify(payload, null, 2);
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    statusLabel.textContent = "Copied.";
  } catch (error) {
    statusLabel.textContent = "Copy is unavailable in this browser.";
  }
}

form.addEventListener("input", refreshPreview);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const endpoint = endpointInput.value.trim();
  const payload = buildPayload();

  if (!endpoint || !payload.params.message.parts[0].text) {
    statusLabel.textContent = "Endpoint and task are required.";
    return;
  }

  statusLabel.textContent = "Sending request...";
  responsePreview.textContent = "";

  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    const text = await response.text();
    let parsed;
    try {
      parsed = JSON.parse(text);
    } catch (error) {
      parsed = text;
    }

    responsePreview.textContent = typeof parsed === "string"
      ? parsed
      : JSON.stringify(parsed, null, 2);

    statusLabel.textContent = response.ok
      ? "Request completed."
      : "Server returned HTTP " + response.status + ".";
  } catch (error) {
    responsePreview.textContent = String(error);
    statusLabel.textContent = "Request failed. Check the endpoint, CORS and server status.";
  }
});

document.getElementById("copy-request").addEventListener("click", () => {
  copyText(requestPreview.textContent);
});

document.getElementById("clear-response").addEventListener("click", () => {
  responsePreview.textContent = "No response yet.";
  statusLabel.textContent = "Ready.";
});

refreshPreview();
