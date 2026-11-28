'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require(process.env.SONARNET_PLAYWRIGHT_PATH || 'playwright');

const root = path.resolve(__dirname, '..');
const bankPath = process.argv[2] || path.join(root,'reports/final/chang2/study-cases.json');
const bankBytes = fs.readFileSync(bankPath);
const bank = JSON.parse(bankBytes);
const bankHash = crypto.createHash('sha256').update(bankBytes).digest('hex');
const packCounts = ['A','B'].map(pack=>bank.filter(c=>c.pack===pack).length);
assert.equal(packCounts[0],packCounts[1]);
assert.equal(packCounts[0]+packCounts[1],bank.length);
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
    if (process.argv[2]) await page.addInitScript(benchmark=>{
      // Override the 16-case bank only in this private automation context.
      Object.defineProperty(window,'SONARNET_STUDY',{get:()=>benchmark,set:()=>{}});
    },{sha256:bankHash,cases:bank});
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
      for (let i=0; i<packCounts[0]; i++) {
        const {id, hint} = await page.evaluate(()=>{
          const field=document.getElementById('hint');
          const suggested=field.textContent.startsWith('Gợi ý mô hình: ưu tiên rà');
          return {id:document.getElementById('case-title').textContent.slice(3),
            hint:field.hidden ? null : suggested};
        });
        const {speed_kn, east_m, north_m} = cases.get(id);
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
    assert.equal(data.bank_sha256,bankHash);
    assert.equal(data.responses.length,bank.length);
    assert.equal(expected.size,bank.length);
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
  const outputs = {}, decisions = {};
  for (const condition of ['control','ai']) {
    const unique = new Map();
    for (const row of rows.filter(r => r.condition===condition)) {
      if (unique.has(row.case_id)) assert.equal(unique.get(row.case_id).decision, row.decision);
      unique.set(row.case_id, row);
    }
    assert.equal(unique.size,bank.length);
    outputs[condition] = score([...unique.values()]);
    decisions[condition] = unique;
  }
  const per_case = [...cases].map(([id,sample]) => ({
    id, priority:sample.priority, hint_priority:sample.hint_priority,
    control:decisions.control.get(id).decision, ai:decisions.ai.get(id).decision,
  }));
  return {...profiles[index], ...outputs, per_case};
}

function quantile(sorted,p) {
  const index=(sorted.length-1)*p, left=Math.floor(index);
  return sorted[left]+(sorted[Math.ceil(index)]-sorted[left])*(index-left);
}

function timing(values) {
  assert.ok(values.length);
  const sorted=[...values].sort((a,b)=>a-b);
  return {n:sorted.length, median_ms:quantile(sorted,.5), min_ms:sorted[0],
    max_ms:sorted.at(-1), p90_ms:quantile(sorted,.9)};
}

function pairedTimings(runs) {
  const groups=new Map();
  for (const run of runs) for (const r of run.responses) {
    const key=[run.profile,r.case_id,r.block].join('/');
    if (!groups.has(key)) groups.set(key,{profile:run.profile,id:r.case_id,block:r.block});
    const row=groups.get(key);
    assert.ok(!(r.condition in row));
    row[r.condition]=r.time_ms;
  }
  return [...groups.values()].map(row=>{
    assert.ok('control' in row && 'ai' in row);
    return {...row, delta_ms:row.ai-row.control};
  });
}

async function main() {
  const chrome = process.env.SONARNET_CHROME;
  const browser = await chromium.launch(chrome ? {executablePath:chrome} : {});
  try {
    const jobs = profiles.flatMap((profile, index) =>
      Array.from({length:4}, (_, layout) => ({profile, index, layout})));
    const runs = [];
    for (const job of jobs) {
      runs.push(await session(browser,job.profile,job.index,job.layout));
    }
    const all = runs.flatMap(r => r.responses);
    const policies = profiles.map((_, i) => pairedPolicy(runs, i));
    const pairs = pairedTimings(runs);
    function summarize(times) {
      return {control:timing(times.map(row=>row.control)), ai:timing(times.map(row=>row.ai)),
        delta:timing(times.map(row=>row.delta_ms)),
        faster_with_ai:times.filter(row=>row.delta_ms<0).length,
        tied:times.filter(row=>row.delta_ms===0).length,
        slower_with_ai:times.filter(row=>row.delta_ms>0).length};
    }
    assert.equal(pairs.length*2,all.length);
    const result = {
      evidence_type:'browser_simulation_only', human_survey_responses:0,
      sessions:runs.length, browser_decisions:all.length, unique_cases:cases.size,
      chrome_version:browser.version(), bank_sha256:bankHash,
      browser_click_time_ms:{unit:'automation telemetry only', ...summarize(pairs)},
      paired_case_times:[...cases.keys()].map(id=>({
        id, ...summarize(pairs.filter(p=>p.id===id))
      })),
      timing_pairs:pairs,
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
