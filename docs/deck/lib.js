/**
 * Dual renderer: every primitive is drawn into a pptxgenjs slide AND into an
 * HTML twin at 96 px/inch, so the HTML screenshot is a faithful preview of the
 * .pptx (no LibreOffice available in this environment).
 */
const PX = 96;
const W = 13.333;
const H = 7.5;

const C = {
  navy: "10256D",       // reference deck's heading navy
  navyDeep: "0D2454",
  blue: "004AAD",       // reference deck's accent blue
  blueSoft: "3B6FD4",
  tint: "EEF2FA",
  tintDeep: "DCE6F7",
  line: "C9D6EE",
  ink: "12203A",
  body: "3C4A63",
  muted: "6B7A94",
  white: "FFFFFF",
  red: "B3261E",
  redBg: "FDECEA",
  amber: "9A5B00",
  amberBg: "FFF6E5",
  green: "1B6B36",
  greenBg: "EAF6EE",
};

const FONT = "Arial";

class Deck {
  constructor(pptx) {
    this.pptx = pptx;
    this.slides = [];
  }

  addSlide(bg) {
    const s = this.pptx.addSlide();
    if (bg) s.background = { color: bg };
    const rec = { s, html: [], bg: bg || C.white };
    this.slides.push(rec);
    return rec;
  }

  // ---------------------------------------------------------------- shapes
  rect(rec, o) {
    const shape = o.radius
      ? this.pptx.ShapeType.roundRect
      : this.pptx.ShapeType.rect;
    const opts = {
      x: o.x, y: o.y, w: o.w, h: o.h,
      fill: o.fill ? { color: o.fill } : { color: "FFFFFF", transparency: 100 },
      line: o.line ? { color: o.line, width: o.lineW || 1 } : { type: "none" },
    };
    if (o.radius) opts.rectRadius = o.radius;
    rec.s.addShape(shape, opts);
    rec.html.push(
      `<div style="position:absolute;left:${o.x * PX}px;top:${o.y * PX}px;` +
        `width:${o.w * PX}px;height:${o.h * PX}px;` +
        `background:${o.fill ? "#" + o.fill : "transparent"};` +
        (o.line ? `border:${(o.lineW || 1) * 1.33}px solid #${o.line};box-sizing:border-box;` : "") +
        (o.radius ? `border-radius:${o.radius * PX}px;` : "") +
        `"></div>`,
    );
  }

  circle(rec, o) {
    rec.s.addShape(this.pptx.ShapeType.ellipse, {
      x: o.x, y: o.y, w: o.d, h: o.d,
      fill: { color: o.fill },
      line: o.line ? { color: o.line, width: 1 } : { type: "none" },
    });
    rec.html.push(
      `<div style="position:absolute;left:${o.x * PX}px;top:${o.y * PX}px;` +
        `width:${o.d * PX}px;height:${o.d * PX}px;border-radius:50%;` +
        `background:#${o.fill};` + (o.line ? `border:1.3px solid #${o.line};box-sizing:border-box;` : "") + `"></div>`,
    );
    if (o.label !== undefined) {
      this.text(rec, [{ text: String(o.label), bold: true }], {
        x: o.x, y: o.y + (o.d - 0.24) / 2, w: o.d, h: 0.24,
        size: o.labelSize || 11, color: o.labelColor || C.white, align: "center",
        lineSpacingPt: (o.labelSize || 11) * 1.15,
      });
    }
  }

  line(rec, o) {
    rec.s.addShape(this.pptx.ShapeType.line, {
      x: o.x, y: o.y, w: o.w, h: o.h || 0,
      line: { color: o.color || C.line, width: o.width || 1, dashType: o.dash || "solid" },
    });
    rec.html.push(
      `<div style="position:absolute;left:${o.x * PX}px;top:${o.y * PX}px;` +
        `width:${Math.max(o.w * PX, 1)}px;height:${Math.max((o.h || 0) * PX, (o.width || 1) * 1.33)}px;` +
        `background:#${o.color || C.line};"></div>`,
    );
  }

