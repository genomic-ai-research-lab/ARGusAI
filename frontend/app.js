import { uploadFile, processJob, getStatus, getResults } from "./api.js?v=20260327-2";

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
const textSummaryEl = document.getElementById("textSummary");
const jsonReportEl  = document.getElementById("jsonReport");
const downloadJsonBtn = document.getElementById("downloadJsonBtn");

const stageAlignment = document.getElementById("stage-alignment");
const stageRetrieval = document.getElementById("stage-retrieval");
const stageReasoning = document.getElementById("stage-reasoning");

let pollTimer = null;
let latestReport = null;

// ── Helpers ───────────────────────────────────────────────────────────────────
function formatEValue(value) {
  return Number(value).toExponential(2);
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatValidationBadge(isValid, confidence) {
  const confidenceText = Number.isFinite(Number(confidence)) ? `${confidence}%` : "0%";
  if (isValid) {
    return `<span class="validation-pill valid">VALID · ${confidenceText}</span>`;
  }
  return `<span class="validation-pill invalid">NOT VALID · ${confidenceText}</span>`;
}

function hitKey(geneId, rawSubjectId) {
  return `${geneId || ""}::${rawSubjectId || ""}`;
}

function buildReasoningIndex(report) {
  const map = new Map();
  const entries = report && Array.isArray(report.results) ? report.results : [];
  entries.forEach((entry) => {
    const key = hitKey(entry.gene_id, entry.raw_subject_id);
    map.set(key, entry.validation || {});
  });
  return map;
}

function renderOutputs(report, textSummary) {
  latestReport = report || null;

  textSummaryEl.textContent = textSummary && textSummary.trim().length
    ? textSummary
    : "No natural-language summary returned for this run.";

  jsonReportEl.textContent = report
    ? JSON.stringify(report, null, 2)
    : '{\n  "message": "No JSON report returned for this run"\n}';

  downloadJsonBtn.disabled = !report;
}

function resetOutputsForRun() {
  textSummaryEl.textContent = "Running pipeline... summary will appear here.";
  jsonReportEl.textContent = '{\n  "status": "running"\n}';
  downloadJsonBtn.disabled = true;
  latestReport = null;
}

/** Return a colour class for identity percentage */
function identityClass(pct) {
  if (pct >= 90) return "style=\"color:var(--accent-green);\"";
  if (pct >= 70) return "style=\"color:var(--accent-teal);\"";
  if (pct >= 50) return "style=\"color:var(--accent-amber);\"";
  return "style=\"color:var(--accent-red);\"";
}

// ── Render results ────────────────────────────────────────────────────────────
function renderResults(hits, report = null) {
  hitCount.textContent = String(hits.length);
  const reasoningIndex = buildReasoningIndex(report);

  if (hits.length === 0) {
    resultsBody.innerHTML = `
      <tr class="empty-row">
        <td colspan="7">
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
    const key = hitKey(hit.gene_id, hit.raw_subject_id);
    const validation = reasoningIndex.get(key) || {};
    const reasoningText = validation.reasoning || "No LLM reasoning text available.";
    const resistanceSummary = hit.resistance_summary || validation.resistance_summary || "No summary available.";
    const drugImpacts = Array.isArray(hit.drug_impacts) ? hit.drug_impacts : [];
    const impactText = drugImpacts.length ? drugImpacts.join(", ") : "n/a";
    const limitationsAndFixes =
      hit.limitations_and_fixes ||
      validation.limitations_and_fixes ||
      "No limitations/fixes explanation available.";

    tr.style.animationDelay = `${i * 40}ms`;
    tr.innerHTML = `
      <td>${escapeHtml(hit.gene_id)}</td>
      <td ${identityClass(Number(pct))}>${pct}%</td>
      <td>${formatEValue(hit.e_value)}</td>
      <td>${Number(hit.alignment_score).toFixed(2)}</td>
      <td title="${escapeHtml(hit.raw_subject_id)}">${escapeHtml(hit.raw_subject_id)}</td>
      <td>${formatValidationBadge(hit.is_valid_hit, hit.confidence)}</td>
      <td>
        <details class="reasoning-details">
          <summary>View</summary>
          <div class="reasoning-body">
            <p><strong>Summary:</strong> ${escapeHtml(resistanceSummary)}</p>
            <p><strong>Drug Impacts:</strong> ${escapeHtml(impactText)}</p>
            <p><strong>Reasoning:</strong> ${escapeHtml(reasoningText)}</p>
            <p><strong>Limitations & Fixes:</strong> ${escapeHtml(limitationsAndFixes)}</p>
          </div>
        </details>
      </td>
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

  setStageBadges(status, stage);
}

function setStageBadges(status, stage) {
  // Reset all
  stageAlignment.className = "stage-node";
  stageRetrieval.className = "stage-node blocked";
  stageReasoning.className = "stage-node blocked";

  if (status === "running" || status === "pending") {
    if (stage === "retrieval") {
      stageAlignment.className = "stage-node complete";
      stageRetrieval.className = "stage-node active";
      return;
    }

    if (stage === "reasoning") {
      stageAlignment.className = "stage-node complete";
      stageRetrieval.className = "stage-node complete";
      stageReasoning.className = "stage-node active";
      return;
    }

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
        renderResults(results.hits, results.report);
        renderOutputs(results.report, results.text_summary);
        startBtn.disabled = false;
        startBtn.querySelector("span").textContent = "Run Pipeline";
      }

      if (status.status === "error") {
        clearInterval(pollTimer);
        startBtn.disabled = false;
        startBtn.querySelector("span").textContent = "Run Pipeline";
      }
    } catch (err) {
      clearInterval(pollTimer);
      setStatus("error", "status_check", err.message);
      startBtn.disabled = false;
      startBtn.querySelector("span").textContent = "Run Pipeline";
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
      <td colspan="7">
        <div class="empty-state">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <p>Running pipeline — results will appear here</p>
        </div>
      </td>
    </tr>`;
  hitCount.textContent = "0";
  resetOutputsForRun();

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
    startBtn.querySelector("span").textContent = "Run Pipeline";
  }
});

downloadJsonBtn.addEventListener("click", () => {
  if (!latestReport) {
    return;
  }

  const payload = JSON.stringify(latestReport, null, 2);
  const blob = new Blob([payload], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "argusai-report.json";
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
});
