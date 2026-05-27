/**
 * viAct AI Content Agent — Daily Email Report
 * Google Apps Script
 *
 * SETUP (one time):
 *   1. Open https://script.google.com → New Project
 *   2. Paste this entire file → Save
 *   3. Run setupDailyTrigger() once → approve permissions
 *   4. Done — email arrives every day at 9:30 AM IST automatically
 *
 * To change recipients: edit RECIPIENTS below.
 * To change send time:  edit setupDailyTrigger() hour value.
 */

// ─── CONFIG ────────────────────────────────────────────────────────────────────
const SHEET_ID    = '1vo2UiNHJIFGyLj7wxAweEMyvwnNJoOVUTrJM4M9KOec';
const RECIPIENTS  = ['marketing@viact.ai'];   // add more: ['a@viact.ai','b@viact.ai']
const TIMEZONE    = 'Asia/Kolkata';
const BRAND_COLOR = '#ff6a3d';
const SHEET_URL   = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/edit`;

// ─── MAIN: called by the daily trigger ─────────────────────────────────────────
function sendDailyViActReport() {
  const ss      = SpreadsheetApp.openById(SHEET_ID);
  const today   = Utilities.formatDate(new Date(), TIMEZONE, 'yyyy-MM-dd');
  const dateLabel = Utilities.formatDate(new Date(), TIMEZONE, 'dd MMM yyyy');

  // 1. Scan "Webpage Content" tab for today's entries
  const webpageItems = _scanWebpageContent(ss, today);

  // 2. Scan all industry page tabs for recent entries (last 7 days)
  const industryItems = _scanIndustryTabs(ss, today);

  // 3. Nothing generated today → still send a summary saying 0 items
  const totalPages = webpageItems.pillar.length + webpageItems.blogs.length + industryItems.length;

  const subject = `viAct AI Daily Report — ${dateLabel} — ${totalPages} page${totalPages !== 1 ? 's' : ''} generated`;
  const htmlBody = _buildEmailHtml(webpageItems, industryItems, dateLabel, totalPages);

  for (const recipient of RECIPIENTS) {
    GmailApp.sendEmail(recipient, subject, _buildPlainText(webpageItems, industryItems, dateLabel), {
      htmlBody: htmlBody,
      name: 'viAct Content Agent',
    });
  }

  Logger.log(`Report sent to ${RECIPIENTS.join(', ')} — ${totalPages} pages.`);
}

// ─── PARSE "Webpage Content" tab ───────────────────────────────────────────────
function _scanWebpageContent(ss, today) {
  const result = { pillar: [], blogs: [] };
  const sheet  = ss.getSheetByName('Webpage Content');
  if (!sheet) return result;

  const data   = sheet.getDataRange().getValues();
  let current  = null;

  for (let r = 0; r < data.length; r++) {
    const colA = String(data[r][0] || '').trim();
    const colB = String(data[r][1] || '').trim();

    if (colA.startsWith('TOPIC:')) {
      current = { topic: colA.replace('TOPIC:', '').trim(), date: '', source: '', keyword: '', meta_title: '', meta_desc: '' };
    }
    if (!current) continue;

    if (colA === 'Date')              current.date        = colB;
    if (colA === 'Input Source')      current.source      = colB;
    if (colA === 'Primary Keyword')   current.keyword     = colB;
    if (colA === 'Meta Title')        current.meta_title  = colB;
    if (colA === 'Meta Description')  current.meta_desc   = colB;

    // Save when we hit the Decision Logic row (last field of a block)
    if (colA === 'Decision Logic' && current.date === today) {
      const isBlog = current.source.toLowerCase().includes('blog cluster');
      isBlog ? result.blogs.push(current) : result.pillar.push(current);
      current = null;
    }
  }
  return result;
}

// ─── SCAN industry page tabs ────────────────────────────────────────────────────
function _scanIndustryTabs(ss, today) {
  const SKIP_TABS = ['Webpage Content', 'Reference_Library', 'Dedup_Log', 'Sheet1'];
  const items = [];
  const sevenDaysAgo = new Date(); sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

  ss.getSheets().forEach(sheet => {
    const name = sheet.getName();
    if (SKIP_TABS.some(s => name === s)) return;
    // Date-format tabs (2026-05-27) → skip, those are Webpage Content date tabs
    if (/^\d{4}-\d{2}-\d{2}$/.test(name)) return;

    // Read col B row 1 for date (first field after SEO & META header is Meta Title row 2)
    const data = sheet.getRange(1, 1, Math.min(sheet.getLastRow(), 10), 2).getValues();
    let dateFound = '';
    for (const row of data) {
      if (String(row[0]).trim() === 'Date') { dateFound = String(row[1]).trim(); break; }
    }
    // Show if updated in last 7 days (or if date field not found, still show)
    const tabDate = dateFound ? new Date(dateFound) : null;
    if (!tabDate || tabDate >= sevenDaysAgo) {
      items.push({ name, date: dateFound || 'Unknown', isToday: dateFound === today });
    }
  });

  return items;
}

// ─── BUILD HTML EMAIL ──────────────────────────────────────────────────────────
function _buildEmailHtml(web, industry, dateLabel, total) {
  const pillarRows  = web.pillar.map(_pillarRow).join('');
  const blogRows    = web.blogs.map(_blogRow).join('');
  const industryRows = industry.map(_industryRow).join('');

  const nothingMsg = total === 0
    ? `<tr><td style="padding:16px; color:#8b949e; font-size:0.9rem;">No new pages generated today. The daily automation may still be running.</td></tr>`
    : '';

  return `<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0; padding:0; background:#f4f4f7; font-family:'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f7; padding:30px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff; border-radius:12px; overflow:hidden; box-shadow:0 4px 20px rgba(0,0,0,0.08);">

  <!-- Header -->
  <tr>
    <td style="background:linear-gradient(135deg,${BRAND_COLOR},#e54d1f); padding:28px 32px;">
      <p style="margin:0; color:rgba(255,255,255,0.75); font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:2px;">viAct · Content Intelligence</p>
      <h1 style="margin:6px 0 0; color:#ffffff; font-size:22px; font-weight:700;">Daily Content Report</h1>
      <p style="margin:4px 0 0; color:rgba(255,255,255,0.85); font-size:14px;">${dateLabel} &nbsp;·&nbsp; ${total} page${total !== 1 ? 's' : ''} generated</p>
    </td>
  </tr>

  <!-- Stats bar -->
  <tr>
    <td style="background:#fafafa; border-bottom:1px solid #eee; padding:16px 32px;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td align="center" style="padding:8px;">
            <div style="font-size:24px; font-weight:700; color:${BRAND_COLOR};">${web.pillar.length}</div>
            <div style="font-size:11px; color:#888; text-transform:uppercase; letter-spacing:1px;">Pillar Pages</div>
          </td>
          <td align="center" style="padding:8px; border-left:1px solid #eee; border-right:1px solid #eee;">
            <div style="font-size:24px; font-weight:700; color:#58a6ff;">${web.blogs.length}</div>
            <div style="font-size:11px; color:#888; text-transform:uppercase; letter-spacing:1px;">Blog Posts</div>
          </td>
          <td align="center" style="padding:8px;">
            <div style="font-size:24px; font-weight:700; color:#3fb950;">${industry.filter(i => i.isToday).length}</div>
            <div style="font-size:11px; color:#888; text-transform:uppercase; letter-spacing:1px;">Industry Pages</div>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- Content -->
  <tr><td style="padding:24px 32px;">

    <!-- Pillar Pages -->
    ${web.pillar.length > 0 ? `
    <h2 style="margin:0 0 12px; font-size:13px; font-weight:700; text-transform:uppercase; letter-spacing:1.5px; color:#333;">
      📄 Pillar Pages (${web.pillar.length})
    </h2>
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
      ${pillarRows}
    </table>` : ''}

    <!-- Blog Cluster -->
    ${web.blogs.length > 0 ? `
    <h2 style="margin:0 0 12px; font-size:13px; font-weight:700; text-transform:uppercase; letter-spacing:1.5px; color:#333;">
      📝 Blog Cluster (${web.blogs.length})
    </h2>
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
      ${blogRows}
    </table>` : ''}

    <!-- Industry Pages -->
    ${industry.length > 0 ? `
    <h2 style="margin:0 0 12px; font-size:13px; font-weight:700; text-transform:uppercase; letter-spacing:1.5px; color:#333;">
      🏭 Industry Pages — Available in Sheet (${industry.length})
    </h2>
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
      ${industryRows}
    </table>` : ''}

    ${nothingMsg ? `<table width="100%">${nothingMsg}</table>` : ''}

    <!-- CTA -->
    <div style="text-align:center; margin-top:8px;">
      <a href="${SHEET_URL}" style="display:inline-block; background:${BRAND_COLOR}; color:#fff; text-decoration:none; padding:12px 28px; border-radius:8px; font-weight:700; font-size:14px;">
        Open Google Sheet →
      </a>
    </div>

  </td></tr>

  <!-- Footer -->
  <tr>
    <td style="background:#f9f9f9; border-top:1px solid #eee; padding:16px 32px; text-align:center;">
      <p style="margin:0; font-size:11px; color:#aaa;">
        Sent automatically by <strong>viAct Content Agent</strong> ·
        <a href="${SHEET_URL}" style="color:#aaa;">View Sheet</a>
      </p>
    </td>
  </tr>

