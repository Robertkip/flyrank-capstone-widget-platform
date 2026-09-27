/* Widget bundle. Served at /assets/widget-<hash>.js (immutable, cached 1 year).
   Renders every <script data-lead-widget="ID"> it finds, inside a Shadow DOM so the host page's CSS can't break it. */
(function () {
  "use strict";
  var API = (window.__LEAD_WIDGET_API__ || "").replace(/\/$/, "");
  function el(tag, attrs, text) {
    var e = document.createElement(tag);
    for (var k in attrs || {}) e.setAttribute(k, attrs[k]);
    if (text) e.textContent = text;              // textContent only: never innerHTML with config data
    return e;
  }
  function render(host, cfg) {
    var root = host.attachShadow ? host.attachShadow({ mode: "open" }) : host;
    var c = cfg.display.theme_color;
    var style = el("style");
    style.textContent = ":host{all:initial}.w{font-family:system-ui,sans-serif;max-width:360px;border:1px solid #e5e7eb;border-radius:12px;padding:18px;background:#fff;box-shadow:0 6px 20px rgba(0,0,0,.08);color:#111}" +
      ".w.bottom-right{position:fixed;right:20px;bottom:20px;z-index:2147483000}.w.bottom-left{position:fixed;left:20px;bottom:20px;z-index:2147483000}" +
      "h3{margin:0 0 6px;font-size:18px}p{margin:0 0 12px;color:#555;font-size:14px}label{display:block;font-size:13px;margin:8px 0 4px}" +
      "input,textarea{width:100%;box-sizing:border-box;padding:9px;border:1px solid #d1d5db;border-radius:8px;font:inherit}" +
      "button{margin-top:12px;width:100%;padding:10px;border:0;border-radius:8px;color:#fff;font-weight:600;cursor:pointer;background:" + c + "}" +
      ".hp{position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden}.msg{margin-top:10px;font-size:14px}.err{color:#b91c1c}.ok{color:#15803d}";
    var box = el("div", { class: "w " + cfg.display.position });
    box.appendChild(el("h3", {}, cfg.title));
    if (cfg.description) box.appendChild(el("p", {}, cfg.description));
    var form = el("form", { novalidate: "" });
    cfg.fields.forEach(function (f) {
      var id = "f_" + f.name;
      form.appendChild(el("label", { for: id }, f.label + (f.required ? " *" : "")));
      var input = el(f.type === "textarea" ? "textarea" : "input",
        { id: id, name: f.name, type: f.type === "textarea" ? null : f.type, maxlength: String(f.max_length) });
      if (f.type === "textarea") input.removeAttribute("type");
      if (f.required) input.setAttribute("required", "");
      form.appendChild(input);
    });
    // Honeypot: invisible to humans, bots fill it in.
    var hp = el("div", { class: "hp", "aria-hidden": "true" });
    hp.appendChild(el("input", { name: "_hp", tabindex: "-1", autocomplete: "off" }));
    form.appendChild(hp);
    var btn = el("button", { type: "submit" }, cfg.button_text);
    var msg = el("div", { class: "msg", role: "status" });
    form.appendChild(btn); form.appendChild(msg);
    var renderedAt = Date.now();
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var data = {};
      cfg.fields.forEach(function (f) { var v = form.elements[f.name].value; if (v) data[f.name] = v; });
      btn.disabled = true; msg.className = "msg"; msg.textContent = "Sending...";
      fetch(API + "/submissions", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ widget_id: cfg.id, fields: data, _hp: form.elements._hp.value, _t: Date.now() - renderedAt })
      }).then(function (r) { return r.json().then(function (b) { return { s: r.status, b: b }; }); })
        .then(function (res) {
          btn.disabled = false;
          if (res.s >= 200 && res.s < 300) { msg.className = "msg ok"; msg.textContent = "Thank you! We received your details."; form.reset(); }
          else if (res.s === 429) { msg.className = "msg err"; msg.textContent = "Too many attempts, please wait a moment."; }
          else { msg.className = "msg err"; msg.textContent = (res.b.errors || []).map(function (e) { return e.field + ": " + e.error; }).join("; ") || res.b.message || "Something went wrong."; }
        }).catch(function () { btn.disabled = false; msg.className = "msg err"; msg.textContent = "Network error, please try again."; });
    });
    box.appendChild(form);
    root.appendChild(style); root.appendChild(box);
  }
  function mount(script) {
    var id = script.getAttribute("data-lead-widget");
    if (!id || script.__mounted) return;
    script.__mounted = true;
    var host = document.createElement("div");
    script.parentNode.insertBefore(host, script.nextSibling);
    fetch(API + "/widgets/" + encodeURIComponent(id) + "/config")
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (cfg) { render(host, cfg); })
      .catch(function (e) { if (window.console) console.warn("lead widget " + id + " failed to load:", e); });
  }
  function scan() {
    var scripts = document.querySelectorAll("script[data-lead-widget]");
    for (var i = 0; i < scripts.length; i++) mount(scripts[i]);
  }
  window.__leadWidgetScan = scan;   // later loaders (2nd widget on the page) re-scan instead of re-loading the bundle
  scan();
})();
