document.addEventListener("alpine:init", () => {
  Alpine.data("app", () => ({
    tabs: [
      { id: "home",         label: "Home" },
      { id: "chat",         label: "Chat" },
      { id: "bots",         label: "Bots" },
      { id: "notes",        label: "Notes" },
      { id: "files",        label: "Files" },
      { id: "reminders",    label: "Reminders" },
      { id: "integrations", label: "Tools" },
      { id: "models",       label: "Models" },
      { id: "help",         label: "Help" },
    ],
    // Mobile bottom-nav. Chat is the primary entry now (built-in agent),
    // Bots is the second (Telegram / 微信 / 企业微信 channels into the
    // same agent). Everything else lives under More.
    mobileTabs: [
      { id: "home",  label: "Home", icon: "🏠" },
      { id: "chat",  label: "Chat", icon: "💬" },
      { id: "bots",  label: "Bots", icon: "🤖" },
      { id: "notes", label: "Notes", icon: "📒" },
    ],
    moreTabs: [
      { id: "files",        label: "Files",      icon: "📁" },
      { id: "reminders",    label: "Reminders",  icon: "⏰" },
      { id: "integrations", label: "Tools",      icon: "🧰" },
      { id: "models",       label: "Models",     icon: "🧠" },
      { id: "help",         label: "Help",       icon: "?" },
    ],
    moreOpen: false,
    settingsOpen: false,

    active: localStorage.getItem("automate-active-tab") || "home",
    region: "",
    status: null,
    welcomeOpen: false,
    wizardOpen: false,
    wizardStep: 1,
    wizardChoice: null,        // selected provider id

    // Curated 'popular' providers — shown first in the wizard. Order = ranking.
    wizardPicks: [
      { id: "anthropic", title: "Anthropic Claude",          subtitle: "Best for coding & agents",        hint: "Sign in with email, no payment needed for API trial credit." },
      { id: "openai",    title: "OpenAI",                    subtitle: "GPT-4o · widely supported",        hint: "Pay-per-use, no subscription." },
      { id: "kimi",      title: "Moonshot Kimi (web API)",   subtitle: "OpenAI 协议 · 国内直连",          hint: "moonshot.cn 工作台 → 用户中心 → API Keys。" },
      { id: "kimi_code", title: "Kimi Code (Anthropic API)", subtitle: "若你在用 Kimi for Coding CLI",     hint: "同一个 Moonshot key,但走 Anthropic 兼容端点。" },
      { id: "deepseek",  title: "DeepSeek",                  subtitle: "便宜 + 国内访问",                 hint: "platform.deepseek.com → API keys → 充几块钱就够测试。" },
      { id: "qwen",      title: "通义千问",                   subtitle: "阿里 DashScope",                  hint: "需要阿里云账号,有免费额度。" },
      { id: "zhipu",     title: "智谱 GLM",                   subtitle: "glm-4-flash 永久免费",            hint: "open.bigmodel.cn → 用户中心 → API Keys。" },
      { id: "ollama",    title: "Ollama (local)",            subtitle: "完全离线 · 不要 API key",         hint: "先 ollama.com 装上,然后跑 `ollama serve` + `ollama pull qwen2.5-coder`。" },
    ],
    catalog: [],
    catalogById: {},
    providers: [],
    integrations: [],
    tools: [],

    editingProvider: null,
    editForm: { api_key: "", base_url: "", default_model: "" },
    testResult: null,

    editingIntegration: null,
    integrationForm: { token: "" },
    connecting: false,
    connectResult: null,
    integrationFilter: "",
    botForm: {},

    // ---- v4.5.3: in-app notice (replaces native alert) ----
    notice: { open: false, icon: "", title: "", body: "", cta: null, cta_secondary: null },
    hubUrlFlash: false,

    showNotice(opts) {
      this.notice = {
        open: true,
        icon: opts.icon || "💡",
        title: opts.title || "",
        body: opts.body || "",
        cta: opts.cta || null,
        cta_secondary: opts.cta_secondary || null,
      };
    },
    dismissNotice() {
      this.notice = { ...this.notice, open: false };
    },

    openSettingsToHub() {
      // Open settings AND scroll to the Hub URL field AND briefly
      // highlight it. Without this, opening settings dumps the user
      // wherever the sheet was last scrolled — they don't know where
      // to look.
      this.settingsOpen = true;
      this.$nextTick(() => {
        const el = document.getElementById("settings-hub-url");
        if (el) {
          el.scrollIntoView({ behavior: "smooth", block: "start" });
          this.hubUrlFlash = true;
          setTimeout(() => { this.hubUrlFlash = false; }, 2400);
        }
      });
    },

    // ---- v4.5: voice recording ----
    recording: false,
    recordingTimer: "0:00",
    transcribing: false,
    transcriptResult: null,
    transcriptProvider: "",
    _mediaRecorder: null,
    _recordedChunks: [],
    _recordingStart: 0,
    _recordingInterval: null,

    async toggleRecording() {
      if (this.recording) return this.stopRecording();
      // Pre-flight: tell the user up-front if they need to sign in. Saves
      // the awkward "you talked for 10 minutes and now I'm telling you
      // it's a paid feature" experience.
      if (!this.cloudInfo?.logged_in) {
        await this.loadCloudInfo();
        if (!this.cloudInfo?.logged_in) {
          this.showNotice({
            icon: "🎙",
            title: "Pro feature",
            body:
              "Audio transcription needs an autoMate Cloud account. " +
              "Sign in (or sign up) from Settings → autoMate Cloud.",
            cta: {
              label: "Open Settings",
              action: () => { this.settingsOpen = true; },
            },
          });
          return;
        }
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        // Prefer webm/opus (small + universal). Browsers that lack opus
        // fall back to whatever they like; backend re-muxes via the ASR
        // provider's supported formats, but the server's filename
        // extension drives Tencent's VoiceFormat so leave it consistent.
        const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
          ? "audio/webm;codecs=opus" : "";
        this._mediaRecorder = new MediaRecorder(stream, mime ? { mimeType: mime } : {});
        this._recordedChunks = [];
        this._mediaRecorder.ondataavailable = (e) => {
          if (e.data && e.data.size > 0) this._recordedChunks.push(e.data);
        };
        this._mediaRecorder.onstop = () => {
          stream.getTracks().forEach(t => t.stop());
          this.uploadRecording();
        };
        this._mediaRecorder.start(1000);
        this.recording = true;
        this._recordingStart = Date.now();
        this._recordingInterval = setInterval(() => {
          const s = Math.floor((Date.now() - this._recordingStart) / 1000);
          const m = Math.floor(s / 60);
          this.recordingTimer = `${m}:${String(s % 60).padStart(2, "0")}`;
        }, 500);
      } catch (e) {
        this.showNotice({ icon: "🎙", title: "Microphone blocked",
          body: "autoMate couldn't access the microphone:\n\n" + e.message });
      }
    },

    stopRecording() {
      if (!this._mediaRecorder) return;
      this._mediaRecorder.stop();
      this.recording = false;
      clearInterval(this._recordingInterval);
    },

    async uploadRecording() {
      if (!this._recordedChunks.length) return;
      const blob = new Blob(this._recordedChunks, { type: this._mediaRecorder.mimeType || "audio/webm" });
      const ext = (blob.type.split(";")[0].split("/")[1] || "webm").replace(/[^a-z0-9]/gi, "");
      const filename = `recording-${new Date().toISOString().replace(/[:.]/g, "-")}.${ext}`;
      const fd = new FormData();
      fd.append("file", blob, filename);
      this.transcribing = true;
      this.transcriptResult = null;
      try {
        const r = await fetch(hubBase() + "/api/audio/record", { method: "POST", body: fd });
        if (!r.ok) {
          const detail = await r.json().catch(() => ({ detail: r.statusText }));
          this.transcriptResult = { error: detail.detail || `HTTP ${r.status}` };
        } else {
          this.transcriptResult = await r.json();
          await this.loadFiles();
          if (this.transcriptResult.note_id) await this.loadNotes();
        }
      } catch (e) {
        this.transcriptResult = { error: e.message };
      } finally {
        this.transcribing = false;
      }
    },

    // ---- v4.5.6: channels bridge ----
    bridgeInfo: null,
    bridgeTokenShown: false,
    // Install instructions for plugging autoMate into OpenClaw / other
    // MCP gateways. Loaded by loadBridge() with mcp_url + bearer token.
    installInfo: null,
    installCopied: false,

    async loadBridge() {
      try {
        const info = await api("/api/channels/bridge");
        // Compose the full URL the gateway will POST to. We can't infer
        // a public hostname from the server side, so we anchor it to
        // wherever the SPA is currently loaded from.
        const base = (hubBase() || location.origin).replace(/\/$/, "");
        this.bridgeInfo = { ...info, inbox_url: base + info.inbox_url_path };
        // Also prefetch the connect instructions so the Copy button is
        // instant — the markdown is small (a few KB) and we want zero
        // latency between click and clipboard.
        const ci = await api(`/api/channels/connect-instructions?public_url=${encodeURIComponent(base)}`);
        this.installInfo = { ...ci, base };
      } catch (e) {
        this.bridgeInfo = null;        // local-only mode: no bridge to show
        this.installInfo = null;
      }
    },

    async copyInstallText() {
      if (!this.installInfo?.markdown) return;
      try {
        await navigator.clipboard.writeText(this.installInfo.markdown);
        this.installCopied = true;
        setTimeout(() => { this.installCopied = false; }, 2000);
      } catch (e) {
        this.showNotice({
          icon: "📋", title: "Clipboard blocked",
          body: "Your browser blocked clipboard access. Open the connection details below and copy the URL + token manually.",
        });
      }
    },
    async copyText(text) {
      if (!text) return false;
      try { await navigator.clipboard.writeText(text); return true; }
      catch (e) {
        const ta = document.createElement("textarea");
        ta.value = text; document.body.appendChild(ta); ta.select();
        try { document.execCommand("copy"); } finally { document.body.removeChild(ta); }
        return true;
      }
    },

    // OpenClaw bundle-mcp config block, ready to drop into
    // ~/.openclaw/openclaw.json5 — pre-filled with the live MCP URL +
    // bearer token of this hub. Returns "" until installInfo loads.
    get openclawConfigSnippet() {
      if (!this.installInfo?.mcp_url) return "";
      const url = this.installInfo.mcp_url;
      const token = this.installInfo.token || "<token>";
      return [
        "{",
        "  plugins: {",
        "    \"bundle-mcp\": {",
        "      servers: {",
        "        automate: {",
        "          transport: \"streamable-http\",",
        `          url: "${url}",`,
        `          headers: { Authorization: "Bearer ${token}" },`,
        "        },",
        "      },",
        "    },",
        "  },",
        "}",
      ].join("\n");
    },
    openclawSnippetCopied: false,
    async copyOpenclawSnippet() {
      const ok = await this.copyText(this.openclawConfigSnippet);
      if (!ok) return;
      this.openclawSnippetCopied = true;
      setTimeout(() => { this.openclawSnippetCopied = false; }, 2000);
    },
    mcpUrlCopied: false,
    async copyMcpUrl() {
      const ok = await this.copyText(this.installInfo?.mcp_url || "");
      if (!ok) return;
      this.mcpUrlCopied = true;
      setTimeout(() => { this.mcpUrlCopied = false; }, 2000);
    },
    mcpTokenCopied: false,
    async copyMcpToken() {
      const ok = await this.copyText(this.installInfo?.token || "");
      if (!ok) return;
      this.mcpTokenCopied = true;
      setTimeout(() => { this.mcpTokenCopied = false; }, 2000);
    },
    async copyBridge(field) {
      if (!this.bridgeInfo?.[field]) return;
      try { await navigator.clipboard.writeText(this.bridgeInfo[field]); }
      catch (e) { /* clipboard blocked — silently fail; the input is selectable */ }
    },
    async regenerateBridgeToken() {
      if (!confirm("Regenerate the bridge token? Any gateway using the old token will stop delivering messages until you update it there.")) return;
      const r = await api("/api/channels/bridge/regenerate", "POST");
      this.bridgeInfo = { ...this.bridgeInfo, token: r.token };
    },

    // ---- v4.5.2: storage location ----
    storageInfo: null,
    storageForm: { path: "" },
    storageBusy: false,
    storageResult: null,

    async loadStorage() {
      try {
        this.storageInfo = await api("/api/system/storage");
        // Default the input to the current path so the user can edit
        // it instead of starting from blank.
        this.storageForm.path = this.storageInfo?.current || "";
      } catch (e) {
        // Local-mode (no hub) — silently skip; the section will just
        // show "..." which is honest.
      }
    },

    async saveStorageDir() {
      this.storageBusy = true;
      this.storageResult = null;
      try {
        const r = await api("/api/system/storage", "PUT", { path: this.storageForm.path });
        this.storageInfo = { ...this.storageInfo, ...r };
        this.storageResult = { ok: true, message: "Saved. New uploads will land here." };
      } catch (e) {
        this.storageResult = { ok: false, message: e.message };
      } finally {
        this.storageBusy = false;
      }
    },

    // ---- v4.4: update check ----
    updateInfo: null,
    updateBusy: false,
    updateMirror: localStorage.getItem("automate-update-mirror") || "",

    // ---- v4.4: cloud auth ----
    cloudInfo: null,
    cloudLoginForm: { email: "", password: "" },
    cloudBusy: false,
    cloudResult: null,

    saveUpdateMirror() {
      const v = (this.updateMirror || "").trim().replace(/\/$/, "");
      if (v) localStorage.setItem("automate-update-mirror", v);
      else localStorage.removeItem("automate-update-mirror");
    },

    async checkForUpdates() {
      // v4.5.4: this is a pure information lookup against GitHub. There
      // is no reason to require a hub for it. Try the SPA-direct path
      // first; only fall back to the hub if the user has explicitly
      // configured a private mirror that needs server-side rewriting.
      this.updateBusy = true;
      try {
        const direct = await this._checkUpdatesDirect();
        if (direct) { this.updateInfo = direct; return; }
        // No direct path possible (mirror not http) — try the hub.
        const params = new URLSearchParams({ force: "true" });
        if (this.updateMirror) params.set("mirror", this.updateMirror);
        this.updateInfo = await api(`/api/system/update_check?${params}`);
      } catch (e) {
        this.updateInfo = { error: e.message };
      } finally {
        this.updateBusy = false;
      }
    },

    async _checkUpdatesDirect() {
      const repo = "yuruotong1/autoMate";
      const url = `https://api.github.com/repos/${repo}/releases/latest`;
      try {
        const r = await fetch(url, { headers: { Accept: "application/vnd.github+json" } });
        if (!r.ok) return null;
        const payload = await r.json();
        const latest = (payload.tag_name || "").replace(/^v/, "");
        const current = this.status?.version || (window.AUTOMATE_VERSION || "");
        const downloads = {};
        for (const a of (payload.assets || [])) {
          const name = a.name || "";
          let url = a.browser_download_url || "";
          if (this.updateMirror && url.startsWith("https://github.com/")) {
            const host = this.updateMirror.replace(/\/$/, "");
            url = (host.startsWith("http") ? host : `https://${host}`) + "/" + url;
          }
          if (name.endsWith("windows-x64.zip")) downloads.windows = url;
          else if (name.endsWith("macos-arm64.zip") || name.endsWith("darwin-arm64.zip")) downloads.macos = url;
          else if (name.endsWith("linux-x64.tar.gz")) downloads.linux = url;
          else if (name.endsWith(".whl")) downloads.wheel = url;
        }
        return {
          current, latest, newer: this._isNewer(latest, current),
          release_notes_url: payload.html_url || "",
          release_notes_body: (payload.body || "").slice(0, 4000),
          download_urls: downloads,
          source: this.updateMirror ? "mirror" : "github",
        };
      } catch (e) {
        // CORS or offline — caller falls back to hub.
        return null;
      }
    },

    _isNewer(latest, current) {
      const parts = (s) => s.split(/[.\-]/).map(p => parseInt(p, 10)).filter(n => !isNaN(n));
      const a = parts(latest), b = parts(current);
      for (let i = 0; i < Math.max(a.length, b.length); i++) {
        if ((a[i] || 0) > (b[i] || 0)) return true;
        if ((a[i] || 0) < (b[i] || 0)) return false;
      }
      return false;
    },

    currentVersion() {
      // Hub status wins (definitive), then the bundled version.js,
      // then last-resort empty. Lets the UI work in local mode too.
      return this.status?.version || (window.AUTOMATE_VERSION || "?");
    },

    async loadCloudInfo() {
      try { this.cloudInfo = await api("/api/auth/me"); }
      catch (e) { this.cloudInfo = { logged_in: false, cloud_configured: false }; }
    },

    async cloudLogin() {
      this.cloudBusy = true;
      this.cloudResult = null;
      try {
        await api("/api/auth/login", "POST", this.cloudLoginForm);
        this.cloudResult = { ok: true, message: "Signed in." };
        this.cloudLoginForm = { email: "", password: "" };
        await this.loadCloudInfo();
      } catch (e) {
        this.cloudResult = { ok: false, message: e.message };
      } finally {
        this.cloudBusy = false;
      }
    },

    async cloudLogout() {
      try {
        await api("/api/auth/logout", "POST");
      } catch (e) { /* best effort */ }
      await this.loadCloudInfo();
    },

    messages: [],
    liveEvents: [],
    input: "",
    busy: false,
    ws: null,

    runs: [],
    hubBaseInput: "",

    // ---- v4.2: smart-NAS local-mode ----
    // mode: 'connected' (talking to a hub), 'local' (IndexedDB only), or null
    // (still detecting). The mode flips to 'connected' as soon as any /api/*
    // call succeeds; otherwise we stay in 'local' and the SPA serves notes +
    // memory out of IndexedDB.
    storageMode: null,
    syncing: false,
    lastSync: null,

    // ---- v5: notes ----
    notes: [],
    notesQuery: "",
    notesTag: "",
    activeNote: null,
    noteDraft: { title: "", body: "", tags: "", pinned: false },

    // ---- v5: files ----
    files: [],
    filesUsage: { total_bytes: 0, count: 0 },
    fileUploading: false,

    // ---- v5: reminders ----
    reminders: [],
    reminderDraft: { body: "", when: "", recurrence: "" },

    // ---- v5: push subscription state ----
    pushEnabled: false,
    pushBusy: false,

    saveHubBase() {
      const v = (this.hubBaseInput || "").trim().replace(/\/$/, "");
      if (v) localStorage.setItem("automate-hub-base", v);
      else localStorage.removeItem("automate-hub-base");
      location.reload();
    },
    get currentHubBase() {
      return localStorage.getItem("automate-hub-base") || "(this server)";
    },

    quickPrompts: [
      "在当前目录运行 `git status` 并总结",
      "Open https://news.ycombinator.com and list the top 5 story titles",
      "Create a GitHub issue in <owner>/<repo> titled 'demo from autoMate'",
      "Take a screenshot of my desktop",
    ],

    // ---- v4.3: bots ----
    botCatalog: [],
    botInstances: [],
    activeBotId: null,
    botFormDirty: false,
    botBusy: false,
    botResult: null,

    async loadBots() {
      try {
        [this.botCatalog, this.botInstances] = await Promise.all([
          api("/api/bots/catalog"),
          api("/api/bots"),
        ]);
      } catch (e) { /* no hub */ }
    },
    botInstance(id) {
      return this.botInstances.find(b => b.id === id) || { id, enabled: false, status: "stopped", config_set: false };
    },
    openBot(id) {
      this.activeBotId = id;
      const meta = this.botCatalog.find(b => b.id === id);
      if (!meta) return;
      // Reset draft form per-bot.
      this.botForm = {};
      meta.config_fields.forEach(f => { this.botForm[f.name] = ""; });
      this.botResult = null;
    },
    closeBot() {
      this.activeBotId = null;
      this.botResult = null;
    },
    async saveBot() {
      if (!this.activeBotId) return;
      this.botBusy = true;
      this.botResult = null;
      try {
        await api(`/api/bots/${this.activeBotId}/config`, "PUT", { config: this.botForm });
        this.botResult = { ok: true, message: "Saved." };
        await this.loadBots();
      } catch (e) {
        this.botResult = { ok: false, message: e.message };
      } finally {
        this.botBusy = false;
      }
    },
    async toggleBot(id) {
      const inst = this.botInstance(id);
      this.botBusy = true;
      this.botResult = null;
      try {
        if (inst.enabled) {
          await api(`/api/bots/${id}/stop`, "POST");
          this.botResult = { ok: true, message: "Stopped." };
        } else {
          const r = await api(`/api/bots/${id}/start`, "POST");
          this.botResult = { ok: true, message: `Started · ${r.status}` };
        }
        await this.loadBots();
      } catch (e) {
        this.botResult = { ok: false, message: e.message };
      } finally {
        this.botBusy = false;
      }
    },

    helpExamples: [
      { kind: "shell",        text: "git status this folder and summarise what changed",
        note: "Uses shell.exec — runs from the folder where automate started." },
      { kind: "browser",      text: "Open https://news.ycombinator.com and list the top 5 story titles",
        note: "Uses browser.* (Playwright). Install Chromium first: python -m playwright install chromium" },
      { kind: "real browser", text: "Read the visible text on my active tab and summarise it",
        note: "Uses bx.* — needs the autoMate Bridge browser extension installed." },
      { kind: "github",       text: "List the 5 most recent issues in microsoft/playwright",
        note: "Uses the GitHub integration — connect it in the Tools tab first." },
      { kind: "script",       text: "Write a Python script that prints prime numbers up to 100 and run it",
        note: "Uses script.run — saves the file under ~/.automate/scripts/ for replay." },
    ],

    async init() {
      // Persist active tab so reopening the SPA lands where you left off.
      this.$watch?.("active", v => v && localStorage.setItem("automate-active-tab", v));

      // First, try to talk to a hub. If it works, we're in connected mode.
      // If not, we drop to local mode and the SPA serves notes/memory from
      // IndexedDB. The user can flip to connected mode any time.
      try {
        await api("/api/health");
        this.storageMode = "connected";
      } catch {
        this.storageMode = "local";
      }
      this.lastSync = parseFloat(localStorage.getItem("automate-last-sync") || "0") || null;

      if (this.storageMode === "connected") {
        await this.refreshAll();
        this.connectWS();
        setInterval(() => this.refreshStatus(), 5000);
      } else {
        // Local mode: only load what we have locally.
        await this.loadNotes();
      }

      const dismissed = localStorage.getItem("automate-welcomed") === "1";
      if (!dismissed) {
        // Show welcome unless they're already configured.
        const configured = this.status && this.status.providers_configured > 0;
        if (!configured) this.welcomeOpen = true;
      }
    },

    dismissWelcome(jumpToWizard) {
      localStorage.setItem("automate-welcomed", "1");
      this.welcomeOpen = false;
      if (jumpToWizard) this.openWizard();
    },

    openWizard() {
      // Hard pre-flight: configuring a provider lives on the hub, so
      // the wizard cannot work in local-only mode. Without this we'd
      // happily collect the user's API key and then fail with "Failed
      // to fetch" with no way for them to know why.
      if (this.storageMode === "local") {
        this.showNotice({
          icon: "💻",
          title: "Connect a hub first",
          body:
            "AI providers (Kimi, Claude, etc.) run on a 'hub' — a copy of " +
            "autoMate running on your computer or server. Your phone talks " +
            "to it over Wi-Fi.\n\nPaste the hub URL in Settings, then come " +
            "back here to add a model.",
          cta: {
            label: "Open Settings",
            action: () => this.openSettingsToHub(),
          },
          cta_secondary: {
            label: "Help",
            action: () => { this.active = "help"; },
          },
        });
        return;
      }
      this.wizardOpen = true;
      this.wizardStep = 1;
      this.wizardChoice = null;
      this.editForm = { api_key: "", base_url: "", default_model: "" };
      this.testResult = null;
    },
    pickWizardProvider(p) {
      this.wizardChoice = p;
      const meta = this.catalogById[p.id] || {};
      this.editForm = {
        api_key: "",
        base_url: meta.base_url || "",
        default_model: (meta.models && meta.models[0]) || "",
      };
      this.wizardStep = 2;
      this.testResult = null;
    },
    async wizardConnect() {
      // Pretend the wizard is the modal — reuse saveAndUse logic.
      this.editingProvider = { id: this.wizardChoice.id, api_key_set: false };
      await this.saveAndUse();
      if (this.testResult?.ok) {
        this.wizardStep = 3;        // celebrate
      }
    },
    closeWizard() {
      this.wizardOpen = false;
      this.editingProvider = null;
    },

    async refreshAll() {
      await Promise.all([
        this.refreshStatus(),
        this.loadCatalog(),
        this.loadProviders(),
        this.loadIntegrations(),
        this.loadTools(),
        this.loadRuns(),
        this.loadNotes(),
        this.loadFiles(),
        this.loadReminders(),
        this.loadBots(),
        this.loadCloudInfo(),
        this.loadStorage(),
        this.loadBridge(),
      ]);
      this.checkPushEnabled();
    },

    // ---- notes (local + connected) ----
    async loadNotes() {
      if (this.storageMode === "local") {
        this.notes = await window.localStore.listNotes({
          query: this.notesQuery, tag: this.notesTag,
        });
      } else {
        this.notes = await api(`/api/notes?query=${encodeURIComponent(this.notesQuery)}&tag=${encodeURIComponent(this.notesTag)}`);
      }
    },
    newNote() {
      this.activeNote = { id: null };
      this.noteDraft = { title: "", body: "", tags: "", pinned: false };
    },
    openNote(n) {
      this.activeNote = n;
      this.noteDraft = { title: n.title, body: n.body, tags: n.tags, pinned: !!n.pinned };
    },
    async saveNote() {
      const isLocal = this.storageMode === "local";
      if (this.activeNote?.id) {
        this.activeNote = isLocal
          ? await window.localStore.updateNote(this.activeNote.id, this.noteDraft)
          : await api(`/api/notes/${this.activeNote.id}`, "PATCH", this.noteDraft);
      } else {
        this.activeNote = isLocal
          ? await window.localStore.createNote(this.noteDraft)
          : await api("/api/notes", "POST", this.noteDraft);
      }
      await this.loadNotes();
    },
    async deleteNote() {
      if (!this.activeNote?.id) return;
      if (!confirm("Delete this note?")) return;
      if (this.storageMode === "local") {
        await window.localStore.deleteNote(this.activeNote.id);
      } else {
        await api(`/api/notes/${this.activeNote.id}`, "DELETE");
      }
      this.activeNote = null;
      this.noteDraft = { title: "", body: "", tags: "", pinned: false };
      await this.loadNotes();
    },

    // ---- one-shot sync: push every local note/memory to a hub, then pull. ----
    async syncWithHub() {
      const hub = (this.hubBaseInput || hubBase()).trim().replace(/\/$/, "");
      if (!hub) {
        this.showNotice({ title: "Enter a hub URL first",
          body: "Paste your hub's URL above (e.g. http://192.168.1.20:8765) before syncing." });
        return;
      }
      this.syncing = true;
      try {
        // Push local → hub. We use last-write-wins by upserting on the hub.
        const snapshot = await window.localStore.exportAll();
        for (const n of snapshot.notes) {
          await fetch(`${hub}/api/notes`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              title: n.title, body: n.body, tags: n.tags, pinned: !!n.pinned,
            }),
          });
        }
        for (const m of snapshot.memory) {
          await fetch(`${hub}/api/memory`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ key: m.key, value: m.value }),
          });
        }
        // Pull hub → local. Merge by updated_at.
        const remoteNotes = await (await fetch(`${hub}/api/notes`)).json();
        const remoteMemory = await (await fetch(`${hub}/api/memory`)).json();
        await window.localStore.importMerge({
          schema: 1, notes: remoteNotes, memory: remoteMemory,
        });
        // Persist this hub URL and flip mode if not already connected.
        localStorage.setItem("automate-hub-base", hub);
        localStorage.setItem("automate-last-sync", String(Date.now() / 1000));
        this.lastSync = Date.now() / 1000;
        this.showNotice({ icon: "✅", title: "Sync complete",
          body: `Synced ${snapshot.notes.length} notes + ${snapshot.memory.length} memory items.\n\nReloading…`,
          cta: { label: "OK", action: () => location.reload() } });
        return;
        location.reload();
      } catch (e) {
        this.showNotice({ icon: "⚠️", title: "Sync failed", body: e.message });
      } finally {
        this.syncing = false;
      }
    },

    // ---- files (local IndexedDB or hub) ----
    async loadFiles() {
      if (this.storageMode === "local") {
        this.files = await window.localStore.listFiles({});
        this.filesUsage = await window.localStore.filesUsage();
      } else {
        this.files = await api("/api/files");
        this.filesUsage = await api("/api/files/usage");
      }
    },
    async uploadFiles(ev) {
      const fileList = Array.from(ev.target.files || []);
      if (!fileList.length) return;
      this.fileUploading = true;
      try {
        if (this.storageMode === "local") {
          for (const f of fileList) {
            await window.localStore.createFile(f);
          }
        } else {
          for (const f of fileList) {
            const fd = new FormData();
            fd.append("file", f);
            await fetch(hubBase() + "/api/files", { method: "POST", body: fd });
          }
        }
        await this.loadFiles();
      } finally {
        this.fileUploading = false;
        ev.target.value = "";
      }
    },
    async deleteFile(id) {
      if (!confirm("Delete this file?")) return;
      if (this.storageMode === "local") {
        await window.localStore.deleteFile(id);
      } else {
        await api(`/api/files/${id}`, "DELETE");
      }
      await this.loadFiles();
    },
    async downloadLocalFile(f) {
      // For local files we don't have a stable URL — open the blob via
      // a one-shot object URL.
      const blob = await window.localStore.getFileBlob(f.id);
      if (!blob) return;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = f.filename || "download";
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    },
    fileDownloadUrl(f) {
      // Hub-mode raw URL. Local-mode files don't have one — the UI uses
      // downloadLocalFile() instead.
      return `${hubBase()}/api/files/${f.id}/raw`;
    },
    fmtBytes(n) {
      if (!n) return "0 B";
      const u = ["B", "KB", "MB", "GB", "TB"];
      let i = 0;
      while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
      return `${n.toFixed(i ? 1 : 0)} ${u[i]}`;
    },

    // ---- v5: reminders ----
    async loadReminders() {
      this.reminders = await api("/api/reminders");
    },
    async createReminder() {
      if (!this.reminderDraft.body || !this.reminderDraft.when) return;
      const due = new Date(this.reminderDraft.when).getTime() / 1000;
      await api("/api/reminders", "POST", {
        body: this.reminderDraft.body,
        due_at: due,
        recurrence: this.reminderDraft.recurrence || null,
      });
      this.reminderDraft = { body: "", when: "", recurrence: "" };
      await this.loadReminders();
    },
    async snoozeReminder(id, minutes = 10) {
      await api(`/api/reminders/${id}/snooze?minutes=${minutes}`, "POST");
      await this.loadReminders();
    },
    async dismissReminder(id) {
      await api(`/api/reminders/${id}/dismiss`, "POST");
      await this.loadReminders();
    },
    async deleteReminder(id) {
      await api(`/api/reminders/${id}`, "DELETE");
      await this.loadReminders();
    },
    fmtTime(ts) { return new Date(ts * 1000).toLocaleString(); },

    // ---- v5: web push subscription ----
    async checkPushEnabled() {
      if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;
      try {
        const reg = await navigator.serviceWorker.ready;
        const sub = await reg.pushManager.getSubscription();
        this.pushEnabled = !!sub;
      } catch {}
    },
    async enablePush() {
      this.pushBusy = true;
      try {
        const perm = await Notification.requestPermission();
        if (perm !== "granted") {
          this.showNotice({ icon: "🔕", title: "Notifications blocked",
            body: "Enable notifications in your browser/OS to get reminder pings." });
          return;
        }
        const reg = await navigator.serviceWorker.ready;
        const cfg = await api("/api/push/config");
        const key = urlBase64ToUint8Array(cfg.vapid_public_key);
        const sub = await reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: key,
        });
        const json = sub.toJSON();
        await api("/api/push/subscribe", "POST", {
          endpoint: json.endpoint,
          p256dh: json.keys.p256dh,
          auth: json.keys.auth,
        });
        this.pushEnabled = true;
      } catch (e) {
        this.showNotice({ icon: "⚠️", title: "Push setup failed", body: e.message });
      } finally {
        this.pushBusy = false;
      }
    },
    async testPush() {
      const r = await api("/api/push/test", "POST");
      this.showNotice({ icon: "📨", title: "Test push sent",
        body: `sent=${r.sent}, failed=${r.failed}` + (r.reason ? `\n${r.reason}` : "") });
    },

    async refreshStatus() { this.status = await api("/api/status"); },
    async loadCatalog() {
      this.catalog = await api("/api/models/catalog");
      this.catalogById = Object.fromEntries(this.catalog.map(p => [p.id, p]));
    },
    async loadProviders() { this.providers = await api("/api/models"); },
    async loadIntegrations() { this.integrations = await api("/api/integrations"); },
    async loadTools() {
      const grouped = await api("/api/tools");
      this.tools = grouped;
    },
    async loadRuns() { this.runs = await api("/api/agent/runs"); },

    get filteredProviders() {
      if (!this.region) return this.providers;
      return this.providers.filter(p => {
        const meta = this.catalogById[p.id];
        return meta && meta.region === this.region;
      });
    },

    get groupedIntegrations() {
      const q = (this.integrationFilter || "").trim().toLowerCase();
      const out = {};
      for (const i of this.integrations) {
        if (q && !`${i.id} ${i.display_name} ${i.category}`.toLowerCase().includes(q)) continue;
        (out[i.category] ||= []).push(i);
      }
      return out;
    },

    get toolsByCategory() {
      // tools is grouped { category: [...] } already
      return this.tools || {};
    },

    get totalToolCount() {
      return Object.values(this.tools || {}).reduce((acc, arr) => acc + arr.length, 0);
    },

    // ---- providers ----
    showAdvanced: false,
    saving: false,

    openProvider(p) {
      this.editingProvider = p;
      const meta = this.catalogById[p.id] || {};
      this.editForm = {
        api_key: "",
        base_url: p.base_url || meta.base_url || "",
        default_model: p.default_model || (meta.models && meta.models[0]) || "",
      };
      this.testResult = null;
      this.showAdvanced = false;
    },
    closeProviderModal() {
      this.editingProvider = null;
      this.testResult = null;
      this.saving = false;
    },
    async saveAndUse() {
      const id = this.editingProvider.id;
      const meta = this.catalogById[id] || {};
      const requiresKey = meta.requires_key !== false;
      if (requiresKey && !this.editForm.api_key && !this.editingProvider.api_key_set) {
        this.testResult = { ok: false, message: "Paste an API key first." };
        return;
      }
      this.saving = true;
      this.testResult = { ok: true, message: "Saving and testing…" };
      try {
        await api(`/api/models/${id}`, "PATCH", this.editForm);
        const r = await api(`/api/models/${id}/test`, "POST");
        await api("/api/models/active", "POST", {
          provider_id: id,
          model: this.editForm.default_model || (meta.models && meta.models[0]),
        });
        this.testResult = { ok: true, message: `Reply received: "${(r.reply || "").trim()}"` };
        await Promise.all([this.loadProviders(), this.refreshStatus()]);
        // Auto-close on success after a brief pause so the user sees the green tick.
        setTimeout(() => this.closeProviderModal(), 1200);
      } catch (e) {
        this.testResult = {
          ok: false,
          message: e.message,
          hint: this._diagnoseError(e.message, meta),
        };
      } finally {
        this.saving = false;
      }
    },
    _diagnoseError(msg, meta) {
      const m = (msg || "").toLowerCase();
      if (m.includes("401") || m.includes("invalid api key") || m.includes("authentication")) {
        return "Your API key was rejected. Check it was copied in full (no spaces).";
      }
      if (m.includes("404") || m.includes("model_not_found")) {
        return `The model "${this.editForm.default_model}" wasn't found. Open Advanced and pick a different one.`;
      }
      if (m.includes("403") || m.includes("permission") || m.includes("not allowed")) {
        return "Your account doesn't have access to this model. Try a smaller/cheaper one in Advanced.";
      }
      if (m.includes("timeout") || m.includes("connection") || m.includes("dns")) {
        return `Could not reach ${meta.base_url || "the endpoint"}. Network or firewall issue?`;
      }
      return "";
    },
    async setActive(id) {
      const meta = this.catalogById[id];
      const prov = this.providers.find(p => p.id === id);
      await api("/api/models/active", "POST", {
        provider_id: id,
        model: prov?.default_model || meta?.models?.[0],
      });
      await this.refreshStatus();
    },

    // ---- integrations ----
    openIntegration(i) {
      this.editingIntegration = i;
      this.integrationForm = { token: "" };
      this.connectResult = null;
      this.connecting = false;
    },
    closeIntegrationModal() {
      this.editingIntegration = null;
      this.connectResult = null;
      this.connecting = false;
    },
    async connectApiKey() {
      const id = this.editingIntegration.id;
      if (!this.integrationForm.token) {
        this.connectResult = { ok: false, message: "Paste the credential first." };
        return;
      }
      this.connecting = true;
      try {
        await api(`/api/integrations/${id}/apikey`, "POST", { token: this.integrationForm.token });
        await Promise.all([this.loadIntegrations(), this.loadTools(), this.refreshStatus()]);
        this.connectResult = { ok: true, message: "Connected. autoMate's tools for this provider are now available." };
        setTimeout(() => this.closeIntegrationModal(), 1200);
      } catch (e) {
        this.connectResult = { ok: false, message: e.message };
      } finally {
        this.connecting = false;
      }
    },

    // Open the OAuth popup and listen for the success postMessage from
    // the callback page. The popup runs window.opener.postMessage() after
    // the token is stored, so by the time we hear back the connections
    // table already has the new row — we just need to refresh.
    async beginOAuth() {
      const id = this.editingIntegration.id;
      this.connecting = true;
      this.connectResult = null;
      let r;
      try {
        r = await api(`/api/integrations/${id}/connect`);
      } catch (e) {
        this.connecting = false;
        // 503 typically means the broker is unreachable. Surface a
        // clear pointer to the API-key fallback rather than leaving the
        // user staring at a stack trace.
        const fallbackHint = this.editingIntegration?.token_help
          ? " You can paste an API key below as a fallback."
          : "";
        this.connectResult = { ok: false, message: (e.message || "couldn't start OAuth") + fallbackHint };
        return;
      }
      const popup = window.open(r.authorize_url, "automate-oauth", "width=560,height=720");
      if (!popup) {
        this.connecting = false;
        this.connectResult = { ok: false, message: "Browser blocked the popup. Allow popups for this site and try again." };
        return;
      }
      // The callback page postMessages back. We bind a one-shot listener.
      const onMessage = async (ev) => {
        if (ev.origin !== window.location.origin) return;
        const m = ev.data || {};
        if (m.kind !== "automate-oauth" || m.provider !== id) return;
        window.removeEventListener("message", onMessage);
        clearInterval(closedPoll);
        this.connecting = false;
        if (m.ok) {
          await Promise.all([this.loadIntegrations(), this.loadTools(), this.refreshStatus()]);
          this.connectResult = { ok: true, message: "Authorized. The provider's tools are now available." };
          setTimeout(() => this.closeIntegrationModal(), 1200);
        } else {
          this.connectResult = { ok: false, message: m.message || "Authorization failed." };
        }
      };
      window.addEventListener("message", onMessage);
      // If the user closes the popup without finishing, stop spinning.
      const closedPoll = setInterval(() => {
        if (popup.closed) {
          clearInterval(closedPoll);
          window.removeEventListener("message", onMessage);
          if (this.connecting) {
            this.connecting = false;
            this.connectResult = { ok: false, message: "Popup closed before authorization completed." };
          }
        }
      }, 800);
    },

    async disconnect() {
      const id = this.editingIntegration.id;
      await api(`/api/integrations/${id}/disconnect`, "POST");
      await this.loadIntegrations();
      this.editingIntegration = null;
    },

    // ---- chat ----
    connectWS() {
      this.ws = new WebSocket(wsUrlFor("/api/sessions/ws"));
      this.ws.onmessage = (e) => {
        const ev = JSON.parse(e.data);
        if (ev.kind === "done") { this.busy = false; this.loadRuns(); return; }
        if (ev.kind === "final") {
          this.messages.push({ role: "assistant", text: ev.payload.text });
          this.liveEvents = [];
          this.$nextTick(() => this.scrollChat());
          return;
        }
        if (ev.kind === "error") {
          this.messages.push({ role: "assistant", text: "⚠ " + ev.payload.message });
          this.liveEvents = [];
          this.busy = false;
          return;
        }
        this.liveEvents.push(ev);
        this.$nextTick(() => this.scrollChat());
      };
      this.ws.onclose = () => setTimeout(() => this.connectWS(), 1500);
    },
    scrollChat() {
      const el = this.$refs.chatScroll;
      if (el) el.scrollTop = el.scrollHeight;
    },
    send() {
      if (!this.input.trim() || this.busy) return;
      const prompt = this.input.trim();
      this.messages.push({ role: "user", text: prompt });
      this.input = "";
      this.liveEvents = [];
      this.busy = true;
      this.ws.send(JSON.stringify({ prompt }));
    },
  }));
});

