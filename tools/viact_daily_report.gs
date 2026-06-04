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
const SHEET_ID          = '1vo2UiNHJIFGyLj7wxAweEMyvwnNJoOVUTrJM4M9KOec';
const INDUSTRY_SHEET_ID = '14Y16ikpkAfnVFXm38Ot6CG4PIPTbrQ89jUPCiCjXjf4';
const RECIPIENTS        = ['marketing@viact.ai'];
const TIMEZONE     = 'Asia/Kolkata';
const BRAND_COLOR  = '#ff6a3d';
const SHEET_URL          = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/edit`;
const INDUSTRY_SHEET_URL = `https://docs.google.com/spreadsheets/d/${INDUSTRY_SHEET_ID}/edit`;
const REPORT_TAB         = 'Daily Report';
const SCAN_DAYS          = 7;   // show content from last N days

// GitHub — needed to trigger Market Radar from this script
// SETUP: paste your GitHub Personal Access Token below (needs repo + workflow scope)
// Create at: https://github.com/settings/tokens → Fine-grained → repo: Adityameshramofficial/viact-webcontent-agent → Actions: read+write
const GITHUB_TOKEN = '';   // ← paste token here, e.g. 'github_pat_xxx...'
const GITHUB_OWNER = 'Adityameshramofficial';
const GITHUB_REPO  = 'viact-webcontent-agent';
const GITHUB_WORKFLOW = 'weekly_viact.yml';

