(() => {
  const $ = (sel, root = document) => root.querySelector(sel);
  const loginEl = $("#login");
  const appEl = $("#app");
  const view = $("#view");
  const pinEl = $("#pin");
  const loginErr = $("#login-err");

  const state = {
    path: "/mnt/SDCARD",
    hidden: false,
    sys: null,
    editing: null,
    term: null,
    fit: null,
    ws: null,
  };

  async function api(url, opts = {}) {
    const headers = Object.assign({ Accept: "application/json" }, opts.headers || {});
    if (opts.json) {
      headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(opts.json);
    }
    const res = await fetch(url, Object.assign({}, opts, { headers, credentials: "same-origin" }));
    const ctype = res.headers.get("content-type") || "";
    const data = ctype.includes("application/json") ? await res.json() : await res.text();
    if (!res.ok) {
      const msg = (data && data.error) || res.statusText || "请求失败";
      throw new Error(msg);
    }
    return data;
  }

  function fmtSize(n) {
    const units = ["B", "K", "M", "G", "T"];
    let i = 0;
    let x = Number(n) || 0;
    while (x >= 1024 && i < units.length - 1) {
      x /= 1024;
      i += 1;
    }
    return i === 0 ? `${x}${units[i]}` : `${x.toFixed(1)}${units[i]}`;
  }

  function fmtTime(ts) {
    if (!ts) return "";
    const d = new Date(ts * 1000);
    const p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  }

  function route() {
    const hash = location.hash.replace(/^#/, "") || "/";
    return hash.split("?")[0];
  }

  function setNav() {
    document.querySelectorAll("nav a").forEach((a) => {
      a.classList.toggle("active", a.dataset.route === route());
    });
  }

  function showLogin(msg) {
    loginEl.hidden = false;
    appEl.hidden = true;
    loginErr.hidden = !msg;
    loginErr.textContent = msg || "";
  }

  function showApp() {
    loginEl.hidden = true;
    appEl.hidden = false;
  }

  async function boot() {
    try {
      const st = await api("/api/status");
      if (st.auth) {
        showApp();
        await render();
        return;
      }
    } catch (err) {
      showLogin("连不上掌机，确认 WebDesk 还开着");
      return;
    }
    showLogin();
  }

  $("#login-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    loginErr.hidden = true;
    try {
      await api("/api/login", { method: "POST", json: { pin: pinEl.value.trim() } });
      pinEl.value = "";
      showApp();
      await render();
    } catch (err) {
      loginErr.hidden = false;
      loginErr.textContent = err.message;
    }
  });

  window.addEventListener("hashchange", () => render());

  async function render() {
    setNav();
    const r = route();
    if (r === "/files") return renderFiles();
    if (r === "/term") return renderTerm();
    if (r === "/edit") return renderEdit();
    return renderHome();
  }

  async function renderHome() {
    destroyTerm();
    let info;
    try {
      info = await api("/api/sys");
      state.sys = info;
      if (info.root) state.path = info.root;
    } catch (err) {
      if (String(err.message).includes("访问码")) {
        showLogin(err.message);
        return;
      }
      view.innerHTML = `<div class="card err">${esc(err.message)}</div>`;
      return;
    }
    $("#host-label").textContent = info.host || "";
    const urls = (info.ips || []).map((ip) => {
      const suffix = info.port === 80 ? "" : `:${info.port}`;
      return `http://${ip}${suffix}/`;
    });
    view.innerHTML = `
      <div class="grid">
        <div class="card">
          <p class="eyebrow">本机地址</p>
          <ul class="url-list">${urls.map((u) => `<li><a href="${esc(u)}">${esc(u)}</a></li>`).join("") || "<li class='muted'>没有局域网 IP</li>"}</ul>
          <p class="muted">关掉掌机上的 WebDesk 后，这些地址会立刻打不开。</p>
        </div>
        <div class="grid cols">
          <div class="card"><p class="muted">主机</p><div class="stat">${esc(info.host || "-")}</div></div>
          <div class="card"><p class="muted">内存可用</p><div class="stat">${fmtSize(info.mem_avail || 0)}</div><p class="muted">共 ${fmtSize(info.mem_total || 0)}</p></div>
          <div class="card"><p class="muted">已运行</p><div class="stat">${fmtUptime(info.uptime)}</div></div>
          <div class="card"><p class="muted">负载</p><div class="stat">${esc((info.load || []).join(" ") || "-")}</div></div>
        </div>
        <div class="card">
          <p class="eyebrow">磁盘</p>
          ${(info.disks || []).map((d) => `<p><strong>${esc(d.mount)}</strong> · 已用 ${esc(d.pct)} · 剩 ${fmtSize(d.avail)}</p>`).join("") || "<p class='muted'>没有读到 df</p>"}
        </div>
      </div>`;
  }

  function fmtUptime(sec) {
    const s = Math.floor(Number(sec) || 0);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    if (h > 48) return `${Math.floor(h / 24)} 天`;
    return h ? `${h} 小时 ${m} 分` : `${m} 分`;
  }

  async function renderFiles() {
    destroyTerm();
    state.editing = null;
    const q = new URLSearchParams({ path: state.path, hidden: state.hidden ? "1" : "0" });
    let data;
    try {
      data = await api(`/api/fs?${q}`);
      state.path = data.path;
    } catch (err) {
      view.innerHTML = `<div class="card err">${esc(err.message)}</div>`;
      return;
    }
    const crumbs = crumbHtml(data.path);
    view.innerHTML = `
      <div class="card">
        <div class="toolbar">
          <button class="ghost" id="btn-up" ${data.parent ? "" : "disabled"}>上级</button>
          <button class="ghost" id="btn-home">SD 卡</button>
          <button class="ghost" id="btn-new">新建目录</button>
          <label class="btn ghost">上传<input id="file-in" type="file" multiple hidden></label>
          <button class="ghost" id="btn-hidden">${state.hidden ? "隐藏点文件" : "显示点文件"}</button>
          <span class="drop" id="drop">文件拖到这里也可以上传</span>
        </div>
        <div class="crumbs">${crumbs}</div>
        <table>
          <thead><tr><th>名称</th><th>大小</th><th>时间</th><th></th></tr></thead>
          <tbody>
            ${data.entries.map((e) => rowHtml(data.path, e)).join("") || `<tr><td colspan="4" class="muted">空目录</td></tr>`}
          </tbody>
        </table>
      </div>`;

    $("#btn-up")?.addEventListener("click", () => {
      if (data.parent) {
        state.path = data.parent;
        renderFiles();
      }
    });
    $("#btn-home").addEventListener("click", () => {
      state.path = (state.sys && state.sys.root) || "/mnt/SDCARD";
      renderFiles();
    });
    $("#btn-hidden").addEventListener("click", () => {
      state.hidden = !state.hidden;
      renderFiles();
    });
    $("#btn-new").addEventListener("click", async () => {
      const name = prompt("新目录名");
      if (!name) return;
      try {
        await api("/api/fs/mkdir", { method: "POST", json: { path: state.path, name } });
        renderFiles();
      } catch (err) {
        alert(err.message);
      }
    });
    $("#file-in").addEventListener("change", (ev) => uploadFiles(ev.target.files));
    const drop = $("#drop");
    drop.addEventListener("dragover", (ev) => ev.preventDefault());
    drop.addEventListener("drop", (ev) => {
      ev.preventDefault();
      uploadFiles(ev.dataTransfer.files);
    });
    view.querySelectorAll("[data-open]").forEach((el) => {
      el.addEventListener("click", () => {
        const p = el.getAttribute("data-open");
        const dir = el.getAttribute("data-dir") === "1";
        if (dir) {
          state.path = p;
          renderFiles();
        } else {
          window.location.href = `/api/fs/download?path=${encodeURIComponent(p)}`;
        }
      });
    });
    view.querySelectorAll("[data-act]").forEach((btn) => {
      btn.addEventListener("click", () => fileAction(btn.dataset.act, btn.dataset.path, btn.dataset.dir === "1"));
    });
  }

  function joinPath(dir, name) {
    if (!dir) return name;
    if (dir.endsWith("/") || dir.endsWith("\\")) return dir + name;
    return `${dir}/${name}`;
  }

  function rowHtml(dir, e) {
    const full = joinPath(dir, e.name);
    return `<tr class="${e.dir ? "dir" : ""}">
      <td><a href="javascript:void(0)" data-open="${esc(full)}" data-dir="${e.dir ? "1" : "0"}">${e.dir ? "📁 " : ""}${esc(e.name)}</a></td>
      <td>${e.dir ? "" : fmtSize(e.size)}</td>
      <td>${fmtTime(e.mtime)}</td>
      <td class="row-actions">
        ${e.dir ? "" : `<button class="ghost" data-act="edit" data-path="${esc(full)}">编辑</button>`}
        ${e.dir ? "" : `<button class="ghost" data-act="dl" data-path="${esc(full)}">下载</button>`}
        <button class="ghost" data-act="rename" data-path="${esc(full)}">改名</button>
        <button class="danger" data-act="del" data-path="${esc(full)}">删除</button>
      </td>
    </tr>`;
  }

  function crumbHtml(path) {
    const sep = path.includes("\\") ? "\\" : "/";
    const parts = path.split(/[/\\]/).filter((p, i) => p || i === 0);
    let acc = path.match(/^[A-Za-z]:/) ? "" : "";
    const out = [];
    if (path.startsWith("/")) acc = "";
    parts.forEach((part, i) => {
      if (path.startsWith("/")) acc += `/${part}`;
      else acc = acc ? `${acc}${sep}${part}` : part;
      const label = part || "/";
      out.push(`<button class="ghost crumb" data-path="${esc(acc)}">${esc(label)}</button>`);
    });
    setTimeout(() => {
      view.querySelectorAll(".crumb").forEach((b) => {
        b.addEventListener("click", () => {
          state.path = b.dataset.path;
          renderFiles();
        });
      });
    }, 0);
    return out.join("<span class='muted'>/</span>");
  }

  async function fileAction(act, path, isDir) {
    try {
      if (act === "dl") {
        window.location.href = `/api/fs/download?path=${encodeURIComponent(path)}`;
        return;
      }
      if (act === "edit") {
        state.editing = path;
        location.hash = "#/edit";
        return;
      }
      if (act === "rename") {
        const name = prompt("新名字", path.split(/[/\\]/).pop());
        if (!name) return;
        await api("/api/fs/rename", { method: "POST", json: { path, name } });
        renderFiles();
        return;
      }
      if (act === "del") {
        if (!confirm(`删除 ${path} ？`)) return;
        await api("/api/fs/delete", { method: "POST", json: { path } });
        renderFiles();
      }
    } catch (err) {
      alert(err.message);
    }
  }

  async function uploadFiles(files) {
    if (!files || !files.length) return;
    for (const file of files) {
      try {
        const q = new URLSearchParams({ dir: state.path, name: file.name });
        await api(`/api/fs/upload?${q}`, {
          method: "PUT",
          headers: { "Content-Type": "application/octet-stream" },
          body: file,
        });
      } catch (err) {
        alert(`${file.name}: ${err.message}`);
      }
    }
    renderFiles();
  }

  async function renderEdit() {
    destroyTerm();
    const path = state.editing;
    if (!path) {
      location.hash = "#/files";
      return;
    }
    let data;
    try {
      data = await api(`/api/fs/read?path=${encodeURIComponent(path)}`);
    } catch (err) {
      view.innerHTML = `<div class="card err">${esc(err.message)} <button class="ghost" id="back">返回</button></div>`;
      $("#back").addEventListener("click", () => (location.hash = "#/files"));
      return;
    }
    view.innerHTML = `
      <div class="card editor">
        <div class="toolbar">
          <strong>${esc(path)}</strong>
          <button id="save">保存</button>
          <button class="ghost" id="back">返回文件</button>
        </div>
        <textarea id="ed">${esc(data.content)}</textarea>
      </div>`;
    $("#back").addEventListener("click", () => (location.hash = "#/files"));
    $("#save").addEventListener("click", async () => {
      try {
        await api("/api/fs/write", { method: "POST", json: { path, content: $("#ed").value } });
        alert("已保存");
      } catch (err) {
        alert(err.message);
      }
    });
  }

  function destroyTerm() {
    if (state.onResize) {
      window.removeEventListener("resize", state.onResize);
      state.onResize = null;
    }
    if (state.ws) {
      try { state.ws.close(); } catch (_) {}
      state.ws = null;
    }
    if (state.term) {
      try { state.term.dispose(); } catch (_) {}
      state.term = null;
      state.fit = null;
    }
  }

  function renderTerm() {
    destroyTerm();
    view.innerHTML = `<div class="term-wrap" id="term"></div>`;
    const el = $("#term");
    if (typeof Terminal === "undefined") {
      el.innerHTML = `<div class="card">浏览器终端组件没加载到。刷新试试，或用 SSH。</div>`;
      return;
    }
    const term = new Terminal({
      cursorBlink: true,
      fontSize: 14,
      fontFamily: 'Cascadia Mono, Sarasa Mono SC, Consolas, monospace',
      theme: {
        background: "#1e1e2e",
        foreground: "#cdd6f4",
        cursor: "#89dceb",
        selectionBackground: "#45475a",
      },
    });
    const Fit = window.FitAddon && window.FitAddon.FitAddon;
    const fit = Fit ? new Fit() : null;
    if (fit) term.loadAddon(fit);
    term.open(el);
    if (fit) fit.fit();
    state.term = term;
    state.fit = fit;
    state.onResize = null;

    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/term`);
    ws.binaryType = "arraybuffer";
    state.ws = ws;

    const sendResize = () => {
      if (fit) fit.fit();
      if (ws.readyState === 1) {
        ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
      }
    };

    ws.onopen = () => {
      sendResize();
      term.focus();
    };
    ws.onmessage = (ev) => {
      if (typeof ev.data === "string") {
        term.write(ev.data);
      } else {
        term.write(new Uint8Array(ev.data));
      }
    };
    ws.onclose = () => term.writeln("\r\n\x1b[33m[终端已断开。掌机上的 WebDesk 关了，或刷新重连]\x1b[0m");
    ws.onerror = () => term.writeln("\r\n\x1b[31m[WebSocket 失败]\x1b[0m");
    term.onData((data) => {
      if (ws.readyState === 1) ws.send(data);
    });
    state.onResize = sendResize;
    window.addEventListener("resize", sendResize, { passive: true });
    setTimeout(sendResize, 80);
  }

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  boot();
})();
