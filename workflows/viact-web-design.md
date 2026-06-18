---
name: viAct Web Design Engineer
description: Build production-grade, brand-accurate HTML/CSS pages for viAct.ai. Use this skill when the user asks to design, redesign, or improve any viAct webpage — industry pages, landing pages, homepage sections. Output is a complete, localhost-previewable HTML file.
type: agent-skill
version: 3.0
---

# viAct Web Design Skill

You are the design lead for viAct.ai's web presence. Every page you build must look like it was designed by a premium B2B tech agency — not generated. The design system below is fixed. Content changes per page; the visual language never does.

---

## 0. Design Thinking — Run Before Every Build

Before writing a single line of code, commit to a clear aesthetic direction. Generic defaults are not a choice — they are a failure.

### viAct Aesthetic Direction: "Industrial Intelligence"
- **Purpose:** Convert EHS Directors, HSE Managers, and Plant Managers at industrial enterprises. This is a B2B safety-tech platform, not a consumer app.
- **Tone:** Dark precision. High contrast. Surgical orange accents. Like a control room designed by a product studio, not a marketing agency.
- **Audience:** Senior decision-makers who have seen SaaS dashboards a thousand times. They trust specificity over polish. Show outcomes, not features.
- **What makes viAct UNFORGETTABLE:** Real CCTV imagery with AI bounding boxes, animated live-monitoring dashboard UI, and hard metric numbers that feel earned — not generic.

### Aesthetic Decision Checklist (answer before building)
1. **What is the ONE signature element this page will be remembered by?** (e.g., hero scan-line animation, counter stats, CCTV card hover scale — pick ONE focal signature per page, keep the rest disciplined)
2. **Is every section earning its place?** Cut any section that doesn't directly serve the conversion goal.
3. **Does the typography create tension or just deliver content?** Oxanium for machine-precision labels. Jost for human-readable body. Caveat for personality moments. Each must feel deliberate.
4. **Are you spending boldness in ONE place?** Let the signature element lead. Keep everything around it restrained and precise.

### What viAct Is NOT
- Not a startup landing page (no hero-centred "feature bullets" with floating card graphics)
- Not a generic SaaS dashboard (no purple/teal, no glassmorphism, no Inter font)
- Not a corporate brochure (no stock-photo backgrounds, no hero-image-with-overlay)
- Not a consumer app (no playful illustration, no rounded "friendly" cards)

---

## 1. The Non-Negotiables (Read Before Every Build)

**NEVER use:**
- Inter, Roboto, Arial, system-ui — banned.
- Purple-to-blue gradients.
- Rounded cards that look like SaaS pricing templates.
- Generic stock-photo placeholder boxes.
- More than 4 font weights in one section.
- Inline `style=""` for anything other than one-off position/color overrides.
- **Emojis as UI icons** — emojis (🎯🔌) are fine in body text, headings, and card descriptions. NEVER use them as standalone icon replacements in production. Use inline SVG (Heroicons/Lucide) or named icon components instead. The construction page currently uses emojis as decorative card accents — acceptable for localhost reference, but flag for Wix replacement.
- Hover states that cause layout shift — `width`, `height`, `margin`, `padding` changes on hover. Use only `transform`, `opacity`, `border-color`, `box-shadow`, `color`.

**ALWAYS do:**
- Use the viAct design token system (Section 2) — zero raw hex values in components.
- Test every section in a 980px container (Wix width).
- Make every grid translate directly to a Wix column system (2-col, 3-col, 4-col only).
- Add hover states to every interactive element.
- Add `data-target` on stat numbers and wire the counter animation (Section 7).
- Include Intersection Observer scroll fade-in on all card grids (Section 7).
- **Add `cursor: pointer` to every clickable element** — cards, buttons, links, FAQ items, tabs. No exceptions.
- **Add `:focus-visible` outline** on all interactive elements — keyboard users must see where focus is.

---

## 2. Brand Design Token System

Paste this `:root` block into every HTML file. Never override these variables with raw values.

```css
:root {
  /* ── Backgrounds ── */
  --bg-dark:     #0a0a0f;   /* Primary dark sections */
  --bg-dark-2:   #0d0d16;   /* Alternating dark sections */
  --bg-card:     #12121c;   /* Cards on dark sections */
  --bg-light:    #f4f5f8;   /* Light sections */
  --bg-white:    #ffffff;   /* White sections */

  /* ── Brand ── */
  --orange:      #ff6a3d;
  --orange-soft: rgba(255, 106, 61, 0.10);
  --orange-bdr:  rgba(255, 106, 61, 0.22);

  /* ── Text — Dark Backgrounds ── */
  --t-white:  #ffffff;
  --t-g1:     #E9ECF1;
  --t-g2:     #C9D0D9;
  --t-g3:     #A8B0BE;
  --t-g4:     #818181;

  /* ── Text — Light Backgrounds ── */
  --t-black:  #000000;
  --t-dark:   #1a1a2e;
  --t-mid:    #424242;
  --t-soft:   #818181;

  /* ── Borders ── */
  --bdr-dark:  rgba(255, 255, 255, 0.07);
  --bdr-light: rgba(0, 0, 0, 0.09);

  /* ── Shadows ── */
  --shadow-sm: 0 2px 12px rgba(0, 0, 0, 0.08);
  --shadow-md: 0 8px 32px rgba(0, 0, 0, 0.12);
  --shadow-or: 0 8px 32px rgba(255, 106, 61, 0.14);
}
```

