import { uploadFile, processJob, getStatus, getResults } from "./api.js";

const uploadInput = document.getElementById("fastaFile");
const evalueInput = document.getElementById("evalue");
const programInput = document.getElementById("program");
const startBtn = document.getElementById("startBtn");
const statusText = document.getElementById("statusText");
const stageText = document.getElementById("stageText");
const errorText = document.getElementById("errorText");
const resultsBody = document.getElementById("resultsBody");
const hitCount = document.getElementById("hitCount");
const stageAlignment = document.getElementById("stage-alignment");
const stageRetrieval = document.getElementById("stage-retrieval");
const stageReasoning = document.getElementById("stage-reasoning");

let pollTimer = null;

function formatEValue(value) {
  return Number(value).toExponential(2);
}

function renderResults(hits) {
  resultsBody.innerHTML = "";
  hitCount.textContent = String(hits.length);

  hits.forEach((hit) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${hit.gene_id}</td>
      <td>${Number(hit.identity_pct).toFixed(2)}</td>
      <td>${formatEValue(hit.e_value)}</td>
      <td>${Number(hit.alignment_score).toFixed(2)}</td>
      <td>${hit.raw_subject_id}</td>
    `;
    resultsBody.appendChild(tr);
  });
}

function setStatus(status, stage, error = "") {
  statusText.textContent = status;
  stageText.textContent = stage;
  errorText.textContent = error;
  setStageBadges(status);
}

function setStageBadges(status) {
  stageAlignment.className = "stage-item";
  stageRetrieval.className = "stage-item blocked";
  stageReasoning.className = "stage-item blocked";

  if (status === "running" || status === "pending") {
    stageAlignment.className = "stage-item active";
    return;
  }

  if (status === "complete") {
    stageAlignment.className = "stage-item complete";
    return;
  }

  if (status === "error") {
    stageAlignment.className = "stage-item";
  }
}

async function pollStatusAndResults(jobId) {
  if (pollTimer) {
    clearInterval(pollTimer);
  }

  pollTimer = setInterval(async () => {
    try {
      const status = await getStatus(jobId);
      setStatus(status.status, status.stage, status.error || "");

      if (status.status === "complete") {
        clearInterval(pollTimer);
        const results = await getResults(jobId);
        renderResults(results.hits);
      }

      if (status.status === "error") {
        clearInterval(pollTimer);
      }
    } catch (error) {
      clearInterval(pollTimer);
      setStatus("error", "status_check", error.message);
    }
  }, 2000);
}

startBtn.addEventListener("click", async () => {
  const file = uploadInput.files[0];
  if (!file) {
    setStatus("error", "upload", "Please choose a FASTA file first.");
    return;
  }

  const evalue = Number(evalueInput.value);
  const program = programInput.value;

  resultsBody.innerHTML = "";
  hitCount.textContent = "0";
  setStatus("pending", "upload", "");

  try {
    const upload = await uploadFile(file);
    setStatus("pending", "queued", "");

    await processJob(upload.job_id, evalue, program);
    await pollStatusAndResults(upload.job_id);
  } catch (error) {
    setStatus("error", "process", error.message);
  }
});
