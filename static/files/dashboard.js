let currentPath = ".";
let tasksPoller = null;

const pathInput = document.getElementById("pathInput");
const uploadDir = document.getElementById("uploadDir");

function writeOut(target, payload) {
  document.getElementById(target).textContent = JSON.stringify(payload, null, 2);
}

async function api(url, opts = {}) {
  const resp = await fetch(url, opts);
  const body = await resp.json();
  writeOut("apiOut", body);
  if (!resp.ok || !body.ok) {
    throw new Error(body.error?.message || `Request failed: ${resp.status}`);
  }
  return body.data;
}

function parentOf(path) {
  const cleaned = path.replace(/\/+$/, "");
  const idx = cleaned.lastIndexOf("/");
  if (idx <= 0) return ".";
  return cleaned.slice(0, idx);
}

function rowForItem(item) {
  const tr = document.createElement("tr");
  const nameTd = document.createElement("td");
  if (item.type === "dir") {
    const btn = document.createElement("button");
    btn.className = "linkish";
    btn.textContent = item.name;
    btn.addEventListener("click", () => loadItems(item.path));
    nameTd.appendChild(btn);
  } else {
    nameTd.textContent = item.name;
  }

  const typeTd = document.createElement("td");
  typeTd.textContent = item.type;

  const sizeTd = document.createElement("td");
  sizeTd.textContent = item.size ?? "-";

  const actionsTd = document.createElement("td");
  const actions = document.createElement("div");
  actions.className = "actions";
  if (item.type === "file") {
    const dl = document.createElement("a");
    dl.href = `/files/download?path=${encodeURIComponent(item.path)}`;
    dl.textContent = "Download";
    dl.className = "small-btn";
    actions.appendChild(dl);
  }

  const fillArchive = document.createElement("button");
  fillArchive.className = "small-btn";
  fillArchive.textContent = "Use for archive";
  fillArchive.addEventListener("click", () => {
    document.getElementById("archiveSource").value = item.path;
  });
  actions.appendChild(fillArchive);

  actionsTd.appendChild(actions);
  tr.append(nameTd, typeTd, sizeTd, actionsTd);
  return tr;
}

async function loadItems(path = currentPath) {
  const data = await api(`/files/list?path=${encodeURIComponent(path)}`);
  currentPath = data.path;
  pathInput.value = data.path;
  uploadDir.value = data.path;
  document.getElementById("cwdLabel").textContent = `Current directory: ${data.path}`;

  const tbody = document.querySelector("#itemsTable tbody");
  tbody.innerHTML = "";
  data.items.forEach((item) => tbody.appendChild(rowForItem(item)));
}

async function pollTask(taskId) {
  const out = document.getElementById("tasksOut");
  if (tasksPoller) {
    clearInterval(tasksPoller);
  }
  tasksPoller = setInterval(async () => {
    try {
      const resp = await fetch(`/tasks/${taskId}`);
      const body = await resp.json();
      out.textContent = JSON.stringify(body, null, 2);
      const status = body?.data?.status;
      if (["done", "failed"].includes(status)) {
        clearInterval(tasksPoller);
        tasksPoller = null;
      }
    } catch (error) {
      out.textContent = String(error);
    }
  }, 1000);
}

document.getElementById("goBtn").addEventListener("click", () => loadItems(pathInput.value || "."));
document.getElementById("refreshBtn").addEventListener("click", () => loadItems(currentPath));
document.getElementById("upBtn").addEventListener("click", () => loadItems(parentOf(currentPath)));

document.getElementById("createBtn").addEventListener("click", async () => {
  const name = document.getElementById("createName").value.trim();
  const kind = document.getElementById("createKind").value;
  if (!name) return;
  await api("/files/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: `${currentPath}/${name}`, kind }),
  });
  await loadItems(currentPath);
});

document.getElementById("renameBtn").addEventListener("click", async () => {
  const oldPath = document.getElementById("renameOld").value.trim();
  const newPath = document.getElementById("renameNew").value.trim();
  if (!oldPath || !newPath) return;
  await api("/files/rename", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ old_path: oldPath, new_path: newPath }),
  });
  await loadItems(currentPath);
});

document.getElementById("uploadBtn").addEventListener("click", async () => {
  const fileInput = document.getElementById("uploadFile");
  if (!fileInput.files.length) return;
  const form = new FormData();
  form.set("target_dir", uploadDir.value || currentPath);
  form.set("file", fileInput.files[0]);
  await api("/files/upload", { method: "POST", body: form });
  fileInput.value = "";
  await loadItems(currentPath);
});

async function runAsyncAction(endpoint) {
  const sourcePath = document.getElementById("archiveSource").value.trim();
  const outputName = document.getElementById("archiveOut").value.trim();
  if (!sourcePath || !outputName) return;
  const data = await api(`/files/${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_path: sourcePath, output_name: outputName }),
  });
  await pollTask(data.task_id);
}

document.getElementById("archiveBtn").addEventListener("click", () => runAsyncAction("archive"));
document.getElementById("compressBtn").addEventListener("click", () => runAsyncAction("compress"));

loadItems().catch((error) => writeOut("apiOut", { ok: false, error: String(error) }));