  /** Small right-pointing chevron used in the workflow column. */
  chevron(rec, o) {
    rec.s.addShape(this.pptx.ShapeType.triangle, {
      x: o.x, y: o.y, w: o.w, h: o.h,
      fill: { color: o.fill || C.blue }, line: { type: "none" }, rotate: 180,
    });
    rec.html.push(
      `<div style="position:absolute;left:${o.x * PX}px;top:${o.y * PX}px;` +
        `width:0;height:0;border-left:${(o.w / 2) * PX}px solid transparent;` +
        `border-right:${(o.w / 2) * PX}px solid transparent;` +
        `border-top:${o.h * PX}px solid #${o.fill || C.blue};"></div>`,
    );
  }

  // ----------------------------------------------------------------- text
  /**
   * runs: array of { text, bold, italic, color, size, breakLine }
   */
  text(rec, runs, o) {
    const size = o.size || 11;
    const color = o.color || C.body;
    const align = o.align || "left";
    const lineSpacingPt = o.lineSpacingPt || size * 1.35;

    const pptRuns = runs.map((r, i) => ({
      text: r.text,
      options: {
        bold: !!r.bold,
        italic: !!r.italic,
        color: r.color || color,
        fontSize: r.size || size,
        breakLine: r.breakLine !== undefined ? r.breakLine : i < runs.length - 1,
        fontFace: FONT,
      },
    }));

    rec.s.addText(pptRuns, {
      x: o.x, y: o.y, w: o.w, h: o.h,
      align,
      valign: o.valign || "top",
      margin: 0,
      isTextBox: true,
      fontFace: FONT,
      fontSize: size,
      color,
      lineSpacing: lineSpacingPt,
      paraSpaceAfter: o.paraSpaceAfter || 0,
      shrinkText: false,
    });

    // HTML twin
    let html = "";
    let buf = "";
    runs.forEach((r, i) => {
      const style =
        `color:#${r.color || color};font-size:${(r.size || size) * (PX / 72)}px;` +
        `font-weight:${r.bold ? 700 : 400};${r.italic ? "font-style:italic;" : ""}`;
      buf += `<span style="${style}">${esc(r.text)}</span>`;
      const br = r.breakLine !== undefined ? r.breakLine : i < runs.length - 1;
      if (br) {
        html += `<div style="margin-bottom:${(o.paraSpaceAfter || 0) * (PX / 72)}px">${buf || "&nbsp;"}</div>`;
        buf = "";
      }
    });
    if (buf) html += `<div>${buf}</div>`;

    const valignCss =
      (o.valign || "top") === "middle" ? "center" : (o.valign || "top") === "bottom" ? "flex-end" : "flex-start";
    rec.html.push(
      `<div style="position:absolute;left:${o.x * PX}px;top:${o.y * PX}px;` +
        `width:${o.w * PX}px;height:${o.h * PX}px;display:flex;flex-direction:column;` +
        `justify-content:${valignCss};text-align:${align};` +
        `font-family:Arial,Helvetica,sans-serif;line-height:${lineSpacingPt * (PX / 72)}px;` +
        `overflow:hidden;">${html}</div>`,
    );
  }

  notes(rec, str) {
    rec.s.addNotes(str);
  }

  toHtml() {
    const pages = this.slides
      .map(
        (rec, i) =>
          `<section style="position:relative;width:${W * PX}px;height:${H * PX}px;` +
          `background:#${rec.bg};overflow:hidden;margin:0 auto 24px;` +
          `box-shadow:0 2px 14px rgba(0,0,0,.25);">${rec.html.join("")}` +
          `<div style="position:absolute;right:6px;bottom:2px;font:10px Arial;color:#bbb">preview ${i + 1}</div>` +
          `</section>`,
      )
      .join("\n");
    return `<!doctype html><html><head><meta charset="utf-8"><title>deck preview</title>
<style>body{margin:0;background:#4a4a4a;padding:24px 0;font-family:Arial}</style></head>
<body>${pages}</body></html>`;
  }
}

function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

module.exports = { Deck, C, FONT, W, H, PX };
