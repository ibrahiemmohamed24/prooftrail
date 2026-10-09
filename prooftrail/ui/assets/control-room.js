/* Local audit UI. All evidence is rendered as text, never as executable HTML. */
(function () {
  "use strict";
  var button = document.querySelector("[data-audit-submit]");
  if (!button) { return; }
  var input = document.querySelector("[data-evidence-json]");
  var file = document.querySelector("[data-evidence-file]");
  var status = document.querySelector("[data-audit-status]");
  var panel = document.querySelector("[data-audit-result]");
  var example = document.querySelector("[data-audit-example]");
  var urls = [];
  var pending = false;
  function busy(value) {
    pending = value;
    button.disabled = example.disabled = file.disabled = value;
    panel.setAttribute("aria-busy", value ? "true" : "false");
  }
  function text(tag, value) {
    var node = document.createElement(tag);
    node.textContent = value;
    return node;
  }
  function download(label, content, mime, filename) {
    var url = URL.createObjectURL(new Blob([content], {type: mime}));
    urls.push(url);
    var link = text("a", label);
    link.href = url;
    link.download = filename;
    link.className = "btn btn--ghost";
    panel.appendChild(link);
  }
  async function request(path, options) {
    var controller = new AbortController();
    var timer = window.setTimeout(function () { controller.abort(); }, 20000);
    try {
      var response = await fetch(path, Object.assign({signal: controller.signal}, options || {}));
      var data;
      try { data = await response.json(); }
      catch (_) { throw new Error("Start python -m prooftrail.web; the static viewer cannot run audits."); }
      if (!response.ok) { throw new Error(data.error || "Request failed."); }
      return data;
    } finally { window.clearTimeout(timer); }
  }
  file.addEventListener("change", async function () {
    var selected = file.files[0];
    if (!selected) { return; }
    if (selected.size > 2 * 1024 * 1024) { status.textContent = "File exceeds 2 MiB."; file.value = ""; return; }
    try { input.value = await selected.text(); status.textContent = "File loaded. Inspect evidence before running."; }
    catch (_) { status.textContent = "Unable to read the file."; }
  });
  example.addEventListener("click", async function () {
    if (pending) { return; }
    busy(true);
    status.textContent = "Loading original frozen evidence…";
    try {
      input.value = JSON.stringify(await request("/api/v1/cases/F04-s00"), null, 2);
      status.textContent = "Example loaded; its labels are not sent to the auditor.";
    } catch (error) { status.textContent = error.message; }
    finally { busy(false); }
  });
  button.addEventListener("click", async function () {
    if (pending) { return; }
    panel.hidden = true;
    var raw = input.value;
    if (new Blob([raw]).size > 2 * 1024 * 1024) { status.textContent = "Evidence exceeds 2 MiB."; return; }
    try { JSON.parse(raw); } catch (_) { status.textContent = "Invalid JSON. Fix it before running."; return; }
    busy(true);
    status.textContent = "Auditing evidence locally…";
    try {
      var data = await request("/api/v1/audits", {method: "POST", headers: {"Content-Type": "application/json"}, body: raw});
      urls.forEach(function (url) { URL.revokeObjectURL(url); });
      urls = [];
      panel.replaceChildren();
      panel.appendChild(text("h2", data.audit.verdict));
      panel.appendChild(text("p", data.audit.explanation));
      panel.appendChild(text("p", "Ledger integrity: " + (data.ledger.valid ? "valid" : "broken") + "; first bad event: " + (data.audit.first_bad_event_seq === null ? "none" : data.audit.first_bad_event_seq)));
      data.audit.claims.forEach(function (claim) {
        var section = document.createElement("section");
        section.className = "audit-claim";
        section.appendChild(text("h3", claim.claim_id + " · " + claim.status));
        section.appendChild(text("p", claim.claim_text));
        section.appendChild(text("p", claim.reason));
        section.appendChild(text("p", "Evidence sequences: " + claim.evidence_seqs.join(", ")));
        panel.appendChild(section);
      });
      panel.appendChild(text("p", data.limitations));
      panel.appendChild(text("p", data.ledger.trust_note));
      download("Certificate JSON", JSON.stringify(data.certificate, null, 2), "application/json", "prooftrail-certificate.json");
      download("Certificate Markdown", data.certificate_markdown, "text/markdown", "prooftrail-certificate.md");
      var details = document.createElement("details");
      details.appendChild(text("summary", "Full certificate / before-and-after state"));
      details.appendChild(text("pre", JSON.stringify(data.certificate, null, 2)));
      panel.appendChild(details);
      panel.hidden = false;
      status.textContent = "Audit complete. No uploads saved; 0 model calls.";
    } catch (error) { status.textContent = error.name === "AbortError" ? "Request timed out; no result is claimed." : error.message; }
    finally { busy(false); }
  });
}());
