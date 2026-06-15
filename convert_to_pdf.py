import markdown
import re
import base64
from pathlib import Path

md_path = Path("/Users/lalit.tak/Documents/Workspace/Prod_tool_troubleshoot_guide/Production_Jigs_Software_Troubleshooting_Guide.md")
pdf_path = Path("/Users/lalit.tak/Documents/Workspace/Prod_tool_troubleshoot_guide/Production_Jigs_Software_Troubleshooting_Guide.pdf")
html_path = Path("/Users/lalit.tak/Documents/Workspace/Prod_tool_troubleshoot_guide/Production_Jigs_Software_Troubleshooting_Guide.html")

md_text = md_path.read_text(encoding="utf-8")

# Load PNG flowcharts as base64 data URIs
fc_dir = Path("/Users/lalit.tak/Documents/Workspace/Prod_tool_troubleshoot_guide/flowcharts")
fc_names = ["fc_app", "fc_hw", "fc_test", "fc_comm", "fc_file", "fc_prod", "fc_arch"]
fc_imgs = []
for name in fc_names:
    data = (fc_dir / f"{name}.png").read_bytes()
    b64 = base64.b64encode(data).decode()
    fc_imgs.append(f'data:image/png;base64,{b64}')

# Replace each mermaid block in order with its corresponding PNG image
fc_idx = [0]
def replace_mermaid(m):
    if fc_idx[0] < len(fc_imgs):
        src = fc_imgs[fc_idx[0]]
        fc_idx[0] += 1
        return f'\n<div class="flowchart-wrap"><img src="{src}" style="max-width:100%;height:auto;display:block;"/></div>\n'
    return ""

md_text_clean = re.sub(r"```mermaid.*?```", replace_mermaid, md_text, flags=re.DOTALL)

md_ext = ["tables", "fenced_code", "toc", "attr_list", "def_list"]
body_html = markdown.markdown(md_text_clean, extensions=md_ext)

css = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

* { box-sizing: border-box; margin: 0; padding: 0; }

@page {
    size: A4;
    margin: 18mm 15mm 20mm 18mm;
    @top-center {
        content: "Production Jigs — Software Troubleshooting Guide";
        font-family: 'Inter', sans-serif;
        font-size: 8pt;
        color: #6b7280;
        border-bottom: 0.5pt solid #e5e7eb;
        padding-bottom: 4pt;
    }
    @bottom-right {
        content: "Page " counter(page) " of " counter(pages);
        font-family: 'Inter', sans-serif;
        font-size: 8pt;
        color: #6b7280;
    }
    @bottom-left {
        content: "CONFIDENTIAL — Polaris Grids Engineering";
        font-family: 'Inter', sans-serif;
        font-size: 8pt;
        color: #6b7280;
    }
}

@page :first {
    @top-center { content: ""; border: none; }
    @bottom-left { content: ""; }
    @bottom-right { content: ""; }
}

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 9.5pt;
    line-height: 1.55;
    color: #1f2937;
    background: #ffffff;
}

/* Cover block */
.cover {
    page-break-after: always;
    padding: 60px 40px;
    background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 60%, #1d4ed8 100%);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    justify-content: center;
    color: white;
}
.cover-badge {
    background: rgba(255,255,255,0.15);
    border: 1px solid rgba(255,255,255,0.3);
    border-radius: 6px;
    padding: 4px 12px;
    display: inline-block;
    font-size: 8pt;
    font-weight: 600;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin-bottom: 24px;
    color: #93c5fd;
}
.cover-title {
    font-size: 28pt;
    font-weight: 700;
    line-height: 1.2;
    margin-bottom: 12px;
    color: #ffffff;
}
.cover-subtitle {
    font-size: 14pt;
    font-weight: 400;
    color: #93c5fd;
    margin-bottom: 40px;
}
.cover-divider {
    width: 60px;
    height: 3px;
    background: #3b82f6;
    border-radius: 2px;
    margin-bottom: 40px;
}
.cover-meta {
    display: flex;
    gap: 40px;
    flex-wrap: wrap;
}
.cover-meta-item { }
.cover-meta-label {
    font-size: 7pt;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #93c5fd;
    margin-bottom: 4px;
}
.cover-meta-value {
    font-size: 10pt;
    font-weight: 600;
    color: white;
}
.cover-footer {
    margin-top: 60px;
    padding-top: 20px;
    border-top: 1px solid rgba(255,255,255,0.2);
    font-size: 8pt;
    color: rgba(255,255,255,0.5);
}

/* Headings */
h1 {
    font-size: 22pt;
    font-weight: 700;
    color: #0f172a;
    margin: 32px 0 16px;
    padding-bottom: 10px;
    border-bottom: 3px solid #1d4ed8;
    page-break-after: avoid;
}
h2 {
    font-size: 15pt;
    font-weight: 700;
    color: #1e3a5f;
    margin: 28px 0 12px;
    padding: 8px 12px;
    background: #eff6ff;
    border-left: 4px solid #1d4ed8;
    border-radius: 0 4px 4px 0;
    page-break-after: avoid;
}
h3 {
    font-size: 12pt;
    font-weight: 600;
    color: #1e40af;
    margin: 22px 0 10px;
    padding-bottom: 4px;
    border-bottom: 1.5px solid #bfdbfe;
    page-break-after: avoid;
}
h4 {
    font-size: 10pt;
    font-weight: 600;
    color: #374151;
    margin: 16px 0 8px;
    page-break-after: avoid;
}

