const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
async function main(){
 const out=process.env.E2E_OUTPUT_DIR,data=JSON.parse(await fs.readFile(path.join(out,'fixture-context.json'),'utf8'));
 const before=await Promise.all(data.files.map(p=>fs.readFile(p)));
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1280,height:900}}),errors=[];
 page.setDefaultTimeout(15000);page.on('pageerror',error=>errors.push(String(error)));
 const waitImages=()=>page.waitForFunction(()=>Array.from(document.querySelectorAll('.plot-card img')).length>0&&Array.from(document.querySelectorAll('.plot-card img')).every(el=>el.complete&&el.naturalWidth>0));
 try{
  await page.goto('file://'+data.grouped);
  await page.getByRole('heading',{name:'组库指标与分组比较 — 箱线图结果',exact:true}).waitFor();
  assert.equal(await page.locator('.stat-item').filter({has:page.getByText('分类字段',{exact:true})}).locator('span').innerText(),'类别, 批次');
  assert.equal(await page.locator('.plot-card:visible').count(),1);
  const pairs=await page.locator('.pvalue-list span').allTextContents();
  assert(pairs.some(text=>text.startsWith('01 对比 1 p=')));assert.equal(pairs.length,3);
  await waitImages();await page.screenshot({path:path.join(out,'exports-grouped-desktop.png'),fullPage:true});
  await page.goto('file://'+data.ungrouped);
  assert.equal(await page.getByLabel('指标字段',{exact:true}).inputValue(),'TRA_Shannon');
  assert.equal(await page.locator('.plot-card:visible').count(),1);
  assert.equal(await page.locator('.plot-card[data-sig="unknown"]').count(),1);
  assert.equal(await page.locator('.plot-head em').count(),0);
  assert(await page.getByRole('button',{name:'仅显示显著',exact:true}).isHidden());
  assert(await page.getByLabel('分类字段',{exact:true}).isHidden());
  assert(await page.locator('#modeSelect option[value="summary"]').isDisabled());
  assert.equal(await page.locator('.stat-item').filter({has:page.getByText('分类字段',{exact:true})}).locator('span').innerText(),'未分组');
  assert.equal(await page.locator('.stat-item').filter({has:page.getByText('p 值阈值',{exact:true})}).locator('span').innerText(),'不适用');
  assert.match(await page.locator('#counter').innerText(),/未进行组间检验/);
  await waitImages();await page.screenshot({path:path.join(out,'exports-ungrouped-desktop.png'),fullPage:true});
  await page.getByLabel('指标字段',{exact:true}).focus();await page.keyboard.press('ArrowDown');await page.keyboard.press('Tab');
  assert.equal(await page.getByLabel('指标字段',{exact:true}).inputValue(),'TRB_Shannon');
  assert.equal(await page.locator('.plot-head strong').innerText(),'TRB_Shannon');
  await waitImages();
  assert.match(await page.locator('.plot-card img').getAttribute('src'),/ungrouped\/TRB_Shannon\.png$/);
  for(const width of [390,320]){
   await page.setViewportSize({width,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   await page.screenshot({path:path.join(out,'exports-ungrouped-'+width+'px.png'),fullPage:true});
  }
  await page.reload();assert.equal(await page.locator('.plot-card:visible').count(),1);await waitImages();
  for(let i=0;i<data.files.length;i++)assert.deepEqual(await fs.readFile(data.files[i]),before[i]);
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(out,'browser-results.json'),JSON.stringify({
   passed:true,groupedJob:data.groupedJob,ungroupedJob:data.ungroupedJob,
   exactAggregatePvalue:data.originalPvalue,rawGroups:data.groups,originalSampleHeader:'Sample',
   ungroupedPlotsVisible:true,inapplicableControlsHidden:true,filesUnchanged:true,
   viewports:[1280,390,320],pageErrors:errors,
  },null,2));
  console.log('PASS: grouped comparison labels, actual ungrouped plots, no invented significance, keyboard metric selection, mobile layout and unchanged exports.');
 }finally{await browser.close();}
}
main().catch(error=>{console.error(error);process.exit(1);});
