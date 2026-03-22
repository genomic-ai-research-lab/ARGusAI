import { uploadFile, processJob, getStatus, getResults } from "./api.js";

// ── DOM refs ──────────────────────────────────────────────────────────────────
const uploadInput   = document.getElementById("fastaFile");
const evalueInput   = document.getElementById("evalue");
const programInput  = document.getElementById("program");
const startBtn      = document.getElementById("startBtn");

const statusText    = document.getElementById("statusText");
const stageText     = document.getElementById("stageText");
const errorBox      = document.getElementById("errorBox");
const errorText     = document.getElementById("errorText");

const resultsBody   = document.getElementById("resultsBody");
const hitCount      = document.getElementById("hitCount");

const stageAlignment = document.getElementById("stage-alignment");
const stageRetrieval = document.getElementById("stage-retrieval");
const stageReasoning = document.getElementById("stage-reasoning");

let pollTimer = null;

// ── Helpers ───────────────────────────────────────────────────────────────────
function formatEValue(value) {
  return Number(value).toExponential(2);
}

/** Return a colour class for identity percentage */
function identityClass(pct) {
  if (pct >= 90) return "style=\"color:var(--accent-green);\"";
  if (pct >= 70) return "style=\"color:var(--accent-teal);\"";
  if (pct >= 50) return "style=\"color:var(--accent-amber);\"";
  return "style=\"color:var(--accent-red);\"";
}

// ── Render results ────────────────────────────────────────────────────────────
function renderResults(hits) {
  hitCount.textContent = String(hits.length);

  if (hits.length === 0) {
    resultsBody.innerHTML = `
      <tr class="empty-row">
        <td colspan="5">
          <div class="empty-state">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            <p>No hits found for this query</p>
          </div>
        </td>
      </tr>`;
    return;
  }

  resultsBody.innerHTML = "";
  hits.forEach((hit, i) => {
    const pct = Number(hit.identity_pct).toFixed(2);
    const tr  = document.createElement("tr");
    tr.style.animationDelay = `${i * 40}ms`;
    tr.innerHTML = `
      <td>${hit.gene_id}</td>
      <td ${identityClass(Number(pct))}>${pct}%</td>
      <td>${formatEValue(hit.e_value)}</td>
      <td>${Number(hit.alignment_score).toFixed(2)}</td>
      <td title="${hit.raw_subject_id}">${hit.raw_subject_id}</td>
    `;
    resultsBody.appendChild(tr);
  });
}

// ── Status display ────────────────────────────────────────────────────────────
function setStatus(status, stage, error = "") {
  // Status dot + text
  const dotClass = ["idle","pending","running","complete","error"].includes(status)
    ? status : "idle";

  statusText.innerHTML = `<span class="status-dot ${dotClass}"></span>${status}`;
  stageText.textContent = stage;

  // Error box
  if (error) {
    errorText.textContent = error;
    errorBox.style.display = "flex";
  } else {
    errorBox.style.display = "none";
    errorText.textContent  = "";
  }

  setStageBadges(status);
}

function setStageBadges(status) {
  // Reset all
  stageAlignment.className = "stage-node";
  stageRetrieval.className = "stage-node blocked";
  stageReasoning.className = "stage-node blocked";

  if (status === "running" || status === "pending") {
    stageAlignment.className = "stage-node active";
    return;
  }

  if (status === "complete") {
    stageAlignment.className = "stage-node complete";
    stageRetrieval.className = "stage-node complete";
    stageReasoning.className = "stage-node complete";
    return;
  }

  if (status === "error") {
    stageAlignment.className = "stage-node";
  }
}

// ── Polling ───────────────────────────────────────────────────────────────────
async function pollStatusAndResults(jobId) {
  if (pollTimer) clearInterval(pollTimer);

  pollTimer = setInterval(async () => {
    try {
      const status = await getStatus(jobId);
      setStatus(status.status, status.stage, status.error || "");

      if (status.status === "complete") {
        clearInterval(pollTimer);
        const results = await getResults(jobId);
        renderResults(results.hits);
        startBtn.disabled = false;
        startBtn.querySelector("span").textContent = "Run Alignment";
      }

      if (status.status === "error") {
        clearInterval(pollTimer);
        startBtn.disabled = false;
        startBtn.querySelector("span").textContent = "Run Alignment";
      }
    } catch (err) {
      clearInterval(pollTimer);
      setStatus("error", "status_check", err.message);
      startBtn.disabled = false;
      startBtn.querySelector("span").textContent = "Run Alignment";
    }
  }, 2000);
}

// ── Start button ──────────────────────────────────────────────────────────────
startBtn.addEventListener("click", async () => {
  const file = uploadInput.files[0];
  if (!file) {
    setStatus("error", "upload", "Please choose a FASTA file first.");
    return;
  }

  const evalue  = Number(evalueInput.value);
  const program = programInput.value;

  // Reset results
  resultsBody.innerHTML = `
    <tr class="empty-row">
      <td colspan="5">
        <div class="empty-state">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <p>Running alignment — results will appear here</p>
        </div>
      </td>
    </tr>`;
  hitCount.textContent = "0";

  // Disable button while running
  startBtn.disabled = true;
  startBtn.querySelector("span").textContent = "Running…";

  setStatus("pending", "upload", "");

  try {
    const upload = await uploadFile(file);
    setStatus("pending", "queued", "");

    await processJob(upload.job_id, evalue, program);
    await pollStatusAndResults(upload.job_id);
  } catch (err) {
    setStatus("error", "process", err.message);
    startBtn.disabled = false;
    startBtn.querySelector("span").textContent = "Run Alignment";
  }
});
