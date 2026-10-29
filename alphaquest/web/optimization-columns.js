"use strict";

// Browser presentation only; saved calculations, sorting and CSVs remain intact.
window.OptimizationColumns = class {
  constructor(table, region, panel) {
    Object.assign(this, {table, region, panel, columns: [], preferences: new Map(), frame: null, dirty: true});
    this.search = panel.querySelector("input[type=search]");
    this.choices = panel.querySelector(".optimization-column-choices");
    this.status = panel.querySelector("[role=status]");
    this.summary = panel.querySelector(".optimization-freeze-count");
    this.shownSummary = panel.querySelector(".optimization-column-count");
    this.empty = document.querySelector("#optimization-visible-empty");
    this.search.addEventListener("input", () => this.filter());
    panel.querySelector("[data-columns=reset]").onclick = () => {
      this.state = this.defaults();
      this.save();
    };
    panel.querySelector("[data-columns=all]").onclick = () => { this.state.visible = null; this.save(); };
    panel.querySelector("[data-columns=hide]").onclick = () => { this.state.visible = []; this.state.frozen = []; this.save(); };
    panel.querySelector("[data-freeze=none]").onclick = () => this.choose([]);
    window.addEventListener("scroll", () => this.layout(), {passive: true});
    window.addEventListener("resize", () => this.layout(true));
    new ResizeObserver(() => this.layout(true)).observe(region);
    new ResizeObserver(() => this.layout(true)).observe(table);
  }

  defaults() { return {visible: null, frozen: ["trial"], order: []}; }
  keys(value) { return Array.isArray(value) && value.every((key) => typeof key === "string"); }
  unique(keys) { return [...new Set(keys)]; }

  load(strategyId) {
    if (this.preferences.has(this.identity)) return this.preferences.get(this.identity);
    try {
      const saved = JSON.parse(localStorage.getItem(this.identity));
      if (saved && (saved.visible === null || this.keys(saved.visible)) && this.keys(saved.frozen) && this.keys(saved.order)) {
        return {visible: saved.visible === null ? null : this.unique(saved.visible), frozen: this.unique(saved.frozen), order: this.unique(saved.order)};
      }
      // Preserve the previous freeze-only preferences on first use of Columns.
      const legacy = JSON.parse(localStorage.getItem(`alphaquest.optimization.frozen-columns.v1:${strategyId}`));
      if (this.keys(legacy)) return {...this.defaults(), frozen: this.unique(legacy)};
    } catch { /* Invalid or blocked storage falls back to an editable default. */ }
    return this.defaults();
  }

  configure(strategyId, columns) {
    const identity = `alphaquest.optimization.column-layout.v2:${strategyId}`;
    const changed = this.identity !== identity || JSON.stringify(this.columns) !== JSON.stringify(columns);
    if (this.identity !== identity) {
      this.identity = identity;
      this.state = this.load(strategyId);
    }
    this.columns = columns;
    this.panel.hidden = false;
    if (changed) this.renderChoices();
    this.layout(true);
  }

  renderChoices() {
    this.choices.replaceChildren();
    for (const [key, title] of this.columns) {
      const row = document.createElement("div");
      row.className = "optimization-column-choice";
      Object.assign(row.dataset, {column: key, title});
      const name = document.createElement("span");
      name.className = "optimization-column-name";
      name.textContent = title;
      const hint = document.createElement("small");
      hint.className = "optimization-column-limit";
      hint.textContent = "Width limit";
      name.append(hint);
      row.append(name);
      for (const control of ["show", "freeze"]) {
        const label = document.createElement("label");
        const input = document.createElement("input");
        input.type = "checkbox";
        input.dataset.control = control;
        const action = control === "show" ? "Show" : "Freeze";
        input.setAttribute("aria-label", `${action} ${title}`);
        input.setAttribute("aria-describedby", "optimization-freeze-help optimization-freeze-status");
        input.onchange = () => control === "show" ? this.show(key, input.checked)
          : this.choose(input.checked ? [...this.state.frozen, key] : this.state.frozen.filter((item) => item !== key));
        label.append(input, action);
        row.append(label);
      }
      const actions = document.createElement("div");
      actions.className = "optimization-column-move";
      for (const [delta, action, icon] of [[-1, "earlier", "↑"], [1, "later", "↓"]]) {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = icon;
        button.dataset.delta = delta;
        button.setAttribute("aria-label", `Move ${title} ${action}`);
        button.title = `Move ${title} ${action} within its frozen or scrolling group`;
        button.onclick = () => this.move(key, delta);
        actions.append(button);
      }
      row.append(actions);
      this.choices.append(row);
    }
    this.filter();
  }

  clear() {
    this.columns = [];
    this.panel.hidden = true;
    this.empty.hidden = true;
    this.layout(true);
  }

  save() {
    this.preferences.set(this.identity, this.state);
    try { localStorage.setItem(this.identity, JSON.stringify(this.state)); }
    catch { /* Preferences still work in this page session. */ }
    this.layout(true);
  }

  shown() { return new Set(this.state.visible ?? this.columns.map(([key]) => key)); }
  orderedKeys() {
    const available = new Set(this.columns.map(([key]) => key));
    return this.unique([...this.state.order, ...available]).filter((key) => available.has(key));
  }
  displayOrder(active) { return [...active, ...this.orderedKeys().filter((key) => !active.includes(key))]; }

  choose(keys) {
    this.state.frozen = this.unique(keys);
    this.state.order = this.unique([...keys, ...this.orderedKeys(), ...this.state.order]);
    this.save();
  }

  show(key, visible) {
    const shown = this.shown();
    if (visible) shown.add(key);
    else {
      shown.delete(key);
      this.state.frozen = this.state.frozen.filter((item) => item !== key);
    }
    this.state.visible = [...shown];
    this.save();
  }

  moveGroup(key) {
    const shown = this.shown(), active = this.active || [];
    return this.displayOrder(active).filter((item) => shown.has(item) && active.includes(item) === active.includes(key));
  }

  move(key, delta) {
    const group = this.moveGroup(key), target = group[group.indexOf(key) + delta];
    if (!target || !this.shown().has(key)) return;
    const order = this.displayOrder(this.active || []);
    const first = order.indexOf(key), second = order.indexOf(target);
    [order[first], order[second]] = [order[second], order[first]];
    this.state.order = order;
    if (this.active.includes(key)) this.state.frozen.sort((a, b) => order.indexOf(a) - order.indexOf(b));
    this.save();
  }

  filter() {
    const query = this.search.value.trim().toLocaleLowerCase();
    for (const row of this.choices.children) row.hidden = !row.dataset.title.toLocaleLowerCase().includes(query) && !row.dataset.column.toLocaleLowerCase().includes(query);
    this.panel.querySelector(".optimization-column-empty").hidden = Array.from(this.choices.children).some((row) => !row.hidden);
  }

  widths() {
    return new Map(Array.from(this.table.tHead.rows[0].cells, (cell) => [cell.dataset.column, cell.getBoundingClientRect().width]));
  }

  order(active) {
    const order = this.displayOrder(active);
    for (const row of this.table.rows) {
      if (Array.from(row.cells, (cell) => cell.dataset.column).every((key, index) => key === order[index])) continue;
      const cells = new Map(Array.from(row.cells, (cell) => [cell.dataset.column, cell]));
      for (const key of order) row.append(cells.get(key));
    }
    const current = Array.from(this.choices.children);
    if (current.some((row, index) => row.dataset.column !== order[index])) {
      const focus = this.choices.contains(document.activeElement) ? document.activeElement : null;
      const scrollTop = this.choices.scrollTop;
      const rows = new Map(current.map((row) => [row.dataset.column, row]));
      for (const key of order) this.choices.append(rows.get(key));
      focus?.focus({preventScroll: true});
      this.choices.scrollTop = scrollTop;
    }
  }

  layout(columnsChanged = false) {
    this.dirty ||= columnsChanged;
    if (this.frame !== null) return;
    this.frame = requestAnimationFrame(() => {
      this.frame = null;
      if (!this.region.clientWidth || !this.table.tHead.rows.length) return;
      if (this.columns.length && this.dirty) this.applyColumns();
      const height = this.table.tHead.getBoundingClientRect().height;
      const top = Math.min(Math.max(0, -this.region.getBoundingClientRect().top), Math.max(0, this.region.clientHeight - height));
      this.region.style.setProperty("--optimization-header-top", `${top}px`);
    });
  }

  applyColumns() {
    this.dirty = false;
    const shown = this.shown();
    for (const row of this.table.rows) for (const cell of row.cells) cell.hidden = !shown.has(cell.dataset.column);
    const visibleCount = this.columns.filter(([key]) => shown.has(key)).length;
    this.empty.hidden = visibleCount > 0;
    const limit = Math.floor(this.region.clientWidth * 0.4);
    let widths = this.widths(), used = 0;
    const active = this.state.frozen.filter((key) => {
      const width = widths.get(key);
      if (!shown.has(key) || !width || used + width > limit) return false;
      used += width;
      return true;
    });
    this.order(active);
    widths = this.widths();
    used = active.reduce((sum, key) => sum + widths.get(key), 0);
    while (used > limit && active.length) used -= widths.get(active.pop());
    this.order(active);
    widths = this.widths();
    const positions = new Map();
    let left = 0;
    for (const key of active) { positions.set(key, left); left += widths.get(key); }
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
      const key = row.dataset.column;
      const show = row.querySelector('[data-control="show"]'), freeze = row.querySelector('[data-control="freeze"]');
      show.checked = shown.has(key);
      freeze.checked = active.includes(key);
      const tooWide = !freeze.checked && left + widths.get(key) > limit;
      freeze.disabled = !show.checked || tooWide;
      blocked ||= show.checked && tooWide;
      row.querySelector("small").hidden = !show.checked || !tooWide;
      row.title = !show.checked ? "Show this column before freezing or moving it." : tooWide
        ? "Unfreeze another column to preserve space for results. Frozen columns can use at most 40% of the table width." : "";
      const group = this.moveGroup(key), index = group.indexOf(key);
      for (const button of row.querySelectorAll("button")) button.disabled = !show.checked || !group[index + Number(button.dataset.delta)];
    }
    this.summary.textContent = `${active.length} frozen`;
    this.shownSummary.textContent = `${visibleCount} shown ·`;
    const paused = this.state.frozen.some((key) => shown.has(key) && widths.has(key) && !active.includes(key));
    this.status.textContent = `${visibleCount} shown · ${active.length} frozen · ${Math.round(left / this.region.clientWidth * 100)}% of table width (40% maximum).${paused ? " Some saved selections do not fit at this width; they will return when space permits." : ""}${blocked ? " Unfreeze another column to preserve space for results, or widen the table." : ""}`;
  }
};
