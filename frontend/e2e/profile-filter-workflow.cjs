const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
async function main(){
 const out=process.env.E2E_OUTPUT_DIR,data=JSON.parse(await fs.readFile(path.join(out,'fixture-context.json'),'utf8'));
 const before=await Promise.all(data.files.map(p=>fs.readFile(p)));
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1280,height:900}}),errors=[];
 page.setDefaultTimeout(15000);page.on('pageerror',error=>errors.push(String(error)));
 const waitImages=()=>page.waitForFunction(()=>Array.from(document.querySelectorAll('.plot-card img')).length>0&&Array.from(document.querySelectorAll('.plot-card img')).every(el=>el.complete&&el.naturalWidth>0));
 const shot=name=>page.screenshot({path:path.join(out,name+'.png'),fullPage:true});
 const load=name=>page.goto('file://'+data[name]);
 const toggle=()=>page.getByRole('button',{name:'仅显示显著',exact:true});
 const clear=()=>page.getByRole('button',{name:'清除筛选',exact:true});
 const metric=()=>page.getByLabel('指标字段',{exact:true});
 const classification=()=>page.getByLabel('分类字段',{exact:true});
 try{
  await load('grouped');
  assert.equal(await metric().inputValue(),'TRA_Shannon');
  await classification().selectOption('批次');
  await toggle().focus();await page.keyboard.press('Enter');
  assert.equal(await page.locator('#sigToggle').getAttribute('aria-pressed'),'true');
  assert.equal(await classification().inputValue(),'批次');
  await metric().selectOption('TRB_Shannon');
  assert.equal(await page.locator('.plot-card:visible').count(),0);
  assert.equal(await page.locator('.plot-card[data-sig="0"]:visible').count(),0);
  assert.equal(await page.locator('#sigToggle').getAttribute('aria-pressed'),'true');
  assert(await classification().isDisabled());
  assert.equal(await classification().locator('option:checked').innerText(),'暂无匹配项');
  assert.equal(await classification().locator('option:not(:disabled)').count(),0);
  assert.match(await page.getByRole('status').innerText(),/当前显示 0 张图.*0 \/ 2/);
  assert(await page.getByText('当前筛选没有匹配图表，可清除筛选查看已有结果。',{exact:true}).isVisible());
  await shot('filters-empty-desktop');
  await page.reload();
  assert.equal(await metric().inputValue(),'TRB_Shannon');
  assert.equal(await page.locator('#sigToggle').getAttribute('aria-pressed'),'true');
  assert.equal(await page.locator('.plot-card:visible').count(),0);
  await clear().focus();await page.keyboard.press('Enter');
  assert.equal(await metric().inputValue(),'TRB_Shannon');
  assert.equal(await classification().inputValue(),'批次');
  assert(await classification().isEnabled());
  assert.equal(await page.locator('#sigToggle').getAttribute('aria-pressed'),'false');
  assert.equal(await page.locator('.plot-card[data-sig="0"]:visible').count(),1);
  assert(await clear().isDisabled());
  await waitImages();await shot('filters-clear-desktop');
  await page.reload();assert.equal(await classification().inputValue(),'批次');
  await metric().selectOption('TRA_Shannon');
  assert.equal(await classification().inputValue(),'批次');
  await toggle().click();assert.equal(await page.locator('.plot-card[data-sig="1"]:visible').count(),1);
  await classification().selectOption('类别');
  await metric().selectOption('TRB_Shannon');assert.equal(await page.locator('.plot-card:visible').count(),0);
  await page.getByLabel('图表类型',{exact:true}).selectOption('summary');
  assert(await toggle().isHidden());assert(await clear().isHidden());
  await page.getByLabel('汇总分组',{exact:true}).selectOption('批次');
  await waitImages();
  await page.reload();
  assert.equal(await page.getByLabel('图表类型',{exact:true}).inputValue(),'summary');
  assert.equal(await page.getByLabel('汇总分组',{exact:true}).inputValue(),'批次');
  assert.equal(await page.locator('.plot-card:visible').count(),1);
  await shot('filters-summary-restored');
  await page.getByLabel('图表类型',{exact:true}).selectOption('boxplot');
  assert.equal(await metric().inputValue(),'TRB_Shannon');
  assert.equal(await page.locator('#sigToggle').getAttribute('aria-pressed'),'true');
  assert.equal(await page.locator('.plot-card:visible').count(),0);
  for(const width of [390,320]){
   await page.setViewportSize({width,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   await shot('filters-empty-'+width+'px');
  }
  await clear().click();
  assert.equal(await classification().inputValue(),'类别');
  await waitImages();await shot('filters-clear-mobile');
  await page.evaluate(()=>sessionStorage.setItem('profile-report-filters:'+location.pathname,JSON.stringify({
   param:'不存在的指标',classification:'类别',significant:true,mode:'boxplot',
  })));
  await page.reload();
  assert.equal(await metric().inputValue(),'TRA_Shannon');
  assert.equal(await classification().inputValue(),'类别');
  assert.equal(await page.locator('#sigToggle').getAttribute('aria-pressed'),'false');
  await page.evaluate(()=>sessionStorage.setItem('profile-report-filters:'+location.pathname,JSON.stringify({
   param:'TRB_Shannon',classification:'不存在的分类',significant:true,mode:'summary',
  })));
  await page.reload();
  assert.equal(await metric().inputValue(),'TRA_Shannon');
  assert.equal(await page.getByLabel('图表类型',{exact:true}).inputValue(),'boxplot');
  assert.equal(await page.locator('#sigToggle').getAttribute('aria-pressed'),'false');
  await load('ungrouped');
  assert.equal(await metric().inputValue(),'TRA_Shannon');
  assert(await toggle().isHidden());assert(await clear().isHidden());
  await metric().selectOption('TRB_Shannon');
  await page.reload();assert.equal(await metric().inputValue(),'TRB_Shannon');
  assert.equal(await page.locator('.plot-card[data-sig="unknown"]:visible').count(),1);
  assert.equal(await page.locator('.plot-head em').count(),0);
  await waitImages();
  await load('empty');
  assert(await page.getByText('所选条件下没有生成箱线图。',{exact:true}).isVisible());
  assert.equal(await page.getByRole('status').innerText(),'本次未生成箱线图。');
  assert.equal(await page.getByText('当前筛选没有匹配图表，可清除筛选查看已有结果。',{exact:true}).count(),0);
  const restricted=await browser.newContext({viewport:{width:390,height:844}});
  await restricted.addInitScript(()=>Object.defineProperty(window,'sessionStorage',{get(){throw new DOMException('Storage disabled','SecurityError');}}));
  const denied=await restricted.newPage();denied.on('pageerror',error=>errors.push(String(error)));
  await denied.goto('file://'+data.grouped);
  await denied.getByRole('button',{name:'仅显示显著',exact:true}).click();
  await denied.getByLabel('指标字段',{exact:true}).selectOption('TRB_Shannon');
  assert.equal(await denied.locator('.plot-card:visible').count(),0);
  await denied.getByRole('button',{name:'清除筛选',exact:true}).click();
  assert.equal(await denied.locator('.plot-card:visible').count(),1);
  await restricted.close();
  for(let i=0;i<data.files.length;i++)assert.deepEqual(await fs.readFile(data.files[i]),before[i]);
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(out,'browser-results.json'),JSON.stringify({
   passed:true,groupedJob:data.groupedJob,ungroupedJob:data.ungroupedJob,
   significancePersistsAcrossMetrics:true,zeroMatchesSurviveReload:true,
   currentClassAndMetricPreserved:true,summarySelectionRestored:true,
   clearWorksWithKeyboard:true,staleSelectionsFallBack:true,
   ungroupedSelectionRestored:true,emptyReportDistinct:true,disabledStorageWorks:true,
   rawFilesUnchanged:true,viewports:[1280,390,320],pageErrors:errors,
  },null,2));
  console.log('PASS: real positive/negative filters across metrics, zero-match/reload/clear, raw class selection, summary restore, stale state, empty report, disabled storage and mobile layout.');
 }finally{await browser.close();}
}
main().catch(error=>{console.error(error);process.exit(1);});