p { margin: 0 0 10px; }

/* Tables */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 12px 0 20px;
    font-size: 8.5pt;
    page-break-inside: auto;
}
thead tr {
    background: #1e3a5f;
    color: white;
}
thead th {
    padding: 7px 10px;
    text-align: left;
    font-weight: 600;
    font-size: 8pt;
    letter-spacing: 0.3px;
    border: 1px solid #1e3a5f;
}
tbody tr:nth-child(even) { background: #f0f9ff; }
tbody tr:nth-child(odd) { background: #ffffff; }
tbody tr:hover { background: #dbeafe; }
tbody td {
    padding: 6px 10px;
    border: 1px solid #e2e8f0;
    vertical-align: top;
    line-height: 1.4;
}
tbody td:first-child { font-weight: 500; color: #1e3a5f; }

/* Code blocks */
pre {
    background: #0f172a;
    color: #e2e8f0;
    padding: 14px 16px;
    border-radius: 6px;
    font-family: 'JetBrains Mono', 'Courier New', monospace;
    font-size: 7.5pt;
    line-height: 1.6;
    overflow-x: auto;
    margin: 12px 0 20px;
    border-left: 3px solid #3b82f6;
    page-break-inside: avoid;
}
code {
    font-family: 'JetBrains Mono', 'Courier New', monospace;
    font-size: 8pt;
    background: #f1f5f9;
    color: #be185d;
    padding: 1px 5px;
    border-radius: 3px;
    border: 1px solid #e2e8f0;
}
pre code {
    background: none;
    color: #e2e8f0;
    padding: 0;
    border: none;
    font-size: inherit;
}

/* Lists */
ul, ol {
    margin: 6px 0 12px 20px;
    padding: 0;
}
li { margin-bottom: 4px; }

/* Blockquotes */
blockquote {
    border-left: 3px solid #f59e0b;
    background: #fffbeb;
    padding: 10px 14px;
    margin: 12px 0;
    font-size: 8.5pt;
    color: #92400e;
    border-radius: 0 4px 4px 0;
}

/* Horizontal rules */
hr {
    border: none;
    border-top: 1.5px solid #e5e7eb;
    margin: 24px 0;
}

/* TOC styling */
.toc {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 20px 24px;
    margin-bottom: 32px;
}
.toc ul { list-style: none; margin: 0; padding: 0; }
.toc li { padding: 2px 0; }
.toc a { color: #1d4ed8; text-decoration: none; }

/* Page break helpers */
.page-break { page-break-before: always; }

/* Flowchart container */
.flowchart-wrap {
    margin: 16px 0 24px;
    page-break-inside: avoid;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    overflow: hidden;
    background: #f8fafc;
}
.flowchart-wrap svg {
    display: block;
    max-width: 100%;
    height: auto;
}

/* Strong emphasis */
strong { color: #0f172a; font-weight: 600; }

/* Annotation / note blocks */
em { color: #6b7280; font-style: italic; }
"""

full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Production Jigs — Software Troubleshooting Guide</title>
<style>
{css}
</style>
</head>
<body>

<div class="cover">
  <div class="cover-badge">Internal Engineering Document</div>
  <div class="cover-title">Model-Wise Software<br>Troubleshooting Guide</div>
  <div class="cover-subtitle">Production Jigs — SmartManufacturingSuite</div>
  <div class="cover-divider"></div>
  <div class="cover-meta">
    <div class="cover-meta-item">
      <div class="cover-meta-label">Document Version</div>
      <div class="cover-meta-value">2.0</div>
    </div>
    <div class="cover-meta-item">
      <div class="cover-meta-label">Date</div>
      <div class="cover-meta-value">June 15, 2026</div>
    </div>
    <div class="cover-meta-item">
      <div class="cover-meta-label">Models Covered</div>
      <div class="cover-meta-value">FG23 · 3PH LTCT · 3PH WC · IMG STG1 · IMG STG2</div>
    </div>
    <div class="cover-meta-item">
      <div class="cover-meta-label">Repository</div>
      <div class="cover-meta-value">lalit-tak/Production_jigs</div>
    </div>
  </div>
  <div class="cover-footer">
    Polaris Grids Engineering · Confidential · For Internal Use Only
  </div>
</div>

{body_html}

</body>
</html>"""

html_path.write_text(full_html, encoding="utf-8")
print(f"HTML written: {html_path}")

from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration

font_config = FontConfiguration()
print("Converting to PDF (this may take 30-60 seconds)...")
HTML(filename=str(html_path)).write_pdf(
    str(pdf_path),
    font_config=font_config,
)
print(f"PDF written: {pdf_path}")
print(f"Size: {pdf_path.stat().st_size / 1024:.1f} KB")
