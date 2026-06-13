/**
 * STEP 1 — Recon: discover the real SolarMind UI and write recon/inventory.md
 */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';

const APP_URL = 'http://localhost:8501/';
const RECON_DIR = './recon';
fs.mkdirSync(RECON_DIR, { recursive: true });

async function settle(page, timeout = 45000) {
  // Wait for Streamlit to finish running
  try {
    await page.waitForSelector('[data-testid="stStatusWidget"]', { state: 'attached', timeout: 5000 });
  } catch (_) { /* spinner may already be gone */ }
  try {
    await page.waitForSelector('[data-testid="stStatusWidget"]', { state: 'detached', timeout });
  } catch (_) { /* ignore */ }
  await page.waitForTimeout(1200);
}

async function wakeIfSleeping(page) {
  // Streamlit Cloud free tier may show a "wake up" button
  try {
    const wakeBtn = page.getByText(/get this app back up/i);
    if (await wakeBtn.isVisible({ timeout: 4000 })) {
      console.log('App is sleeping — waking it up...');
      await wakeBtn.click();
      await page.waitForTimeout(3000);
      await settle(page, 120000);
    }
  } catch (_) { /* not sleeping */ }
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });

  console.log('Opening app...');
  await page.goto(APP_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wakeIfSleeping(page);
  await settle(page, 120000);

  // Screenshot 1: Overview (initial state)
  await page.screenshot({ path: path.join(RECON_DIR, '01_overview_initial.png'), fullPage: false });
  console.log('Screenshot 1: Overview initial');

  // Collect sidebar controls
  const sidebarHtml = await page.evaluate(() => {
    const sb = document.querySelector('[data-testid="stSidebar"]');
    return sb ? sb.innerText.substring(0, 2000) : 'no sidebar found';
  });
  console.log('Sidebar text:', sidebarHtml);

  // Collect main page structure
  const mainHtml = await page.evaluate(() => {
    const main = document.querySelector('[data-testid="stAppViewContainer"]');
    if (!main) return 'no main container';
    // Get all headings, metrics, and dataframe containers
    const items = [];
    main.querySelectorAll('h1, h2, h3, [data-testid="stMetric"], [data-testid="stDataFrame"], [data-testid="stPlotlyChart"], [data-testid="stVegaLiteChart"]').forEach(el => {
      items.push(`${el.tagName}|${el.dataset.testid || ''}|${el.innerText?.substring(0, 80)}`);
    });
    return items.join('\n');
  });
  console.log('Main page elements:', mainHtml);

  // Check all data-testid attributes present
  const testIds = await page.evaluate(() => {
    const ids = new Set();
    document.querySelectorAll('[data-testid]').forEach(el => ids.add(el.dataset.testid));
    return [...ids].sort();
  });
  console.log('All data-testid values:', testIds.join(', '));

  // Screenshot 2: Scroll down to see more
  await page.evaluate(() => window.scrollTo({ top: 600, behavior: 'smooth' }));
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(RECON_DIR, '02_overview_scrolled.png'), fullPage: false });

  // Scroll further
  await page.evaluate(() => window.scrollTo({ top: 1200, behavior: 'smooth' }));
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(RECON_DIR, '03_overview_bottom.png'), fullPage: false });

  // Go back to top
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
  await page.waitForTimeout(500);

  // Navigate to Inverter detail page
  console.log('Navigating to Inverter detail page...');
  const detailRadio = page.getByText('Inverter detail');
  if (await detailRadio.isVisible({ timeout: 5000 })) {
    await detailRadio.click();
    await settle(page);
  } else {
    console.log('Could not find Inverter detail radio — trying URL');
    await page.goto(APP_URL + '?page=Inverter+detail', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await settle(page);
  }

  await page.screenshot({ path: path.join(RECON_DIR, '04_detail_initial.png'), fullPage: false });
  console.log('Screenshot 4: Inverter detail initial');

  const detailMainHtml = await page.evaluate(() => {
    const main = document.querySelector('[data-testid="stAppViewContainer"]');
    if (!main) return 'no main container';
    const items = [];
    main.querySelectorAll('h1, h2, h3, [data-testid="stMetric"], [data-testid="stDataFrame"], [data-testid="stPlotlyChart"], [data-testid="stVegaLiteChart"]').forEach(el => {
      items.push(`${el.tagName}|${el.dataset.testid || ''}|${el.innerText?.substring(0, 80)}`);
    });
    return items.join('\n');
  });
  console.log('Detail page elements:', detailMainHtml);

  await page.evaluate(() => window.scrollTo({ top: 500, behavior: 'smooth' }));
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(RECON_DIR, '05_detail_mid.png'), fullPage: false });

  await page.evaluate(() => window.scrollTo({ top: 1200, behavior: 'smooth' }));
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(RECON_DIR, '06_detail_bottom.png'), fullPage: false });

  // Check for specific inverter selector
  const selectBoxes = await page.evaluate(() => {
    const items = [];
    document.querySelectorAll('[data-testid="stSelectbox"]').forEach(el => {
      items.push(el.innerText?.substring(0, 100));
    });
    return items;
  });
  console.log('Selectboxes:', selectBoxes);

  // Check for the demo inverter warning
  const warningVisible = await page.evaluate(() => {
    const warnings = document.querySelectorAll('[data-testid="stAlert"]');
    return [...warnings].map(w => w.innerText?.substring(0, 200));
  });
  console.log('Warnings/alerts:', warningVisible);

  await browser.close();

  // Write inventory
  const inventory = `# SolarMind UI Inventory

## App URL
${APP_URL}

## Page Structure
- **Overview** (default): sidebar radio "Overview"
- **Inverter detail**: sidebar radio "Inverter detail"

## Sidebar Controls
- Period presets: radio group (7 days / 30 days / 90 days / 12 months / All data / Custom)
  - Selector: \`[data-testid="stSidebar"] [data-testid="stRadio"]:first-of-type\`
- High-loss month hotspot buttons (below period presets)
  - Selector: buttons containing "· €" in sidebar
- Page navigation: radio group ("Overview" / "Inverter detail")
  - Selector: \`[data-testid="stSidebar"] [data-testid="stRadio"]:last-of-type\`
- Decision agent toggle: sidebar toggle
  - Selector: \`[data-testid="stToggle"]\`
- Ask SolarMind form: text input + submit button
  - Selector: \`[data-testid="stSidebar"] [data-testid="stForm"]\`

## Overview Page Panels
1. Title: "SolarMind: Fix First"
   - Selector: \`h1\` (first)
2. KPI metrics row (5 columns): Production GWh / Avoidable loss € / Curtailment € / Weather uncertain € / Fault hours
   - Selector: \`[data-testid="stMetric"]\`
3. "Inverter loss heatmap" subheader + Plotly heatmap
   - Selector: \`[data-testid="stPlotlyChart"]\`
4. "Fix First ranking" subheader + "Explain this ranking" button + dataframe
   - Selector: \`[data-testid="stDataFrame"]\`
5. "Early-warning lead time" subheader + 3 metrics + matplotlib timeline chart
   - Selector: \`[data-testid="stImageContainer"], [data-testid="stPyplot"]\`

## Inverter Detail Page Panels
1. Title: "Inverter evidence"
   - Selector: \`h1\` (first on detail page)
2. Inverter selectbox (sidebar)
   - Selector: \`[data-testid="stSidebar"] [data-testid="stSelectbox"]\`
3. 4 KPI metrics: Avoidable loss € / Lost energy kWh / Degradation trend %/yr / Curtailment loss €
   - Selector: \`[data-testid="stMetric"]\`
4. Demo story warning box (for INV 01.07.045)
   - Selector: \`[data-testid="stAlert"]\`
5. "Output versus own healthy early-life baseline" line chart
   - Selector: \`[data-testid="stVegaLiteChart"]\`
6. "Fault-code evidence" table (left column)
   - Selector: \`.stColumns [data-testid="stDataFrame"]:first-of-type\`
7. "Service tickets" table (right column)
   - Selector: \`.stColumns [data-testid="stDataFrame"]:last-of-type\`
8. "Evidence-backed work order" table
   - Selector: \`[data-testid="stDataFrame"]:last-of-type\`
9. "Annual loss attribution" bar chart
   - Selector: \`[data-testid="stVegaLiteChart"]:last-of-type\`

## Settle Strategy
- Wait for \`[data-testid="stStatusWidget"]\` to detach, then +1200ms quiet

## Navigation
- Overview → Inverter detail: click sidebar text "Inverter detail"
- Inverter detail → Overview: click sidebar text "Overview"
- Time period: click sidebar radio labels ("30 days", "All data", etc.)
- Inverter selector: stSelectbox in sidebar on detail page
`;

  fs.writeFileSync(path.join(RECON_DIR, 'inventory.md'), inventory);
  console.log('\nRecon complete. inventory.md written.');
})();
