/* ProofTrail static UI. Progressive enhancement only: every page reads without this file. */
(function () {
  "use strict";

  function setLabel(button, text) {
    var label = button.querySelector("span");
    if (label) {
      label.textContent = text;
    }
  }

  function copyText(value) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(value);
    }
    // file:// pages are not a secure context, so fall back to a hidden field.
    return new Promise(function (resolve, reject) {
      var field = document.createElement("textarea");
      field.value = value;
      field.setAttribute("readonly", "");
      field.style.position = "fixed";
      field.style.opacity = "0";
      document.body.appendChild(field);
      field.select();
      var copied = document.execCommand("copy");
      document.body.removeChild(field);
      if (copied) {
        resolve();
      } else {
        reject(new Error("copy blocked"));
      }
    });
  }

  document.addEventListener("click", function (event) {
    var copyButton = event.target.closest("[data-copy]");
    if (copyButton) {
      copyText(copyButton.getAttribute("data-copy")).then(
        function () {
          setLabel(copyButton, "Copied");
        },
        function () {
          setLabel(copyButton, "Copy failed");
        }
      ).then(function () {
        window.setTimeout(function () {
          setLabel(copyButton, "Copy");
        }, 1400);
      });
      return;
    }
    if (event.target.closest("[data-print]")) {
      window.print();
    }
  });

  var app = document.querySelector(".app");
  var sidebarToggle = document.querySelector("[data-sidebar-toggle]");
  if (app && sidebarToggle) {
    sidebarToggle.addEventListener("click", function () {
      var expanded = app.getAttribute("data-sidebar") !== "expanded";
      app.setAttribute("data-sidebar", expanded ? "expanded" : "collapsed");
      sidebarToggle.setAttribute("aria-expanded", expanded ? "true" : "false");
    });
  }

  var filters = document.getElementById("filters");
  document.addEventListener("click", function (event) {
    if (!filters) {
      return;
    }
    if (event.target.closest("[data-open-filters]")) {
      if (typeof filters.showModal === "function") {
        filters.showModal();
      } else {
        filters.setAttribute("open", "");
      }
    }
    if (event.target.closest("[data-close-filters]")) {
      if (typeof filters.close === "function") {
        filters.close();
      } else {
        filters.removeAttribute("open");
      }
    }
  });

  var caseTable = document.querySelector("[data-case-table]");
  if (caseTable) {
    var rows = Array.prototype.slice.call(caseTable.querySelectorAll("tbody tr"));
    var controls = Array.prototype.slice.call(document.querySelectorAll("[data-filter]"));
    var counter = document.querySelector("[data-count]");
    var empty = document.querySelector("[data-empty]");
    var search = document.querySelector("[data-case-search]");
    var sort = document.querySelector("[data-case-sort]");
    var params = new URLSearchParams(window.location.search);
    controls.forEach(function (control) {
      var value = params.get(control.getAttribute("data-filter"));
      if (value !== null) { control.value = value; }
    });
    if (search) { search.value = params.get("q") || ""; }
    if (sort) { sort.value = params.get("sort") === "desc" ? "desc" : "asc"; }

    var applyFilters = function () {
      var active = {};
      controls.forEach(function (control) {
        active[control.getAttribute("data-filter")] = control.value;
      });
      var shown = 0;
      rows.forEach(function (row) {
        var matches = Object.keys(active).every(function (key) {
          return !active[key] || row.getAttribute("data-" + key) === active[key];
        });
        matches = matches && (!search || row.textContent.toLowerCase().includes(search.value.trim().toLowerCase()));
        row.hidden = !matches;
        if (matches) {
          shown += 1;
        }
      });
      if (counter) {
        counter.textContent = "Showing " + shown + " of " + rows.length + " cases";
      }
      if (empty) {
        empty.hidden = shown !== 0;
      }
      rows.sort(function (a, b) {
        var order = a.cells[0].textContent.localeCompare(b.cells[0].textContent);
        return sort && sort.value === "desc" ? -order : order;
      }).forEach(function (row) { caseTable.tBodies[0].appendChild(row); });
      var query = new URLSearchParams();
      Object.keys(active).forEach(function (key) { if (active[key]) { query.set(key, active[key]); } });
      if (search && search.value) { query.set("q", search.value); }
      if (sort && sort.value === "desc") { query.set("sort", "desc"); }
      if (window.location.protocol !== "file:") {
        window.history.replaceState(null, "", window.location.pathname + (query.size ? "?" + query.toString() : "") + window.location.hash);
      }
    };

    controls.forEach(function (control) {
      control.addEventListener("change", applyFilters);
    });
    if (search) { search.addEventListener("input", applyFilters); }
    if (sort) { sort.addEventListener("change", applyFilters); }
    var reset = document.querySelector("[data-reset-filters]");
    if (reset) {
      reset.addEventListener("click", function () {
        controls.forEach(function (control) {
          control.value = "";
        });
        if (search) { search.value = ""; }
        if (sort) { sort.value = "asc"; }
        applyFilters();
      });
    }
  }

  if (caseTable) { applyFilters(); }

  // Mobile starts the long sections collapsed. A deep link still opens its own section.
  if (window.matchMedia && window.matchMedia("(max-width: 767px)").matches) {
    Array.prototype.forEach.call(document.querySelectorAll("details[data-collapsible]"), function (section) {
      section.open = false;
    });
  }

  var inspectors = document.querySelectorAll("[data-inspector]");
  if (inspectors.length) {
    var eventItems = document.querySelectorAll("[data-event-seq]");

    var selectClaim = function (slug) {
      var found = false;
      Array.prototype.forEach.call(inspectors, function (panel) {
        var on = panel.getAttribute("data-inspector") === slug;
        panel.hidden = !on;
        found = found || on;
      });
      if (!found) {
        return;
      }
      Array.prototype.forEach.call(document.querySelectorAll(".claim-card"), function (card) {
        var on = card.getAttribute("data-select-claim") === slug;
        card.classList.toggle("is-selected", on);
        card.setAttribute("aria-pressed", on ? "true" : "false");
      });
      Array.prototype.forEach.call(document.querySelectorAll(".claim-span"), function (span) {
        span.classList.toggle("is-selected", span.getAttribute("data-select-claim") === slug);
      });
      Array.prototype.forEach.call(eventItems, function (item) {
        var cited = (item.getAttribute("data-cited-by") || "").split(" ");
        item.classList.toggle("is-cited", cited.indexOf(slug) !== -1);
      });
    };

    var syncFromHash = function () {
      var id = decodeURIComponent(window.location.hash.slice(1));
      if (!id) {
        return;
      }
      var target = document.getElementById(id);
      for (var node = target; node; node = node.parentElement) {
        if (node.tagName === "DETAILS") {
          node.open = true;
        }
      }
      if (id.indexOf("claim-") === 0) {
        selectClaim(id);
      } else if (id.indexOf("event-") === 0 && target) {
        var cited = (target.getAttribute("data-cited-by") || "").split(" ");
        if (cited[0]) {
          selectClaim(cited[0]);
        }
      }
    };

    document.addEventListener("click", function (event) {
      var trigger = event.target.closest("[data-select-claim]");
      if (!trigger) {
        return;
      }
      var slug = trigger.getAttribute("data-select-claim");
      selectClaim(slug);
      if (window.history && window.history.replaceState) {
        window.history.replaceState(null, "", "#" + slug);
      }
    });
    window.addEventListener("hashchange", syncFromHash);
    syncFromHash();
  }
})();