---

## 3. Typography System

### Google Fonts Import (paste in `<head>`)
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Oxanium:wght@300;400;600;700&family=Jost:wght@300;400;500;600;700&family=Caveat:wght@500;600&display=swap" rel="stylesheet">
```

### Font Roles
| Role | Font | Weight | Size | Use For |
|------|------|--------|------|---------|
| Page Label | Oxanium | 300 | 16px | H1 eyebrow labels, industry category tag |
| Hero Headline | Oxanium | 400 | 36px | Main page H1 or H2 |
| Section Headline (dark) | Jost | 700 | 32px | H2/H3 headings on dark sections |
| Section Headline (light) | Jost | 700 | 32px | H2/H3 headings on light sections |
| Section Headline (orange) | Jost | 700 | 32px | Orange accent headings |
| Body Paragraph | Jost | 300 | 16px | Main body text (dark bg — color: `--t-g2`) |
| Body Paragraph (light) | Jost | 300 | 16px | Main body text (light bg — color: `--t-mid`) |
| Card Title | Jost | 600 | 15px | Card/block headings |
| Card Body | Jost | 300 | 13px | Card descriptions |
| Accent / Handwriting | Caveat | 500 | 24px | Orange handwritten accent lines |
| Stat Number | Oxanium | 700 | 56–60px | Impact metric numbers |
| Eyebrow Label | Oxanium | 300 | 11px | Section eyebrow tags (uppercase, letter-spaced) |
| Nav / Footer Link | Jost | 400 | 13–14px | Navigation items |

### CSS Utility Classes (copy into every file)
```css
.t-h1        { font-family:'Oxanium',sans-serif; font-weight:300; font-size:16px; color:var(--t-g3); letter-spacing:0.12em; text-transform:uppercase; }
.t-h2        { font-family:'Oxanium',sans-serif; font-weight:400; font-size:36px; color:var(--t-white); line-height:1.2; }
.t-h2 .hi    { color:var(--orange); }
.t-h4        { font-family:'Jost',sans-serif; font-weight:700; font-size:32px; color:var(--t-white); line-height:1.25; }
.t-h5        { font-family:'Jost',sans-serif; font-weight:700; font-size:32px; color:var(--t-white); line-height:1.25; }
.t-h6-blk    { font-family:'Jost',sans-serif; font-weight:700; font-size:32px; color:var(--t-black); line-height:1.25; }
.t-h6-wh     { font-family:'Jost',sans-serif; font-weight:700; font-size:32px; color:var(--t-white); line-height:1.25; }
.t-h6-or     { font-family:'Jost',sans-serif; font-weight:700; font-size:32px; color:var(--orange); line-height:1.25; }
.t-jost-light18  { font-family:'Jost',sans-serif; font-weight:300; font-size:16px; color:var(--t-g2); line-height:1.75; }
.t-jost-lt-mid   { font-family:'Jost',sans-serif; font-weight:300; font-size:16px; color:var(--t-mid); line-height:1.75; }
.t-caveat-or     { font-family:'Caveat',cursive; font-size:24px; color:var(--orange); font-weight:500; }
```

---

## 4. Layout Rules (Wix-Compatible)

### Container
```css
.wrap  { max-width: 980px; margin: 0 auto; padding: 0 28px; }
.sec   { padding: 88px 0; }
.sec-sm { padding: 60px 0; }
```

### Grid Systems (map directly to Wix columns)
```css
/* 3-column grid → Wix: 3 equal columns */
.grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }

/* 2-column grid → Wix: 2 equal columns */
.grid-2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }

/* 4-column grid → Wix: 4 equal columns */
.grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }

/* 50/50 split with gap → Wix: 2 columns with spacing */
.grid-split { display: grid; grid-template-columns: 1fr 1fr; gap: 64px; align-items: center; }

