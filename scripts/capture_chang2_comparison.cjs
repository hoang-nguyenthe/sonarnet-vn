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
      if(width===1160 && !process.argv[2]){
        await picker.selectOption('Q16');
        await pair.screenshot({path:path.join(web,'review-comparison.png'),animations:'disabled'});
      }
      const ids=await picker.locator('option').evaluateAll(options=>options.map(o=>o.value));
      assert.equal(ids.length,16);
      for(const id of ids){
        await picker.selectOption(id);
        assert.equal(await a.locator('[data-case-number]').textContent(),'Ca '+id);
        assert.equal(await b.locator('[data-case-number]').textContent(),'Ca '+id);
        for(const select of ['[data-track]','[data-speed]','[data-observations]']){
          assert.equal(await a.locator(select).innerHTML(),await b.locator(select).innerHTML());
        }
        assert.equal(await a.locator('[data-hint]').isVisible(),false);
        assert.equal(await b.locator('[data-hint]').isVisible(),true);
        await a.getByRole('button',{name:'Chưa đủ dữ liệu'}).click();
        await b.getByRole('button',{name:'Ưu tiên rà',exact:true}).click();
        assert.match(await a.locator('[data-feedback]').textContent(),/Chưa đủ dữ liệu/);
        assert.match(await b.locator('[data-feedback]').textContent(),/Ưu tiên rà/);
        assert.equal(await page.locator('#case-rules tr').count(),8);
        assert.match(await page.locator('#case-metrics').textContent(),/16 lượt/);
      }
      const filter=page.getByLabel('Lọc theo tác động');
      for(const [mode,n] of [['all',16],['changed',6],['conflict',3],['stable',10]]){
        await filter.selectOption(mode);
        assert.equal(await page.locator('#all-case-rows tr').count(),n);
      }
      await filter.selectOption('all');
      await page.locator('#all-case-rows a').first().click();
      assert.equal(await picker.inputValue(),ids[0]);
      assert.equal(await a.locator('[data-case-number]').textContent(),'Ca '+ids[0]);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width);
      assert.deepEqual(errors,[]);
      await page.close();
    }
    console.log('Verified 16 cases, both conditions, filter counts, desktop and mobile.');
  }finally{
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
