/**
 * viAct AI Content Agent — Daily Email + Sheet Report
 * Google Apps Script
 *
 * SETUP (one time):
 *   1. Open your Google Sheet → Extensions → Apps Script
 *   2. Paste this entire file → Save (Ctrl+S)
 *   3. Select function: setupDailyTrigger → click Run → approve permissions
 *   4. Done — email + sheet report every day at 6:00 PM IST automatically
 *
 * To test right now: select testSendNow → Run
 */

// ─── CONFIG ────────────────────────────────────────────────────────────────────
const SHEET_ID     = '1vo2UiNHJIFGyLj7wxAweEMyvwnNJoOVUTrJM4M9KOec';
const RECIPIENTS   = ['adityameshramofficial@gmail.com'];  // add more: ['marketing@viact.ai', 'b@viact.ai']
const TIMEZONE     = 'Asia/Kolkata';
const BRAND_COLOR  = '#ff6a3d';
const SHEET_URL    = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/edit`;
const REPORT_TAB   = 'Daily Report';          // tab where report rows are saved

// ─── MAIN ──────────────────────────────────────────────────────────────────────
function sendDailyViActReport() {
  const ss        = SpreadsheetApp.openById(SHEET_ID);
  const today     = Utilities.formatDate(new Date(), TIMEZONE, 'yyyy-MM-dd');
  const dateLabel = Utilities.formatDate(new Date(), TIMEZONE, 'dd MMM yyyy, EEE');

  const webItems  = _scanWebpageContent(ss, today);
  const indItems  = _scanIndustryTabs(ss, today);
  const total     = webItems.pillar.length + webItems.blogs.length + indItems.filter(i => i.isToday).length;

  // ── Save to Daily Report tab in Sheet ──────────────────────────────────────
  _writeReportToSheet(ss, today, webItems, indItems, total);

  // ── Send email ──────────────────────────────────────────────────────────────
  const subject  = `viAct AI Daily Report — ${dateLabel} — ${total} page${total !== 1 ? 's' : ''} generated`;
  const htmlBody = _buildEmailHtml(webItems, indItems, dateLabel, total, today);
  const plain    = _buildPlainText(webItems, indItems, dateLabel);

  for (const to of RECIPIENTS) {
    GmailApp.sendEmail(to, subject, plain, { htmlBody, name: 'viAct Content Agent' });
  }
  Logger.log(`✅ Report sent — ${total} pages — ${today}`);
}

// ─── SCAN "Webpage Content" tab ────────────────────────────────────────────────
function _scanWebpageContent(ss, today) {
  const result = { pillar: [], blogs: [] };
  const sheet  = ss.getSheetByName('Webpage Content');
  if (!sheet) return result;

  const data = sheet.getDataRange().getValues();
  let cur    = null;

  for (const row of data) {
    const a = String(row[0] || '').trim();
    const b = String(row[1] || '').trim();

    if (a.startsWith('TOPIC:')) {
      cur = {
        topic: a.replace('TOPIC:', '').trim(),
        date: '', source: '', keyword: '', meta_title: '',
        meta_desc: '', canonical: '', competitors: '',
        decision: '', unverified: ''
      };
    }
    if (!cur) continue;

    if (a === 'Date')              cur.date        = b;
    if (a === 'Input Source')      cur.source      = b;
    if (a === 'Unverified')        cur.unverified  = b;
    if (a === 'Competitor URLs')   cur.competitors = b;
    if (a === 'Primary Keyword')   cur.keyword     = b;
    if (a === 'Meta Title')        cur.meta_title  = b;
    if (a === 'Meta Description')  cur.meta_desc   = b;
    if (a === 'Canonical Slug')    cur.canonical   = b;
    if (a === 'Decision Logic') {
      cur.decision = b.length > 220 ? b.slice(0, 220) + '...' : b;
      if (cur.date === today) {
        const isBlog = cur.source.toLowerCase().includes('blog cluster');
        isBlog ? result.blogs.push({...cur}) : result.pillar.push({...cur});
      }
      cur = null;
    }
  }
  return result;
}

// ─── SCAN industry tabs ────────────────────────────────────────────────────────
function _scanIndustryTabs(ss, today) {
  const SKIP = new Set(['Webpage Content', 'Reference_Library', 'Dedup_Log', 'Sheet1', REPORT_TAB]);
  const items = [];
  const cutoff = new Date(); cutoff.setDate(cutoff.getDate() - 7);

  ss.getSheets().forEach(sh => {
    const name = sh.getName();
    if (SKIP.has(name) || /^\d{4}-\d{2}-\d{2}$/.test(name)) return;

    const rows = sh.getRange(1, 1, Math.min(sh.getLastRow(), 20), 2).getValues();
    let dateVal = '', metaTitle = '', metaDesc = '', keyword = '', heroSub = '';

    for (const r of rows) {
      const a = String(r[0]).trim(), b = String(r[1]).trim();
      if (a === 'Date')                  dateVal   = b;
      if (a === 'Meta Title')            metaTitle = b;
      if (a === 'Meta Description')      metaDesc  = b;
      if (a === 'Primary Keyword')       keyword   = b;
      if (a === 'Hero Subheadline [H2]') heroSub   = b;
    }

    const d = dateVal ? new Date(dateVal) : null;
    if (!d || d >= cutoff) {
      items.push({ name, date: dateVal || '—', isToday: dateVal === today, metaTitle, metaDesc, keyword, heroSub });
    }
  });
  return items;
}

// ─── WRITE TO "Daily Report" TAB ───────────────────────────────────────────────
function _writeReportToSheet(ss, today, web, ind, total) {
  let reportSheet = ss.getSheetByName(REPORT_TAB);
  if (!reportSheet) {
    reportSheet = ss.insertSheet(REPORT_TAB);
    reportSheet.appendRow(['Date', 'Total Pages', 'Pillar Pages', 'Blog Posts',
                           'Industry Pages (today)', 'Topics Generated', 'Industry Tabs Updated']);
    reportSheet.getRange(1, 1, 1, 7).setBackground('#ff6a3d').setFontColor('#ffffff').setFontWeight('bold');
  }

  const topicsStr  = [...web.pillar, ...web.blogs].map(p => p.topic).join(' | ') || '—';
  const indStr     = ind.filter(i => i.isToday).map(i => i.name).join(' | ') || '—';
  const indAllStr  = ind.map(i => i.name).join(' | ') || '—';

  reportSheet.appendRow([
    today,
    total,
    web.pillar.length,
    web.blogs.length,
    ind.filter(i => i.isToday).length,
    topicsStr,
    indAllStr,
  ]);
}

// ─── BUILD HTML EMAIL ──────────────────────────────────────────────────────────
function _buildEmailHtml(web, ind, dateLabel, total, today) {
  const pillarHtml  = web.pillar.map(_pillarCard).join('');
  const blogHtml    = web.blogs.map(_blogCard).join('');
  const indHtml     = ind.map(_industryCard).join('');
  const todayInd    = ind.filter(i => i.isToday).length;
  const noContent   = total === 0
    ? `<p style="color:#8b949e;font-size:13px;text-align:center;padding:16px 0;">
        No new pages generated today. Automation runs at 9:30 AM IST — check GitHub Actions if expected.
       </p>` : '';

  return `<!DOCTYPE html><html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:'Segoe UI',Arial,sans-serif;font-size:14px;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f5;padding:28px 0;">
