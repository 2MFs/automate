document.addEventListener("alpine:init", () => {
  Alpine.data("app", () => ({
    tabs: [
      { id: "notes",        label: "Notes" },
      { id: "files",        label: "Files" },
      { id: "reminders",    label: "Reminders" },
      { id: "connect",      label: "Connect AI" },
      { id: "integrations", label: "Tools" },
      { id: "models",       label: "Models" },
      { id: "help",         label: "Help" },
    ],
    active: "notes",
    region: "",
    status: null,
    welcomeOpen: false,
    wizardOpen: false,
    wizardStep: 1,
    wizardChoice: null,        // selected provider id

    // Curated 'popular' providers — shown first in the wizard. Order = ranking.
    wizardPicks: [
      { id: "anthropic", title: "Anthropic Claude", subtitle: "Best for coding & agents",       hint: "Sign in with email, no payment needed for API trial credit." },
      { id: "openai",    title: "OpenAI",           subtitle: "GPT-4o · widely supported",       hint: "Pay-per-use, no subscription." },
      { id: "kimi",      title: "Moonshot Kimi",    subtitle: "国内可直接访问",                  hint: "moonshot.cn account → 用户中心 → API Keys。" },
      { id: "deepseek",  title: "DeepSeek",         subtitle: "便宜 + 国内访问",                 hint: "platform.deepseek.com → API keys → 充几块钱就够测试。" },
      { id: "qwen",      title: "通义千问",          subtitle: "阿里 DashScope",                  hint: "需要阿里云账号,有免费额度。" },
      { id: "zhipu",     title: "智谱 GLM",          subtitle: "glm-4-flash 永久免费",            hint: "open.bigmodel.cn → 用户中心 → API Keys。" },
      { id: "ollama",    title: "Ollama (local)",   subtitle: "完全离线 · 不要 API key",         hint: "先 ollama.com 装上,然后跑 `ollama serve` + `ollama pull qwen2.5-coder`。" },
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
    integrationForm: { token: "", client_id: "", client_secret: "" },
    connecting: false,
    connectResult: null,
    showOAuthAdvanced: false,
    integrationFilter: "",

    messages: [],
    liveEvents: [],
    input: "",
    busy: false,
    ws: null,

    runs: [],
    connectInfo: null,
    copiedKey: null,
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

    async loadConnectInfo() {
      try { this.connectInfo = await api("/api/connect"); }
      catch (e) { console.warn(e); }
    },
    async copySnippet(key, text) {
      try {
        await navigator.clipboard.writeText(text);
        this.copiedKey = key;
        setTimeout(() => { if (this.copiedKey === key) this.copiedKey = null; }, 1600);
      } catch (e) {
        // Fallback for old browsers
        const ta = document.createElement("textarea");
        ta.value = text; document.body.appendChild(ta); ta.select();
        document.execCommand("copy"); document.body.removeChild(ta);
        this.copiedKey = key;
        setTimeout(() => { if (this.copiedKey === key) this.copiedKey = null; }, 1600);
      }
    },

    quickPrompts: [
      "在当前目录运行 `git status` 并总结",
      "Open https://news.ycombinator.com and list the top 5 story titles",
      "Create a GitHub issue in <owner>/<repo> titled 'demo from autoMate'",
      "Take a screenshot of my desktop",
    ],

    integrationHints: {
      github:     { label: "Personal Access Token",       url: "https://github.com/settings/tokens/new?scopes=repo,read:user,read:org", hint: "Settings → Developer settings → Personal access tokens (classic). Tick: repo, read:user, read:org." },
      gitlab:     { label: "Personal Access Token",       url: "https://gitlab.com/-/user_settings/personal_access_tokens", hint: "Profile → Access tokens. Tick api scope." },
      gitee:      { label: "Personal Access Token",       url: "https://gitee.com/profile/personal_access_tokens", hint: "用户中心 → 个人访问令牌。" },
      notion:     { label: "Internal Integration Token",  url: "https://www.notion.so/my-integrations", hint: "Create a new internal integration, copy its secret. Then share each page/db with that integration." },
      slack:      { label: "Bot User OAuth Token",        url: "https://api.slack.com/apps", hint: "Create an app → OAuth & Permissions → install to workspace → copy 'Bot User OAuth Token' (xoxb-…)." },
      linear:     { label: "Personal API Key",            url: "https://linear.app/settings/api", hint: "Settings → API → Create new key." },
      jira:       { label: "API Token",                   url: "https://id.atlassian.com/manage-profile/security/api-tokens", hint: "Atlassian account → Security → API tokens." },
      confluence: { label: "API Token",                   url: "https://id.atlassian.com/manage-profile/security/api-tokens", hint: "Same as Jira — uses your Atlassian token." },
      trello:     { label: "API Key",                     url: "https://trello.com/app-key", hint: "Trello App Key page — copy the Key." },
      asana:      { label: "Personal Access Token",       url: "https://app.asana.com/0/my-apps", hint: "Settings → Apps → Personal access tokens." },
      monday:     { label: "API Token",                   url: "https://monday.com/developers/v2", hint: "Avatar menu → Developers → API." },
      hubspot:    { label: "Private App Token",           url: "https://app.hubspot.com/private-apps/", hint: "Settings → Integrations → Private Apps → Create." },
      airtable:   { label: "Personal Access Token",       url: "https://airtable.com/create/tokens", hint: "Token must be granted access to your bases." },
      stripe:     { label: "Secret Key",                  url: "https://dashboard.stripe.com/apikeys", hint: "Use a restricted key in test mode first." },
      shopify:    { label: "Admin API Token",             url: "https://admin.shopify.com/", hint: "Apps → Develop apps → Configure Admin API scopes → Install." },
      telegram:   { label: "Bot Token",                   url: "https://t.me/BotFather", hint: "Talk to @BotFather → /newbot → copy the token." },
      discord:    { label: "Bot Token",                   url: "https://discord.com/developers/applications", hint: "Create application → Bot → Reset Token." },
      teams:      { label: "Incoming Webhook URL",        url: "https://learn.microsoft.com/microsoftteams/platform/webhooks-and-connectors/how-to/add-incoming-webhook", hint: "Channel → Connectors → Incoming Webhook → copy URL." },
      zoom:       { label: "Server-to-Server credentials", url: "https://marketplace.zoom.us/develop/create", hint: "Create a Server-to-Server OAuth app. Paste 3 lines — see Advanced." },
      twitter:    { label: "Bearer Token",                url: "https://developer.twitter.com/en/portal/projects-and-apps", hint: "Project → Keys and tokens → Bearer Token." },
      sendgrid:   { label: "API Key",                     url: "https://app.sendgrid.com/settings/api_keys", hint: "Settings → API Keys → Full Access." },
      mailchimp:  { label: "API Key",                     url: "https://us1.admin.mailchimp.com/account/api/", hint: "Account → Extras → API keys." },
      twilio:     { label: "Auth Token",                  url: "https://console.twilio.com/", hint: "Console homepage → Account info → Auth Token." },
      sentry:     { label: "Auth Token",                  url: "https://sentry.io/settings/account/api/auth-tokens/", hint: "Settings → API → Auth Tokens." },
      feishu:     { label: "App ID + App Secret",         url: "https://open.feishu.cn/app", hint: "Open Platform → 创建应用. Paste two lines (see Advanced)." },
      dingtalk:   { label: "Webhook URL",                 url: "https://open-dev.dingtalk.com/fe/app", hint: "群机器人 → 添加 → Webhook 地址。" },
      wecom:      { label: "Webhook URL",                 url: "https://work.weixin.qq.com/", hint: "群聊 → 群机器人 → 添加 → 复制 Webhook 地址。" },
      weixin:     { label: "App ID + App Secret",         url: "https://mp.weixin.qq.com/", hint: "公众平台 → 开发 → 基本配置. Paste two lines (see Advanced)." },
      weibo:      { label: "Access Token",                url: "https://open.weibo.com/", hint: "微博开放平台 → 应用管理 → 高级信息 → access_token。" },
      yuque:      { label: "Personal Token",              url: "https://www.yuque.com/settings/tokens", hint: "设置 → Token。" },
      amap:       { label: "Web Service Key",             url: "https://console.amap.com/dev/key/app", hint: "高德开放平台 → 应用管理 → Web服务 类型的 Key。" },
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
        this.loadConnectInfo(),
        this.loadNotes(),
        this.loadFiles(),
        this.loadReminders(),
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
        alert("Enter a hub URL first.");
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
        alert(`Synced ${snapshot.notes.length} notes + ${snapshot.memory.length} memory items.\nReloading…`);
        location.reload();
      } catch (e) {
        alert("Sync failed: " + e.message);
      } finally {
        this.syncing = false;
      }
    },

    // ---- v5: files ----
    async loadFiles() {
      this.files = await api("/api/files");
      this.filesUsage = await api("/api/files/usage");
    },
    async uploadFiles(ev) {
      const fileList = Array.from(ev.target.files || []);
      if (!fileList.length) return;
      this.fileUploading = true;
      try {
        for (const f of fileList) {
          const fd = new FormData();
          fd.append("file", f);
          await fetch(hubBase() + "/api/files", { method: "POST", body: fd });
        }
        await this.loadFiles();
      } finally {
        this.fileUploading = false;
        ev.target.value = "";
      }
    },
    async deleteFile(id) {
      if (!confirm("Delete this file?")) return;
      await api(`/api/files/${id}`, "DELETE");
      await this.loadFiles();
    },
    fileDownloadUrl(f) {
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
        if (perm !== "granted") { alert("Notifications denied."); return; }
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
        alert("Push setup failed: " + e.message);
      } finally {
        this.pushBusy = false;
      }
    },
    async testPush() {
      const r = await api("/api/push/test", "POST");
      alert(`sent=${r.sent}, failed=${r.failed}` + (r.reason ? `\n${r.reason}` : ""));
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
      const meta = i.metadata || {};
      this.integrationForm = {
        token: "",
        client_id: meta.client_id || "",
        client_secret: "",
      };
      this.connectResult = null;
      this.connecting = false;
      this.showOAuthAdvanced = false;
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
    async saveOAuthApp() {
      const id = this.editingIntegration.id;
      await api(`/api/integrations/${id}/oauth-app`, "POST", {
        client_id: this.integrationForm.client_id,
        client_secret: this.integrationForm.client_secret,
      });
      await this.loadIntegrations();
    },
    async beginOAuth() {
      // Persist credentials first (in case the user typed without clicking Save).
      if (this.integrationForm.client_id && this.integrationForm.client_secret) {
        await this.saveOAuthApp();
      }
      const id = this.editingIntegration.id;
      const r = await api(`/api/integrations/${id}/connect`);
      window.open(r.authorize_url, "_blank", "width=600,height=720");
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
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(hubBase() + path, opts);
  if (!r.ok) {
    let msg = await r.text();
    try { msg = JSON.parse(msg).detail || msg; } catch {}
    throw new Error(`${r.status}: ${msg}`);
  }
  if (r.status === 204) return null;
  return r.json();
}
