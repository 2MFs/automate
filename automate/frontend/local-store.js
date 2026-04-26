// Local IndexedDB store — used when no hub URL is configured.
//
// autoMate's "smart NAS for AI" model: each device has its own data, sync
// is opt-in. This module gives the SPA a working notes/memory/files store
// even when the user has no hub running on their laptop yet.
//
// v4.5.4: files now live here too. Most phones can comfortably hold a few
// hundred MB of attachments in IndexedDB. Bigger libraries should connect
// a hub.

const DB_NAME = "automate-local";
const DB_VERSION = 2;
const STORES = ["notes", "memory", "files_meta", "files_blob"];

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      // notes / memory existed in v1; files_meta / files_blob are v2.
      if (!db.objectStoreNames.contains("notes"))      db.createObjectStore("notes",      { keyPath: "id" });
      if (!db.objectStoreNames.contains("memory"))     db.createObjectStore("memory",     { keyPath: "key" });
      if (!db.objectStoreNames.contains("files_meta")) db.createObjectStore("files_meta", { keyPath: "id" });
      if (!db.objectStoreNames.contains("files_blob")) db.createObjectStore("files_blob", { keyPath: "id" });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function tx(db, store, mode = "readonly") {
  return db.transaction(store, mode).objectStore(store);
}
function asPromise(req) {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
function uuid() {
  return (crypto.randomUUID && crypto.randomUUID()) ||
    "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
      const r = Math.random() * 16 | 0;
      return (c === "x" ? r : (r & 0x3 | 0x8)).toString(16);
    });
}