<tr><td align="center">
<table width="620" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:14px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.09);">

  <!-- HEADER -->
  <tr>
    <td style="background:linear-gradient(135deg,#ff6a3d 0%,#e54d1f 100%);padding:26px 32px 22px;">
      <p style="margin:0 0 4px;color:rgba(255,255,255,0.7);font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:2.5px;">viAct · Content Intelligence Agent</p>
      <h1 style="margin:0 0 4px;color:#fff;font-size:22px;font-weight:700;line-height:1.2;">Daily Content Report</h1>
      <p style="margin:0;color:rgba(255,255,255,0.85);font-size:13px;">${dateLabel}</p>
    </td>
  </tr>

  <!-- STATS BAR -->
  <tr>
    <td style="background:#fafafa;border-bottom:1px solid #eee;padding:0;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td align="center" style="padding:16px 8px;border-right:1px solid #eee;">
            <div style="font-size:28px;font-weight:800;color:#ff6a3d;line-height:1;">${web.pillar.length}</div>
            <div style="font-size:10px;color:#999;text-transform:uppercase;letter-spacing:1px;margin-top:4px;">Pillar Pages</div>
          </td>
          <td align="center" style="padding:16px 8px;border-right:1px solid #eee;">
            <div style="font-size:28px;font-weight:800;color:#58a6ff;line-height:1;">${web.blogs.length}</div>
            <div style="font-size:10px;color:#999;text-transform:uppercase;letter-spacing:1px;margin-top:4px;">Blog Posts</div>
          </td>
          <td align="center" style="padding:16px 8px;border-right:1px solid #eee;">
            <div style="font-size:28px;font-weight:800;color:#3fb950;line-height:1;">${todayInd}</div>
            <div style="font-size:10px;color:#999;text-transform:uppercase;letter-spacing:1px;margin-top:4px;">Industry Pages</div>
          </td>
          <td align="center" style="padding:16px 8px;">
            <div style="font-size:28px;font-weight:800;color:#a371f7;line-height:1;">${total}</div>
            <div style="font-size:10px;color:#999;text-transform:uppercase;letter-spacing:1px;margin-top:4px;">Total Today</div>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- BODY -->
  <tr><td style="padding:24px 32px;">
    ${noContent}

    <!-- PILLAR PAGES -->
    ${web.pillar.length > 0 ? `
    <div style="margin-bottom:24px;">
      <h2 style="margin:0 0 14px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1.8px;color:#ff6a3d;border-bottom:2px solid #ffe0d0;padding-bottom:6px;">
        📄 Pillar Pages — ${web.pillar.length} Generated
      </h2>
      ${pillarHtml}
    </div>` : ''}

    <!-- BLOG CLUSTER -->
    ${web.blogs.length > 0 ? `
    <div style="margin-bottom:24px;">
      <h2 style="margin:0 0 14px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1.8px;color:#58a6ff;border-bottom:2px solid #d0e0ff;padding-bottom:6px;">
        📝 Blog Cluster — ${web.blogs.length} Posts
      </h2>
      ${blogHtml}
    </div>` : ''}

    <!-- INDUSTRY PAGES -->
    ${ind.length > 0 ? `
    <div style="margin-bottom:24px;">
      <h2 style="margin:0 0 14px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1.8px;color:#3fb950;border-bottom:2px solid #c3e6c3;padding-bottom:6px;">
        🏭 Industry Pages in Sheet — ${ind.length} Total
      </h2>
      ${indHtml}
    </div>` : ''}

    <!-- CTA BUTTON -->
    <div style="text-align:center;margin-top:8px;padding-top:16px;border-top:1px solid #f0f0f0;">
      <a href="${SHEET_URL}" style="display:inline-block;background:#ff6a3d;color:#fff;text-decoration:none;padding:13px 32px;border-radius:8px;font-weight:700;font-size:14px;letter-spacing:0.3px;">
        Open Google Sheet →
      </a>
      <p style="margin:12px 0 0;font-size:11px;color:#aaa;">All content is saved in the <strong>Webpage Content</strong> tab in vertical format</p>
    </div>
  </td></tr>

  <!-- FOOTER -->
  <tr>
    <td style="background:#f9f9f9;border-top:1px solid #eee;padding:14px 32px;text-align:center;">
      <p style="margin:0;font-size:11px;color:#bbb;">
        Auto-sent by <strong style="color:#888;">viAct Content Agent</strong> every day at 6:00 PM IST &nbsp;·&nbsp;
        <a href="${SHEET_URL}" style="color:#bbb;text-decoration:none;">View Sheet</a>
      </p>
    </td>
  </tr>

