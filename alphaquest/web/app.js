"use strict";

const $ = (selector) => document.querySelector(selector);
const fmt = new Intl.NumberFormat("en-US");
let selectedFile = null;
let validated = null;
let generation = 0;
let busy = false;
let datasets = [];
const deleting = new Set();
const MAX_BYTES = 1_000_000_000;

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function bytes(value) {
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(2)} GB`;
  return value >= 1024 * 1024
    ? `${(value / 1024 / 1024).toFixed(1)} MiB`
    : `${(value / 1024).toFixed(1)} KiB`;
}

function date(value) {
  return value.replace("T", " ").replace("Z", " UTC");
}
function spacing(dataset) {
  if (dataset.interval_kind !== "regular")
    return dataset.interval_kind === "single row" ? "Single row" : "Irregular";
  const s = dataset.interval_seconds;
  if (s % 86400 === 0) return `${s / 86400} day`;
  if (s % 3600 === 0) return `${s / 3600} hr`;
  if (s % 60 === 0) return `${s / 60} min`;
  return `${s} sec`;
}

function invalidate() {
  generation++;
  validated = null;
  $("#validation-result").hidden = true;
  $("#validation-result").replaceChildren();
  $("#operation-progress").hidden = true;
  $("#validate-button").disabled = !selectedFile || busy;
  $("#form-hint").textContent = selectedFile
    ? "Ready for a full-file check."
    : "Choose a file to get started.";
}

function pickFile(file) {
  if (busy || !file) return;
  selectedFile = file;
  $("#file-label").textContent = file.name;
  $("#file-hint").textContent =
    `${bytes(file.size)} · Click to choose another file`;
  $("#dataset-name").value = file.name.replace(/\.csv$/i, "").slice(0, 120);
  invalidate();
}

function setBusy(value, action) {
  busy = value;
  if (value)
    $("#form-hint").textContent =
      action === "Saving…"
        ? "Saving your dataset…"
        : "Checking the complete CSV…";
  document.body.classList.toggle("busy", value);
  for (const input of document.querySelectorAll(
    "#upload-form input, #upload-form select",
  ))
    input.disabled = value;
  $("#validate-button").disabled = value || !selectedFile;
  $("#validate-button").textContent = value ? action : "Validate CSV →";
  const save = $("#save-button");
  if (save) save.disabled = value;
}

function showProgress(state, started, saving) {
  const labels = {
    uploading: "Uploading CSV",
    waiting: "Waiting for server",
    hashing: "Scanning file",
    validating: saving ? "Revalidating rows before save" : "Validating rows",
    saving: "Saving dataset",
    committing: "Finalizing save",
    done: saving ? "Dataset saved" : "Validation complete",
    failed: saving ? "Save failed" : "Validation failed",
  };
  const panel = $("#operation-progress");
  panel.hidden = false;
  panel.classList.toggle("failed", state.stage === "failed");
  $("#progress-title").textContent = labels[state.stage] || "Processing CSV";
  const determinate =
    state.total_bytes > 0 &&
    !["waiting", "committing", "failed"].includes(state.stage);
  const percent = determinate
    ? Math.min(100, (state.completed_bytes / state.total_bytes) * 100)
    : null;
  $("#progress-percent").textContent =
    percent === null ? "" : `${Math.floor(percent)}%`;
  const bar = $("#progress-bar");
  bar.hidden = state.stage === "failed";
  if (percent === null) bar.removeAttribute("value");
  else bar.value = percent;
  const details = [];
  if (["validating", "saving", "committing", "done"].includes(state.stage))
    details.push(
      `${fmt.format(state.rows_checked || 0)} rows ${state.stage === "validating" ? "checked" : "validated"}`,
    );
  if (determinate)
    details.push(
      `${bytes(state.completed_bytes)} / ${bytes(state.total_bytes)}`,
    );
  if (state.stage === "waiting")
    details.push("Upload sent. Waiting for processing to start.");
  if (state.stage === "committing")
    details.push("Writing the final database transaction.");
  $("#progress-detail").textContent = details.join(" · ");
  const seconds = Math.floor((performance.now() - started) / 1000);
  $("#progress-elapsed").textContent =
    seconds < 60
      ? `${seconds}s elapsed`
      : `${Math.floor(seconds / 60)}m ${seconds % 60}s elapsed`;
}

function upload(path) {
  const saving = path === "/api/datasets";
  const operationId = crypto.randomUUID();
  const started = performance.now();
  const params = new URLSearchParams({
    filename: selectedFile.name,
    source_timezone: $("#source-timezone").value.trim(),
    progress_id: operationId,
  });
  if (saving) {
    params.set("name", $("#dataset-name").value.trim());
    params.set("symbol", $("#symbol").value.trim());
  }
  let current = {
    stage: "uploading",
    completed_bytes: 0,
    total_bytes: selectedFile.size,
    rows_checked: 0,
  };
  const paint = (state) => {
    current = state;
    showProgress(state, started, saving);
  };
  paint(current);
  $("#operation-progress").scrollIntoView({
    block: "nearest",
    behavior: "smooth",
  });
  return new Promise((resolve, reject) => {
    let finished = false;
    let timer;
    const poll = async () => {
      try {
        const response = await fetch(`/api/progress/${operationId}`, {
          cache: "no-store",
        });
        if (response.ok && !finished) {
          const state = await response.json();
          if (finished) return;
          if (state.stage === "uploading") {
            if (current.stage === "uploading")
              paint({
                ...current,
                completed_bytes: Math.max(
                  current.completed_bytes,
                  state.completed_bytes,
                ),
              });
          } else if (!["done", "failed"].includes(state.stage)) paint(state);
        }
      } catch {
        // The main request still determines success or failure if polling fails.
      }
      if (!finished) {
        showProgress(current, started, saving);
        timer = setTimeout(poll, 500);
      }
    };
    const finish = (result, error) => {
      finished = true;
      clearTimeout(timer);
      paint({
        stage: error ? "failed" : "done",
        completed_bytes: result?.bytes || 0,
        total_bytes: result?.bytes || selectedFile.size,
        rows_checked: result?.row_count || current.rows_checked,
      });
      if (error) reject(error);
      else resolve(result);
    };
    const request = new XMLHttpRequest();
    request.open("POST", `${path}?${params}`);
    request.setRequestHeader("Content-Type", "text/csv");
    request.upload.onprogress = (event) => {
      if (current.stage === "uploading")
        paint({
          ...current,
          completed_bytes: event.loaded,
          total_bytes: event.lengthComputable ? event.total : selectedFile.size,
        });
    };
    request.upload.onload = () => {
      if (current.stage === "uploading")
        paint({ ...current, stage: "waiting" });
    };
    request.onload = () => {
      let result;
      try {
        result = JSON.parse(request.responseText);
      } catch {
        finish(null, {
          detail: `Server returned HTTP ${request.status}. Try again.`,
        });
        return;
      }
      if (request.status >= 200 && request.status < 300) finish(result, null);
      else finish(null, result);
    };
    request.onerror = () =>
      finish(null, {
        detail:
          "The server connection was interrupted. Reload the library to check whether a save completed before trying again.",
      });
    request.onabort = () =>
      finish(null, {
        detail:
          "The upload was interrupted. Reload the library to check its status.",
      });
    request.send(selectedFile);
    timer = setTimeout(poll, 200);
  });
}

function resultBox(className, title) {
  const box = node("div", `validation-box ${className}`);
  box.append(node("div", "validation-title", title));
  $("#validation-result").replaceChildren(box);
  $("#validation-result").hidden = false;
  return box;
}

function showError(error) {
  const box = resultBox("error", "Dataset needs attention");
  let message =
    typeof error.detail === "string"
      ? error.detail
      : error.message ||
        "The request failed. Check the server connection and try again.";
  box.append(node("p", "", message));
  const errors =
    error.errors ||
    (Array.isArray(error.detail)
      ? error.detail.map((e) => ({ column: e.loc?.at(-1), message: e.msg }))
      : []);
  if (errors.length) {
    const list = node("ul");
    for (const e of errors)
      list.append(
        node(
          "li",
          "",
          `${e.line ? `Line ${e.line}` : "File"}${e.column ? ` · ${e.column}` : ""}: ${e.message}`,
        ),
      );
    box.append(list);
  }
  if (error.truncated)
    box.append(
      node(
        "p",
        "",
        "Showing the first 20 errors. Fix them and validate again to check the full file.",
      ),
    );
}

function previewTable(dataset) {
  const wrap = node("div", "table-scroll preview-table");
  const table = node("table");
  const head = node("thead");
  const header = node("tr");
  const columns = dataset.columns.includes("Date")
    ? [...dataset.columns, "datetime"]
    : dataset.columns;
  for (const column of columns) {
    const th = node(
      "th",
      "",
      column === "datetime" ? "datetime (UTC)" : column,
    );
    th.scope = "col";
    header.append(th);
  }
  head.append(header);
  const body = node("tbody");
  for (const row of dataset.preview) {
    const tr = node("tr");
    for (const column of columns) tr.append(node("td", "", row[column]));
    body.append(tr);
  }
  table.append(head, body);
  wrap.append(table);
  return wrap;
}

function warnings(parent, dataset) {
  for (const warning of dataset.warnings)
    parent.append(node("div", "warning", warning));
}

function showValidation(dataset) {
  const box = resultBox("", "✓  Validation passed");
  box.append(
    node(
      "p",
      "",
      "All rows passed the CSV checks. Review the preview, then save this dataset to your library.",
    ),
  );
  const summary = node("div", "result-summary");
  for (const text of [
    `${fmt.format(dataset.row_count)} bars`,
    `${spacing(dataset)} spacing`,
    `${bytes(dataset.bytes)}`,
  ])
    summary.append(node("span", "", text));
  box.append(summary);
  warnings(box, dataset);
  box.append(
    node(
      "span",
      "preview-label",
      `FIRST ${dataset.preview.length} ROWS · ${dataset.columns.includes("Date") ? "SOURCE TIME + UTC" : "UTC"}`,
    ),
    previewTable(dataset),
  );
  const actions = node("div", "result-actions");
  actions.append(node("span", "small muted", "Validated. Not yet saved."));
  const button = node("button", "button primary", "Save dataset ↓");
  button.id = "save-button";
  button.type = "button";
  button.addEventListener("click", saveDataset);
  actions.append(button);
  box.append(actions);
}

async function saveDataset() {
  if (busy || !validated || !$("#upload-form").reportValidity()) return;
  setBusy(true, "Saving…");
  try {
    const saved = await upload("/api/datasets");
    validated = null;
    const box = resultBox("saved", "✓  Dataset saved");
    box.dataset.savedDatasetId = saved.id;
    box.append(
      node(
        "p",
        "",
        `${saved.name} is now in your library. The original CSV and generated metadata are stored together.`,
      ),
    );
    const actions = node("div", "result-actions");
    const open = node("button", "button secondary", "View dataset →");
    open.type = "button";
    open.addEventListener("click", () => showDetails(saved));
    actions.append(
      node("span", "small muted", `${fmt.format(saved.row_count)} bars saved`),
      open,
    );
    box.append(actions);
    await loadLibrary();
    $("#form-hint").textContent = "Saved. Choose another CSV to continue.";
  } catch (error) {
    validated = null;
    showError(error);
  } finally {
    setBusy(false);
  }
}

function deleteButton(dataset) {
  const button = node("button", "button danger", "Delete");
  button.type = "button";
  button.dataset.deleteId = dataset.id;
  button.setAttribute("aria-label", `Delete ${dataset.name}`);
  button.disabled = deleting.has(dataset.id);
  button.addEventListener("click", () => deleteDataset(dataset));
  return button;
}

async function deleteDataset(dataset) {
  if (deleting.has(dataset.id)) return;
  if (
    !window.confirm(
      `Delete “${dataset.name}”?\n\nThis removes its saved CSV and metadata from your library. This cannot be undone.`,
    )
  )
    return;
  deleting.add(dataset.id);
  for (const button of document.querySelectorAll("[data-delete-id]")) {
    if (button.dataset.deleteId === dataset.id) button.disabled = true;
  }
  $("#library-status").textContent = "";
  try {
    const response = await fetch(`/api/datasets/${dataset.id}`, {
      method: "DELETE",
    });
    // Another tab may already have deleted it; synchronize the visible library.
    if (!response.ok && response.status !== 404)
      throw new Error(`HTTP ${response.status}`);
    datasets = datasets.filter((item) => item.id !== dataset.id);
    renderLibrary();
    if ($("#dataset-dialog").dataset.datasetId === dataset.id)
      $("#dataset-dialog").close();
    if (
      $("#validation-result .validation-box")?.dataset.savedDatasetId ===
      dataset.id
    )
      invalidate();
  } catch {
    $("#library-status").textContent =
      `Could not delete “${dataset.name}”. Check the server connection and try again.`;
  } finally {
    deleting.delete(dataset.id);
    for (const button of document.querySelectorAll("[data-delete-id]")) {
      if (button.dataset.deleteId === dataset.id) button.disabled = false;
    }
  }
}

function renderLibrary() {
  const total = datasets.reduce((sum, dataset) => sum + dataset.row_count, 0);
  $("#dataset-count").textContent = fmt.format(datasets.length);
  $("#nav-count").textContent = datasets.length;
  $("#library-count").textContent = datasets.length;
  $("#bar-count").textContent = fmt.format(total);
  const library = $("#library");
  library.replaceChildren();
  if (!datasets.length) {
    const empty = node("div", "empty-state");
    empty.append(
      node("span", "empty-icon", "▤"),
      node("strong", "", "A clean start for your next idea"),
      node("p", "", "Upload and validate a CSV to add your first dataset."),
    );
    library.append(empty);
    return;
  }
  const wrap = node("div", "table-scroll");
  const table = node("table", "library-table");
  const head = node("thead");
  const header = node("tr");
  for (const title of [
    "Dataset",
    "Bars",
    "Date range · UTC",
    "Spacing",
    "Status",
    "CSV",
    "Actions",
  ]) {
    const th = node("th", "", title);
    th.scope = "col";
    header.append(th);
  }
  head.append(header);
  const body = node("tbody");
  for (const dataset of datasets) {
    const tr = node("tr");
    const title = node("td");
    const open = node("button", "dataset-link", dataset.name);
    open.type = "button";
    open.addEventListener("click", () => showDetails(dataset));
    title.append(
      open,
      node(
        "span",
        "dataset-sub",
        [dataset.symbol, dataset.filename].filter(Boolean).join(" · "),
      ),
    );
    const range = node("td", "", dataset.start.slice(0, 10));
    range.append(node("span", "dataset-sub", `to ${dataset.end.slice(0, 10)}`));
    const status = node("td");
    status.append(node("span", "pill success", "✓ Validated"));
    const downloadCell = node("td");
    const download = node("a", "row-download", "↓");
    download.href = `/api/datasets/${dataset.id}/csv`;
    download.setAttribute("aria-label", `Download ${dataset.name}`);
    downloadCell.append(download);
    const actions = node("td");
    actions.append(deleteButton(dataset));
    tr.append(
      title,
      node("td", "", fmt.format(dataset.row_count)),
      range,
      node("td", "", spacing(dataset)),
      status,
      downloadCell,
      actions,
    );
    body.append(tr);
  }
  table.append(head, body);
  wrap.append(table);
  library.append(wrap);
}

async function loadLibrary() {
  try {
    const response = await fetch("/api/datasets");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    datasets = await response.json();
    $("#library-status").textContent = "";
    renderLibrary();
  } catch {
    $("#library-status").textContent =
      "Could not load the library. Reload the page to try again.";
  }
}

function showDetails(dataset) {
  $("#dataset-dialog").dataset.datasetId = dataset.id;
  $("#detail-title").textContent = dataset.name;
  const content = $("#detail-content");
  content.replaceChildren();
  const grid = node("dl", "metadata-grid");
  const fields = [
    ["Symbol", dataset.symbol || "Not specified"],
    ["Bars", fmt.format(dataset.row_count)],
    ["Observed spacing", spacing(dataset)],
    ["Start · UTC", date(dataset.start)],
    ["End · UTC", date(dataset.end)],
    ["Source timezone", dataset.source_timezone],
    ["Original file", dataset.filename],
    ["File size", bytes(dataset.bytes)],
    ["Saved · UTC", date(dataset.created_at)],
  ];
  for (const [key, value] of fields) {
    const pair = node("div");
    pair.append(node("dt", "", key), node("dd", "", value));
    grid.append(pair);
  }
  content.append(grid);
  warnings(content, dataset);
  const checksum = node("div", "checksum", "Original CSV · SHA-256");
  checksum.append(node("code", "", dataset.sha256));
  content.append(
    checksum,
    node(
      "p",
      "small muted",
      `First ${dataset.preview.length} rows. ${dataset.columns.includes("Date") ? "Date and Time match the source; computed datetime is UTC." : "Timestamps shown in UTC."} CSV downloads preserve the original bytes.`,
    ),
    previewTable(dataset),
  );
  const actions = node("div", "dialog-actions");
  const download = node("a", "button primary", "Download original CSV ↓");
  download.href = `/api/datasets/${dataset.id}/csv`;
  actions.append(deleteButton(dataset), download);
  content.append(actions);
  $("#dataset-dialog").showModal();
}

$("#csv-file").addEventListener("change", (event) =>
  pickFile(event.target.files[0]),
);
for (const selector of ["#dataset-name", "#symbol"])
  $(selector).addEventListener("input", invalidate);
$("#source-timezone").addEventListener("change", invalidate);
const dropzone = $("#dropzone");
for (const type of ["dragenter", "dragover"])
  dropzone.addEventListener(type, (event) => {
    event.preventDefault();
    if (!busy) dropzone.classList.add("dragover");
  });
for (const type of ["dragleave", "drop"])
  dropzone.addEventListener(type, (event) => {
    event.preventDefault();
    dropzone.classList.remove("dragover");
  });
dropzone.addEventListener("drop", (event) => {
  if (busy) return;
  if (event.dataTransfer.files.length !== 1) {
    showError({ detail: "Choose one CSV at a time." });
    return;
  }
  pickFile(event.dataTransfer.files[0]);
});
$("#upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy || !selectedFile) return;
  invalidate();
  if (selectedFile.size > MAX_BYTES) {
    showError({ detail: "The CSV exceeds the 1 GB limit." });
    return;
  }
  const current = generation;
  setBusy(true, "Validating…");
  try {
    const result = await upload("/api/datasets/validate");
    if (current !== generation) return;
    validated = result;
    showValidation(result);
    $("#form-hint").textContent = "All rows checked. Review and save below.";
  } catch (error) {
    if (current === generation) showError(error);
  } finally {
    setBusy(false);
  }
});
$("#close-dialog").addEventListener("click", () =>
  $("#dataset-dialog").close(),
);
$("#dataset-dialog").addEventListener("click", (event) => {
  const rect = event.currentTarget.getBoundingClientRect();
  if (
    event.target === event.currentTarget &&
    (event.clientX < rect.left ||
      event.clientX > rect.right ||
      event.clientY < rect.top ||
      event.clientY > rect.bottom)
  )
    event.currentTarget.close();
});
async function loadTimezones() {
  try {
    const response = await fetch("/api/timezones");
    if (!response.ok) return;
    const timezones = await response.json();
    const select = $("#source-timezone");
    const common = new Set(
      Array.from(select.options, (option) => option.value),
    );
    const group = node("optgroup");
    group.label = "Other timezones";
    for (const timezone of timezones) {
      if (common.has(timezone)) continue;
      const option = node("option", "", timezone);
      option.value = timezone;
      group.append(option);
    }
    select.append(group);
  } catch {
    // The common timezone choices remain usable if this request fails.
  }
}

loadTimezones();
loadLibrary();
