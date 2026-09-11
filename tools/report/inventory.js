"use strict";

(() => {
  const db = globalThis.SYMBOL_INVENTORY;
  const byId = (id) => document.getElementById(id);
  if (!db) {
    byId("result-count").textContent = "Could not load inventory.js. Rebuild with tools/build_inventory.py and keep the generated files together.";
    return;
  }
  const format = (value) => value.toLocaleString("en-US");
  const hex = (value) => `U+${value.toString(16).toUpperCase().padStart(4, "0")}`;
  const human = (value) => value.replaceAll("_", " ");
  const make = (tag, className = "", text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  };
  const symbolsByCodepoint = new Map(db.symbols.map((symbol) => [symbol.codepoint, symbol]));
  const controls = {
    search: byId("search"), group: byId("group-by"), groupFilter: byId("group-filter"),
    pool: byId("pool"), letters: byId("letters"), script: byId("script"),
  };
  const results = byId("results");
  const detail = byId("detail");
  let selected = null;
  let toastTimer;
  const subheading = (symbol) => db.sections[symbol.namesList.section]?.label || "No subheading";
  const searchable = new Map(db.symbols.map((symbol) => [symbol.codepoint, [
    symbol.name, symbol.block, symbol.script, subheading(symbol), ...symbol.aliases,
    ...symbol.formalAliases.map((alias) => alias.name),
    ...symbol.namesList.annotations.filter((note) => ["note", "notice"].includes(note.type)).map((note) => note.text),
  ].join(" ").toLowerCase()]));

  byId("version").textContent = db.unicodeVersion;
  for (const [label, value] of [
    ["Candidates to review", db.summary.candidates], ["With Math property", db.summary.math],
    ["Additional candidates", db.summary.additional], ["Unicode blocks", Object.keys(db.summary.blocks).length],
    ["Non-ASCII letters", db.summary.nonAsciiLetters],
  ]) {
    const stat = make("div", "stat");
    stat.append(make("strong", "", format(value)), make("span", "", label));
    byId("summary").append(stat);
  }
  for (const [script, count] of Object.entries(db.summary.scripts)) {
    controls.script.add(new Option(`${human(script)} (${format(count)})`, script));
  }
  for (const [source, count] of Object.entries(db.summary.candidateReasons)) {
    byId("source-counts").append(make("p", "", `${source}: ${format(count)}`));
  }

  function preview(symbol, text = symbol.char) {
    if (["Separator", "Format/control"].includes(symbol.kind)) {
      return make("span", "invisible", symbol.kind === "Separator" ? "space" : "invisible");
    }
    const glyph = make("bdi", "glyph", (symbol.kind === "Combining mark" ? "◌" : "") + text);
    glyph.setAttribute("aria-hidden", "true");
    return glyph;
  }

  function notify(message) {
    clearTimeout(toastTimer);
    byId("toast").textContent = message;
    toastTimer = setTimeout(() => { byId("toast").textContent = ""; }, 3500);
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const active = document.activeElement;
      const textarea = make("textarea", "clipboard-fallback");
      textarea.value = text;
      document.body.append(textarea);
      textarea.select();
      let copied = false;
      try { copied = document.execCommand("copy"); } catch { /* Manual copy remains possible. */ }
      textarea.remove();
      active?.focus({ preventScroll: true });
      if (!copied) {
        notify("Copy was unavailable. Select and copy the character in its details.");
        return;
      }
    }
    notify(`Copied ${Array.from(text, (char) => hex(char.codePointAt(0))).join(" ")}`);
  }

  function section(title) {
    const container = make("section", "detail-section");
    container.append(make("h3", "", title));
    detail.append(container);
    return container;
  }

  function listSection(title, values) {
    if (!values.length) return;
    const list = make("ul");
    for (const value of values) list.append(make("li", "", value));
    section(title).append(list);
  }

  function showDetails(symbol) {
    detail.replaceChildren();
    if (!symbol) {
      detail.append(make("p", "empty", "Choose a symbol to inspect its Unicode data."));
      return;
    }
    const display = make("div", "detail-preview");
    display.append(preview(symbol));
    const copy = make("button", "copy-button", "Copy character");
    copy.type = "button";
    copy.addEventListener("click", () => copyText(symbol.char));
    detail.append(display, make("p", "detail-code", hex(symbol.codepoint)), make("h2", "detail-title", symbol.name), copy);
    const metadata = make("dl", "metadata");
    const values = [
      ["Block", symbol.block], ["Unicode subheading", subheading(symbol)],
      ["General category", `${symbol.generalCategory} · ${human(symbol.generalCategoryName)}`],
      ["Script", human(symbol.script)], ["Script extensions", symbol.scriptExtensions.map(human).join(", ")],
      ["Math property", symbol.math ? "Yes" : "No · additional review candidate"],
      ["Combining class / bidi class", `${symbol.combiningClass} / ${symbol.bidiClass}`],
      ["Bidi mirrored", symbol.bidiMirrored ? "Yes" : "No"],
    ];
    if (symbol.numericValue !== null) values.push(["Numeric value", symbol.numericValue]);
    for (const [label, value] of values) {
      const row = make("div");
      row.append(make("dt", "", label), make("dd", "", value));
      metadata.append(row);
    }
    detail.append(metadata);
    listSection("Aliases and uses · NamesList", symbol.aliases);
    listSection("Formal aliases · NameAliases", symbol.formalAliases.map((alias) => `${alias.name} (${alias.type})`));
    listSection("Character notes", symbol.namesList.annotations.filter((a) => ["note", "notice"].includes(a.type)).map((a) => a.text));
    const context = [
      ...(db.chartBlocks[symbol.namesList.chartBlock]?.annotations || []),
      ...(db.sections[symbol.namesList.section]?.annotations || []),
    ];
    listSection("Block and subheading notes", context.filter((a) => ["note", "notice"].includes(a.type)).map((a) => a.text));
    if (symbol.crossReferences.length) {
      const references = section("Related characters · not an equivalence mapping");
      for (const reference of symbol.crossReferences) {
        const label = `${String.fromCodePoint(reference.codepoint)}  ${hex(reference.codepoint)} · ${reference.name}`;
        if (reference.inInventory) {
          const button = make("button", "reference", label);
          button.type = "button";
          button.addEventListener("click", () => {
            resetFilters();
            controls.search.value = hex(reference.codepoint);
            render();
          });
          references.append(button);
        } else {
          references.append(make("p", "", `${label} (outside this inventory)`));
        }
      }
    }
    if (symbol.decomposition) {
      const {type, codepoints} = symbol.decomposition;
      const mapping = section(type === "canonical" ? "Canonical decomposition" : `Compatibility decomposition · ${type}`);
      mapping.append(make("p", "", codepoints.map(hex).join(" ")));
      const glyph = make("bdi", "glyph", String.fromCodePoint(...codepoints));
      mapping.append(glyph);
    }
    if (symbol.variants.length) {
      const variants = section("Standardized variants");
      for (const variant of symbol.variants) {
        const row = make("div", "variant");
        const info = make("div", "variant-info");
        info.append(make("p", "", variant.description), make("p", "", variant.codepoints.map(hex).join(" ")));
        if (variant.contexts.length) info.append(make("p", "", variant.contexts.join(", ")));
        const button = make("button", "", "Copy");
        button.type = "button";
        button.setAttribute("aria-label", `Copy variant: ${variant.description}`);
        button.addEventListener("click", () => copyText(variant.char));
        row.append(preview(symbol, variant.char), info, button);
        variants.append(row);
      }
    }
    listSection("Candidate sources", symbol.candidateReasons);
    listSection("Additional Unicode properties", symbol.properties);
    const raw = make("details", "detail-section");
    raw.append(make("summary", "", `NamesList annotations · entry at line ${symbol.namesList.line}`));
    for (const annotation of symbol.namesList.annotations) {
      const row = make("div", "raw-annotation");
      row.append(make("code", "", `${annotation.line} ${annotation.marker || "(text)"}`), document.createTextNode(annotation.text));
      raw.append(row);
    }
    detail.append(raw);
    detail.scrollTop = 0;
  }

  function selectSymbol(symbol) {
    if (selected !== null) byId(`symbol-${selected}`)?.setAttribute("aria-pressed", "false");
    selected = symbol?.codepoint ?? null;
    if (selected !== null) byId(`symbol-${selected}`)?.setAttribute("aria-pressed", "true");
    showDetails(symbol);
  }

  function groupName(symbol) {
    if (controls.group.value === "all") return "All candidates";
    if (controls.group.value === "subheading") return subheading(symbol);
    return human(symbol[controls.group.value]);
  }

  function matchingSymbols() {
    const query = controls.search.value.trim();
    const exactCodepoint = /^(?:U\+|0x)([0-9a-f]{1,6})$/i.exec(query)
      || /^([0-9a-f]{4,6})$/i.exec(query);
    const queryCp = exactCodepoint ? Number.parseInt(exactCodepoint[1], 16) : null;
    const glyphQuery = Array.from(query).length === 1 && symbolsByCodepoint.has(query.codePointAt(0));
    const variantQuery = Array.from(query).length > 1 && db.symbols.some((s) => s.variants.some((v) => v.char === query));
    const tokens = query.toLowerCase().split(/\s+/).filter(Boolean);
    return db.symbols.filter((symbol) => {
      if (controls.pool.value === "math" && !symbol.math) return false;
      if (controls.pool.value === "additional" && symbol.math) return false;
      const nonAsciiLetter = symbol.kind === "Letter" && !symbol.ascii;
      if (controls.letters.value === "hide" && nonAsciiLetter) return false;
      if (controls.letters.value === "only" && !nonAsciiLetter) return false;
      if (controls.script.value && symbol.script !== controls.script.value) return false;
      if (!query) return true;
      if (glyphQuery) return symbol.char === query;
      if (variantQuery) return symbol.variants.some((variant) => variant.char === query);
      if (queryCp !== null && symbol.codepoint === queryCp) return true;
      return tokens.every((token) => searchable.get(symbol.codepoint).includes(token));
    });
  }

  function render() {
    const matches = matchingSymbols();
    const groups = new Map();
    for (const symbol of matches) {
      const name = groupName(symbol);
      if (!groups.has(name)) groups.set(name, []);
      groups.get(name).push(symbol);
    }
    const groupNames = [...groups.keys()];
    if (controls.group.value !== "block") groupNames.sort((a, b) => a.localeCompare(b, "en"));
    const previousFilter = controls.groupFilter.value;
    controls.groupFilter.replaceChildren(new Option(`All groups (${format(matches.length)})`, ""));
    for (const name of groupNames) controls.groupFilter.add(new Option(`${name} (${format(groups.get(name).length)})`, name));
    if (previousFilter && !groups.has(previousFilter)) controls.groupFilter.add(new Option(`${previousFilter} (0)`, previousFilter));
    controls.groupFilter.value = previousFilter;
    controls.groupFilter.disabled = controls.group.value === "all";
    const visibleGroups = controls.groupFilter.value ? [controls.groupFilter.value] : groupNames;
    const visible = visibleGroups.flatMap((name) => groups.get(name) || []);
    const fragment = document.createDocumentFragment();
    for (const name of visibleGroups) {
      const items = groups.get(name) || [];
      if (!items.length) continue;
      const group = make("section", "symbol-group");
      const heading = make("h2", "group-heading", name);
      heading.append(make("span", "group-count", format(items.length)));
      const grid = make("div", "symbol-grid");
      for (const symbol of items) {
        const button = make("button", "symbol-card");
        button.type = "button";
        button.id = `symbol-${symbol.codepoint}`;
        button.dataset.codepoint = symbol.codepoint;
        button.setAttribute("aria-pressed", "false");
        button.setAttribute("aria-label", `${hex(symbol.codepoint)} ${symbol.name}`);
        button.title = `${hex(symbol.codepoint)} ${symbol.name}\n${symbol.math ? "Math property" : "Additional candidate"}`;
        button.append(preview(symbol), make("span", "code", hex(symbol.codepoint)));
        if (symbol.math) button.append(make("span", "math-mark"));
        grid.append(button);
      }
      group.append(heading, grid);
      fragment.append(group);
    }
    if (!visible.length) fragment.append(make("p", "empty", "No candidates match these filters. Try another term or reset the filters."));
    results.replaceChildren(fragment);
    const mathCount = visible.filter((symbol) => symbol.math).length;
    byId("result-count").textContent = `${format(visible.length)} of ${format(db.symbols.length)} candidates · ${format(mathCount)} Math · ${format(visible.length - mathCount)} additional`;
    selectSymbol(visible.find((symbol) => symbol.codepoint === selected) || visible[0]);
  }

  results.addEventListener("click", (event) => {
    const button = event.target.closest(".symbol-card");
    if (!button) return;
    selectSymbol(symbolsByCodepoint.get(Number(button.dataset.codepoint)));
    if (window.matchMedia("(max-width: 700px)").matches) detail.scrollIntoView({block: "start"});
  });

  function resetFilters() {
    controls.search.value = "";
    controls.pool.value = controls.letters.value = "all";
    controls.script.value = controls.groupFilter.value = "";
  }

  let searchTimer;
  controls.search.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(render, 100);
  });
  for (const [name, control] of Object.entries(controls)) {
    if (name === "search") continue;
    control.addEventListener("change", () => {
      if (name === "group") controls.groupFilter.value = "";
      render();
    });
  }
  byId("reset").addEventListener("click", () => { resetFilters(); render(); });
  byId("glyph-size").addEventListener("input", (event) => {
    const value = event.target.value;
    document.documentElement.style.setProperty("--glyph-size", `${value}px`);
    byId("size-value").value = `${value} px`;
  });
  render();
})();