</table>
</td></tr>
</table>
</body></html>`;
}

// ─── CARD BUILDERS ────────────────────────────────────────────────────────────
function _pillarCard(p) {
  const compList = p.competitors
    ? p.competitors.split(',').map(c => `<span style="display:inline-block;background:#fff3f0;color:#cc4400;border:1px solid #ffcbb0;border-radius:4px;padding:1px 7px;font-size:10px;margin:2px 2px 0 0;">${_esc(c.trim().replace(/https?:\/\/(www\.)?/,'').split('/')[0])}</span>`).join('')
    : '';

  return `
  <div style="background:#fff8f5;border:1px solid #ffe0d0;border-radius:10px;padding:16px;margin-bottom:12px;">

    <!-- INPUT -->
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:#aaa;margin-bottom:6px;">INPUT</div>
    <div style="font-size:11px;color:#888;margin-bottom:2px;">🔍 Source: <strong style="color:#555;">${_esc(p.source)}</strong>${p.unverified === 'Yes' ? ' &nbsp;<span style="background:#fff3cd;color:#856404;font-size:10px;padding:1px 6px;border-radius:3px;">Unverified</span>' : ''}</div>
    ${compList ? `<div style="font-size:11px;color:#888;margin-bottom:2px;margin-top:4px;">🌐 Competitors scraped: ${compList}</div>` : ''}

    <div style="border-top:1px dashed #eee;margin:10px 0;"></div>

    <!-- OUTPUT -->
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:#aaa;margin-bottom:6px;">OUTPUT</div>
    <div style="font-weight:700;color:#1a1a1a;font-size:15px;margin-bottom:6px;">${_esc(p.topic)}</div>
    ${p.meta_title ? `<div style="font-size:12px;color:#555;margin-bottom:3px;">📌 <strong>Meta Title:</strong> ${_esc(p.meta_title)}</div>` : ''}
    ${p.keyword    ? `<div style="font-size:12px;color:#555;margin-bottom:3px;">🔑 <strong>Keyword:</strong> ${_esc(p.keyword)}</div>` : ''}
    ${p.canonical  ? `<div style="font-size:12px;color:#555;margin-bottom:3px;">🔗 <strong>Slug:</strong> ${_esc(p.canonical)}</div>` : ''}
    ${p.meta_desc  ? `<div style="font-size:11px;color:#888;margin-top:6px;font-style:italic;">"${_esc(p.meta_desc)}"</div>` : ''}
    ${p.decision   ? `<div style="font-size:11px;color:#999;margin-top:8px;padding:8px 10px;background:#fff;border-left:3px solid #ff6a3d;border-radius:0 4px 4px 0;">${_esc(p.decision)}</div>` : ''}
  </div>`;
}

function _blogCard(b) {
  return `
  <div style="background:#f5f8ff;border:1px solid #d0e0ff;border-radius:10px;padding:14px;margin-bottom:10px;display:flex;align-items:flex-start;gap:10px;">
    <div style="min-width:28px;height:28px;background:#58a6ff;border-radius:50%;display:flex;align-items:center;justify-content:center;color:#fff;font-size:11px;font-weight:700;flex-shrink:0;"></div>
    <div>
      <div style="font-weight:600;color:#1a1a1a;font-size:13px;margin-bottom:3px;">${_esc(b.topic)}</div>
      ${b.keyword   ? `<div style="font-size:11px;color:#5580cc;">🔑 ${_esc(b.keyword)}</div>` : ''}
      ${b.meta_title ? `<div style="font-size:11px;color:#888;margin-top:2px;">📌 ${_esc(b.meta_title)}</div>` : ''}
      <div style="font-size:10px;color:#aaa;margin-top:4px;">Source: ${_esc(b.source)}</div>
    </div>
  </div>`;
}

function _industryCard(item) {
  const badge = item.isToday
    ? `<span style="background:#e6f4ea;color:#2e7d32;font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px;margin-left:8px;">NEW TODAY</span>`
    : `<span style="font-size:10px;color:#aaa;margin-left:8px;">${item.date}</span>`;

  return `
  <div style="background:#f5fdf7;border:1px solid #c3e6c3;border-radius:10px;padding:14px;margin-bottom:10px;">
    <div style="font-weight:700;color:#1a1a1a;font-size:13px;margin-bottom:6px;">🏭 ${_esc(item.name)}${badge}</div>
    ${item.heroSub  ? `<div style="font-size:12px;color:#444;margin-bottom:3px;font-style:italic;">"${_esc(item.heroSub)}"</div>` : ''}
    ${item.keyword  ? `<div style="font-size:11px;color:#5a9a5a;">🔑 ${_esc(item.keyword)}</div>` : ''}
    ${item.metaDesc ? `<div style="font-size:11px;color:#888;margin-top:4px;">${_esc(item.metaDesc)}</div>` : ''}
  </div>`;
}

// ─── PLAIN TEXT FALLBACK ───────────────────────────────────────────────────────
function _buildPlainText(web, ind, dateLabel) {
  const lines = [`viAct AI Daily Content Report — ${dateLabel}`, '='.repeat(50), ''];

  if (web.pillar.length) {
    lines.push(`PILLAR PAGES (${web.pillar.length})`);
    web.pillar.forEach(p => {
      lines.push(`  Topic   : ${p.topic}`);
      lines.push(`  Keyword : ${p.keyword}`);
      lines.push(`  Slug    : ${p.canonical}`);
      lines.push(`  Source  : ${p.source}`);
      lines.push('');
    });
  }

  if (web.blogs.length) {
    lines.push(`BLOG POSTS (${web.blogs.length})`);
    web.blogs.forEach(b => lines.push(`  • ${b.topic}  [${b.keyword}]`));
    lines.push('');
  }

  if (ind.length) {
    lines.push(`INDUSTRY PAGES IN SHEET (${ind.length})`);
    ind.forEach(i => lines.push(`  • ${i.name}${i.isToday ? ' [NEW TODAY]' : ` (${i.date})`}`));
    lines.push('');
  }

  lines.push(`Open Sheet: ${SHEET_URL}`);
  return lines.join('\n');
}

function _esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ─── SETUP TRIGGER — run once ──────────────────────────────────────────────────
function setupDailyTrigger() {
  ScriptApp.getProjectTriggers().forEach(t => {
    if (t.getHandlerFunction() === 'sendDailyViActReport') ScriptApp.deleteTrigger(t);
  });

  // 6:00 PM IST = 12:30 PM UTC
  ScriptApp.newTrigger('sendDailyViActReport')
    .timeBased()
    .atHour(12)
    .nearMinute(30)
    .everyDays(1)
    .inTimezone('Etc/UTC')
    .create();

  Logger.log('✅ Trigger set — email every day at 6:00 PM IST');
}

// ─── TEST: send right now ──────────────────────────────────────────────────────
function testSendNow() {
  sendDailyViActReport();
  Logger.log('Test report sent.');
}
