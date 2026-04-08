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
const downloadCsvBtn = document.getElementById("downloadCsvBtn");
const highConfidenceOnly = document.getElementById("highConfidenceOnly");
const confidenceHistogramEl = document.getElementById("confidenceHistogram");

const stageAlignment = document.getElementById("stage-alignment");
const stageRetrieval = document.getElementById("stage-retrieval");
const stageReasoning = document.getElementById("stage-reasoning");

let pollTimer = null;
let latestReport = null;
let latestHits = [];

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

function classifyHit(hit) {
  const provided = String(hit.validation_class || "").trim();
  if (provided) {
    return provided;
  }

  const confidence = Number(hit.final_confidence || 0);
  if (confidence >= 85) return "Confirmed ARG";
  if (confidence >= 70 || Boolean(hit.is_valid_hit)) return "Probable ARG";
  if (confidence >= 50) return "Review Required";
  return "Unlikely ARG";
}

function classSlug(label) {
  switch (label) {
    case "Confirmed ARG":
      return "class-confirmed";
    case "Probable ARG":
      return "class-probable";
    case "Review Required":
      return "class-review";
    default:
      return "class-unlikely";
  }
}

function formatValidationBadge(hit) {
  const confidence = Number(hit.final_confidence || 0);
  const confidenceText = Number.isFinite(confidence) ? `${confidence.toFixed(1)}%` : "0.0%";
  const label = classifyHit(hit);
  return `<span class="validation-pill ${classSlug(label)}">${label} · ${confidenceText}</span>`;
}

function histogramBucketLabel(idx) {
  const start = idx * 10;
  const end = start + 9;
  return `${start}-${end}`;
}

function renderConfidenceHistogram(hits) {
  if (!Array.isArray(hits) || hits.length === 0) {
    confidenceHistogramEl.className = "confidence-histogram empty";
    confidenceHistogramEl.textContent = "No confidence data available yet.";
    return;
  }

  const buckets = Array.from({ length: 10 }, () => 0);
  hits.forEach((hit) => {
    const value = Math.max(0, Math.min(100, Number(hit.final_confidence || 0)));
    const bucket = Math.min(9, Math.floor(value / 10));
    buckets[bucket] += 1;
  });

  const maxCount = Math.max(...buckets, 1);
  confidenceHistogramEl.className = "confidence-histogram";
  confidenceHistogramEl.innerHTML = buckets
    .map((count, idx) => {
      const heightPct = Math.max(6, (count / maxCount) * 100);
      return `
        <div class="hist-bar-wrap" title="${histogramBucketLabel(idx)}: ${count}">
          <div class="hist-bar" style="height:${heightPct}%"></div>
          <span class="hist-count">${count}</span>
          <span class="hist-label">${histogramBucketLabel(idx)}</span>
        </div>
      `;
    })
    .join("");
}

function hitKey(geneId, rawSubjectId) {
  return `${geneId || ""}::${rawSubjectId || ""}`;
}