/* 40/60 split → Wix: narrow left, wide right */
.grid-asym { display: grid; grid-template-columns: 2fr 3fr; gap: 56px; align-items: start; }
```

### Section Background Alternation Pattern (follow this order)
```
Section 1 (Hero)              → --bg-dark      [dot-grid texture + orange glow]
Section 2 (Awards Marquee)    → --bg-dark-2
Section 3 (Impact Stats)      → --bg-dark
Section 4 (Platform/Tech)     → --bg-dark-2
Section 5 (How It Works)      → --bg-white
Section 6 (AI Use Cases)      → --bg-dark
Section 7 (Pre-Built Solutions) → --bg-light
Section 8 (Hardware)          → --bg-dark-2
Section 9 (Why viAct)         → --bg-dark
Section 10 (Case Studies)     → --bg-white
Section 11 (viGent)           → --bg-dark
Section 12 (Reviews)          → --bg-dark-2
Section 13 (FAQ)              → --bg-light
Section 14 (CTA)              → --bg-dark     [dot-grid + centered orange glow]
Section 15 (Footer)           → --bg-dark-2
```

---

## 5. Component Library

### Eyebrow Label
```html
<p class="eyebrow dark">Section Label</p>   <!-- on dark sections -->
<p class="eyebrow light">Section Label</p>  <!-- on light sections -->
```
```css
.eyebrow {
  display:inline-flex; align-items:center; gap:10px;
  font-family:'Oxanium',sans-serif; font-weight:300;
  font-size:11px; letter-spacing:0.2em; text-transform:uppercase; margin-bottom:14px;
}
.eyebrow::before { content:''; display:block; width:20px; height:2px; background:var(--orange); }
.eyebrow.dark  { color:var(--t-g3); }
.eyebrow.light { color:var(--t-soft); }
```

### Buttons
```html
<a href="#" class="btn btn-primary">Book My Demo →</a>
<a href="#" class="btn btn-dark">Explore Solutions</a>
<a href="#" class="btn btn-light">Learn More →</a>
<a href="#" class="btn btn-primary btn-sm">Small Button →</a>
```
```css
.btn { display:inline-flex; align-items:center; gap:8px; font-family:'Jost',sans-serif; font-weight:600; font-size:15px; padding:13px 28px; border-radius:6px; border:none; cursor:pointer; transition:all 0.25s; white-space:nowrap; min-height:44px; }
.btn-primary     { background:var(--orange); color:#fff; }
.btn-primary:hover { background:#e8572e; transform:translateY(-1px); box-shadow:var(--shadow-or); }
.btn-dark        { background:transparent; color:#fff; border:1.5px solid rgba(255,255,255,0.22); }
.btn-dark:hover  { border-color:var(--orange); color:var(--orange); }
.btn-light       { background:transparent; color:var(--t-black); border:1.5px solid rgba(0,0,0,0.2); }
.btn-light:hover { border-color:var(--orange); color:var(--orange); }
.btn-sm  { font-size:13px; padding:10px 20px; min-height:44px; }
/* ── Focus state for keyboard navigation ── */
.btn:focus-visible { outline:2px solid var(--orange); outline-offset:3px; }
```

### Dark Section Card (used for Platform, Why viAct, Hardware products)
```html
<div class="dark-card">
  <div class="card-icon"><!-- inline SVG icon --></div>
  <h3 class="card-title">Card Title</h3>
  <p class="card-body">Card description text here...</p>
</div>
```
```css
.dark-card {
  background:var(--bg-card); border:1px solid var(--bdr-dark);
  border-radius:12px; padding:28px; cursor:default;
  transition:border-color 0.25s, transform 0.25s;
}
.dark-card:hover { border-color:var(--orange-bdr); transform:translateY(-3px); }
.card-icon { width:44px; height:44px; border-radius:9px; background:var(--orange-soft); border:1px solid var(--orange-bdr); display:flex; align-items:center; justify-content:center; font-size:20px; margin-bottom:16px; }
.card-title { font-family:'Jost',sans-serif; font-weight:600; font-size:15px; color:#fff; margin-bottom:8px; }
.card-body  { font-family:'Jost',sans-serif; font-weight:300; font-size:13px; color:var(--t-g2); line-height:1.65; }
```

**Icon guidance:** For the localhost reference file, emoji decorators in card icons are acceptable. When building for Wix production, replace emojis with Wix vector art or SVG. Recommended Heroicons (outline, 24px viewBox): `shield-check`, `eye`, `bolt`, `cube`, `map-pin`, `chart-bar`.

### Light Section Card (used for Solutions, Case Studies)
```html
<div class="light-card">
  <div class="card-icon-light">🗺️</div>
  <p class="card-tag">Tag Label</p>
  <h3 class="card-title-dark">Card Title</h3>
  <p class="card-body-dark">Card description text here...</p>
  <a href="#" class="card-link">Learn More →</a>
</div>
```
```css
.light-card {
  background:var(--bg-white); border:1px solid var(--bdr-light);
  border-radius:12px; padding:28px;
  transition:box-shadow 0.25s, transform 0.25s;
}
.light-card:hover { box-shadow:var(--shadow-or); transform:translateY(-3px); }
.card-icon-light { width:46px; height:46px; border-radius:9px; background:var(--orange-soft); border:1px solid var(--orange-bdr); display:flex; align-items:center; justify-content:center; font-size:20px; margin-bottom:14px; }
.card-tag        { font-family:'Oxanium',sans-serif; font-size:10px; color:var(--orange); text-transform:uppercase; letter-spacing:0.14em; margin-bottom:6px; }
.card-title-dark { font-family:'Jost',sans-serif; font-weight:700; font-size:16px; color:var(--t-black); margin-bottom:8px; }
.card-body-dark  { font-family:'Jost',sans-serif; font-weight:300; font-size:13px; color:var(--t-mid); line-height:1.65; margin-bottom:16px; }
.card-link       { font-family:'Jost',sans-serif; font-weight:500; font-size:13px; color:var(--orange); display:inline-flex; align-items:center; gap:5px; transition:gap 0.2s; }
.card-link:hover { gap:9px; }
```

### AI CCTV Use Case Card (image + body)
```html
<div class="uc-card">
  <img class="uc-image" src="path/to/image.webp" alt="...">
  <div class="uc-body">
    <p class="uc-tag">Tag</p>
    <h3 class="uc-title">Use Case Title</h3>
    <p class="uc-desc">Description text 20–30 words...</p>
    <a href="#" class="uc-link">Explore More →</a>
  </div>
</div>
```
```css
.uc-card { background:var(--bg-card); border:1px solid var(--bdr-dark); border-radius:12px; overflow:hidden; transition:border-color 0.25s, transform 0.25s; }
.uc-card:hover { border-color:var(--orange-bdr); transform:translateY(-4px); }
.uc-image { width:100%; height:185px; object-fit:cover; display:block; transition:transform 0.4s ease; }
.uc-card:hover .uc-image { transform:scale(1.04); }
.uc-body  { padding:20px; }
.uc-tag   { font-family:'Oxanium',sans-serif; font-size:10px; color:var(--orange); text-transform:uppercase; letter-spacing:0.14em; margin-bottom:7px; }
.uc-title { font-family:'Jost',sans-serif; font-weight:400; font-size:17px; color:#fff; margin-bottom:8px; line-height:1.35; }
.uc-desc  { font-family:'Jost',sans-serif; font-weight:300; font-size:13px; color:var(--t-g2); line-height:1.65; margin-bottom:14px; }
.uc-link  { font-family:'Jost',sans-serif; font-weight:500; font-size:13px; color:var(--orange); display:inline-flex; align-items:center; gap:5px; transition:gap 0.2s; }
.uc-link:hover { gap:9px; }
```

### Review Card (testimonial)
```html
<div class="rev-card">
  <div class="rev-stars">★★★★★</div>
  <div class="rev-quote">"</div>
  <p class="rev-text">Review text here — 35–50 words...</p>
  <p class="rev-summary">Bold one-line outcome summary.</p>
  <div class="rev-author">
    <img class="rev-photo" src="path/to/photo.webp" alt="Name">
    <div>
      <div class="rev-role">Job Title, Country</div>
      <div class="rev-org">Company Name</div>
    </div>
  </div>
</div>
```
```css
.rev-card    { background:var(--bg-card); border:1px solid var(--bdr-dark); border-radius:12px; padding:28px; transition:border-color 0.25s; }
.rev-card:hover { border-color:var(--orange-bdr); }
.rev-stars   { color:var(--orange); font-size:14px; letter-spacing:2px; margin-bottom:12px; }
.rev-quote   { font-family:'Caveat',cursive; font-size:52px; color:var(--orange); line-height:1; margin-bottom:8px; }
.rev-text    { font-family:'Jost',sans-serif; font-weight:300; font-size:14px; color:var(--t-g2); line-height:1.8; margin-bottom:12px; }
.rev-summary { font-family:'Jost',sans-serif; font-weight:700; font-size:13px; color:#fff; margin-bottom:18px; }
.rev-author  { display:flex; align-items:center; gap:12px; padding-top:16px; border-top:1px solid var(--bdr-dark); }
.rev-photo   { width:44px; height:44px; border-radius:50%; object-fit:cover; border:2px solid var(--orange-bdr); flex-shrink:0; }
.rev-role    { font-family:'Jost',sans-serif; font-weight:300; font-size:13px; color:var(--orange); }
.rev-org     { font-family:'Jost',sans-serif; font-weight:300; font-size:12px; color:var(--t-g2); margin-top:1px; }
```

### Impact Stat Card
```html
<div class="stat-card">
  <div class="stat-arrow">↑</div>   <!-- ↑ for increase, ↓ for decrease/reduction -->
  <div class="stat-number" data-target="65">0<em>%</em></div>
  <div class="stat-name">Metric Name</div>
  <div class="stat-desc">10–15 word description of what was achieved.</div>
</div>
```
```css
.stat-card { background:var(--bg-card); border:1px solid var(--bdr-dark); border-radius:14px; padding:44px 32px; text-align:center; position:relative; overflow:hidden; transition:border-color 0.25s, transform 0.25s; }
.stat-card:hover { border-color:var(--orange-bdr); transform:translateY(-4px); box-shadow:0 16px 48px rgba(0,0,0,0.2); }
.stat-card::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; background:linear-gradient(90deg,transparent,var(--orange),transparent); }
.stat-arrow  { display:inline-flex; align-items:center; justify-content:center; width:32px; height:32px; border-radius:50%; background:rgba(255,106,61,0.12); margin-bottom:12px; font-size:14px; color:var(--orange); }
.stat-number { font-family:'Oxanium',sans-serif; font-weight:700; font-size:60px; color:#fff; line-height:1; margin-bottom:8px; }
.stat-number em { color:var(--orange); font-style:normal; }
.stat-name   { font-family:'Jost',sans-serif; font-weight:700; font-size:16px; color:#fff; margin-bottom:8px; text-transform:uppercase; letter-spacing:0.04em; }
.stat-desc   { font-family:'Jost',sans-serif; font-weight:300; font-size:13px; color:var(--t-g3); line-height:1.6; }
```

### FAQ Accordion
```html
<div class="faq-item open">
  <button class="faq-btn">
    <span class="faq-q">Question text here?</span>
    <span class="faq-ico">+</span>
  </button>
  <div class="faq-ans"><p class="faq-a">Answer text here...</p></div>
</div>
```
```css
.faq-list { max-width:700px; margin:0 auto; display:flex; flex-direction:column; gap:10px; }
.faq-item { background:#fff; border:1px solid var(--bdr-light); border-radius:10px; overflow:hidden; }
.faq-btn  { width:100%; padding:18px 22px; display:flex; justify-content:space-between; align-items:center; background:transparent; border:none; cursor:pointer; text-align:left; }
.faq-q    { font-family:'Jost',sans-serif; font-weight:600; font-size:15px; color:var(--t-black); }
.faq-ico  { font-size:20px; color:var(--orange); transition:transform 0.25s; flex-shrink:0; margin-left:12px; }
.faq-ans  { max-height:0; overflow:hidden; transition:max-height 0.3s ease, padding 0.3s ease; padding:0 22px; }
.faq-item.open .faq-ans { max-height:200px; padding:0 22px 18px; }
.faq-item.open .faq-ico { transform:rotate(45deg); }
.faq-a    { font-family:'Jost',sans-serif; font-weight:300; font-size:14px; color:var(--t-mid); line-height:1.7; }
```

---

## 6. JavaScript Blocks (Copy Into Every File)

Paste the entire `<script>` block before `</body>`:

```javascript
<script>
/* ── FAQ accordion ── */
document.querySelectorAll('.faq-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const item = btn.closest('.faq-item');
    const isOpen = item.classList.contains('open');
    document.querySelectorAll('.faq-item').forEach(i => i.classList.remove('open'));
    if (!isOpen) item.classList.add('open');
  });
});

/* ── Filter tabs (Case Studies) ── */
document.querySelectorAll('.cs-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.cs-tab').forEach(t => t.classList.remove('on'));
    tab.classList.add('on');
  });
});

/* ── Counter animation (Intersection Observer) ── */
const counterObs = new IntersectionObserver(entries => {
  entries.forEach(e => {
    if (!e.isIntersecting) return;
    const el = e.target;
    const target = parseInt(el.dataset.target);
    if (!target) return;
    const suffix = el.innerHTML.replace(/^\d+/, '');
    let t0 = null;
    const tick = ts => {
      if (!t0) t0 = ts;
      const p = Math.min((ts - t0) / 1800, 1);
      const v = Math.floor((1 - Math.pow(1 - p, 3)) * target);
      el.innerHTML = v + suffix;
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
    counterObs.unobserve(el);
  });
}, { threshold: 0.6 });
document.querySelectorAll('.stat-number[data-target]').forEach(el => counterObs.observe(el));

/* ── Scroll fade-in for all cards ── */
const cards = document.querySelectorAll(
  '.dark-card, .light-card, .uc-card, .rev-card, .stat-card, .faq-item, .hiw-step'
);
const fadeObs = new IntersectionObserver(entries => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      e.target.style.opacity = '1';
      e.target.style.transform = 'translateY(0)';
    }
  });
}, { threshold: 0.08 });
cards.forEach((el, i) => {
  el.style.opacity = '0';
  el.style.transform = 'translateY(22px)';
  el.style.transition = `opacity 0.5s ease ${(i % 3) * 0.09}s, transform 0.5s ease ${(i % 3) * 0.09}s`;
  fadeObs.observe(el);
});
</script>
```

---

## 7. Animation & Motion System

### Timing Scale
| Layer | Duration | Easing | Used For |
|---|---|---|---|
| Micro | 150ms | `ease` | Button hover color, link color, focus rings |
| UI | 250ms | `ease` | Card border-color, card transform, icon fill |
| Reveal | 500ms | `ease` | Scroll fade-in for cards (staggered) |
| Counter | 1800ms | cubic-bezier ease-out | Stat number count-up animation |
| Marquee | 22s | `linear` | Awards bar continuous scroll |

**Rule:** One well-orchestrated moment lands harder than ten scattered animations. The hero scan-line is viAct's signature motion. Every other animation is supporting cast — not competing.

### CSS Transition Standard
```css
/* Micro — 150ms */
.nav-links a { transition: color 150ms ease; }

