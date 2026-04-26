// Local IndexedDB store — used when no hub URL is configured.
//
// autoMate's "smart NAS for AI" model: each device has its own data, sync
// is opt-in. This module gives the SPA a working notes/memory store even
// when the user has no hub running on their laptop yet. Files and reminders
// stay hub-only for now (binary blobs are heavy in IndexedDB; reminders
// need a scheduler the phone OS won't let us run reliably).

const DB_NAME = "automate-local";
const DB_VERSION = 1;
const STORES = ["notes", "memory"];

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      for (const name of STORES) {
        if (!db.objectStoreNames.contains(name)) {
          const keyPath = name === "memory" ? "key" : "id";
          db.createObjectStore(name, { keyPath });
        }
      }
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