const localStore = {
  _db: null,

  async init() {
    if (!this._db) this._db = await openDB();
    return this;
  },

  // ---- notes ----

  async createNote({ title = "Untitled", body = "", tags = "", pinned = false }) {
    await this.init();
    const now = Date.now() / 1000;
    const note = {
      id: uuid(),
      title: title.trim() || "Untitled",
      body, tags: this._normTags(tags),
      pinned: pinned ? 1 : 0,
      created_at: now, updated_at: now,
    };
    await asPromise(tx(this._db, "notes", "readwrite").add(note));
    return note;
  },

  async updateNote(id, patch) {
    await this.init();
    const existing = await asPromise(tx(this._db, "notes").get(id));
    if (!existing) return null;
    const updated = {
      ...existing,
      ...(patch.title !== undefined && { title: patch.title }),
      ...(patch.body !== undefined && { body: patch.body }),
      ...(patch.tags !== undefined && { tags: this._normTags(patch.tags) }),
      ...(patch.pinned !== undefined && { pinned: patch.pinned ? 1 : 0 }),
      updated_at: Date.now() / 1000,
    };
    await asPromise(tx(this._db, "notes", "readwrite").put(updated));
    return updated;
  },

  async getNote(id) {
    await this.init();
    return asPromise(tx(this._db, "notes").get(id));
  },

  async listNotes({ query = "", tag = "", limit = 200 } = {}) {
    await this.init();
    const all = await asPromise(tx(this._db, "notes").getAll());
    const q = query.toLowerCase();
    let f = all;
    if (q) f = f.filter(n => n.title.toLowerCase().includes(q) || n.body.toLowerCase().includes(q));
    if (tag) f = f.filter(n => (`,${n.tags},`).includes(`,${tag.trim()},`));
    f.sort((a, b) => (b.pinned - a.pinned) || (b.updated_at - a.updated_at));
    return f.slice(0, limit);
  },

  async deleteNote(id) {
    await this.init();
    const existing = await asPromise(tx(this._db, "notes").get(id));
    if (!existing) return false;
    await asPromise(tx(this._db, "notes", "readwrite").delete(id));
    return true;
  },

  _normTags(raw) {
    return [...new Set((raw || "").split(",").map(s => s.trim()).filter(Boolean))]
      .sort().join(",");
  },

  // ---- memory ----

  async memorySet(key, value) {
    await this.init();
    await asPromise(tx(this._db, "memory", "readwrite").put({
      key, value, updated_at: Date.now() / 1000,
    }));
  },
  async memoryGet(key) {
    await this.init();
    const row = await asPromise(tx(this._db, "memory").get(key));
    return row?.value ?? null;
  },
  async memoryList(prefix = "") {
    await this.init();
    const all = await asPromise(tx(this._db, "memory").getAll());
    return all.filter(r => !prefix || r.key.startsWith(prefix)).sort((a, b) => a.key.localeCompare(b.key));
  },
  async memoryDelete(key) {
    await this.init();
    const existing = await asPromise(tx(this._db, "memory").get(key));
    if (!existing) return false;
    await asPromise(tx(this._db, "memory", "readwrite").delete(key));
    return true;
  },

  // ---- files (v4.5.4) ----

  async createFile(file, { tags = "", description = "" } = {}) {
    await this.init();
    const id = uuid();
    const buf = await file.arrayBuffer();
    const meta = {
      id,
      filename: file.name || "upload",
      mime: file.type || "application/octet-stream",
      size: buf.byteLength,
      tags: this._normTags(tags),
      description,
      created_at: Date.now() / 1000,
      // We keep blobs by the same id; sha256 is unused locally (the hub
      // dedupes via content hash, but the cost of computing SHA-256 on a
      // 100 MB video in JS is high enough that we skip it).
      sha256: "",
      storage_root: "indexeddb",
    };
    await asPromise(tx(this._db, "files_meta", "readwrite").put(meta));
    await asPromise(tx(this._db, "files_blob", "readwrite").put({ id, blob: new Blob([buf], { type: meta.mime }) }));
    return meta;
  },

  async getFileMeta(id) {
    await this.init();
    return asPromise(tx(this._db, "files_meta").get(id));
  },

  async getFileBlob(id) {
    await this.init();
    const row = await asPromise(tx(this._db, "files_blob").get(id));
    return row?.blob || null;
  },

  async listFiles({ query = "", tag = "", limit = 200 } = {}) {
    await this.init();
    const all = await asPromise(tx(this._db, "files_meta").getAll());
    const q = query.toLowerCase();
    let f = all;
    if (q) f = f.filter(m => (m.filename || "").toLowerCase().includes(q) ||
                              (m.description || "").toLowerCase().includes(q));
    if (tag) f = f.filter(m => (`,${m.tags || ""},`).includes(`,${tag.trim()},`));
    f.sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
    return f.slice(0, limit);
  },

  async filesUsage() {
    await this.init();
    const all = await asPromise(tx(this._db, "files_meta").getAll());
    return { count: all.length, total_bytes: all.reduce((s, m) => s + (m.size || 0), 0) };
  },

  async deleteFile(id) {
    await this.init();
    const existing = await asPromise(tx(this._db, "files_meta").get(id));
    if (!existing) return false;
    await asPromise(tx(this._db, "files_meta", "readwrite").delete(id));
    await asPromise(tx(this._db, "files_blob", "readwrite").delete(id));
    return true;
  },

  // ---- export / import (for manual sync) ----

  async exportAll() {
    await this.init();
    return {
      schema: 1,
      exported_at: Date.now() / 1000,
      notes: await asPromise(tx(this._db, "notes").getAll()),
      memory: await asPromise(tx(this._db, "memory").getAll()),
    };
  },

  async importMerge(snapshot) {
    if (!snapshot || snapshot.schema !== 1) throw new Error("incompatible export");
    await this.init();
    let added = 0, updated = 0;
    for (const n of snapshot.notes || []) {
      const existing = await asPromise(tx(this._db, "notes").get(n.id));
      if (!existing) { await asPromise(tx(this._db, "notes", "readwrite").add(n)); added++; }
      else if ((existing.updated_at || 0) < (n.updated_at || 0)) {
        await asPromise(tx(this._db, "notes", "readwrite").put(n)); updated++;
      }
    }
    for (const m of snapshot.memory || []) {
      const existing = await asPromise(tx(this._db, "memory").get(m.key));
      if (!existing || (existing.updated_at || 0) < (m.updated_at || 0)) {
        await asPromise(tx(this._db, "memory", "readwrite").put(m));
        existing ? updated++ : added++;
      }
    }
    return { added, updated };
  },
};

window.localStore = localStore;
