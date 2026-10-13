/* global CSInterface */
(function () {
  const cs = new CSInterface();
  const STORAGE_KEY = "neurocut.apiUrl";

  const apiUrlInput = document.getElementById("apiUrl");
  const mediaPathInput = document.getElementById("mediaPath");
  const promptInput = document.getElementById("prompt");
  const generateBtn = document.getElementById("generateBtn");
  const applyBtn = document.getElementById("applyBtn");
  const browseBtn = document.getElementById("browseBtn");
  const statusBox = document.getElementById("statusBox");
  const progressBar = document.getElementById("progressBar");
  const jobInfo = document.getElementById("jobInfo");

  let currentJobId = null;
  let editPlanPayload = null;
  let pollTimer = null;

  function loadSettings() {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      apiUrlInput.value = saved;
    }
  }

  function saveSettings() {
    localStorage.setItem(STORAGE_KEY, apiUrlInput.value.trim());
  }

  function setStatus(text, mode) {
    statusBox.textContent = text;
    statusBox.className = "status " + (mode || "idle");
  }

  function setProgress(percent) {
    const value = Math.max(0, Math.min(100, percent || 0));
    progressBar.style.width = value + "%";
  }

  function apiBase() {
    return apiUrlInput.value.trim().replace(/\/$/, "");
  }

  function evalHost(script) {
    return new Promise((resolve, reject) => {
      cs.evalScript(script, (result) => {
        if (result === "EvalScript error.") {
          reject(new Error("ExtendScript error"));
          return;
        }
        resolve(result);
      });
    });
  }

  async function browseMedia() {
    try {
      const result = await evalHost("browseMediaFile()");
      if (result) {
        mediaPathInput.value = result;
      }
    } catch (error) {
      setStatus("Failed to open file picker: " + error.message, "error");
    }
  }

  async function checkHealth() {
    const response = await fetch(apiBase() + "/plugin/health");
    if (!response.ok) {
      throw new Error("API unavailable (" + response.status + ")");
    }
    return response.json();
  }

  async function startJob() {
    saveSettings();
    const localPath = mediaPathInput.value.trim();
    const prompt = promptInput.value.trim();

    if (!localPath) {
      setStatus("Enter the path to the video file.", "error");
      return;
    }
    if (!prompt) {
      setStatus("Enter the edit brief.", "error");
      return;
    }

    generateBtn.disabled = true;
    applyBtn.disabled = true;
    editPlanPayload = null;
    currentJobId = null;
    setProgress(0);
    setStatus("Connecting to API...", "running");

    try {
      await checkHealth();
      setStatus("Starting processing...", "running");

      const response = await fetch(apiBase() + "/plugin/jobs/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ local_path: localPath, prompt }),
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || "Start failed (" + response.status + ")");
      }

      const payload = await response.json();
      currentJobId = payload.job_id;
      jobInfo.textContent = "Job: " + currentJobId;
      pollStatus();
    } catch (error) {
      setStatus(error.message, "error");
      generateBtn.disabled = false;
    }
  }

  async function pollStatus() {
    if (!currentJobId) {
      return;
    }

    try {
      const response = await fetch(apiBase() + "/plugin/jobs/" + currentJobId + "/status");
      if (!response.ok) {
        throw new Error("Failed to get status (" + response.status + ")");
      }

      const payload = await response.json();
      const pipeline = payload.pipeline;
      setProgress(pipeline.progress_percent || 0);
      setStatus(pipeline.message || pipeline.stage, "running");

      if (pipeline.stage === "failed") {
        throw new Error(pipeline.error || "Processing failed");
      }

      if (pipeline.stage === "completed") {
        await loadEditPlan();
        return;
      }

      pollTimer = setTimeout(pollStatus, 2000);
    } catch (error) {
      setStatus(error.message, "error");
      generateBtn.disabled = false;
    }
  }

  async function loadEditPlan() {
    const response = await fetch(apiBase() + "/plugin/jobs/" + currentJobId + "/edit-plan");
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || "Failed to load edit plan");
    }

    editPlanPayload = await response.json();
    setProgress(100);
    setStatus(
      "Done: " + editPlanPayload.clip_count + " clips, " + editPlanPayload.marker_count + " markers",
      "done"
    );
    applyBtn.disabled = false;
    generateBtn.disabled = false;
  }

  async function applyToTimeline() {
    if (!editPlanPayload) {
      setStatus("Generate an edit plan first.", "error");
      return;
    }

    applyBtn.disabled = true;
    setStatus("Applying to Premiere timeline...", "running");

    try {
      const escapedPayload = JSON.stringify(JSON.stringify(editPlanPayload));
      const result = await evalHost("applyEditPlan(" + escapedPayload + ")");
      const parsed = JSON.parse(result || "{}");

      if (!parsed.ok) {
        throw new Error(parsed.error || "ExtendScript returned an error");
      }

      setStatus("Edit applied: " + (parsed.sequence || "new sequence"), "done");
    } catch (error) {
      setStatus("Apply failed: " + error.message, "error");
    } finally {
      applyBtn.disabled = false;
    }
  }

  browseBtn.addEventListener("click", browseMedia);
  generateBtn.addEventListener("click", startJob);
  applyBtn.addEventListener("click", applyToTimeline);

  loadSettings();
})();