function buildReasoningIndex(report) {
  const map = new Map();
  const entries = report && Array.isArray(report.results) ? report.results : [];
  entries.forEach((entry) => {
    const key = hitKey(entry.gene_id, entry.raw_subject_id);
    map.set(key, entry.validation || entry || {});
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
  downloadCsvBtn.disabled = latestHits.length === 0;
}

function resetOutputsForRun() {
  textSummaryEl.textContent = "Running pipeline... summary will appear here.";
  jsonReportEl.textContent = '{\n  "status": "running"\n}';
  downloadJsonBtn.disabled = true;
  downloadCsvBtn.disabled = true;
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
  latestHits = Array.isArray(hits) ? hits : [];
  renderConfidenceHistogram(latestHits);

  const visibleHits = highConfidenceOnly && highConfidenceOnly.checked
    ? latestHits.filter((hit) => Number(hit.final_confidence || 0) >= 70)
    : latestHits;

  hitCount.textContent = String(visibleHits.length);
  const reasoningIndex = buildReasoningIndex(report);

  if (visibleHits.length === 0) {
    resultsBody.innerHTML = `
      <tr class="empty-row">
        <td colspan="7">
          <div class="empty-state">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            <p>No hits match the current filter</p>
          </div>
        </td>
      </tr>`;
    return;
  }

  resultsBody.innerHTML = "";
  visibleHits.forEach((hit, i) => {
    const pct = Number(hit.identity_pct).toFixed(2);
    const tr  = document.createElement("tr");
    const key = hitKey(hit.gene_id, hit.raw_subject_id);
    const validation = reasoningIndex.get(key) || {};
    const reasoningText =
      hit.reasoning ||
      validation.reasoning ||
      "No LLM reasoning text available.";
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
      <td>${formatValidationBadge(hit)}</td>
      <td>
        <details class="reasoning-details">
          <summary>View</summary>
          <div class="reasoning-body">
            <p><strong>Class:</strong> ${escapeHtml(classifyHit(hit))}</p>
            <p><strong>Coverage:</strong> ${Number(hit.coverage_pct || 0).toFixed(2)}%</p>
            <p><strong>Alignment Confidence:</strong> ${Number(hit.alignment_confidence || 0).toFixed(2)}</p>
            <p><strong>LLM Confidence:</strong> ${Number(hit.llm_confidence || 0).toFixed(2)}</p>
            <p><strong>Final Confidence:</strong> ${Number(hit.final_confidence || 0).toFixed(2)}</p>
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

    if (stage === "reasoning" || stage === "fusion" || stage === "reporting") {
      stageAlignment.className = "stage-node complete";
      stageRetrieval.className = "stage-node complete";
      stageReasoning.className = "stage-node active";
      return;
    }

    if (stage === "scoring") {
      stageAlignment.className = "stage-node active";
      stageRetrieval.className = "stage-node blocked";
      stageReasoning.className = "stage-node blocked";
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
      const message = String(err.message || "Status check failed");
      if (message.toLowerCase().includes("job not found")) {
        setStatus(
          "error",
          "status_check",
          "Job record was lost after a server restart. Re-run the pipeline for this file.",
        );
      } else {
        setStatus("error", "status_check", message);
      }
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
  latestHits = [];
  renderConfidenceHistogram([]);
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

function buildCsv(hits) {
  const headers = [
    "gene_id",
    "identity_pct",
    "coverage_pct",
    "e_value",
    "alignment_score",
    "alignment_confidence",
    "llm_confidence",
    "final_confidence",
    "validation_class",
    "raw_subject_id",
    "resistance_summary",
    "drug_impacts",
    "reasoning",
  ];

  const escapeCsv = (value) => {
    const raw = String(value ?? "");
    if (raw.includes(",") || raw.includes('"') || raw.includes("\n")) {
      return `"${raw.replace(/"/g, '""')}"`;
    }
    return raw;
  };

  const rows = hits.map((hit) => [
    hit.gene_id,
    hit.identity_pct,
    hit.coverage_pct,
    hit.e_value,
    hit.alignment_score,
    hit.alignment_confidence,
    hit.llm_confidence,
    hit.final_confidence,
    classifyHit(hit),
    hit.raw_subject_id,
    hit.resistance_summary,
    Array.isArray(hit.drug_impacts) ? hit.drug_impacts.join("; ") : "",
    hit.reasoning,
  ]);

  const csvLines = [headers, ...rows].map((row) => row.map(escapeCsv).join(","));
  return csvLines.join("\n");
}

downloadCsvBtn.addEventListener("click", () => {
  if (!latestHits.length) {
    return;
  }

  const csvPayload = buildCsv(latestHits);
  const blob = new Blob([csvPayload], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "argusai-report.csv";
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
});

if (highConfidenceOnly) {
  highConfidenceOnly.addEventListener("change", () => {
    renderResults(latestHits, latestReport);
  });
}