</table>
</td></tr>
</table>
</body>
</html>`;
}

function _pillarRow(item) {
  return `
  <tr>
    <td style="background:#fff8f5; border:1px solid #ffe0d0; border-radius:8px; padding:14px 16px; margin-bottom:8px; display:block;">
      <div style="font-weight:700; color:#1a1a1a; font-size:14px; margin-bottom:4px;">${_esc(item.topic)}</div>
      ${item.keyword ? `<div style="font-size:12px; color:#888; margin-bottom:2px;">🔑 ${_esc(item.keyword)}</div>` : ''}
      ${item.meta_title ? `<div style="font-size:12px; color:#555;">📌 ${_esc(item.meta_title)}</div>` : ''}
      <div style="font-size:11px; color:#bbb; margin-top:6px;">Source: ${_esc(item.source)}</div>
    </td>
  </tr>
  <tr><td style="height:8px;"></td></tr>`;
}

function _blogRow(item) {
  return `
  <tr>
    <td style="background:#f5f8ff; border:1px solid #d0e0ff; border-radius:8px; padding:12px 16px; display:block;">
      <div style="font-weight:600; color:#1a1a1a; font-size:13px; margin-bottom:2px;">${_esc(item.topic)}</div>
      ${item.keyword ? `<div style="font-size:11px; color:#888;">🔑 ${_esc(item.keyword)}</div>` : ''}
    </td>
  </tr>
  <tr><td style="height:6px;"></td></tr>`;
}

function _industryRow(item) {
  const badge = item.isToday
    ? `<span style="background:#e6f4ea; color:#2e7d32; font-size:10px; font-weight:700; padding:2px 7px; border-radius:10px; margin-left:8px;">NEW TODAY</span>`
    : `<span style="font-size:11px; color:#aaa; margin-left:8px;">${item.date}</span>`;
  return `
  <tr>
    <td style="background:#f5fdf7; border:1px solid #c3e6c3; border-radius:8px; padding:12px 16px; display:block;">
      <div style="font-size:13px; color:#1a1a1a;">🏭 <strong>${_esc(item.name)}</strong>${badge}</div>
    </td>
  </tr>
  <tr><td style="height:6px;"></td></tr>`;
}

// ─── PLAIN TEXT FALLBACK ───────────────────────────────────────────────────────
function _buildPlainText(web, industry, dateLabel) {
  const lines = [`viAct AI Daily Content Report — ${dateLabel}`, ''];
  if (web.pillar.length) {
    lines.push(`PILLAR PAGES (${web.pillar.length})`);
    web.pillar.forEach(p => lines.push(`  • ${p.topic}`));
    lines.push('');
  }
  if (web.blogs.length) {
    lines.push(`BLOG POSTS (${web.blogs.length})`);
    web.blogs.forEach(b => lines.push(`  • ${b.topic}`));
    lines.push('');
  }
  if (industry.length) {
    lines.push(`INDUSTRY PAGES (${industry.length})`);
    industry.forEach(i => lines.push(`  • ${i.name}${i.isToday ? ' [NEW TODAY]' : ''}`));
    lines.push('');
  }
  lines.push(`Open Sheet: ${SHEET_URL}`);
  return lines.join('\n');
}

function _esc(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ─── SETUP TRIGGER (run this once manually) ────────────────────────────────────
function setupDailyTrigger() {
  // Delete any existing triggers for this function first
  ScriptApp.getProjectTriggers().forEach(t => {
    if (t.getHandlerFunction() === 'sendDailyViActReport') {
      ScriptApp.deleteTrigger(t);
    }
  });

  // Create new daily trigger at 9:30 AM IST = 4:00 AM UTC
  ScriptApp.newTrigger('sendDailyViActReport')
    .timeBased()
    .atHour(4)          // 4 AM UTC = 9:30 AM IST
    .nearMinute(0)
    .everyDays(1)
    .inTimezone('Etc/UTC')
    .create();

  Logger.log('✅ Daily trigger created — report will send every day at 9:30 AM IST');
}

// ─── TEST: send a report right now ────────────────────────────────────────────
function testSendNow() {
  sendDailyViActReport();
  Logger.log('Test email sent.');
}
