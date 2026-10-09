/* GitHub execution audit form. Results are rendered as text only, never as HTML. */
(function () {
  "use strict";
  var form = document.querySelector("[data-github-form]");
  if (!form) { return; }
  var domain = document.querySelector("[data-audit-domain]");
  var status = document.querySelector("[data-github-status]");
  var panel = document.querySelector("[data-github-result]");
  var submit = form.querySelector("[data-github-submit]");
  var exampleSelect = form.querySelector("[data-gh-example]");
  var exampleButton = form.querySelector("[data-gh-load-example]");
  var bundleField = form.querySelector("[data-gh-bundle]");
  var offlineBox = form.querySelector("[data-gh-offline]");
  var liveNote = form.querySelector("[data-gh-live]");
  var pending = false;
  var urls = [];
  var MAX_BYTES = 2 * 1024 * 1024;

  function value(name) {
    return form.elements.namedItem(name).value;
  }

  function node(tag, content, className) {
    var element = document.createElement(tag);
    element.textContent = content === null || content === undefined ? "-" : String(content);
    if (className) { element.className = className; }
    return element;
  }

  function cell(content, className) {
    return node("td", content, className);
  }

  function verdictCell(verdict) {
    var element = document.createElement("td");
    var badge = node("span", verdict, "badge badge--" + String(verdict).toLowerCase() + " verdict-mark");
    element.appendChild(badge);
    return element;
  }

  function table(caption, headers, rows) {
    var wrap = document.createElement("div");
    wrap.className = "table-wrap";
    var element = document.createElement("table");
    element.appendChild(node("caption", caption));
    var head = document.createElement("thead");
    var headRow = document.createElement("tr");
    headers.forEach(function (label) {
      var heading = node("th", label);
      heading.scope = "col";
      headRow.appendChild(heading);
    });
    head.appendChild(headRow);
    element.appendChild(head);
    var body = document.createElement("tbody");
    rows.forEach(function (cells) {
      var row = document.createElement("tr");
      cells.forEach(function (item, index) {
        item.setAttribute("data-label", headers[index]);
        row.appendChild(item);
      });
      body.appendChild(row);
    });
    element.appendChild(body);
    wrap.appendChild(element);
    return wrap;
  }

  function setStatus(message) {
    status.textContent = message;
  }

  function busy(flag) {
    pending = flag;
    submit.disabled = flag;
    exampleButton.disabled = flag;
    panel.setAttribute("aria-busy", flag ? "true" : "false");
  }

  function download(label, content, mime, filename) {
    var url = URL.createObjectURL(new Blob([content], {type: mime}));
    urls.push(url);
    var link = node("a", label, "btn btn--ghost");
    link.href = url;
    link.download = filename;
    panel.appendChild(link);
  }

  async function request(path, options) {
    var controller = new AbortController();
    var timer = window.setTimeout(function () { controller.abort(); }, 30000);
    try {
      var response = await fetch(path, Object.assign({signal: controller.signal}, options || {}));
      var data;
      try { data = await response.json(); }
      catch (_) { throw new Error("The local application did not answer. Start python -m prooftrail.web."); }
      if (!response.ok) { throw new Error(data.error || "The request failed."); }
      return data;
    } finally { window.clearTimeout(timer); }
  }

  function buildRequest() {
    var checks = value("checks").split("\n").map(function (line) { return line.trim(); }).filter(Boolean);
    var claims = Array.prototype.slice.call(form.querySelectorAll('input[name="claim"]:checked'))
      .map(function (input, index) { return {id: "c" + (index + 1), type: input.value}; });
    return {
      schema_version: 1,
      domain: "github",
      repository: {owner: value("owner").trim(), name: value("repo").trim()},
      pull_request: Number(value("number")),
      expected_head_sha: value("sha").trim().toLowerCase(),
      expected_base_branch: value("base").trim(),
      required_checks: checks,
      claims: claims
    };
  }

  function renderClaims(claims) {
    return table("Claims", ["Claim", "Type", "Verdict", "Reason", "Evidence"], claims.map(function (claim) {
      return [cell(claim.claim_id), cell(claim.claim_type, "mono break"), verdictCell(claim.status),
              cell(claim.reason_code + ": " + claim.reason, "break"),
              cell((claim.evidence || []).join(", ") || "-", "mono break")];
    }));
  }

  function renderChecks(checks) {
    if (!checks.length) {
      return node("p", "No required checks were evaluated for this request.", "note");
    }
    return table("Required checks", ["Check", "Verdict", "Reason", "Latest run", "Superseded"], checks.map(function (check) {
      return [cell(check.name, "mono break"), verdictCell(check.status), cell(check.reason_code, "break"),
              cell(check.latest_run_id), cell((check.superseded_ids || []).join(", ") || "-", "mono break")];
    }));
  }

  function renderSources(observations) {
    return table("Evidence sources", ["Source", "Status", "Complete", "Pages", "Collected at"], observations.map(function (item) {
      return [cell(item.name, "mono break"), cell(item.status), cell(item.complete ? "yes" : "no"),
              cell(item.pages), cell(item.collected_at, "mono break")];
    }));
  }

  function renderResult(data) {
    urls.forEach(function (url) { URL.revokeObjectURL(url); });
    urls = [];
    panel.replaceChildren();
    var source = data.source;
    panel.appendChild(node("h2", "GitHub verdict: " + data.verdict));
    panel.appendChild(node("p", "Source: " + source.label + "."));
    if (source.synthetic) {
      panel.appendChild(node("p", "SYNTHETIC FIXTURE: this is not production evidence.", "note"));
    }
    panel.appendChild(node("p", "Bundle SHA-256: " + source.bundle_sha256, "mono break"));
    panel.appendChild(node("p", source.integrity_note));
    panel.appendChild(node("p", "Network used: " + (data.network_used ? "yes" : "no") +
      ". Model calls: 0. Persisted: no."));
    panel.appendChild(renderClaims(data.claims));
    panel.appendChild(renderChecks(data.required_checks));
    panel.appendChild(renderSources(data.certificate.observations));
    if (data.warnings.length) {
      var warnings = document.createElement("ul");
      data.warnings.forEach(function (item) { warnings.appendChild(node("li", item)); });
      panel.appendChild(node("h3", "Warnings"));
      panel.appendChild(warnings);
    }
    var limits = document.createElement("ul");
    data.certificate.limitations.forEach(function (item) { limits.appendChild(node("li", item)); });
    panel.appendChild(node("h3", "What this does not establish"));
    panel.appendChild(limits);
    download("Certificate JSON", JSON.stringify(data.certificate, null, 2), "application/json",
             "prooftrail-github-certificate.json");
    download("Certificate Markdown", data.certificate_markdown, "text/markdown", "prooftrail-github-certificate.md");
    panel.hidden = false;
  }

  function applyDomain() {
    var choice = domain ? domain.value : "refund";
    Array.prototype.forEach.call(document.querySelectorAll("[data-domain-panel]"), function (section) {
      section.hidden = section.getAttribute("data-domain-panel") !== choice;
    });
  }

  function applyMode() {
    var live = value("mode") === "live";
    offlineBox.hidden = live;
    liveNote.hidden = !live;
    bundleField.required = !live;
  }

  function fillFromPack(pack) {
    var request = pack.request;
    form.elements.namedItem("owner").value = request.repository.owner;
    form.elements.namedItem("repo").value = request.repository.name;
    form.elements.namedItem("number").value = String(request.pull_request);
    form.elements.namedItem("sha").value = request.expected_head_sha;
    form.elements.namedItem("base").value = request.expected_base_branch;
    form.elements.namedItem("checks").value = request.required_checks.join("\n");
    var types = request.claims.map(function (claim) { return claim.type; });
    Array.prototype.forEach.call(form.querySelectorAll('input[name="claim"]'), function (input) {
      input.checked = types.indexOf(input.value) !== -1;
    });
    bundleField.value = JSON.stringify(pack.bundle, null, 2);
    form.elements.namedItem("mode").value = "offline";
    applyMode();
  }

  async function loadExamples() {
    try {
      var listing = await request("/api/v1/github/examples");
      listing.examples.forEach(function (item) {
        var option = node("option", item.title);
        option.value = item.id;
        exampleSelect.appendChild(option);
      });
      exampleButton.disabled = listing.examples.length === 0;
    } catch (error) {
      setStatus("Examples need the local application: " + error.message);
    }
  }

  exampleButton.addEventListener("click", async function () {
    if (pending || !exampleSelect.value) { return; }
    busy(true);
    setStatus("Loading the synthetic example...");
    try {
      var pack = await request("/api/v1/github/examples/" + encodeURIComponent(exampleSelect.value));
      fillFromPack(pack);
      setStatus("Example loaded. It is a synthetic fixture, labelled as such in the result.");
    } catch (error) { setStatus(error.message); }
    finally { busy(false); }
  });

  if (domain) { domain.addEventListener("change", applyDomain); }
  Array.prototype.forEach.call(form.querySelectorAll('input[name="mode"]'), function (input) {
    input.addEventListener("change", applyMode);
  });

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    if (pending) { return; }
    panel.hidden = true;
    var live = value("mode") === "live";
    var payload;
    try {
      if (!form.checkValidity()) { throw new Error("Check the highlighted fields. Nothing was sent."); }
      payload = {mode: live ? "live" : "offline", request: buildRequest()};
      if (!live) {
        var raw = bundleField.value.trim();
        if (!raw) { throw new Error("Paste a saved evidence bundle or load a synthetic example first."); }
        if (new Blob([raw]).size > MAX_BYTES) { throw new Error("The bundle exceeds 2 MiB."); }
        try { payload.bundle = JSON.parse(raw); }
        catch (_) { throw new Error("The bundle is not valid JSON. Fix it before running."); }
      }
    } catch (error) { setStatus(error.message); return; }
    busy(true);
    setStatus(live ? "Reading api.github.com (read-only). This can take up to about 20 seconds..."
                   : "Auditing the saved bundle locally...");
    try {
      var data = await request("/api/v1/github/audits", {
        method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
      renderResult(data);
      setStatus("Audit complete. " + (data.network_used ? "Read from GitHub." : "No network used.") +
                " Nothing was saved.");
    } catch (error) {
      setStatus(error.name === "AbortError" ? "The request timed out; no verdict is claimed." : error.message);
    } finally { busy(false); }
  });

  applyDomain();
  applyMode();
  loadExamples();
}());