// ─── TRIGGER GITHUB ACTIONS (Market Radar) ─────────────────────────────────────
function triggerMarketRadar() {
  if (!GITHUB_TOKEN) {
    Logger.log('GITHUB_TOKEN not set — skipping Market Radar trigger.');
    return;
  }
  const url = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/${GITHUB_WORKFLOW}/dispatches`;
  const resp = UrlFetchApp.fetch(url, {
    method: 'post',
    headers: {
      'Authorization': `Bearer ${GITHUB_TOKEN}`,
      'Accept': 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
    },
    payload: JSON.stringify({ ref: 'main' }),
    muteHttpExceptions: true,
  });
  const code = resp.getResponseCode();
  if (code === 204) {
    Logger.log('Market Radar triggered on GitHub Actions.');
  } else {
    Logger.log(`GitHub trigger failed (${code}): ${resp.getContentText()}`);
  }
}

// ─── MAIN ──────────────────────────────────────────────────────────────────────
function sendDailyViActReport() {
  // 1. Kick off Market Radar pipeline on GitHub Actions (runs ~10 min, sheet updates later)
  triggerMarketRadar();

  const ss        = SpreadsheetApp.openById(SHEET_ID);
  const today     = Utilities.formatDate(new Date(), TIMEZONE, 'yyyy-MM-dd');
  const dateLabel = Utilities.formatDate(new Date(), TIMEZONE, 'dd MMM yyyy, EEE');

  const webItems  = _scanWebpageContent(ss, today);
  const indItems  = _scanIndustryTabs(ss, today);
  const oppItems  = _scanOpportunities(today);
  const csItems   = _scanCaseStudies(today);

  // Stats: count only TODAY's entries
  const todayPillar = webItems.pillar.filter(p => p.isToday).length;
  const todayBlogs  = webItems.blogs.filter(b => b.isToday).length;
  const todayInd    = indItems.filter(i => i.isToday).length;
  const todayOpps   = oppItems.length;
  const todayCS     = csItems.filter(c => c.isToday).length;
  const total       = todayPillar + todayBlogs + todayInd + todayCS;

  _writeReportToSheet(ss, today, webItems, indItems, csItems, total);

  const subject  = `viAct AI Daily Report — ${dateLabel} — ${total} page${total !== 1 ? 's' : ''} generated today`;
  const htmlBody = _buildEmailHtml(webItems, indItems, oppItems, csItems, dateLabel, todayPillar, todayBlogs, todayInd, todayOpps, todayCS, total);
  const plain    = _buildPlainText(webItems, indItems, csItems, dateLabel);

  for (const to of RECIPIENTS) {
    GmailApp.sendEmail(to, subject, plain, { htmlBody, name: 'viAct Content Agent' });
  }
  Logger.log(`Report sent — today: ${total} pages, recent: ${webItems.pillar.length + webItems.blogs.length} radar entries — ${today}`);
}

// ─── SCAN "Webpage Content" tab — last SCAN_DAYS days ─────────────────────────
function _scanWebpageContent(ss, today) {
  const result  = { pillar: [], blogs: [] };
  const sheet   = ss.getSheetByName('Webpage Content');
  if (!sheet) return result;

  const cutoff  = new Date(); cutoff.setDate(cutoff.getDate() - SCAN_DAYS);
  const data    = sheet.getDataRange().getValues();
  let cur       = null;

  for (const row of data) {
    const a = String(row[0] || '').trim();
    const b = String(row[1] || '').trim();

    if (a.startsWith('TOPIC:')) {
      cur = {
        topic: a.replace('TOPIC:', '').trim(),
        date: '', source: '', keyword: '', meta_title: '',
        meta_desc: '', canonical: '', competitors: '',
        decision: '', unverified: '', isToday: false
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
      cur.isToday  = cur.date === today;

      // Include if date is today, within last N days, or date is unknown/invalid
      const entryDate = cur.date ? new Date(cur.date) : null;
      const inWindow  = !entryDate || isNaN(entryDate) || entryDate >= cutoff;

      if (inWindow) {
        const isBlog = cur.source.toLowerCase().includes('blog') || cur.source.toLowerCase().includes('cluster');
        isBlog ? result.blogs.push({...cur}) : result.pillar.push({...cur});
      }
      cur = null;
    }
  }
  return result;
}

// ─── SCAN industry tabs — last SCAN_DAYS days ─────────────────────────────────
function _scanIndustryTabs(_ss, today) {
  const SKIP   = new Set(['Sheet1', REPORT_TAB, 'Opportunities']);
  const items  = [];
  const cutoff = new Date(); cutoff.setDate(cutoff.getDate() - SCAN_DAYS);

  // Industry pages live in a separate spreadsheet
  const indSs = SpreadsheetApp.openById(INDUSTRY_SHEET_ID);

  indSs.getSheets().forEach(sh => {
    const name = sh.getName();
    // Skip meta tabs, date tabs, and Case Study tabs (handled separately)
    if (SKIP.has(name) || /^\d{4}-\d{2}-\d{2}$/.test(name) || name.startsWith('CS — ')) return;

    const rows = sh.getRange(1, 1, Math.min(sh.getLastRow(), 25), 2).getValues();
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
    if (!d || isNaN(d) || d >= cutoff) {
      items.push({ name, date: dateVal || '—', isToday: dateVal === today, metaTitle, metaDesc, keyword, heroSub });
    }
  });
  return items;
}

// ─── SCAN "CS — *" tabs — Case Studies ────────────────────────────────────────
function _scanCaseStudies(today) {
  const items  = [];
  const cutoff = new Date(); cutoff.setDate(cutoff.getDate() - SCAN_DAYS);

  try {
    const indSs = SpreadsheetApp.openById(INDUSTRY_SHEET_ID);
    indSs.getSheets().forEach(sh => {
      const name = sh.getName();
      if (!name.startsWith('CS — ')) return;

      const rows = sh.getRange(1, 1, Math.min(sh.getLastRow(), 50), 2).getValues();
      let generatedAt = '', company = '', industry = '', location = '',
          products = '', heroH1 = '', metaTitle = '', metaDesc = '', slug = '';

      for (const r of rows) {
        const a = String(r[0]).trim(), b = String(r[1]).trim();
        if (a === 'Generated')      generatedAt = b.slice(0, 10);  // YYYY-MM-DD
        if (a === 'Company Name')   company     = b;
        if (a === 'Industry')       industry    = b;
        if (a === 'Location')       location    = b;
        if (a === 'Products Used')  products    = b;
        if (a === 'Hero H1')        heroH1      = b;
        if (a === 'Meta Title')     metaTitle   = b;
        if (a === 'Meta Description') metaDesc  = b;
        if (a === 'URL Slug')       slug        = b;
      }

      const displayName = company || name.replace('CS — ', '');
      const dateVal     = generatedAt;
      const d           = dateVal ? new Date(dateVal) : null;
      if (!d || isNaN(d) || d >= cutoff) {
        items.push({ name, displayName, date: dateVal || '—', isToday: dateVal === today,
                     industry, location, products, heroH1, metaTitle, metaDesc, slug });
      }
    });
  } catch(e) {
    Logger.log('_scanCaseStudies error: ' + e.message);
  }
  return items;
}

// ─── WRITE TO "Daily Report" TAB ───────────────────────────────────────────────
function _writeReportToSheet(ss, today, web, ind, cs, total) {
  let sh = ss.getSheetByName(REPORT_TAB);
  if (!sh) {
    sh = ss.insertSheet(REPORT_TAB);
    sh.appendRow(['Date', 'Total Pages', 'Pillar Pages', 'Blog Posts',
                  'Industry Pages (today)', 'Case Studies (today)', 'Topics Generated', 'Industry Tabs', 'Case Study Tabs']);
    sh.getRange(1, 1, 1, 9).setBackground('#ff6a3d').setFontColor('#ffffff').setFontWeight('bold');
  }
  const topicsStr = [...web.pillar, ...web.blogs].filter(p => p.isToday).map(p => p.topic).join(' | ') || '—';
  const indTabs   = ind.map(i => i.name).join(' | ') || '—';
  const csTabs    = cs.filter(c => c.isToday).map(c => c.displayName).join(' | ') || '—';

  sh.appendRow([
    today, total,
    web.pillar.filter(p => p.isToday).length,
    web.blogs.filter(b => b.isToday).length,
    ind.filter(i => i.isToday).length,
    cs.filter(c => c.isToday).length,
    topicsStr, indTabs, csTabs,
  ]);
}

// ─── SCAN "Opportunities" tab — today's new gaps ───────────────────────────────
function _scanOpportunities(today) {
  try {
    const indSs = SpreadsheetApp.openById(INDUSTRY_SHEET_ID);
    const sh = indSs.getSheetByName('Opportunities');
    if (!sh) return [];
    const lastRow = sh.getLastRow();
    if (lastRow < 2) return [];
    // Columns: A=Date, B=PageType, C=Topic, D=Score, E=GapType, F=WhyBuild, G=Evidence, H=Status
    const data = sh.getRange(2, 1, lastRow - 1, 8).getValues();
    return data
      .filter(r => String(r[0]).trim() === today && String(r[7]).trim() === 'New')
      .map(r => ({
        date:      String(r[0]).trim(),
        pageType:  String(r[1]).trim(),
        topic:     String(r[2]).trim(),
        score:     String(r[3]).trim(),
        gapType:   String(r[4]).trim(),
        why:       String(r[5]).trim(),
        evidence:  String(r[6]).trim(),
        status:    String(r[7]).trim(),
      }));
  } catch(e) {
    Logger.log('_scanOpportunities error: ' + e.message);
    return [];
  }
}

// ─── BUILD HTML EMAIL ──────────────────────────────────────────────────────────
function _buildEmailHtml(web, ind, opp, cs, dateLabel, todayPillar, todayBlogs, todayInd, todayOpps, todayCS, total) {
  const recentPillar = web.pillar.length;
  const recentBlogs  = web.blogs.length;

  const pillarHtml = web.pillar.map(_pillarCard).join('');
  const blogHtml   = web.blogs.map(_blogCard).join('');
  const indHtml    = ind.map(_industryCard).join('');
  const oppHtml    = opp.map(_opportunityCard).join('');
  const csHtml     = cs.map(_caseStudyCard).join('');

  const noTodayBanner = total === 0 ? `
    <div style="background:#fff8e1;border:1px solid #ffe082;border-radius:8px;padding:12px 16px;margin-bottom:20px;text-align:center;">
      <span style="font-size:13px;color:#795548;">No new pages generated today. Automation runs at 9:30 AM IST via GitHub Actions.</span>
    </div>` : '';

  const recentNote = (recentPillar + recentBlogs) > 0 ? `
    <p style="font-size:11px;color:#aaa;text-align:center;margin:0 0 16px;">
      Showing last ${SCAN_DAYS} days of content. Today's new pages: ${total}.
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
      <p style="margin:0 0 4px;color:rgba(255,255,255,0.7);font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:2.5px;">viAct &middot; Content Intelligence Agent</p>
      <h1 style="margin:0 0 4px;color:#fff;font-size:22px;font-weight:700;line-height:1.2;">Daily Content Report</h1>
      <p style="margin:0;color:rgba(255,255,255,0.85);font-size:13px;">${dateLabel}</p>
    </td>
  </tr>

  <!-- STATS BAR: today's counts -->
  <tr>
    <td style="background:#fafafa;border-bottom:1px solid #eee;padding:0;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td align="center" style="padding:16px 8px;border-right:1px solid #eee;">
            <div style="font-size:28px;font-weight:800;color:#ff6a3d;line-height:1;">${todayPillar}</div>
            <div style="font-size:10px;color:#999;text-transform:uppercase;letter-spacing:1px;margin-top:4px;">Pillar Pages</div>
          </td>
          <td align="center" style="padding:16px 8px;border-right:1px solid #eee;">
            <div style="font-size:28px;font-weight:800;color:#58a6ff;line-height:1;">${todayBlogs}</div>
            <div style="font-size:10px;color:#999;text-transform:uppercase;letter-spacing:1px;margin-top:4px;">Blog Posts</div>
          </td>
          <td align="center" style="padding:16px 8px;border-right:1px solid #eee;">
            <div style="font-size:28px;font-weight:800;color:#3fb950;line-height:1;">${todayInd}</div>
            <div style="font-size:10px;color:#999;text-transform:uppercase;letter-spacing:1px;margin-top:4px;">Industry Pages</div>
          </td>
          <td align="center" style="padding:16px 8px;border-right:1px solid #eee;">
            <div style="font-size:28px;font-weight:800;color:#0097a7;line-height:1;">${todayCS}</div>
            <div style="font-size:10px;color:#999;text-transform:uppercase;letter-spacing:1px;margin-top:4px;">Case Studies</div>
          </td>
          <td align="center" style="padding:16px 8px;border-right:1px solid #eee;">
            <div style="font-size:28px;font-weight:800;color:#a371f7;line-height:1;">${total}</div>
            <div style="font-size:10px;color:#999;text-transform:uppercase;letter-spacing:1px;margin-top:4px;">Total Today</div>
          </td>
          <td align="center" style="padding:16px 8px;">
            <div style="font-size:28px;font-weight:800;color:#9c27b0;line-height:1;">${todayOpps}</div>
            <div style="font-size:10px;color:#999;text-transform:uppercase;letter-spacing:1px;margin-top:4px;">Opportunities</div>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- BODY -->
  <tr><td style="padding:24px 32px;">
    ${noTodayBanner}
    ${recentNote}

    <!-- PILLAR PAGES -->
    ${recentPillar > 0 ? `
    <div style="margin-bottom:24px;">
      <h2 style="margin:0 0 14px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1.8px;color:#ff6a3d;border-bottom:2px solid #ffe0d0;padding-bottom:6px;">
        [P] Pillar Pages &mdash; ${recentPillar} in last ${SCAN_DAYS} days
      </h2>
      ${pillarHtml}
    </div>` : ''}

    <!-- BLOG CLUSTER -->
    ${recentBlogs > 0 ? `
    <div style="margin-bottom:24px;">
      <h2 style="margin:0 0 14px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1.8px;color:#58a6ff;border-bottom:2px solid #d0e0ff;padding-bottom:6px;">
        [B] Blog Cluster &mdash; ${recentBlogs} in last ${SCAN_DAYS} days
      </h2>
      ${blogHtml}
    </div>` : ''}

    <!-- INDUSTRY PAGES -->
    ${ind.length > 0 ? `
    <div style="margin-bottom:24px;">
      <h2 style="margin:0 0 14px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1.8px;color:#3fb950;border-bottom:2px solid #c3e6c3;padding-bottom:6px;">
        [I] Industry Pages in Sheet &mdash; ${ind.length} Total
      </h2>
      ${indHtml}
    </div>` : ''}

    <!-- CASE STUDIES -->
    ${cs.length > 0 ? `
    <div style="margin-bottom:24px;">
      <h2 style="margin:0 0 14px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1.8px;color:#0097a7;border-bottom:2px solid #b2ebf2;padding-bottom:6px;">
        [CS] Case Studies &mdash; ${cs.length} in last ${SCAN_DAYS} days
      </h2>
      ${csHtml}
    </div>` : ''}

    <!-- TODAY'S OPPORTUNITIES -->
    <div style="margin-bottom:24px;">
      <h2 style="margin:0 0 14px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1.8px;color:#9c27b0;border-bottom:2px solid #e1bee7;padding-bottom:6px;">
        [O] Today's Opportunities &mdash; ${todayOpps} New Gap${todayOpps !== 1 ? 's' : ''} Found
      </h2>
      ${opp.length > 0 ? oppHtml : `<div style="background:#fdf3ff;border:1px solid #e1bee7;border-radius:8px;padding:12px 16px;text-align:center;font-size:12px;color:#9c27b0;">No new content gaps detected today. All competitor topics are covered or already queued.</div>`}
    </div>

    <!-- CTA BUTTONS -->
    <div style="text-align:center;margin-top:8px;padding-top:16px;border-top:1px solid #f0f0f0;">
      <a href="${SHEET_URL}" style="display:inline-block;background:#ff6a3d;color:#fff;text-decoration:none;padding:13px 24px;border-radius:8px;font-weight:700;font-size:13px;letter-spacing:0.3px;margin:4px 6px;">
        Webpage Content Sheet &rarr;
      </a>
      <a href="${INDUSTRY_SHEET_URL}" style="display:inline-block;background:#3fb950;color:#fff;text-decoration:none;padding:13px 24px;border-radius:8px;font-weight:700;font-size:13px;letter-spacing:0.3px;margin:4px 6px;">
        Industry Pages Sheet &rarr;
      </a>
    </div>
  </td></tr>

  <!-- FOOTER -->
  <tr>
    <td style="background:#f9f9f9;border-top:1px solid #eee;padding:14px 32px;text-align:center;">
      <p style="margin:0;font-size:11px;color:#bbb;">
        Auto-sent by <strong style="color:#888;">viAct Content Agent</strong> every day at 6:00 PM IST &nbsp;&middot;&nbsp;
        <a href="${SHEET_URL}" style="color:#bbb;text-decoration:none;">View Sheet</a>
      </p>
    </td>
  </tr>

</table>
</td></tr>
</table>
</body></html>`;
}

// ─── CARD BUILDERS ─────────────────────────────────────────────────────────────
function _pillarCard(p) {
  const todayBadge = p.isToday
    ? `<span style="background:#fff0e6;color:#cc4400;font-size:10px;font-weight:700;padding:2px 7px;border-radius:8px;margin-left:8px;">NEW TODAY</span>`
    : (p.date && p.date !== '—' ? `<span style="font-size:10px;color:#aaa;margin-left:8px;">${_esc(p.date)}</span>` : '');

  const compList = p.competitors
    ? p.competitors.split(',').map(c =>
        `<span style="display:inline-block;background:#fff3f0;color:#cc4400;border:1px solid #ffcbb0;border-radius:4px;padding:1px 7px;font-size:10px;margin:2px 2px 0 0;">${_esc(c.trim().replace(/https?:\/\/(www\.)?/,'').split('/')[0])}</span>`
      ).join('')
    : '';

  return `
  <div style="background:#fff8f5;border:1px solid #ffe0d0;border-radius:10px;padding:16px;margin-bottom:12px;">
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:#aaa;margin-bottom:6px;">INPUT</div>
    <div style="font-size:11px;color:#888;margin-bottom:2px;">Source: <strong style="color:#555;">${_esc(p.source)}</strong>${todayBadge}${p.unverified === 'Yes' ? ' &nbsp;<span style="background:#fff3cd;color:#856404;font-size:10px;padding:1px 6px;border-radius:3px;">Unverified</span>' : ''}</div>
    ${compList ? `<div style="font-size:11px;color:#888;margin-bottom:2px;margin-top:4px;">Competitors: ${compList}</div>` : ''}

    <div style="border-top:1px dashed #eee;margin:10px 0;"></div>

    <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:#aaa;margin-bottom:6px;">OUTPUT</div>
    <div style="font-weight:700;color:#1a1a1a;font-size:15px;margin-bottom:6px;">${_esc(p.topic)}</div>
    ${p.meta_title ? `<div style="font-size:12px;color:#555;margin-bottom:3px;"><strong>Meta Title:</strong> ${_esc(p.meta_title)}</div>` : ''}
    ${p.keyword    ? `<div style="font-size:12px;color:#555;margin-bottom:3px;"><strong>Keyword:</strong> ${_esc(p.keyword)}</div>` : ''}
    ${p.canonical  ? `<div style="font-size:12px;color:#555;margin-bottom:3px;"><strong>Slug:</strong> ${_esc(p.canonical)}</div>` : ''}
    ${p.meta_desc  ? `<div style="font-size:11px;color:#888;margin-top:6px;font-style:italic;">"${_esc(p.meta_desc)}"</div>` : ''}
    ${p.decision   ? `<div style="font-size:11px;color:#999;margin-top:8px;padding:8px 10px;background:#fff;border-left:3px solid #ff6a3d;border-radius:0 4px 4px 0;">${_esc(p.decision)}</div>` : ''}
  </div>`;
}

function _blogCard(b) {
  const todayBadge = b.isToday
    ? `<span style="background:#e8f0fe;color:#1a73e8;font-size:10px;font-weight:700;padding:2px 7px;border-radius:8px;margin-left:6px;">NEW TODAY</span>`
    : (b.date && b.date !== '—' ? `<span style="font-size:10px;color:#aaa;margin-left:6px;">${_esc(b.date)}</span>` : '');

  return `
  <div style="background:#f5f8ff;border:1px solid #d0e0ff;border-radius:10px;padding:14px;margin-bottom:10px;">
    <div style="font-weight:600;color:#1a1a1a;font-size:13px;margin-bottom:4px;">${_esc(b.topic)}${todayBadge}</div>
    ${b.keyword    ? `<div style="font-size:11px;color:#5580cc;margin-bottom:2px;">Keyword: ${_esc(b.keyword)}</div>` : ''}
    ${b.meta_title ? `<div style="font-size:11px;color:#888;margin-bottom:2px;">Meta: ${_esc(b.meta_title)}</div>` : ''}
    <div style="font-size:10px;color:#aaa;margin-top:4px;">Source: ${_esc(b.source)}</div>
  </div>`;
}

function _industryCard(item) {
  const badge = item.isToday
    ? `<span style="background:#e6f4ea;color:#2e7d32;font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px;margin-left:8px;">NEW TODAY</span>`
    : `<span style="font-size:10px;color:#aaa;margin-left:8px;">${_esc(item.date)}</span>`;

  return `
  <div style="background:#f5fdf7;border:1px solid #c3e6c3;border-radius:10px;padding:14px;margin-bottom:10px;">
    <div style="font-weight:700;color:#1a1a1a;font-size:13px;margin-bottom:6px;">${_esc(item.name)}${badge}</div>
    ${item.heroSub  ? `<div style="font-size:12px;color:#444;margin-bottom:3px;font-style:italic;">"${_esc(item.heroSub)}"</div>` : ''}
    ${item.keyword  ? `<div style="font-size:11px;color:#5a9a5a;margin-bottom:2px;">Keyword: ${_esc(item.keyword)}</div>` : ''}
    ${item.metaDesc ? `<div style="font-size:11px;color:#888;margin-top:4px;">${_esc(item.metaDesc)}</div>` : ''}
  </div>`;
}

function _opportunityCard(opp) {
  const gapColors = {
    'REGULATORY_GAP': { bg: '#f9f0ff', border: '#d4a9f7', accent: '#7b1fa2' },
    'MISSING':        { bg: '#f3e5f5', border: '#e1bee7', accent: '#9c27b0' },
    'PARTIAL':        { bg: '#fce4ec', border: '#f8bbd9', accent: '#c2185b' },
  };
  const c = gapColors[opp.gapType] || gapColors['MISSING'];

  const evidencePills = opp.evidence
    ? opp.evidence.split(';').slice(0, 4).map(e => {
        const compName = e.trim().split(':')[0].trim();
        return compName
          ? `<span style="display:inline-block;background:#f3e5f5;color:#7b1fa2;border:1px solid #ce93d8;border-radius:4px;padding:1px 7px;font-size:10px;margin:2px 2px 0 0;">${_esc(compName)}</span>`
          : '';
      }).join('')
    : '';

  const gapBadge = `<span style="display:inline-block;background:${c.bg};color:${c.accent};border:1px solid ${c.border};border-radius:4px;padding:1px 7px;font-size:10px;font-weight:700;margin-left:6px;">${_esc(opp.gapType)}</span>`;
  const scoreBadge = `<span style="display:inline-block;background:#fff;color:#9c27b0;border:1px solid #ce93d8;border-radius:4px;padding:1px 7px;font-size:10px;font-weight:700;margin-left:6px;">Score: ${_esc(opp.score)}/20</span>`;
  const pageBadge = `<span style="display:inline-block;background:#f3e5f5;color:#6a1b9a;border-radius:4px;padding:1px 7px;font-size:10px;margin-right:4px;">${_esc(opp.pageType)}</span>`;

  return `
  <div style="background:${c.bg};border:1px solid ${c.border};border-radius:10px;padding:14px;margin-bottom:10px;">
    <div style="margin-bottom:6px;">${pageBadge}${gapBadge}${scoreBadge}</div>
    <div style="font-weight:700;color:#1a1a1a;font-size:15px;margin-bottom:6px;">${_esc(opp.topic)}</div>
    ${opp.why ? `<div style="font-size:12px;color:#555;margin-bottom:6px;font-style:italic;">${_esc(opp.why)}</div>` : ''}
    ${evidencePills ? `<div style="font-size:11px;color:#888;margin-bottom:4px;">Competitors: ${evidencePills}</div>` : ''}
  </div>`;
}

function _caseStudyCard(cs) {
  const badge = cs.isToday
    ? `<span style="background:#e0f7fa;color:#006064;font-size:10px;font-weight:700;padding:2px 7px;border-radius:8px;margin-left:8px;">NEW TODAY</span>`
    : (cs.date && cs.date !== '—' ? `<span style="font-size:10px;color:#aaa;margin-left:8px;">${_esc(cs.date)}</span>` : '');

  return `
  <div style="background:#e0f7fa;border:1px solid #b2ebf2;border-radius:10px;padding:16px;margin-bottom:12px;">
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:#aaa;margin-bottom:4px;">CASE STUDY</div>
    <div style="font-weight:700;color:#1a1a1a;font-size:15px;margin-bottom:6px;">${_esc(cs.displayName)}${badge}</div>
    ${cs.industry  ? `<div style="font-size:11px;color:#888;margin-bottom:2px;"><strong>Industry:</strong> ${_esc(cs.industry)}${cs.location ? ' &nbsp;&middot;&nbsp; ' + _esc(cs.location) : ''}</div>` : ''}
    ${cs.products  ? `<div style="font-size:11px;color:#888;margin-bottom:2px;"><strong>Products:</strong> ${_esc(cs.products)}</div>` : ''}
    ${cs.heroH1    ? `<div style="font-size:12px;color:#006064;margin-top:6px;font-style:italic;">"${_esc(cs.heroH1)}"</div>` : ''}
    ${cs.metaTitle ? `<div style="font-size:11px;color:#555;margin-top:6px;"><strong>Meta:</strong> ${_esc(cs.metaTitle)}</div>` : ''}
    ${cs.slug      ? `<div style="font-size:11px;color:#888;margin-top:3px;"><strong>Slug:</strong> ${_esc(cs.slug)}</div>` : ''}
  </div>`;
}

// ─── PLAIN TEXT FALLBACK ───────────────────────────────────────────────────────
function _buildPlainText(web, ind, cs, dateLabel) {
  const lines = [`viAct AI Daily Content Report — ${dateLabel}`, '='.repeat(50), ''];

  if (web.pillar.length) {
    lines.push(`PILLAR PAGES (${web.pillar.length} recent)`);
    web.pillar.forEach(p => {
      lines.push(`  Topic   : ${p.topic}${p.isToday ? ' [NEW TODAY]' : ` (${p.date})`}`);
      lines.push(`  Keyword : ${p.keyword}`);
      lines.push(`  Slug    : ${p.canonical}`);
      lines.push(`  Source  : ${p.source}`);
      lines.push('');
    });
  }

  if (web.blogs.length) {
    lines.push(`BLOG POSTS (${web.blogs.length} recent)`);
    web.blogs.forEach(b => lines.push(`  * ${b.topic}  [${b.keyword}]${b.isToday ? ' NEW TODAY' : ` (${b.date})`}`));
    lines.push('');
  }

  if (ind.length) {
    lines.push(`INDUSTRY PAGES (${ind.length} in sheet)`);
    ind.forEach(i => lines.push(`  * ${i.name}${i.isToday ? ' [NEW TODAY]' : ` (${i.date})`}`));
    lines.push('');
  }

  if (cs.length) {
    lines.push(`CASE STUDIES (${cs.length} recent)`);
    cs.forEach(c => {
      lines.push(`  Company : ${c.displayName}${c.isToday ? ' [NEW TODAY]' : ` (${c.date})`}`);
      if (c.industry) lines.push(`  Industry: ${c.industry}${c.location ? ', ' + c.location : ''}`);
      if (c.products) lines.push(`  Products: ${c.products}`);
      lines.push('');
    });
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
  // 6:00 PM IST = 12:30 UTC
  ScriptApp.newTrigger('sendDailyViActReport')
    .timeBased()
    .atHour(12)
    .nearMinute(30)
    .everyDays(1)
    .inTimezone('Etc/UTC')
    .create();
  Logger.log('Trigger set — email every day at 6:00 PM IST');
}

// ─── TEST: send email right now (no Market Radar trigger) ─────────────────────
function testSendNow() {
  const ss        = SpreadsheetApp.openById(SHEET_ID);
  const today     = Utilities.formatDate(new Date(), TIMEZONE, 'yyyy-MM-dd');
  const dateLabel = Utilities.formatDate(new Date(), TIMEZONE, 'dd MMM yyyy, EEE');
  const webItems  = _scanWebpageContent(ss, today);
  const indItems  = _scanIndustryTabs(ss, today);
  const oppItems  = _scanOpportunities(today);
  const csItems   = _scanCaseStudies(today);
  const todayPillar = webItems.pillar.filter(p => p.isToday).length;
  const todayBlogs  = webItems.blogs.filter(b => b.isToday).length;
  const todayInd    = indItems.filter(i => i.isToday).length;
  const todayOpps   = oppItems.length;
  const todayCS     = csItems.filter(c => c.isToday).length;
  const total       = todayPillar + todayBlogs + todayInd + todayCS;
  _writeReportToSheet(ss, today, webItems, indItems, csItems, total);
  const subject  = `[TEST] viAct AI Daily Report — ${dateLabel}`;
  const htmlBody = _buildEmailHtml(webItems, indItems, oppItems, csItems, dateLabel, todayPillar, todayBlogs, todayInd, todayOpps, todayCS, total);
  const plain    = _buildPlainText(webItems, indItems, csItems, dateLabel);
  for (const to of RECIPIENTS) {
    GmailApp.sendEmail(to, subject, plain, { htmlBody, name: 'viAct Content Agent' });
  }
  Logger.log('Test report sent (no Market Radar trigger).');
}

// ─── TEST: trigger Market Radar only ──────────────────────────────────────────
function testTriggerRadarOnly() {
  triggerMarketRadar();
}
