const API_BASE = window.API_BASE || "http://127.0.0.1:8000";

export async function uploadFile(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/upload`, { method: "POST", body: form });
  if (!res.ok) {
    throw new Error((await res.json()).detail || "Upload failed");
  }
  return res.json();
}

export async function processJob(jobId, evalue, program) {
  const res = await fetch(`${API_BASE}/process/${jobId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ evalue, program }),
  });
  if (!res.ok) {
    throw new Error((await res.json()).detail || "Process start failed");
  }
  return res.json();
}

export async function getStatus(jobId) {
  const res = await fetch(`${API_BASE}/status/${jobId}`);
  if (!res.ok) {
    throw new Error((await res.json()).detail || "Status check failed");
  }
  return res.json();
}

export async function getResults(jobId) {
  const res = await fetch(`${API_BASE}/results/${jobId}`);
  if (!res.ok) {
    throw new Error((await res.json()).detail || "Results fetch failed");
  }
  return res.json();
}
