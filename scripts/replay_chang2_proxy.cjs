'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require(process.env.SONARNET_PLAYWRIGHT_PATH || 'playwright');

const root = path.resolve(__dirname, '..');
const bankBytes = fs.readFileSync(path.join(root, 'reports/final/chang2/study-cases.json'));
const bank = JSON.parse(bankBytes);
const cases = new Map(bank.map(c => [c.id, c]));
const profiles = [
  {name:'Nhạy', cutoff:1.2},
  {name:'Cân bằng', cutoff:1.8},
  {name:'Thận trọng', cutoff:2.4},
  {name:'Chọn lọc', cutoff:3.0},
].flatMap(({name, cutoff}) => [
  {name:name+' · AI nhẹ', cutoff, hintWeight:.65},
  {name:name+' · AI mạnh', cutoff, hintWeight:1.45},
]);

function observations({speed_kn, east_m, north_m}) {
  const n = speed_kn.length;
  const mean = speed_kn.reduce((a,b) => a+b, 0) / n;
  const sd = Math.sqrt(speed_kn.reduce((a,b) => a+(b-mean)**2, 0) / n);
  const distance = east_m.slice(1).reduce((a,x,i) =>
    a + Math.hypot(x-east_m[i], north_m[i+1]-north_m[i]), 0);
  const direct = Math.hypot(east_m.at(-1)-east_m[0], north_m.at(-1)-north_m[0]);
  return Number(mean>=1.8 && mean<=6.4) + Number(mean>=2.5 && mean<=5.6)
    + Number(sd>=.65) + Number(distance>0 && direct/distance<.80)
    - Number(mean<1.0 || mean>8.0);
}

function decide(observed, hint, profile) {
  const score = observations(observed) + (hint === null ? 0 : (hint ? 1 : -1)*profile.hintWeight);
  const delta = score - profile.cutoff;
  if (Math.abs(delta)<.20) return 'insufficient';
  return delta>0 ? 'priority' : 'not_priority';
}

async function session(browser, profile, index, layout) {
  const code = 'R'+(810+index*4+layout);
  const context = await browser.newContext({acceptDownloads:true, viewport:{width:1100,height:840}});
  try {
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(String(error)));
    await page.goto(pathToFileURL(path.join(root, 'web/chang2/study.html')).href);
    await page.locator('#reviewer').fill(code);
    await page.locator('#role').selectOption('other');
    await page.locator('#consent').check();
    await page.getByRole('button', {name:'Bắt đầu lượt 1'}).click();
    const expected = new Map();
    for (let block=0; block<2; block++) {
      if (block) await page.locator('#continue').click();
      for (let i=0; i<8; i++) {
        const id = (await page.locator('#case-title').textContent()).slice(3);
        const {speed_kn, east_m, north_m} = cases.get(id);
        const hint = await page.locator('#hint').isVisible()
          ? (await page.locator('#hint').textContent()).startsWith('Gợi ý mô hình: ưu tiên rà')
          : null;
        const decision = decide({speed_kn, east_m, north_m}, hint, profile);
        expected.set(id, {decision, condition:hint === null ? 'control' : 'ai'});
        await page.locator('[data-answer="'+decision+'"]').click();
      }
    }
    const [download] = await Promise.all([
      page.waitForEvent('download'), page.locator('#download').click(),
    ]);
    const data = JSON.parse(fs.readFileSync(await download.path(), 'utf8'));
    await download.delete();
    assert.equal(data.bank_sha256, crypto.createHash('sha256').update(bankBytes).digest('hex'));
    assert.equal(data.responses.length, 16);
    assert.equal(expected.size, 16);
    for (const row of data.responses) {
      assert.deepEqual({decision:row.decision, condition:row.condition}, expected.get(row.case_id));
    }
    assert.deepEqual(errors, []);
    return {profile:index, layout:data.layout, responses:data.responses};
  } finally {
    await context.close();
  }
}

function score(rows) {
  const counts = {decisions:rows.length, positive:0, missed:0, false_flags:0, insufficient:0};
  for (const row of rows) {
    const priority = cases.get(row.case_id).priority, flagged = row.decision==='priority';
    counts.positive += Number(priority);
    counts.missed += Number(priority && !flagged);
    counts.false_flags += Number(!priority && flagged);
    counts.insufficient += Number(row.decision==='insufficient');
  }
  return counts;
}

function pairedPolicy(runs, index) {
  const rows = runs.filter(r => r.profile===index).flatMap(r => r.responses);
  const outputs = {};
  for (const condition of ['control','ai']) {
    const unique = new Map();
    for (const row of rows.filter(r => r.condition===condition)) {
      if (unique.has(row.case_id)) assert.equal(unique.get(row.case_id).decision, row.decision);
      unique.set(row.case_id, row);
    }
    assert.equal(unique.size, 16);
    outputs[condition] = score([...unique.values()]);
  }
  return {...profiles[index], ...outputs};
}

async function main() {
  const chrome = process.env.SONARNET_CHROME;
  const browser = await chromium.launch(chrome ? {executablePath:chrome} : {});
  try {
    const jobs = profiles.flatMap((profile, index) =>
      Array.from({length:4}, (_, layout) => ({profile, index, layout})));
    const runs = [];
    for (let i=0; i<jobs.length; i+=4) {
      runs.push(...await Promise.all(jobs.slice(i,i+4).map(
        job => session(browser, job.profile, job.index, job.layout))));
    }
    const all = runs.flatMap(r => r.responses);
    const policies = profiles.map((_, i) => pairedPolicy(runs, i));
    const result = {
      evidence_type:'browser_simulation_only', human_survey_responses:0,
      sessions:runs.length, browser_decisions:all.length, unique_cases:cases.size,
      chrome_version:browser.version(),
      browser_click_time_ms:{unit:'automation telemetry only', ...Object.fromEntries(
        ['control','ai'].map(condition => {
          const sorted=all.filter(r=>r.condition===condition).map(r=>r.time_ms).sort((a,b)=>a-b);
          return [condition, {median_ms:(sorted[127]+sorted[128])/2, min_ms:sorted[0], max_ms:sorted.at(-1)}];
        }))},
      policies,
      browser_runs:runs.map(({profile, layout, responses}) => ({
        profile, layout,
        counts:Object.fromEntries(['control','ai'].map(c=>[c,score(responses.filter(r=>r.condition===c))])),
      })),
    };
    const out = path.join(root, 'reports/final/chang2/proxy-study.json');
    fs.writeFileSync(out, JSON.stringify(result,null,2)+'\n');
    console.log(result.sessions+' sessions; '+result.browser_decisions+' decisions');
    console.table(policies.map(p=>({rule:p.name,before:p.control.missed,after:p.ai.missed,
      flags_before:p.control.false_flags,flags_after:p.ai.false_flags})));
  } finally {
    await browser.close();
  }
}

main().catch(error => {console.error(error); process.exitCode=1;});
