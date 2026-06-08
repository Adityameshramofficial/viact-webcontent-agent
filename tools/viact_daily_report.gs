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
const RECIPIENTS        = ['gary.ng@viact.ai'];
const CC                = ['surendra.singh@viact.ai'];
const TIMEZONE          = 'Asia/Kolkata';
const BRAND_COLOR       = '#ff6a3d';
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
    return 'skipped';
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
    return 'triggered';
  } else {
    Logger.log(`GitHub trigger failed (${code}): ${resp.getContentText()}`);
    return 'failed';
  }
}

// ─── FETCH RECENT COMMITS ──────────────────────────────────────────────────────
function _fetchRecentCommits() {
  if (!GITHUB_TOKEN) return [];
  try {
    const since = new Date(); since.setDate(since.getDate() - 1);
    const url = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/commits?per_page=10&since=${since.toISOString()}`;
    const resp = UrlFetchApp.fetch(url, {
      headers: { 'Authorization': `Bearer ${GITHUB_TOKEN}`, 'Accept': 'application/vnd.github+json' },
      muteHttpExceptions: true,
    });
    if (resp.getResponseCode() !== 200) return [];
    return JSON.parse(resp.getContentText()).map(c => ({
      message: c.commit.message.split('\n')[0],
      time:    Utilities.formatDate(new Date(c.commit.author.date), TIMEZONE, 'hh:mm a'),
      sha:     c.sha.substring(0, 7),
      url:     c.html_url,
    }));
  } catch(e) {
    Logger.log('Commits fetch failed: ' + e);
    return [];
  }
}

// ─── MAIN ──────────────────────────────────────────────────────────────────────
function sendDailyViActReport() {
  const radarStatus = triggerMarketRadar();
  const triggerTime = Utilities.formatDate(new Date(), TIMEZONE, 'hh:mm a');
  const commits     = _fetchRecentCommits();

  const ss        = SpreadsheetApp.openById(SHEET_ID);
  const today     = Utilities.formatDate(new Date(), TIMEZONE, 'yyyy-MM-dd');
  const dateLabel = Utilities.formatDate(new Date(), TIMEZONE, 'dd MMM yyyy, EEE');

  const webItems  = _scanWebpageContent(ss, today);
  const indItems  = _scanIndustryTabs(ss, today);
  const oppItems  = _scanOpportunities(today);
  const csItems   = _scanCaseStudies(today);
  const intelItem = _scanCompetitorIntel(today);
  const topics    = _scanDailyTopics(today);

  // Stats: count only TODAY's entries
  const todayPillar = webItems.pillar.filter(p => p.isToday).length;
  const todayBlogs  = webItems.blogs.filter(b => b.isToday).length;
  const todayInd    = indItems.filter(i => i.isToday).length;
  const todayOpps   = oppItems.length;
  const todayCS     = csItems.filter(c => c.isToday).length;
  const total       = todayPillar + todayBlogs + todayInd + todayCS;

  _writeReportToSheet(ss, today, webItems, indItems, csItems, total);

  const subject  = `viAct AI Daily Report — ${dateLabel} — ${total} page${total !== 1 ? 's' : ''} generated today`;
  const htmlBody = _buildEmailHtml(webItems, indItems, oppItems, csItems, intelItem, dateLabel, todayPillar, todayBlogs, todayInd, todayOpps, todayCS, total, radarStatus, triggerTime, commits, topics);
  const plain    = _buildPlainText(webItems, indItems, csItems, dateLabel, radarStatus, triggerTime);

  const mailOptions = { htmlBody, name: 'viAct Content Agent' };
  if (CC.length) mailOptions.cc = CC.join(',');

  for (const to of RECIPIENTS) {
    GmailApp.sendEmail(to, subject, plain, mailOptions);
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

// ─── SCAN "Daily Topics" tab — today's 3 suggested content topics ─────────────
function _scanDailyTopics(today) {
  try {
    const indSs = SpreadsheetApp.openById(INDUSTRY_SHEET_ID);
    const sh = indSs.getSheetByName('Daily Topics');
    if (!sh) return null;
    const data = sh.getDataRange().getValues();
    if (data.length < 2) return null;
    const latest = data[data.length - 1];
    // Columns: Date|Industry Topic|Industry|Industry Why|CS Company Type|CS Industry|CS Location|CS Detection Focus|CS Why|VA Detection|VA Why|Urgency
    if (!latest[0]) return null;
    return {
      date:            String(latest[0]).trim(),
      industryTopic:   String(latest[1]).trim(),
      industryIndustry:String(latest[2]).trim(),
      industryWhy:     String(latest[3]).trim(),
      csType:          String(latest[4]).trim(),
      csIndustry:      String(latest[5]).trim(),
      csLocation:      String(latest[6]).trim(),
      csDetection:     String(latest[7]).trim(),
      csWhy:           String(latest[8]).trim(),
      vaDetection:     String(latest[9]).trim(),
      vaWhy:           String(latest[10]).trim(),
      urgency:         String(latest[11]).trim(),
      isToday:         String(latest[0]).trim() === today,
    };
  } catch(e) {
    Logger.log('_scanDailyTopics error: ' + e.message);
    return null;
  }
}

// ─── SCAN "Competitor Intel" tab — daily market intelligence ──────────────────
function _scanCompetitorIntel(today) {
  try {
    const indSs = SpreadsheetApp.openById(INDUSTRY_SHEET_ID);
    const sh = indSs.getSheetByName('Competitor Intel');
    if (!sh) return null;
    const lastRow = sh.getLastRow();
    if (lastRow < 2) return null;
    // Columns: Date | Urgency | Executive Summary | Top Competitor Move | Trending Topic | viAct Opportunity | News Count | Trends Count | Opps Count | Top 3 News | Top 3 Trends | Top 3 Opps
    const data = sh.getRange(2, 1, lastRow - 1, 12).getValues();
    // Get most recent row (last row = most recent)
    const latest = data[data.length - 1];
    if (!latest || !String(latest[0]).trim()) return null;
    return {
      date:              String(latest[0]).trim(),
      urgency:           String(latest[1]).trim(),
      executiveSummary:  String(latest[2]).trim(),
      topCompetitorMove: String(latest[3]).trim(),
      trendingTopic:     String(latest[4]).trim(),
      viactOpportunity:  String(latest[5]).trim(),
      newsCount:         String(latest[6]).trim(),
      trendsCount:       String(latest[7]).trim(),
      oppsCount:         String(latest[8]).trim(),
      topNews:           String(latest[9]).trim(),
      topTrends:         String(latest[10]).trim(),
      topOpps:           String(latest[11]).trim(),
      isToday:           String(latest[0]).trim() === today,
    };
  } catch(e) {
    Logger.log('_scanCompetitorIntel error: ' + e.message);
    return null;
  }
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

// ─── MARKET INTELLIGENCE SECTION ──────────────────────────────────────────────
function _marketIntelSection(intel) {
  if (!intel) {
    return `
    <div style="margin-bottom:24px;">
      <h2 style="margin:0 0 14px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1.8px;color:#0288d1;border-bottom:2px solid #b3e5fc;padding-bottom:6px;">
        [M] Market Intelligence &mdash; Competitor + Trend Monitor
      </h2>
      <div style="background:#e1f5fe;border:1px solid #b3e5fc;border-radius:8px;padding:12px 16px;text-align:center;font-size:12px;color:#01579b;">
        No scan data yet. Run the Competitor News Monitor from the app to populate this section.
      </div>
    </div>`;
  }

  const urgencyColor = intel.urgency === 'HIGH' ? '#d32f2f' : intel.urgency === 'MEDIUM' ? '#f57c00' : '#388e3c';
  const urgencyBg    = intel.urgency === 'HIGH' ? '#ffebee' : intel.urgency === 'MEDIUM' ? '#fff3e0' : '#e8f5e9';
  const staleBadge   = !intel.isToday
    ? `<span style="font-size:10px;color:#aaa;margin-left:8px;">(last scan: ${_esc(intel.date)})</span>`
    : `<span style="background:#e0f7fa;color:#006064;font-size:10px;font-weight:700;padding:2px 7px;border-radius:8px;margin-left:8px;">TODAY</span>`;

  const newsItems  = intel.topNews   ? intel.topNews.split('|').map(s => s.trim()).filter(Boolean) : [];
  const trendItems = intel.topTrends ? intel.topTrends.split('|').map(s => s.trim()).filter(Boolean) : [];
  const oppItems   = intel.topOpps   ? intel.topOpps.split('|').map(s => s.trim()).filter(Boolean) : [];

  const listHtml = (items, color) => items.length
    ? items.map(i => `<div style="font-size:11px;color:#555;padding:3px 0;border-bottom:1px solid #f0f0f0;">${_esc(i)}</div>`).join('')
    : `<div style="font-size:11px;color:#aaa;">—</div>`;

  return `
  <div style="margin-bottom:24px;">
    <h2 style="margin:0 0 14px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1.8px;color:#0288d1;border-bottom:2px solid #b3e5fc;padding-bottom:6px;">
      [M] Market Intelligence &mdash; Competitor + Trend Monitor${staleBadge}
    </h2>

    <!-- Urgency + Summary -->
    <div style="background:${urgencyBg};border:1px solid ${urgencyColor}33;border-radius:8px;padding:14px 16px;margin-bottom:12px;">
      <div style="display:inline-block;background:${urgencyColor};color:#fff;font-size:10px;font-weight:800;padding:2px 8px;border-radius:4px;margin-bottom:8px;text-transform:uppercase;letter-spacing:1px;">${_esc(intel.urgency)} URGENCY</div>
      <div style="font-size:13px;color:#1a1a1a;line-height:1.6;margin-bottom:8px;">${_esc(intel.executiveSummary)}</div>
      <div style="font-size:11px;color:#555;"><strong>🔥 Trending:</strong> ${_esc(intel.trendingTopic)}</div>
    </div>

    <!-- 3-column: Competitor / Trends / viAct Action -->
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td width="33%" style="padding-right:6px;vertical-align:top;">
          <div style="background:#fff8e1;border:1px solid #ffe082;border-radius:8px;padding:12px;">
            <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#f57c00;margin-bottom:8px;">🏢 Competitor Moves (${_esc(intel.newsCount)})</div>
            <div style="font-size:11px;color:#e65100;font-weight:600;margin-bottom:6px;">${_esc(intel.topCompetitorMove)}</div>
            ${listHtml(newsItems, '#f57c00')}
          </div>
        </td>
        <td width="33%" style="padding:0 3px;vertical-align:top;">
          <div style="background:#e8f5e9;border:1px solid #a5d6a7;border-radius:8px;padding:12px;">
            <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#2e7d32;margin-bottom:8px;">📈 Industry Trends (${_esc(intel.trendsCount)})</div>
            ${listHtml(trendItems, '#2e7d32')}
          </div>
        </td>
        <td width="33%" style="padding-left:6px;vertical-align:top;">
          <div style="background:#e3f2fd;border:1px solid #90caf9;border-radius:8px;padding:12px;">
            <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#1565c0;margin-bottom:8px;">⚡ viAct Action</div>
            <div style="font-size:11px;color:#1565c0;line-height:1.5;">${_esc(intel.viactOpportunity)}</div>
          </div>
        </td>
      </tr>
    </table>
  </div>`;
}

// ─── BUILD UPDATE BANNER ───────────────────────────────────────────────────────
function _buildUpdateBanner(dateLabel) {
  // Show this banner only on the build date
  if (!dateLabel.includes('June 5') && !dateLabel.includes('Jun 5')) return '';

  return `
  <div style="background:linear-gradient(135deg,#0d1117 0%,#161b22 100%);border:1px solid #30363d;border-radius:12px;padding:20px 24px;margin-bottom:24px;">
    <div style="display:flex;align-items:center;margin-bottom:12px;">
      <span style="font-size:18px;margin-right:8px;">🚀</span>
      <span style="font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:2px;color:#58a6ff;">System Build Update &mdash; June 5, 2026</span>
    </div>
    <div style="font-size:15px;font-weight:700;color:#e6edf3;margin-bottom:8px;">
      Case Study Dynamic Page Automation — Built from Scratch
    </div>
    <div style="font-size:12px;color:#8b949e;margin-bottom:16px;line-height:1.6;">
      The viAct content system now supports fully automated case study page generation.
      Enter a company name, industry, location, and products — and the AI generates a complete,
      publish-ready Wix CMS case study page in under 60 seconds.
    </div>

    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:16px;">
      <tr>
        <td width="50%" style="padding-right:8px;vertical-align:top;">
          <div style="background:#161b22;border:1px solid #21262d;border-radius:8px;padding:14px;">
            <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:#58a6ff;margin-bottom:10px;">📝 Webpage Content</div>
            <div style="font-size:11px;color:#8b949e;line-height:1.8;">
              ✓ Hero H1 + H3 intro copy<br>
              ✓ Company Overview (80-120 words)<br>
              ✓ The Challenge (200-300 words)<br>
              ✓ The Solution + 2 subsections<br>
              ✓ The Impact section<br>
              ✓ 2 testimonial quotes + roles<br>
              ✓ CTA headline<br>
              ✓ Story Snapshot + Use Case label
            </div>
          </div>
        </td>
        <td width="50%" style="padding-left:8px;vertical-align:top;">
          <div style="background:#161b22;border:1px solid #21262d;border-radius:8px;padding:14px;">
            <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:#3fb950;margin-bottom:10px;">🔍 SEO Fields</div>
            <div style="font-size:11px;color:#8b949e;line-height:1.8;">
              ✓ Meta Title (≤60 chars)<br>
              ✓ Meta Description (150-160 chars)<br>
              ✓ Keywords (5-8 SEO terms)<br>
              ✓ URL Slug (auto-formatted)<br>
              ✓ Filter Tag + Tags array<br>
              ✓ List Page Description<br>
              ✓ Canonical URL (viact.ai/case-studies/...)
            </div>
          </div>
        </td>
      </tr>
      <tr>
        <td width="50%" style="padding-right:8px;padding-top:8px;vertical-align:top;">
          <div style="background:#161b22;border:1px solid #21262d;border-radius:8px;padding:14px;">
            <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:#f78166;margin-bottom:10px;">🎨 Image Prompts (Nano Banana)</div>
            <div style="font-size:11px;color:#8b949e;line-height:1.8;">
              ✓ Hero Banner — 426×423px (square)<br>
              ✓ Company Overview — 342×414px (portrait)<br>
              ✓ Solution Image 1 — 1440×978px<br>
              ✓ Solution Image 2 — 2289×1400px<br>
              ✓ Testimonial — 400×400px (square)<br>
              <span style="color:#555;">Ready to paste directly into Nano Banana</span>
            </div>
          </div>
        </td>
        <td width="50%" style="padding-left:8px;padding-top:8px;vertical-align:top;">
          <div style="background:#161b22;border:1px solid #21262d;border-radius:8px;padding:14px;">
            <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:#0097a7;margin-bottom:10px;">🖼 Alt Texts + Sheet Push</div>
            <div style="font-size:11px;color:#8b949e;line-height:1.8;">
              ✓ All 10 alt text fields (Wix CMS match)<br>
              ✓ Company logo alt text (auto)<br>
              ✓ Profile image alt text (auto)<br>
              ✓ 3 metrics alt texts (auto-derived)<br>
              ✓ Auto-push to Google Sheets<br>
              ✓ Daily report email (this email)<br>
              ✓ Quality gate + auto-retry on fail
            </div>
          </div>
        </td>
      </tr>
    </table>

    <div style="background:#0d1117;border:1px solid #21262d;border-radius:6px;padding:10px 14px;font-size:11px;color:#8b949e;">
      <strong style="color:#e6edf3;">Total CMS Fields Generated:</strong> 56 fields per case study &nbsp;&middot;&nbsp;
      <strong style="color:#e6edf3;">LLM:</strong> Llama 3.3 70B (Groq) &nbsp;&middot;&nbsp;
      <strong style="color:#e6edf3;">Research:</strong> Tavily web search &nbsp;&middot;&nbsp;
      <strong style="color:#e6edf3;">Time:</strong> ~45 seconds per case study
    </div>
  </div>`;
}

// ─── BUILD HTML EMAIL ──────────────────────────────────────────────────────────
function _buildEmailHtml(web, ind, opp, cs, intel, dateLabel, todayPillar, todayBlogs, todayInd, todayOpps, todayCS, total, radarStatus, triggerTime, commits, topics) {
  radarStatus = radarStatus || 'skipped';
  triggerTime = triggerTime || '';
  commits     = commits     || [];
  topics      = topics      || null;
  const recentPillar = web.pillar.length;
  const recentBlogs  = web.blogs.length;

  const pillarHtml = web.pillar.map(_pillarCard).join('');
  const blogHtml   = web.blogs.map(_blogCard).join('');
  const indHtml    = ind.map(_industryCard).join('');
  const oppHtml    = opp.map(_opportunityCard).join('');
  const csHtml     = cs.map(_caseStudyCard).join('');

  // ── Which agents ran today ────────────────────────────────────────────────
  const activeAgents = [];
  if (todayPillar > 0 || todayBlogs > 0) activeAgents.push({ name: 'Agent 01 — Market Radar', color: '#ff6a3d', count: `${todayPillar} pillar + ${todayBlogs} blog` });
  if (todayInd > 0)                       activeAgents.push({ name: 'Agent 05 — Industry Pages', color: '#3fb950', count: `${todayInd} page${todayInd !== 1 ? 's' : ''}` });
  if (todayCS > 0)                        activeAgents.push({ name: 'Agent 06 — Case Studies', color: '#0097a7', count: `${todayCS} case stud${todayCS !== 1 ? 'ies' : 'y'}` });
  if (intel && intel.isToday)             activeAgents.push({ name: 'Competitor Intel Monitor', color: '#f57c00', count: `${intel.newsCount || 0} news · ${intel.trendsCount || 0} trends` });
  if (todayOpps > 0)                      activeAgents.push({ name: 'Opportunity Scanner', color: '#9c27b0', count: `${todayOpps} gap${todayOpps !== 1 ? 's' : ''} found` });

  const todayAgentBadges = activeAgents.length > 0
    ? activeAgents.map(a => `<span style="display:inline-block;background:${a.color}18;border:1px solid ${a.color}55;color:${a.color};font-size:11px;font-weight:700;padding:4px 12px;border-radius:20px;margin:3px 4px;">${_esc(a.name)} &mdash; ${_esc(a.count)}</span>`).join('')
    : `<span style="font-size:12px;color:#aaa;">No agents ran today.</span>`;

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

  <!-- STATS BAR -->
  <tr>
    <td style="background:#fafafa;border-bottom:1px solid #eee;padding:0;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td align="center" style="padding:14px 6px;border-right:1px solid #eee;">
            <div style="font-size:24px;font-weight:800;color:#ff6a3d;line-height:1;">${todayPillar}</div>
            <div style="font-size:9px;color:#999;text-transform:uppercase;letter-spacing:1px;margin-top:3px;">Pillar</div>
          </td>
          <td align="center" style="padding:14px 6px;border-right:1px solid #eee;">
            <div style="font-size:24px;font-weight:800;color:#58a6ff;line-height:1;">${todayBlogs}</div>
            <div style="font-size:9px;color:#999;text-transform:uppercase;letter-spacing:1px;margin-top:3px;">Blogs</div>
          </td>
          <td align="center" style="padding:14px 6px;border-right:1px solid #eee;">
            <div style="font-size:24px;font-weight:800;color:#3fb950;line-height:1;">${todayInd}</div>
            <div style="font-size:9px;color:#999;text-transform:uppercase;letter-spacing:1px;margin-top:3px;">Industry</div>
          </td>
          <td align="center" style="padding:14px 6px;border-right:1px solid #eee;">
            <div style="font-size:24px;font-weight:800;color:#0097a7;line-height:1;">${todayCS}</div>
            <div style="font-size:9px;color:#999;text-transform:uppercase;letter-spacing:1px;margin-top:3px;">Case Studies</div>
          </td>
          <td align="center" style="padding:14px 6px;border-right:1px solid #eee;">
            <div style="font-size:24px;font-weight:800;color:#9c27b0;line-height:1;">${todayOpps}</div>
            <div style="font-size:9px;color:#999;text-transform:uppercase;letter-spacing:1px;margin-top:3px;">Gaps Found</div>
          </td>
          <td align="center" style="padding:14px 6px;">
            <div style="font-size:24px;font-weight:800;color:#a371f7;line-height:1;">${total}</div>
            <div style="font-size:9px;color:#999;text-transform:uppercase;letter-spacing:1px;margin-top:3px;">Total</div>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- BODY -->
  <tr><td style="padding:28px 32px;">

    <!-- PIPELINE STATUS ──────────────────────────────────────────────────────── -->
    <div style="background:#f8f9fa;border:1px solid #e8e8e8;border-radius:10px;padding:14px 18px;margin-bottom:20px;">
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:#999;margin-bottom:10px;">Pipeline Status</div>
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td style="padding:3px 0;font-size:12px;color:#555;width:50%;">
            <span style="color:${radarStatus === 'triggered' ? '#2e7d32' : radarStatus === 'failed' ? '#c62828' : '#888'};font-weight:700;margin-right:6px;">${radarStatus === 'triggered' ? '&#10003;' : radarStatus === 'failed' ? '&#10007;' : '&#8212;'}</span>
            Market Radar &mdash; ${radarStatus === 'triggered' ? 'Triggered successfully' : radarStatus === 'failed' ? 'Trigger failed' : 'No token configured'}
          </td>
          <td style="padding:3px 0;font-size:12px;color:#555;width:50%;">
            <span style="color:#888;margin-right:6px;">&#9200;</span>
            ${triggerTime ? `Triggered at ${triggerTime} IST` : 'Time unavailable'}
          </td>
        </tr>
        <tr>
          <td style="padding:3px 0;font-size:12px;color:#555;">
            <span style="color:#1a73e8;font-weight:700;margin-right:6px;">&#9654;</span>
            GitHub Actions running &mdash; ~10 min to complete
          </td>
          <td style="padding:3px 0;font-size:12px;color:#555;">
            <span style="color:#888;margin-right:6px;">&#128197;</span>
            Next report: Tomorrow at 6:00 PM IST
          </td>
        </tr>
      </table>
      ${commits.length > 0 ? `
      <div style="border-top:1px solid #eee;margin-top:10px;padding-top:10px;">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:#bbb;margin-bottom:8px;">Today's System Improvements</div>
        ${commits.map(c => {
          const type = c.message.startsWith('feat') ? { color:'#1a73e8', label:'FEATURE' }
                     : c.message.startsWith('fix')  ? { color:'#e53935', label:'FIX' }
                     : c.message.startsWith('docs') ? { color:'#fb8c00', label:'DOCS' }
                     : { color:'#888', label:'UPDATE' };
          const cleanMsg = c.message.replace(/^(feat|fix|docs|chore|refactor|test)(\([^)]+\))?:\s*/i, '');
          return `<div style="display:flex;align-items:flex-start;padding:4px 0;border-bottom:1px solid #f5f5f5;">
            <span style="display:inline-block;background:${type.color};color:#fff;font-size:9px;font-weight:700;padding:1px 5px;border-radius:3px;margin-right:7px;margin-top:1px;white-space:nowrap;">${type.label}</span>
            <span style="font-size:11px;color:#333;flex:1;">${_esc(cleanMsg)}</span>
            <a href="${c.url}" style="font-size:10px;color:#bbb;text-decoration:none;margin-left:8px;white-space:nowrap;">${c.sha}</a>
          </div>`;
        }).join('')}
      </div>` : ''}
    </div>

    <!-- TODAY'S 3 CONTENT TOPICS ────────────────────────────────────────────── -->
    ${topics ? `
    <div style="background:#f0f7ff;border:1px solid #c8dff5;border-radius:10px;padding:14px 18px;margin-bottom:20px;">
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:#1a73e8;margin-bottom:10px;">💡 Today's Content Topics — from Daily Intel Scan</div>
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td width="33%" style="padding:4px 8px 4px 0;vertical-align:top;">
            <div style="font-size:10px;font-weight:700;color:#1a73e8;text-transform:uppercase;letter-spacing:1px;margin-bottom:3px;">🏭 Industry Page</div>
            <div style="font-size:12px;font-weight:600;color:#1d3557;margin-bottom:2px;">${_esc(topics.industryTopic || '—')}</div>
            <div style="font-size:10px;color:#888;">${_esc(topics.industryIndustry || '')}</div>
            <div style="font-size:10px;color:#aaa;margin-top:2px;font-style:italic;">${_esc(topics.industryWhy || '')}</div>
          </td>
          <td width="33%" style="padding:4px 8px;vertical-align:top;border-left:1px solid #dde8f5;">
            <div style="font-size:10px;font-weight:700;color:#1a73e8;text-transform:uppercase;letter-spacing:1px;margin-bottom:3px;">📋 Case Study</div>
            <div style="font-size:12px;font-weight:600;color:#1d3557;margin-bottom:2px;">${_esc(topics.csDetection || '—')}</div>
            <div style="font-size:10px;color:#888;">${_esc((topics.csType || '') + ' · ' + (topics.csLocation || ''))}</div>
            <div style="font-size:10px;color:#aaa;margin-top:2px;font-style:italic;">${_esc(topics.csWhy || '')}</div>
          </td>
          <td width="33%" style="padding:4px 0 4px 8px;vertical-align:top;border-left:1px solid #dde8f5;">
            <div style="font-size:10px;font-weight:700;color:#1a73e8;text-transform:uppercase;letter-spacing:1px;margin-bottom:3px;">🎯 Video Analytics</div>
            <div style="font-size:12px;font-weight:600;color:#1d3557;margin-bottom:2px;">${_esc(topics.vaDetection || '—')}</div>
            <div style="font-size:10px;color:#aaa;margin-top:2px;font-style:italic;">${_esc(topics.vaWhy || '')}</div>
          </td>
        </tr>
      </table>
    </div>` : ''}

    <!-- ══════════════════════════════════════════════════════
         SECTION 1 — HAMARE AGENTS
         ══════════════════════════════════════════════════════ -->
    <div style="margin-bottom:28px;">
      <div style="font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:2.5px;color:#aaa;margin-bottom:14px;padding-bottom:6px;border-bottom:2px solid #f0f0f0;">
        01 &mdash; Our Agents (viAct Content System)
      </div>
      <table width="100%" cellpadding="0" cellspacing="4">
        <tr>
          <td width="50%" style="padding:4px 4px 4px 0;vertical-align:top;">
            <div style="background:#fff8f5;border:1px solid #ffe0d0;border-radius:8px;padding:12px 14px;">
              <div style="font-size:11px;font-weight:800;color:#ff6a3d;margin-bottom:4px;">🔍 Agent 01 — Market Radar</div>
              <div style="font-size:11px;color:#666;line-height:1.5;">Scans competitor websites, identifies content gaps, and generates pillar pages &amp; blog posts — keeping viAct ahead of competitors every day.</div>
            </div>
          </td>
          <td width="50%" style="padding:4px 0 4px 4px;vertical-align:top;">
            <div style="background:#f0fff4;border:1px solid #c3e6c3;border-radius:8px;padding:12px 14px;">
              <div style="font-size:11px;font-weight:800;color:#3fb950;margin-bottom:4px;">🏭 Agent 05 — Industry Pages</div>
              <div style="font-size:11px;color:#666;line-height:1.5;">Builds full landing pages for any industry — hero section, use cases, metrics, testimonials, FAQs, SEO copy, 11 image prompts, and schema markup.</div>
            </div>
          </td>
        </tr>
        <tr>
          <td width="50%" style="padding:4px 4px 4px 0;vertical-align:top;">
            <div style="background:#e0f7fa;border:1px solid #b2ebf2;border-radius:8px;padding:12px 14px;">
              <div style="font-size:11px;font-weight:800;color:#0097a7;margin-bottom:4px;">📋 Agent 06 — Case Studies</div>
              <div style="font-size:11px;color:#666;line-height:1.5;">Input a company name, industry, and location — generates 62 CMS-ready fields including hero, challenge, solution, impact, testimonials, SEO, and 5 image prompts for Wix.</div>
            </div>
          </td>
          <td width="50%" style="padding:4px 0 4px 4px;vertical-align:top;">
            <div style="background:#fff8e1;border:1px solid #ffe082;border-radius:8px;padding:12px 14px;">
              <div style="font-size:11px;font-weight:800;color:#f57c00;margin-bottom:4px;">📡 Competitor Intel Monitor</div>
              <div style="font-size:11px;color:#666;line-height:1.5;">Monitors 7 competitor websites and news daily. Tracks industry trends and surfaces AI-generated marketing opportunities for the viAct team.</div>
            </div>
          </td>
        </tr>
      </table>
    </div>

    <!-- ══════════════════════════════════════════════════════
         SECTION 2 — AAJ KIS AGENT PAR KAAM HUA
         ══════════════════════════════════════════════════════ -->
    <div style="margin-bottom:28px;">
      <div style="font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:2.5px;color:#aaa;margin-bottom:14px;padding-bottom:6px;border-bottom:2px solid #f0f0f0;">
        02 &mdash; Agents Active Today
      </div>
      ${activeAgents.length > 0
        ? `<div style="padding:12px 16px;background:#f8f9fa;border-radius:8px;">${todayAgentBadges}</div>`
        : `<div style="background:#fff8e1;border:1px solid #ffe082;border-radius:8px;padding:12px 16px;font-size:12px;color:#795548;text-align:center;">No agents ran today. GitHub Actions runs automatically at 9:30 AM IST.</div>`
      }
    </div>

    <!-- ══════════════════════════════════════════════════════
         SECTION 3 — AGENT OUTPUTS
         ══════════════════════════════════════════════════════ -->
    <div style="margin-bottom:28px;">
      <div style="font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:2.5px;color:#aaa;margin-bottom:14px;padding-bottom:6px;border-bottom:2px solid #f0f0f0;">
        03 &mdash; Agent Outputs (Last ${SCAN_DAYS} Days)
      </div>

      <!-- Agent 01 Output: Pillar + Blog -->
      ${(recentPillar > 0 || recentBlogs > 0) ? `
      <div style="margin-bottom:20px;">
        <div style="font-size:11px;font-weight:700;color:#ff6a3d;margin-bottom:10px;padding:6px 10px;background:#fff8f5;border-radius:6px;border-left:3px solid #ff6a3d;">
          🔍 Agent 01 — Market Radar Output &mdash; ${recentPillar} Pillar + ${recentBlogs} Blog
        </div>
        ${recentPillar > 0 ? pillarHtml : ''}
        ${recentBlogs > 0 ? blogHtml : ''}
      </div>` : ''}

      <!-- Agent 05 Output: Industry Pages -->
      ${ind.length > 0 ? `
      <div style="margin-bottom:20px;">
        <div style="font-size:11px;font-weight:700;color:#3fb950;margin-bottom:10px;padding:6px 10px;background:#f0fff4;border-radius:6px;border-left:3px solid #3fb950;">
          🏭 Agent 05 — Industry Pages Output &mdash; ${ind.length} Page${ind.length !== 1 ? 's' : ''} in Sheet
        </div>
        ${indHtml}
      </div>` : ''}

      <!-- Agent 06 Output: Case Studies -->
      ${cs.length > 0 ? `
      <div style="margin-bottom:20px;">
        <div style="font-size:11px;font-weight:700;color:#0097a7;margin-bottom:10px;padding:6px 10px;background:#e0f7fa;border-radius:6px;border-left:3px solid #0097a7;">
          📋 Agent 06 — Case Studies Output &mdash; ${cs.length} in Last ${SCAN_DAYS} Days
        </div>
        ${csHtml}
      </div>` : ''}

      <!-- Competitor Intel Output -->
      ${_marketIntelSection(intel)}

      <!-- Opportunity Scanner Output -->
      <div style="margin-bottom:20px;">
        <div style="font-size:11px;font-weight:700;color:#9c27b0;margin-bottom:10px;padding:6px 10px;background:#fdf3ff;border-radius:6px;border-left:3px solid #9c27b0;">
          🎯 Opportunity Scanner — ${todayOpps} New Gap${todayOpps !== 1 ? 's' : ''} Found Today
        </div>
        ${opp.length > 0 ? oppHtml : `<div style="background:#fdf3ff;border:1px solid #e1bee7;border-radius:8px;padding:12px 16px;text-align:center;font-size:12px;color:#9c27b0;">No new gaps identified today. All competitor topics are either covered or in the queue.</div>`}
      </div>

      ${(recentPillar + recentBlogs + ind.length + cs.length) === 0 && opp.length === 0 ? `
      <div style="background:#fff8e1;border:1px solid #ffe082;border-radius:8px;padding:16px;text-align:center;font-size:12px;color:#795548;">
        No output generated today. Agents will run again tomorrow.
      </div>` : ''}
    </div>

    <!-- ══════════════════════════════════════════════════════
         SECTION 4 — SHEET LINKS
         ══════════════════════════════════════════════════════ -->
    <div style="margin-bottom:28px;">
      <div style="font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:2.5px;color:#aaa;margin-bottom:14px;padding-bottom:6px;border-bottom:2px solid #f0f0f0;">
        04 &mdash; Sheet Links — All Outputs Available Here
      </div>
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td style="padding:4px 4px 4px 0;">
            <a href="${SHEET_URL}" style="display:block;background:#ff6a3d;color:#fff;text-decoration:none;padding:12px 16px;border-radius:8px;font-weight:700;font-size:12px;text-align:center;">
              📄 Webpage Content Sheet<br><span style="font-size:10px;font-weight:400;opacity:0.85;">Pillar Pages + Blog Posts</span>
            </a>
          </td>
          <td style="padding:4px 0 4px 4px;">
            <a href="${INDUSTRY_SHEET_URL}" style="display:block;background:#1a7a3a;color:#fff;text-decoration:none;padding:12px 16px;border-radius:8px;font-weight:700;font-size:12px;text-align:center;">
              🏭 Industry &amp; Case Study Sheet<br><span style="font-size:10px;font-weight:400;opacity:0.85;">Industry Pages + Case Studies + Competitor Intel</span>
            </a>
          </td>
        </tr>
      </table>
    </div>

    <!-- ══════════════════════════════════════════════════════
         SECTION 5 — PROGRESS MESSAGE
         ══════════════════════════════════════════════════════ -->
    <div style="background:linear-gradient(135deg,#0d1117 0%,#161b22 100%);border-radius:10px;padding:20px 24px;text-align:center;">
      <div style="font-size:18px;margin-bottom:8px;">🚀</div>
      <div style="font-size:14px;font-weight:700;color:#e6edf3;margin-bottom:6px;">
        The system is running — progress is being made.
      </div>
      <div style="font-size:12px;color:#8b949e;line-height:1.6;">
        Every day, a little more content, a little more SEO, a little more competitive edge.<br>
        viAct's content engine ran today — quietly, consistently, without interruption.
      </div>
      <div style="margin-top:12px;font-size:10px;color:#484f58;text-transform:uppercase;letter-spacing:1.5px;">
        viAct Content Agent &middot; Auto-sent daily at 6:00 PM IST
      </div>
    </div>

    <!-- Build Update Banner (shown on build date only) -->
    ${_buildUpdateBanner(dateLabel)}

  </td></tr>

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
function _buildPlainText(web, ind, cs, dateLabel, radarStatus, triggerTime) {
  const lines = [`viAct AI Daily Content Report — ${dateLabel}`, '='.repeat(50), ''];

  lines.push('PIPELINE STATUS');
  lines.push(`  Market Radar : ${radarStatus === 'triggered' ? 'Triggered at ' + triggerTime + ' IST' : radarStatus === 'failed' ? 'Trigger failed' : 'Skipped (no token)'}`);
  lines.push(`  GitHub Actions running (~10 min to complete)`);
  lines.push(`  Next report  : Tomorrow at 6:00 PM IST`);
  lines.push('');

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
  const commits   = _fetchRecentCommits();
  const webItems  = _scanWebpageContent(ss, today);
  const indItems  = _scanIndustryTabs(ss, today);
  const oppItems  = _scanOpportunities(today);
  const csItems   = _scanCaseStudies(today);
  const intelItem = _scanCompetitorIntel(today);
  const topics    = _scanDailyTopics(today);
  const todayPillar = webItems.pillar.filter(p => p.isToday).length;
  const todayBlogs  = webItems.blogs.filter(b => b.isToday).length;
  const todayInd    = indItems.filter(i => i.isToday).length;
  const todayOpps   = oppItems.length;
  const todayCS     = csItems.filter(c => c.isToday).length;
  const total       = todayPillar + todayBlogs + todayInd + todayCS;
  _writeReportToSheet(ss, today, webItems, indItems, csItems, total);
  const triggerTime = Utilities.formatDate(new Date(), TIMEZONE, 'hh:mm a');
  const subject  = `[TEST] viAct AI Daily Report — ${dateLabel}`;
  const htmlBody = _buildEmailHtml(webItems, indItems, oppItems, csItems, intelItem, dateLabel, todayPillar, todayBlogs, todayInd, todayOpps, todayCS, total, 'skipped', triggerTime, commits, topics);
  const plain    = _buildPlainText(webItems, indItems, csItems, dateLabel, 'skipped', triggerTime);
  const mailOptions = { htmlBody, name: 'viAct Content Agent' };
  if (CC.length) mailOptions.cc = CC.join(',');
  for (const to of RECIPIENTS) {
    GmailApp.sendEmail(to, subject, plain, mailOptions);
  }
  Logger.log('Test report sent (no Market Radar trigger).');
}

// ─── TEST: trigger Market Radar only ──────────────────────────────────────────
function testTriggerRadarOnly() {
  triggerMarketRadar();
}
