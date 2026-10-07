const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
async function main(){
 const out=process.env.E2E_OUTPUT_DIR,data=JSON.parse(await fs.readFile(path.join(out,'fixture-context.json'),'utf8'));
 const files=[data.metadata,data.source,data.table,data.stats],before=await Promise.all(files.map(p=>fs.readFile(p)));
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1280,height:900}}),errors=[];
 page.setDefaultTimeout(15000);page.on('pageerror',error=>errors.push(String(error)));
 try{
  await page.goto('file://'+data.viewer);
  await page.getByRole('heading',{name:'组库指标与分组比较 — 箱线图结果',exact:true}).waitFor();
  const grouping=page.locator('.stat-item').filter({has:page.getByText('分类字段',{exact:true})});
  assert.equal(await grouping.locator('span').innerText(),'类别');
  assert.equal(await page.locator('#classSelect').inputValue(),'类别');
  assert.equal(await page.locator('.plot-card:visible').count(),1);
  const pairs=await page.locator('.pvalue-list span').allTextContents();
  assert.equal(pairs.length,3);
  assert(pairs.some(p=>p.startsWith('01 对比 1 p=')));
  assert(pairs.some(p=>p.startsWith('02 对比 01 p=')));
  assert(pairs.some(p=>p.startsWith('02 对比 1 p=')));
  await page.waitForFunction(()=>Array.from(document.querySelectorAll('.plot-card img')).every(el=>el.complete&&el.naturalWidth>0));
  await page.getByRole('button',{name:'仅显示显著',exact:true}).focus();
  await page.keyboard.press('Enter');
  assert.equal(await page.locator('#sigToggle').getAttribute('aria-pressed'),'true');
  assert.equal(await page.locator('.plot-card:visible').count(),1);
  await page.keyboard.press('Enter');
  assert.equal(await page.locator('#sigToggle').getAttribute('aria-pressed'),'false');
  await page.screenshot({path:path.join(out,'groups-desktop.png'),fullPage:true});
  await page.locator('#modeSelect').focus();await page.keyboard.press('ArrowDown');await page.keyboard.press('Tab');
  assert.equal(await page.locator('#modeSelect').inputValue(),'summary');
  assert.equal(await page.locator('#summaryClassSelect').inputValue(),'类别');
  await page.waitForFunction(()=>Array.from(document.querySelectorAll('.plot-card img')).every(el=>el.complete&&el.naturalWidth>0));
  await page.screenshot({path:path.join(out,'groups-summary.png'),fullPage:true});
  await page.locator('#modeSelect').selectOption('boxplot');
  await page.reload();
  assert.equal(await grouping.locator('span').innerText(),'类别');
  for(const width of [390,320]){
   await page.setViewportSize({width,height:844});
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   await page.screenshot({path:path.join(out,'groups-'+width+'px.png'),fullPage:true});
  }
  for(let i=0;i<files.length;i++)assert.deepEqual(await fs.readFile(files[i]),before[i]);
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(out,'browser-results.json'),JSON.stringify({
   passed:true,job:data.job,originalGroups:data.expectedGroups,expectedPvalue:data.expectedPvalue,
   summaryField:'类别',rawFilesUnchanged:true,viewports:[1280,390,320],pageErrors:errors,
  },null,2));
  console.log('PASS: raw 01/1/02 pairs, actual classification summary, real plots, keyboard summary view, mobile layout and saved files unchanged.');
 }finally{await browser.close();}
}
main().catch(error=>{console.error(error);process.exit(1);});