/* UI — 250ms (all interactive cards/components) */
.dark-card   { transition: border-color 250ms ease, transform 250ms ease; }
.btn         { transition: background 250ms ease, box-shadow 250ms ease, transform 250ms ease; }

/* Never animate: width, height, padding, margin (layout shift) */
/* Always animate: transform, opacity, border-color, box-shadow, color, background-color */
```

### Prefers-Reduced-Motion (Required)
Paste this block into every HTML file's `<style>`:
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
  .marquee-track { animation: none; }
  .cam-scanline  { animation: none; }
  .pill-dot      { animation: none; }
}
```

And in JavaScript, wrap the fade-in initialisation:
```javascript
if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
  // attach fadeObs and scroll animations
}
```

---

## 8. Accessibility Baseline (WCAG AA)

### Colour Contrast — Pre-Verified Pairs
| Text Token | Background Token | Contrast | Pass? |
|---|---|---|---|
| `--t-white` (#fff) | `--bg-card` (#12121c) | 16.5:1 | ✅ AAA |
| `--t-g2` (#C9D0D9) | `--bg-card` (#12121c) | 9.1:1 | ✅ AAA |
| `--t-g3` (#A8B0BE) | `--bg-dark` (#0a0a0f) | 7.2:1 | ✅ AA |
| `--t-g4` (#818181) | `--bg-dark` (#0a0a0f) | 4.3:1 | ⚠️ Borderline — labels only, not body |
| `--t-black` (#000) | `--bg-white` (#fff) | 21:1 | ✅ AAA |
| `--t-mid` (#424242) | `--bg-light` (#f4f5f8) | 7.8:1 | ✅ AA |
| `--orange` (#ff6a3d) | `--bg-dark` (#0a0a0f) | 5.1:1 | ✅ AA (large text) |

**Rule:** Never use `--t-g4` for body text or descriptions. It is for labels, stat sub-text, and eyebrow decorations only.

### Semantic HTML — Required Structure
```html
<nav class="navbar">…</nav>
<main>
  <section class="hero">…</section>
  <section class="stats-sec">…</section>
  <!-- …all content sections… -->
</main>
<footer class="footer">…</footer>
```

### Accessibility Checklist
- All `<img>` tags must have descriptive `alt=""` text (not empty, not "image")
- Icon-only buttons must have `aria-label="description"`
- FAQ buttons: `<button>` not `<div>` — already correct in component library
- Tab order: matches visual reading order (left-to-right, top-to-bottom)
- Touch targets: all buttons and links minimum **44×44px** — `min-height: 44px` on `.btn`
- No color-only indicators: orange is supplemented by text/icons, not used alone
- Keyboard navigation: `:focus-visible` outlines on all interactive elements

### Focus-Visible Pattern (paste into every file)
```css
:focus-visible {
  outline: 2px solid var(--orange);
  outline-offset: 3px;
}
/* Override for cards that shouldn't show focus ring */
.dark-card:focus-visible,
.light-card:focus-visible {
  outline: 2px solid var(--orange);
  outline-offset: 2px;
  border-radius: 12px;
}
```

---

## 9. Responsive Breakpoints

The HTML reference file is built at 980px (Wix desktop). Add these breakpoints so the localhost preview is also usable on tablets and phones. Wix has its own mobile editor — these breakpoints are for the HTML reference only.

### Breakpoint Scale
| Viewport | Breakpoint | Grid Changes |
|---|---|---|
| Desktop | 980px (default) | All grids at full columns |
| Tablet | 768px | 3-col → 2-col, 4-col → 2-col, split → stack |
| Mobile | 480px | All grids → 1-col |

### Standard Responsive CSS (add at end of every `<style>` block)
```css
/* ── Tablet ── */
@media (max-width: 768px) {
  .wrap { padding: 0 20px; }
  .sec  { padding: 64px 0; }
  .grid-3, .grid-4 { grid-template-columns: repeat(2, 1fr); }
  .grid-split, .vigent-layout, .hw-layout { grid-template-columns: 1fr; gap: 40px; }
  .hero-layout { grid-template-columns: 1fr; gap: 40px; }
  .t-h2  { font-size: 28px; }
  .t-h4, .t-h5, .t-h6-blk, .t-h6-wh, .t-h6-or { font-size: 26px; }
  .stat-number { font-size: 48px; }
  .footer-grid { grid-template-columns: 1fr 1fr; gap: 28px; }
}

/* ── Mobile ── */
@media (max-width: 480px) {
  .grid-3, .grid-4, .grid-2, .grid-split { grid-template-columns: 1fr; }
  .hero-kpis { flex-direction: column; gap: 20px; }
  .kpi + .kpi { border-left: none; padding-left: 0; border-top: 1px solid var(--bdr-dark); padding-top: 20px; }
  .hiw-steps { grid-template-columns: 1fr 1fr; gap: 32px; }
  .hiw-steps::before { display: none; }
  .nav-links { display: none; }
  .t-h2  { font-size: 24px; }
  .t-h4, .t-h5, .t-h6-blk, .t-h6-wh, .t-h6-or { font-size: 22px; }
  .footer-grid { grid-template-columns: 1fr; }
  .rev-grid { grid-template-columns: 1fr; }
  .cta-heading { font-size: 28px; }
}

/* ── Reduced motion ── */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
  .marquee-track { animation: none; }
  .cam-scanline  { animation: none; }
  .pill-dot      { animation: none; }
}
```

---

## 10. Hero Section Pattern

The hero always follows this layout:

```
┌─────────────────────────────────────────────────────────────────┐
│  [dot-grid bg]              [orange glow: top-right]            │
│  ┌─────────────────────┐   ┌─────────────────────────────────┐  │
│  │ [pill badge: live]  │   │  [screen-card mockup OR image]  │  │
│  │ [H1 eyebrow label]  │   │  • mac-style topbar             │  │
│  │ [H2 headline]       │   │  • cam viewport (scan animation)│  │
│  │ [H3 description]    │   │  • alert card                   │  │
│  │ [award line]        │   │  • 3 metric chips               │  │
│  │ [CTA buttons]       │   └─────────────────────────────────┘  │
│  │ [3 KPI divider]     │                                        │
│  └─────────────────────┘                                        │
└─────────────────────────────────────────────────────────────────┘
```

**Hero content rules:**
- Headline: `AI for Safety & Productivity in [Industry]` — max 10 words
- Sub-headline: metric-led — "Reduce [Industry] downtime by 70%..." — max 20 words, **bold**
- Description: 35–45 words, explains how viAct turns site into predictive intelligence
- 3 KPIs at the bottom with Oxanium numbers + `--t-g4` labels

**Hero background treatment:**
```css
.hero {
  background: var(--bg-dark); min-height: 100vh;
  padding-top: 68px; display: flex; align-items: center;
  position: relative; overflow: hidden;
}
.hero-bg {
  position: absolute; inset: 0; pointer-events: none;
  background-image: radial-gradient(rgba(255,255,255,0.06) 1px, transparent 1px);
  background-size: 28px 28px;
}
.hero-glow {
  position: absolute; top: -10%; right: -10%;
  width: 55%; height: 110%;
  background: radial-gradient(ellipse at 60% 40%, rgba(255,106,61,0.08) 0%, transparent 60%);
  pointer-events: none;
}
```

---

## 11. Image Handling

### Available Local Images
All images live in:
```
Industry dynamic webpage seo content and image/
├── Reference  AI CCTV Use Cases section images/
│   ├── Manufacturing Page LOW-01.webp  (use case card 1)
│   ├── Manufacturing Page LOW-02.webp  (use case card 2)
│   ├── Manufacturing Page LOW-03.webp  (use case card 3)
│   ├── Manufacturing Page LOW-04.webp  (use case card 4)
│   ├── Manufacturing Page LOW-05.webp  (use case card 5)
│   ├── Manufacturing Page LOW-06.webp  (use case card 6)
│   └── viGent.webp                     (viGent AI agent dashboard)
└── Reference Review Section images/
    ├── AI Safety and Productivity System for Electronics Factory in Japan.webp
    ├── AI Safety and Productivity System for Industrial Manufacturing in Germany.webp
    ├── AI Safety and Productivity System for Packaging Plant in UK.webp
    ├── AI Safety and Productivity System for Dairy & Beverage Facility in UAE.webp
    └── AI Safety and Productivity System for Manufacturing Facility in France.webp
```

### Image Path Rule
Use relative paths from the HTML file location. Spaces in filenames are fine — browsers handle URL encoding:
```html
<img src="Industry dynamic webpage seo content and image/Reference  AI CCTV Use Cases section images/Manufacturing Page LOW-01.webp" alt="...">
```

### Image Usage Rules
- Use Cases section: all 6 LOW-0X.webp images in order
- viGent section: always use `viGent.webp` — NOT a CCTV image
- Review section: use the 4–5 available review photos as reviewer profile images (44×44px circle crop)
- Use `object-fit: cover` on all images with fixed heights

---

## 12. Wix Classic Editor Translation Map

When the user says "replicate this in Wix," use these mappings:

| HTML/CSS Element | Wix Editor Equivalent |
|---|---|
| `.wrap` (max-width: 980px) | Site width setting: 980px |
| `grid-template-columns: repeat(3, 1fr)` | 3-column strip layout |
| `grid-template-columns: 1fr 1fr` | 2-column strip layout |
| `background: var(--bg-dark)` | Strip background color: #0a0a0f |
| `.dark-card` | Box widget with background #12121c, border 1px rgba(255,255,255,0.07) |
| `.btn-primary` | Button widget, fill #ff6a3d, text white, corner radius 6px |
| `.eyebrow` | Text widget: Oxanium 11px, spacing 0.2em, color #A8B0BE |
| `.t-h2` | Title widget: Oxanium 36px, weight 400, color white |
| `.t-h6-wh` | Title widget: Jost 32px Bold, color white |
| `.stat-number` | Text widget: Oxanium 60px Bold, color white |
| `.awards-bar` marquee | Slideshow or Gallery in strip mode |
| `.faq-item` accordion | Wix Accordion widget |
| `.footer-grid` | 4-column strip with 2fr 1fr 1fr 1fr widths |
| Image hover scale | Wix Pro Gallery or image with hover effect enabled |

**Wix-specific notes:**
- No custom JavaScript in Wix Classic — FAQ accordion needs to be replaced with Wix Accordion widget
- CSS animations (counter, fade-in, marquee) are reference-only in Wix — use Wix Animations panel instead
- Google Fonts are available in Wix: search "Oxanium", "Jost", "Caveat" in the font picker
- The dot-grid hero background is a repeating SVG pattern — use as a background image in the strip

---

## 13. Quality Gates

Before marking any page complete, check every item:

**Layout:**
- [ ] Every section fits within 980px with 28px side padding
- [ ] No section has fewer than `padding: 88px 0`
- [ ] Dark/light section alternation follows the pattern (Section 4 above)
- [ ] All grids are 2-col, 3-col, or 4-col only
- [ ] Floating navbar does not overlap hero content (`padding-top: 68px` on hero)

**Typography:**
- [ ] H1 eyebrow: Oxanium 300 16px `--t-g3`
- [ ] Page headline: Oxanium 400 36px white
- [ ] Section headings: Jost 700 32px (correct color variant)
- [ ] Body text: Jost 300 16px on dark (`--t-g2`), Jost 300 16px on light (`--t-mid`)
- [ ] Accent handwriting: Caveat 500 24px orange
- [ ] `--t-g4` is NOT used for body text — labels and eyebrows only

**Content (Industry Pages):**
- [ ] Hero: headline ≤10 words, description 35–45 words
- [ ] Stats: exactly 3 cards, 10–15 word descriptions
- [ ] Use Cases: exactly 6 cards with real LOCAL images
- [ ] Reviews: exactly 4 cards, 35–50 words each, star ratings, bold summary line
- [ ] viGent section: uses viGent.webp (NOT a CCTV image)
- [ ] FAQ: minimum 5 questions

**Interactions:**
- [ ] FAQ accordion JavaScript present and wired
- [ ] Counter animation on all `.stat-number[data-target]` elements
- [ ] Scroll fade-in on all cards
- [ ] All buttons have hover states
- [ ] All cards have hover states (border-color or transform)
- [ ] **All clickable elements have `cursor: pointer`**
- [ ] **`:focus-visible` outline block is present in CSS**
- [ ] **Hover states use only `transform`/`opacity`/`border-color`/`box-shadow` — no layout shift**
- [ ] All transitions are between 150ms and 500ms (no instant state changes, no 1s+ hover lags)

**Accessibility:**
- [ ] All `<img>` have descriptive `alt=""` text (never empty or "image")
- [ ] `<nav>`, `<main>`, `<footer>` semantic HTML present
- [ ] All buttons use `<button>` or `<a href>` — never `<div>` as a button
- [ ] Touch targets ≥ 44px height on all buttons (`min-height: 44px` on `.btn`)
- [ ] `prefers-reduced-motion` CSS block present

**Polish:**
- [ ] Awards marquee loops seamlessly (content duplicated)
- [ ] Hero scan-line animation running
- [ ] Hero KPIs separated by `border-left` dividers
- [ ] CTA section has trust signals below buttons
- [ ] Footer has 4-column grid: brand + 3 link columns
- [ ] `@media (max-width: 768px)` and `@media (max-width: 480px)` blocks present

---

## 14. Execution Workflow

When the user says **"Design [page name] page"** or **"Build [section] section"**:

1. **Answer Section 0 questions first** — What is the ONE signature element? What makes this page specific?
2. **Check content** — Do I have all text content? If not, generate it from the CLAUDE.md workflow SOP.
3. **Choose template base** — Industry page (15 sections) or custom page (define sections).
4. **Map images** — Which LOCAL images go in which slots?
5. **Start from the design token system** — Never start from scratch. Copy the `:root`, typography classes, and base layout CSS.
6. **Build section by section** — Hero → Marquee → Stats → Platform → How It Works → Use Cases → Solutions → Hardware → Why viAct → Case Studies → viGent → Reviews → FAQ → CTA → Footer.
7. **Add all JavaScript** — FAQ, counter, fade-in. Never skip. Wrap scroll animations in `prefers-reduced-motion` check.
8. **Add responsive + accessibility CSS blocks** — Both `@media` breakpoints + `prefers-reduced-motion` + `:focus-visible` rules.
9. **Run localhost preview** — `python -m http.server 8000` from the project directory.
10. **Tell user to hard refresh** — `Ctrl+Shift+R` to bust browser cache.

---

## 15. Self-Critique Checklist (Run Before Delivering)

Look at the page with fresh eyes and ask:

**Design Thinking (from Section 0):**
- Is there ONE unforgettable signature element? (Not ten things competing for attention.)
- Does the typography carry personality — or is it just a delivery vehicle for text?
- Does motion serve the content, or is it decoration noise? Remove any animation that doesn't justify its presence.
- Squint test: In each section, does one element immediately dominate? (Stats → numbers. CTA → primary button. Hero → headline.)

**Brand & Content:**
- Does the hero immediately communicate "AI safety platform for [industry]"?
- Does the orange feel intentional — not overused, not absent?
- Are the stat numbers the most visually dominant thing in the stats section?
- Do the use case cards create curiosity, not just catalog items?
- Does the viGent section use the real dashboard image?
- Are reviews believable — not corporate-template? Do the summary lines feel earned?
- Is the CTA the final thing the user sees, with a single, clear next action?

**User Test:**
- Would an EHS Director at a large industrial firm feel confident booking a demo after reading this page?
- Could a designer replicate every section in Wix by looking at this HTML reference?

If any answer is "no" or "unsure" — fix it before delivering.
