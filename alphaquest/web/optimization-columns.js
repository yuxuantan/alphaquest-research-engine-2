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
    panel.querySelector("[data-columns=all]").onclick = () => { this.state.visible = "all"; this.save(); };
    panel.querySelector("[data-columns=hide]").onclick = () => { this.state.visible = []; this.state.frozen = []; this.save(); };
    panel.querySelector("[data-freeze=none]").onclick = () => this.choose([]);
    window.addEventListener("scroll", () => this.layout(), {passive: true});
    window.addEventListener("resize", () => this.layout(true));
    region.addEventListener("scroll", () => this.panFrozen(), {passive: true});
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
      if (saved && (saved.visible === null || saved.visible === "all" || this.keys(saved.visible)) && this.keys(saved.frozen) && this.keys(saved.order)) {
        return {...saved, visible: Array.isArray(saved.visible) ? this.unique(saved.visible) : saved.visible, frozen: this.unique(saved.frozen), order: this.unique(saved.order)};
      }
      const previous = JSON.parse(localStorage.getItem(`alphaquest.optimization.column-layout.v2:${strategyId}`));
      if (previous && (previous.visible === null || this.keys(previous.visible)) && this.keys(previous.frozen) && this.keys(previous.order)) {
        return {visible: previous.visible, frozen: this.unique(previous.frozen), order: this.unique(previous.order)};
      }
      // Preserve the previous freeze-only preferences on first use of Columns.
      const legacy = JSON.parse(localStorage.getItem(`alphaquest.optimization.frozen-columns.v1:${strategyId}`));
      if (this.keys(legacy)) return {...this.defaults(), frozen: this.unique(legacy)};
    } catch { /* Invalid or blocked storage falls back to an editable default. */ }
    return this.defaults();
  }

  configure(strategyId, columns, defaultVisible = columns.map(([key]) => key)) {
    const identity = `alphaquest.optimization.column-layout.v3:${strategyId}`;
    const changed = this.identity !== identity || JSON.stringify(this.columns) !== JSON.stringify(columns) || JSON.stringify(this.defaultVisible) !== JSON.stringify(defaultVisible);
    if (this.identity !== identity) {
      this.identity = identity;
      this.state = this.load(strategyId);
    }
    this.columns = columns;
    this.defaultVisible = defaultVisible;
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
        button.addEventListener("blur", () => this.layout(true));
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

  shown() { return new Set(this.state.visible === "all" ? this.columns.map(([key]) => key) : this.state.visible ?? this.defaultVisible); }
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
    let widths = this.widths();
    const active = this.unique(this.state.frozen).filter(key => shown.has(key) && widths.get(key));
    this.order(active);
    widths = this.widths();
    const positions = new Map();
    let left = 0;
    for (const key of active) { positions.set(key, left); left += widths.get(key); }
    this.active = active;
    this.panWide = left > this.region.clientWidth;
    this.panFrozen();
    for (const row of this.table.rows) {
      for (const cell of row.cells) {
        const frozen = positions.has(cell.dataset.column);
        cell.classList.toggle("optimization-frozen-column", frozen);
        cell.classList.toggle("optimization-frozen-last", frozen && cell.dataset.column === active.at(-1));
        if (frozen) cell.style.setProperty("--optimization-frozen-left", `${positions.get(cell.dataset.column)}px`);
        else cell.style.removeProperty("--optimization-frozen-left");
      }
    }
    for (const row of this.choices.children) {
      const key = row.dataset.column;
      const show = row.querySelector('[data-control="show"]'), freeze = row.querySelector('[data-control="freeze"]');
      show.checked = shown.has(key);
      freeze.checked = active.includes(key);
      freeze.disabled = !show.checked;
      row.title = !show.checked ? "Show this column before freezing or moving it." : "";
      const group = this.moveGroup(key), index = group.indexOf(key);
      for (const button of row.querySelectorAll("button")) {
        const disabled = !show.checked || !group[index + Number(button.dataset.delta)];
        // Retain keyboard focus when a move reaches the end of its group.
        // move() already ignores an unavailable destination.
        button.disabled = disabled && document.activeElement !== button;
        button.setAttribute("aria-disabled", String(disabled));
      }
    }
    this.summary.textContent = `${active.length} frozen`;
    this.shownSummary.textContent = `${visibleCount} shown ·`;
    this.status.textContent = `${visibleCount} shown · ${active.length} frozen.${this.panWide ? " Scroll horizontally to pan the frozen group." : ""}`;
  }

  panFrozen() {
    // An oversized frozen group cannot all fit on screen at once. Keep every
    // selection and pan it with the table so its columns remain reachable.
    this.region.style.setProperty("--optimization-frozen-pan", `${this.panWide ? this.region.scrollLeft : 0}px`);
  }
};
