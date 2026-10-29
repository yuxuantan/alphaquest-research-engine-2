"use strict";

// Presentation preferences only: freezing never changes a job, its sort or CSV.
window.OptimizationColumns = class {
  constructor(table, region, panel) {
    this.table = table;
    this.region = region;
    this.panel = panel;
    this.columns = [];
    this.preferences = new Map();
    this.frame = null;
    this.dirty = true;
    this.search = panel.querySelector("input[type=search]");
    this.choices = panel.querySelector(".optimization-column-choices");
    this.status = panel.querySelector("[role=status]");
    this.summary = panel.querySelector(".optimization-freeze-count");
    this.search.addEventListener("input", () => this.filter());
    panel.querySelector("[data-freeze=reset]").onclick = () => this.choose(["trial"]);
    panel.querySelector("[data-freeze=none]").onclick = () => this.choose([]);
    window.addEventListener("scroll", () => this.layout(), {passive: true});
    window.addEventListener("resize", () => this.layout(true));
    new ResizeObserver(() => this.layout(true)).observe(region);
    new ResizeObserver(() => this.layout(true)).observe(table);
  }

  configure(strategyId, columns) {
    const identity = `alphaquest.optimization.frozen-columns.v1:${strategyId}`;
    const changed = this.identity !== identity || JSON.stringify(this.columns) !== JSON.stringify(columns);
    if (this.identity !== identity) {
      this.identity = identity;
      let saved = this.preferences.get(identity);
      if (!saved) {
        try {
          const value = JSON.parse(localStorage.getItem(identity));
          if (Array.isArray(value) && value.every((key) => typeof key === "string")) saved = [...new Set(value)];
        } catch { /* A blocked or malformed browser store falls back to Trial. */ }
      }
      this.wanted = saved || ["trial"];
    }
    this.columns = columns;
    this.panel.hidden = false;
    if (changed) {
      this.choices.replaceChildren();
      for (const [key, title] of columns) {
        const row = document.createElement("label");
        row.className = "optimization-column-choice";
        row.dataset.column = key;
        const input = document.createElement("input");
        input.type = "checkbox";
        input.setAttribute("aria-label", `Freeze ${title}`);
        input.setAttribute("aria-describedby", "optimization-freeze-help optimization-freeze-status");
        input.onchange = () => this.choose(input.checked ? [...this.wanted, key] : this.wanted.filter((item) => item !== key));
        const text = document.createElement("span");
        text.textContent = title;
        const hint = document.createElement("small");
        hint.className = "optimization-column-limit";
        hint.textContent = "Width limit";
        row.append(input, text, hint);
        this.choices.append(row);
      }
      this.filter();
    }
    this.layout(true);
  }

  clear() {
    this.columns = [];
    this.panel.hidden = true;
    this.layout(true);
  }

  choose(keys) {
    this.wanted = [...new Set(keys)];
    this.preferences.set(this.identity, this.wanted);
    try { localStorage.setItem(this.identity, JSON.stringify(this.wanted)); }
    catch { /* In-session preferences still work when storage is unavailable. */ }
    this.layout(true);
  }

  filter() {
    const query = this.search.value.trim().toLocaleLowerCase();
    for (const row of this.choices.children) row.hidden = !row.querySelector("span").textContent.toLocaleLowerCase().includes(query) && !row.dataset.column.toLocaleLowerCase().includes(query);
    this.panel.querySelector(".optimization-column-empty").hidden = Array.from(this.choices.children).some((row) => !row.hidden);
  }

  widths() {
    return new Map(Array.from(this.table.tHead.rows[0].cells, (cell) => [cell.dataset.column, cell.getBoundingClientRect().width]));
  }

  order(active) {
    const order = [...active, ...this.columns.map(([key]) => key).filter((key) => !active.includes(key))];
    for (const row of this.table.rows) {
      if (Array.from(row.cells, (cell) => cell.dataset.column).every((key, index) => key === order[index])) continue;
      const cells = new Map(Array.from(row.cells, (cell) => [cell.dataset.column, cell]));
      for (const key of order) row.append(cells.get(key));
    }
  }

  layout(columnsChanged = false) {
    this.dirty ||= columnsChanged;
    if (this.frame !== null) return;
    this.frame = requestAnimationFrame(() => {
      this.frame = null;
      if (!this.region.clientWidth || !this.table.tHead.rows.length) return;
      const height = this.table.tHead.getBoundingClientRect().height;
      const top = Math.min(Math.max(0, -this.region.getBoundingClientRect().top), Math.max(0, this.region.clientHeight - height));
      this.region.style.setProperty("--optimization-header-top", `${top}px`);
      if (!this.columns.length || !this.dirty) return;
      this.dirty = false;

      const limit = Math.floor(this.region.clientWidth * 0.4);
      let widths = this.widths(), used = 0;
      const active = this.wanted.filter((key) => {
        const width = widths.get(key);
        if (!width || used + width > limit) return false;
        used += width;
        return true;
      });
      this.order(active);
      // Measure again after reordering, including fractional pixel rounding.
      widths = this.widths();
      used = active.reduce((sum, key) => sum + widths.get(key), 0);
      while (used > limit && active.length) used -= widths.get(active.pop());
      this.order(active);
      widths = this.widths();
      const positions = new Map();
      let left = 0;
      for (const key of active) {
        positions.set(key, left);
        left += widths.get(key);
      }
      this.active = active;
      for (const row of this.table.rows) {
        for (const cell of row.cells) {
          const frozen = positions.has(cell.dataset.column);
          cell.classList.toggle("optimization-frozen-column", frozen);
          cell.classList.toggle("optimization-frozen-last", frozen && cell.dataset.column === active.at(-1));
          if (frozen) cell.style.setProperty("--optimization-frozen-left", `${positions.get(cell.dataset.column)}px`);
          else cell.style.removeProperty("--optimization-frozen-left");
        }
      }
      let blocked = false;
      for (const row of this.choices.children) {
        const input = row.querySelector("input");
        input.checked = active.includes(row.dataset.column);
        input.disabled = !input.checked && left + widths.get(row.dataset.column) > limit;
        blocked ||= input.disabled;
        row.querySelector("small").hidden = !input.disabled;
        row.title = input.disabled ? "Unfreeze another column to preserve space for results. Frozen columns can use at most 40% of the table width." : "";
      }
      this.summary.textContent = `${active.length} frozen`;
      const paused = this.wanted.some((key) => widths.has(key) && !active.includes(key));
      this.status.textContent = `${active.length} frozen · ${Math.round(left / this.region.clientWidth * 100)}% of table width (40% maximum).${paused ? " Some saved selections do not fit at this width; they will return when space permits." : ""}${blocked ? " Unfreeze another column to preserve space for results, or widen the table." : ""}`;
    });
  }
};
