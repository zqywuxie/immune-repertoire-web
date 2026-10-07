// Real generated report mounted at /artifacts/report-localization/viewer.html.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
async function main(){
 const output=process.env.E2E_OUTPUT_DIR;assert(output);
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
 const errors=[];
 try{
  const page=await browser.newPage({viewport:{width:1280,height:900}});
  page.on('pageerror',e=>errors.push(String(e)));
  await page.goto('file://'+path.join(output,'viewer.html'));
  await page.getByRole('heading',{name:'组库指标与分组比较 — 箱线图结果',exact:true}).waitFor();
  assert.equal(await page.getByLabel('图表类型',{exact:true}).inputValue(),'boxplot');
  assert.deepEqual(await page.getByLabel('图表类型',{exact:true}).locator('option').allTextContents(),['箱线图','汇总图']);
  assert((await page.locator('body').innerText()).includes('样本指标.csv'));
  assert(!(await page.locator('body').innerText()).includes('/tmp/'));
  await page.getByLabel('📊 指标字段',{exact:true}).selectOption('TRB_Shannon');
  await page.locator('#plotPanel img').waitFor();
  assert(await page.locator('#plotPanel img').evaluate(img=>img.complete&&img.naturalWidth>0));
  await page.getByRole('button',{name:'🔍 仅显示显著',exact:true}).click();
  assert(await page.locator('#sigToggle').evaluate(el=>el.classList.contains('is-active')));
  await page.screenshot({path:path.join(output,'boxplot-desktop.png'),fullPage:true});
  await page.getByLabel('图表类型',{exact:true}).selectOption('summary');
  assert(await page.getByLabel('汇总指标',{exact:true}).isVisible());
  assert(await page.getByLabel('汇总分组',{exact:true}).isVisible());
  assert(await page.getByLabel('📊 指标字段',{exact:true}).isHidden());
  await page.locator('#plotPanel img').waitFor();
  assert(await page.locator('#plotPanel img').evaluate(img=>img.complete&&img.naturalWidth>0));
  assert.match(await page.locator('#counter').textContent(),/个汇总分组/);
  assert(!/\b(View|Boxplots|Summary|Profile)\b/.test(await page.locator('body').innerText()));
  await page.screenshot({path:path.join(output,'summary-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Report mobile overflow');
  await page.screenshot({path:path.join(output,'summary-mobile.png'),fullPage:true});
  await page.getByLabel('图表类型',{exact:true}).selectOption('boxplot');
  assert(await page.getByLabel('📊 指标字段',{exact:true}).isVisible());
  assert(await page.getByLabel('汇总指标',{exact:true}).isHidden());
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(output,'browser-proof.json'),JSON.stringify({labels:'Chinese',boxplot_image:true,summary_image:true,significance_filter:true,viewport:390,errors},null,2));
  console.log('PASS: actual Chinese report, metric selection, significance filter, boxplot/summary switching, rendered images, mobile layout');
 }finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