function hubBase() {
  return (localStorage.getItem("automate-hub-base") || "").replace(/\/$/, "");
}

function wsUrlFor(path) {
  const base = hubBase();
  if (base) {
    const u = new URL(base);
    return `${u.protocol === "https:" ? "wss" : "ws"}://${u.host}${path}`;
  }
  return `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}${path}`;
}

function urlBase64ToUint8Array(base64) {
  const padding = "=".repeat((4 - base64.length % 4) % 4);
  const b64 = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(b64);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

async function api(path, method = "GET", body) {
  // Pre-flight: catch the most common cause of "Failed to fetch" — the
  // SPA was loaded from file:// but the user never told us where their
  // hub lives. fetch("/api/...") against a file:// origin throws a
  // TypeError that surfaces as the cryptic "Failed to fetch". Give a
  // real error instead.
  const base = hubBase();
  if (!base && location.protocol === "file:") {
    throw new Error(
      "No hub connected yet. Open Settings → paste your hub URL " +
      "(e.g. http://192.168.1.20:8765) and try again."
    );
  }
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  let r;
  try {
    r = await fetch(base + path, opts);
  } catch (e) {
    // Network/CORS/DNS — fetch's TypeError is useless on its own.
    throw new Error(
      `Network error reaching ${base || location.origin}. ` +
      `Check the hub URL in Settings, that the hub is running, and ` +
      `(if on phone) that you're on the same WiFi.`
    );
  }
  if (!r.ok) {
    let msg = await r.text();
    try { msg = JSON.parse(msg).detail || msg; } catch {}
    throw new Error(`${r.status}: ${msg}`);
  }
  if (r.status === 204) return null;
  return r.json();
}
