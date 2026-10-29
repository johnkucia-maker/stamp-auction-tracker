/* Reads a consignor lotting summary (PDF text or pasted text) into a list of lots.
   Runs entirely in the browser (and in Node for testing). Nothing is uploaded anywhere.

   A lot line in the Dutch Country lotting summary looks like:
     "241  1a O VF-XF 5c gray brown Franklin imperf ...        565 CV"
     "244  9 O VF 1c blue Franklin ...                    200 - 300 EST"
     "387  E11c var ** F-VF NH ...                  315 - 420 APX CV"
   Description lines that wrap onto a second line have no value on the right.
*/
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.StampParser = factory();
})(typeof self !== "undefined" ? self : this, function () {
  var LOT_LINE = /^(\d{1,4}[A-Za-z]?)\s+(.+?)\s+(\d[\d,]*)(?:\s*-\s*(\d[\d,]*))?\s+(APX CV|CV|EST)\s*$/;
  var SIMPLE_LINE = /^(\d{1,4}[A-Za-z]?)([\s,;:=\t]+)(\d[\d,]*)(?:\s*-\s*(\d[\d,]*))?(?:\s*(APX CV|CV|EST))?\s*$/i;
  var BARE_LOTS = /^[\d\s,;A-Za-z]+$/;
  var COUNT_LINE = /Number of Lots in Consignment\s+(\d+)/i;
  var BASIS_NOTE = /\((?:CV|Scott|SMQ)[^)]*\)/i;

  function toNum(s) { return s ? Number(String(s).replace(/,/g, "")) : null; }

  /* pdf.js text items -> visual lines (group by vertical position, order by horizontal). */
  function linesFromItems(items) {
    var rows = [];
    items.forEach(function (it) {
      if (!it.str || !it.str.trim()) return;
      var x = it.transform[4], y = it.transform[5];
      var row = null;
      for (var i = 0; i < rows.length; i++) { if (Math.abs(rows[i].y - y) <= 2.5) { row = rows[i]; break; } }
      if (!row) { row = { y: y, parts: [] }; rows.push(row); }
      row.parts.push({ x: x, s: it.str });
    });
    rows.sort(function (a, b) { return b.y - a.y; });
    return rows.map(function (r) {
      r.parts.sort(function (a, b) { return a.x - b.x; });
      return r.parts.map(function (p) { return p.s.trim(); }).join(" ").replace(/\s+/g, " ").trim();
    });
  }

  /* lines -> { lots, declared, warnings } */
  function parseLines(lines) {
    var lots = [], declared = null, warnings = [], seen = {};
    lines.forEach(function (raw) {
      var line = raw.replace(/\s+/g, " ").trim();
      if (!line) return;
      var c = line.match(COUNT_LINE);
      if (c) { declared = Number(c[1]); return; }
      var m = line.match(LOT_LINE);
      if (!m) return;
      var lot = m[1];
      if (seen[lot]) { warnings.push("Lot " + lot + " appears twice in the file; kept the first."); return; }
      seen[lot] = true;
      var bn = m[2].match(BASIS_NOTE);
      lots.push({
        lot: lot, desc: m[2], low: toNum(m[3]), high: toNum(m[4]),
        kind: m[5].toUpperCase(), basisNote: bn ? bn[0] : ""
      });
    });
    if (declared != null && declared !== lots.length) {
      warnings.push("The file says " + declared + " lots but " + lots.length + " were read. Check for missing lots.");
    }
    return { lots: lots, declared: declared, warnings: warnings };
  }

  /* Free text pasted by the user. Accepts PDF-style lines, "lot value [CV|EST]" lines, or just lot numbers. */
  function parseText(text) {
    var lines = String(text).split(/\r?\n/);
    var res = parseLines(lines);
    if (res.lots.length) return res;
    var lots = [], seen = {}, warnings = [];
    lines.forEach(function (raw) {
      var line = raw.trim();
      var m = line.match(SIMPLE_LINE);
      /* "241, 244" is two lot numbers, not lot 241 worth 244. A value needs a CV/EST label or a : = tab separator. */
      if (m && !seen[m[1]] && (m[5] || /[:=\t]/.test(m[2]))) {
        seen[m[1]] = true;
        lots.push({ lot: m[1], desc: "", low: toNum(m[3]), high: toNum(m[4]), kind: (m[5] || "CV").toUpperCase(), basisNote: "" });
      }
    });
    if (lots.length) return { lots: lots, declared: null, warnings: warnings };
    var flat = String(text).trim();
    if (flat && BARE_LOTS.test(flat)) {
      (flat.match(/\d{1,4}[A-Za-z]?/g) || []).forEach(function (n) {
        if (!seen[n]) { seen[n] = true; lots.push({ lot: n, desc: "", low: null, high: null, kind: "", basisNote: "" }); }
      });
    }
    return { lots: lots, declared: null, warnings: warnings };
  }

  /* ---------- keyword-based reading of what a lot IS (approximate, by design) ----------
     Inputs are the SAN "Symbol" cell (e.g. "OVF-XF", "**", "*O"), the consignor's own description
     (e.g. "1a O VF-XF 5c gray brown ...") and SAN's full description. Everything here is a guess from
     keywords, so the dashboard labels it approximate and shows how many lots sit in each group. */
  var GRADE_TOK = "XF-SUP|XF-S|SUP|GEM|VF-XF|F-VF|AVG-F|VG-F|XF|VF|AVG|VG|F|G";
  /* In SAN's Symbol cell the finish and grade are glued together ("OVF-XF"); in prose they are spaced ("O VF-XF"). */
  var GRADE_IN_SYM = new RegExp("^(?:\\*\\*|\\(\\*\\)|\\*|O|P)+\\s*(" + GRADE_TOK + ")\\+?(?![A-Za-z])");
  var GRADE_IN_TEXT = new RegExp("(?:^|[\\s(,])(?:\\*\\*|\\(\\*\\)|\\*|O|P)\\s+(" + GRADE_TOK + ")\\+?(?![A-Za-z])");
  var GRADE_ALONE = new RegExp("(?:^|[\\s(,])(XF-SUP|XF-S|SUP|GEM|VF-XF|F-VF|VF|XF)\\+?(?![A-Za-z])");
  var GRADE_ORDER = ["XF-Superb / Superb", "XF", "VF-XF", "VF", "F-VF", "Fine or below", "No grade shown"];
  var GRADE_MAP = { "SUP": 0, "GEM": 0, "XF-SUP": 0, "XF-S": 0, "XF": 1, "VF-XF": 2, "VF": 3, "F-VF": 4, "F": 5, "AVG-F": 5, "AVG": 5, "VG-F": 5, "VG": 5, "G": 5 };
  var CERT_RE = /\b(PSE|PSAG|PSA|PF|Weiss|certs?|certificates?|certified|graded|slabbed|expertized|expertised)\b/i;
  var COVER_RE = /\b(covers?|FDC|FFC|postal history|stationery|postcards?|envelopes?|entires?|wrappers?|folded letters?|stampless|postmarks?)\b/i;
  var MINT_MARK = /(?:^|[\s(,])(?:\*\*|\(\*\)|\*)(?=$|[\s,/)A-Z])/;
  var USED_IN_SYM = /^(?:\*\*|\(\*\)|\*)*O/;            /* "O", "OVF-XF", "*O" */
  var USED_IN_TEXT = /(?:^|[\s/(,])O(?=$|[\s/,])/;           /* a lone "O", as in "1a O VF-XF" */
  var MINT_WORDS = /\b(mint|NH|MNH|never hinged|unused|hinged|OG|original gum)\b/i;
  var USED_WORDS = /\b(used|cancel|cancelled|cancellation|cds|postmarked?)\b/i;
  var KIND_ORDER = ["Mint", "Used", "Cover / postal history", "Unclear or mixed"];

  function classify(o) {
    var sym = String(o.sym || "").replace(/\s+/g, " ").trim();
    var desc = String(o.text || "").replace(/\s+/g, " ").trim();
    /* The finish and grade sit right after the Scott number, so only look at the start of the text.
       (Searching further would pick up words like "PF Cert" or "MAN OF" as a grade.) */
    var head = (sym + " " + desc.slice(0, 40));
    var g = sym.match(GRADE_IN_SYM) || desc.slice(0, 28).match(GRADE_IN_TEXT) || (sym + " " + desc.slice(0, 60)).match(GRADE_ALONE);
    var gi = g ? GRADE_MAP[g[1]] : 6;
    /* mint / used / cover */
    var kind;
    /* Not the catalog page heading: SAN shows one heading per page, so it often belongs to the previous group of lots. */
    if (COVER_RE.test(desc)) kind = 2;
    else {
      var hm = MINT_MARK.test(head), hu = USED_IN_SYM.test(sym) || USED_IN_TEXT.test(desc.slice(0, 40));
      if (hm && hu) kind = 3;
      else if (hm) kind = 0;
      else if (hu) kind = 1;
      else {
        var wm = MINT_WORDS.test(desc), wu = USED_WORDS.test(desc);
        kind = wm && wu ? 3 : wm ? 0 : wu ? 1 : 3;
      }
    }
    return { grade: GRADE_ORDER[gi], gradeIdx: gi, kind: KIND_ORDER[kind], kindIdx: kind, cert: CERT_RE.test(sym + " " + desc) };
  }

  function valueBand(ref) {
    if (ref == null) return null;
    return ref < 100 ? 0 : ref <= 500 ? 1 : 2;
  }

  return { linesFromItems: linesFromItems, parseLines: parseLines, parseText: parseText,
           classify: classify, valueBand: valueBand, GRADE_ORDER: GRADE_ORDER, KIND_ORDER: KIND_ORDER,
           BAND_LABELS: ["Under 100", "100 to 500", "Over 500"] };
});
