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
  var SIMPLE_LINE = /^(\d{1,4}[A-Za-z]?)[\s,;:=\t]+(\d[\d,]*)(?:\s*-\s*(\d[\d,]*))?(?:\s*(APX CV|CV|EST))?\s*$/i;
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
      if (m && !seen[m[1]]) {
        seen[m[1]] = true;
        lots.push({ lot: m[1], desc: "", low: toNum(m[2]), high: toNum(m[3]), kind: (m[4] || "CV").toUpperCase(), basisNote: "" });
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

  return { linesFromItems: linesFromItems, parseLines: parseLines, parseText: parseText };
});
