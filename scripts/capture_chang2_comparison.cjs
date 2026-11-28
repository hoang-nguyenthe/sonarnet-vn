'use strict';

// Capture the published view for the report after verifying the paired task.
const assert = require('node:assert/strict');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require(process.env.SONARNET_PLAYWRIGHT_PATH || 'playwright');

const web=path.resolve(__dirname,'../web/chang2');
const source=process.argv[2] || pathToFileURL(path.join(web,'compare.html')).href;

(async()=>{
  const browser=await chromium.launch(process.env.SONARNET_CHROME
    ? {executablePath:process.env.SONARNET_CHROME}
    : {});
  try{
    for(const width of [1160,390]){
      const page=await browser.newPage({viewport:{width,height:900},deviceScaleFactor:2});
      const errors=[];
      page.on('pageerror',error=>errors.push(String(error)));
      await page.goto(source);
      const pair=page.locator('#compare-panels');
      const a=pair.locator('[data-mode=control]'), b=pair.locator('[data-mode=ai]');
      const picker=page.getByLabel('Tình huống minh họa');
      const ids=await picker.locator('option').evaluateAll(options=>options.map(o=>o.value));
      const isChallenge=new URL(source).searchParams.get('bo')==='thu-thach';
      assert.equal(ids.length,isChallenge?16:200);
      const defaultId=await picker.inputValue();
      if(width===1160 && !process.argv[2])
        await pair.screenshot({path:path.join(web,'review-comparison.png'),animations:'disabled'});
      const defects=await page.evaluate(ids=>{
        const picker=document.getElementById('demo-case');
        const a=document.querySelector('[data-mode=control]');
        const b=document.querySelector('[data-mode=ai]');
        const problems=[];
        for(const id of ids){
          picker.value=id;
          picker.dispatchEvent(new Event('change',{bubbles:true}));
          const identical=['[data-track]','[data-speed]','[data-observations]'].every(
            selector=>a.querySelector(selector).innerHTML===b.querySelector(selector).innerHTML);
          if(!identical || a.querySelector('[data-case-number]').textContent!=='Ca '+id
            || b.querySelector('[data-case-number]').textContent!=='Ca '+id
            || !a.querySelector('[data-hint]').hidden || b.querySelector('[data-hint]').hidden
            || document.querySelectorAll('#case-rules tr').length!==8)
            problems.push(id);
        }
        return problems;
      },ids);
      assert.deepEqual(defects,[]);
      for(const id of [ids[0],defaultId,ids.at(-1)]){
        await picker.selectOption(id);
        await a.getByRole('button',{name:'Chưa đủ dữ liệu'}).click();
        await b.getByRole('button',{name:'Ưu tiên rà',exact:true}).click();
        assert.match(await a.locator('[data-feedback]').textContent(),/Chưa đủ dữ liệu/);
        assert.match(await b.locator('[data-feedback]').textContent(),/Ưu tiên rà/);
        assert.match(await page.locator('#case-metrics').textContent(),/16 lượt/);
      }
      const totals=await page.evaluate(()=>{
        const data=location.search.includes('thu-thach')?window.SONARNET_CHALLENGE:window.SONARNET_COMPARISON;
        return {changed:data.cases.filter(c=>c.improved+c.worsened).length,
          conflict:data.cases.filter(c=>c.priority!==c.hint_priority).length};
      });
      const filter=page.getByLabel('Lọc theo tác động');
      for(const [mode,n] of [['all',ids.length],['changed',totals.changed],
        ['conflict',totals.conflict],['stable',ids.length-totals.changed]]){
        await filter.selectOption(mode);
        assert.equal(await page.locator('#all-case-rows tr').count(),Math.min(25,n));
      }
      await filter.selectOption('all');
      if(ids.length>25){
        await page.getByRole('button',{name:'Trang sau'}).click();
        assert.equal(await page.locator('#all-case-rows a').first().textContent(),ids[25]);
      }
      await page.getByLabel('Mã ca').fill(ids.at(-1));
      assert.equal(await page.locator('#all-case-rows tr').count(),1);
      await page.locator('#all-case-rows a').first().click();
      assert.equal(await picker.inputValue(),ids.at(-1));
      assert.equal(await a.locator('[data-case-number]').textContent(),'Ca '+ids.at(-1));
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width);
      assert.deepEqual(errors,[]);
      await page.close();
    }
    console.log('Verified every case, both conditions, filters, search, pagination, desktop and mobile.');
  }finally{
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
