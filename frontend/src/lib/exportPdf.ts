// frontend/src/lib/exportPdf.ts
/**
 * Grabs the already-rendered HTML from a DOM element and opens it in a
 * print-ready window so the user can "Save as PDF" via the browser dialog.
 *
 * Zero extra dependencies — works because ReactMarkdown already rendered the
 * markdown into DOM nodes; we just copy the HTML out.
 */

export function exportToPdf(element: HTMLElement, title: string): void {
  const html = element.innerHTML

  const printWindow = window.open("", "_blank", "width=900,height=700")
  if (!printWindow) {
    alert("Please allow pop-ups to export as PDF.")
    return
  }

  printWindow.document.write(`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>${escapeHtml(title)}</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      font-size: 13px;
      line-height: 1.6;
      color: #111;
      background: #fff;
      padding: 40px 56px;
      max-width: 800px;
      margin: 0 auto;
    }

    h1 { font-size: 20px; font-weight: 700; margin: 24px 0 8px; color: #111; }
    h2 { font-size: 16px; font-weight: 700; margin: 20px 0 6px; color: #111; }
    h3 { font-size: 14px; font-weight: 600; margin: 16px 0 4px; color: #222; }

    p  { margin-bottom: 10px; color: #333; }
    ul, ol { padding-left: 20px; margin-bottom: 10px; }
    li { margin-bottom: 4px; color: #333; }

    strong { font-weight: 600; color: #111; }
    em     { font-style: italic; color: #555; }
    code   { font-family: "SFMono-Regular", Consolas, monospace; font-size: 12px;
             background: #f4f4f4; padding: 1px 4px; border-radius: 3px; color: #c7254e; }
    hr     { border: none; border-top: 1px solid #ddd; margin: 16px 0; }

    /* Hide the bullet dot spans from Tailwind — we use native list styles */
    li > span:first-child { display: none; }
    li > span:last-child  { display: block; }

    /* Page title header */
    .pdf-title {
      font-size: 11px;
      color: #888;
      border-bottom: 1px solid #eee;
      padding-bottom: 12px;
      margin-bottom: 24px;
      display: flex;
      justify-content: space-between;
    }

    @media print {
      body { padding: 0; }
      @page { margin: 20mm 18mm; }
    }
  </style>
</head>
<body>
  <div class="pdf-title">
    <span>Sales Copilot — ${escapeHtml(title)}</span>
    <span>${new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })}</span>
  </div>
  ${html}
  <script>
    // Auto-print once fonts/layout settle
    window.onload = function() { window.print(); }
  </script>
</body>
</html>`)

  printWindow.document.close()
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
}
