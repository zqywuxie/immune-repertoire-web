// Real source/task APIs with isolated synthetic saved artifacts; no analysis submission.
const { chromium }=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
const base=process.env.E2E_BASE_URL,out=process.env.E2E_OUTPUT_DIR;
async function main(){
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
 const context=await browser.newContext({viewport:{width:1440,height:1000},timezoneId:'Asia/Shanghai'});
 const page=await context.newPage(),errors=[],reads=[],writes=[],inspections=[];
 page.setDefaultTimeout(20000);
 context.on('page',p=>p.on('pageerror',e=>errors.push(String(e))));
 page.on('pageerror',e=>errors.push(String(e)));
 page.on('request',r=>{
  const u=new URL(r.url());if(u.pathname.includes('/sources')||u.pathname.includes('pep-cache-candidates'))reads.push({path:u.pathname,project:u.searchParams.get('project_id'),dataset:u.searchParams.get('asset_set')});
  if(r.method()==='POST'&&u.pathname.endsWith('/inspect'))inspections.push({path:u.pathname,payload:r.postDataJSON()});
  if(!['GET','HEAD','OPTIONS'].includes(r.method())&&!u.pathname.endsWith('/inspect')&&!u.pathname.endsWith('/validate')&&!['/api/script-hub/read-table-preview','/api/script-hub/boxplot/group-values'].includes(u.pathname))writes.push({path:u.pathname,method:r.method()});
 });
 async function get(p){const r=await page.request.get(base+p);assert.equal(r.status(),200,p);return r.json();}
 const q='project_id=source-selection-project&asset_set=Set1';
 const differential=await get('/api/script-hub/go-kegg-enrichment/sources?'+q);
 const pathway=await get('/api/script-hub/immune-infiltration-pathway/sources?'+q);
 const pep=await get('/api/script-hub/pep-cache-candidates?'+q+'&cache_type=umapin');
 assert.equal(differential.candidates.filter(c=>c.status==='available').length,2);
 assert.equal(pathway.candidates.filter(c=>c.status==='available').length,2);
 const selectedPep=pep.candidates.find(c=>c.job_id==='共享来源-1'&&c.cache_type==='umapin_table');
 assert(selectedPep&&selectedPep.status==='available',JSON.stringify(pep));
 const tool=(id,artifact)=>base+'/analysis/tools/'+id+'?'+new URLSearchParams({project:'source-selection-project',asset_set:'Set1',...(artifact?{upstream_artifact:artifact}:{})});
 const output=()=>page.locator('label').filter({hasText:'输出名称'}).locator('input').first();
 const shot=async name=>{await page.screenshot({path:path.join(out,name+'.png')});};
 const mobile=async name=>{await page.setViewportSize({width:390,height:844});await page.locator('.source-selection').scrollIntoViewIfNeeded();await shot(name);const sizes=await page.evaluate(()=>({width:innerWidth,document:document.documentElement.scrollWidth}));assert(sizes.document<=sizes.width+1,JSON.stringify(sizes));await page.setViewportSize({width:1440,height:1000});};
 async function taskPopup(job,link){
  const before=page.url(),[popup]=await Promise.all([context.waitForEvent('page'),link.click()]);
  await popup.waitForLoadState('domcontentloaded');
  await popup.getByRole('heading',{name:job,exact:true}).waitFor();
  const u=new URL(popup.url());assert.equal(u.searchParams.get('job'),job);assert.equal(u.searchParams.get('project'),'source-selection-project');assert.equal(u.searchParams.get('asset_set'),'Set1');
  await popup.close();assert.equal(page.url(),before);
 }
 let failDeg=true;
 await page.route('**/api/script-hub/go-kegg-enrichment/sources?**',r=>{if(failDeg){failDeg=false;return r.abort('failed');}return r.continue();});
 try{
  await page.goto(tool('go-kegg','差异来源-1:deg'));
  await page.getByRole('button',{name:'重新读取差异来源',exact:true}).waitFor({timeout:60000});
  assert.equal(await page.getByRole('link',{name:'前往差异表达分析 ↗',exact:true}).count(),0);
  await page.getByRole('alert').filter({hasText:'网络连接中断，请重新读取。'}).waitFor();
  await page.getByRole('button',{name:'重新读取差异来源',exact:true}).focus();await page.keyboard.press('Enter');
  const degSelect=page.getByLabel('来源差异表达结果',{exact:true});
  await page.waitForFunction(()=>document.querySelector('select[aria-label="来源差异表达结果"]')?.value==='差异来源-1:deg');
  const opts=await degSelect.locator('option').allTextContents();assert(opts.some(t=>t.includes('差异来源-1')));assert(opts.some(t=>t.includes('差异来源-2')));
  assert.equal(await degSelect.locator('option[value="差异来源-3:deg"]').evaluate(el=>el.disabled),true);
  await page.getByText('比较方向：02 / 01',{exact:true}).waitFor();
  const sourceTime=await page.evaluate(utc=>new Date(utc+'Z').toLocaleString('zh-CN',{hour12:false,timeZoneName:'short'}),differential.candidates[0].created_at);
  await page.getByText('创建时间：'+sourceTime,{exact:true}).waitFor();
  await page.getByText(/对数倍数变化阈值：0/).waitFor();
  await output().fill('保留富集条件');
  const pvalue=page.locator('label').filter({hasText:'富集分析 p 值阈值'}).locator('input');await pvalue.fill('0.02');
  const beforeReads=reads.length;await page.getByRole('button',{name:'刷新差异来源',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('select[aria-label="来源差异表达结果"]')?.value==='差异来源-1:deg');
  assert(reads.length>beforeReads);assert.equal(await output().inputValue(),'保留富集条件');assert.equal(await pvalue.inputValue(),'0.02');
  await taskPopup('差异来源-1',page.getByRole('link',{name:'查看来源任务 差异来源-1',exact:true}));
  assert.equal(await degSelect.inputValue(),'差异来源-1:deg');await shot('desktop-differential');await mobile('mobile-differential');
  console.log('PASS differential network retry, selection/conditions, disabled source, task trace, mobile');
  await page.goto(tool('umapin',selectedPep.artifact_id));
  const pepSelect=page.getByLabel('选择前置分析结果',{exact:true});
  await page.waitForFunction(value=>document.querySelector('select[aria-label="选择前置分析结果"]')?.value===value,selectedPep.artifact_id,{timeout:60000});
  await page.getByText(/已读取 6 个样本、2 个数值特征/).waitFor();
  await output().fill('保留特征投影');
  const minDist=page.locator('label').filter({hasText:'最小距离'}).locator('input');await minDist.fill('0');
  const sample=page.getByRole('button',{name:'01 / tpm_01_001',exact:true});await sample.click();
  let failPep=true;await page.route('**/api/script-hub/pep-cache-candidates?**',r=>{if(failPep){failPep=false;return r.abort('failed');}return r.continue();});
  await page.getByRole('button',{name:'刷新前置结果',exact:true}).click();
  await page.getByRole('button',{name:'重新读取前置结果',exact:true}).waitFor();
  assert.equal(await page.getByRole('link',{name:/前往.*分析/}).count(),0);
  await page.getByRole('button',{name:'重新读取前置结果',exact:true}).focus();await page.keyboard.press('Enter');
  await page.waitForFunction(value=>document.querySelector('select[aria-label="选择前置分析结果"]')?.value===value,selectedPep.artifact_id);
  assert.equal(await output().inputValue(),'保留特征投影');assert.equal(await minDist.inputValue(),'0');assert.equal(await sample.getAttribute('aria-pressed'),'false');
  assert((await pepSelect.locator('option:disabled').count())>0);
  await taskPopup('共享来源-1',page.getByRole('link',{name:'查看来源任务 共享来源-1',exact:true}));
  assert.equal(await pepSelect.inputValue(),selectedPep.artifact_id);await shot('desktop-pep');await mobile('mobile-pep');
  console.log('PASS PEP network retry, raw parameters/sample selection, unavailable artifacts, task trace, mobile');
  await page.goto(tool('infiltration-pathway'));
  const radio=page.getByRole('radio',{name:'02 相对于 01 · 通路来源-2',exact:true});
  await radio.waitFor({timeout:60000});await radio.check();
  assert.equal(await page.getByRole('radio',{name:'02 相对于 01 · 通路来源-3',exact:true}).isDisabled(),true);
  await page.getByRole('radio',{name:'相对比例',exact:true}).check();
  await page.getByLabel('分组列',{exact:true}).selectOption('group');
  const verify=page.getByRole('button',{name:'核对分析范围',exact:true});
  await verify.click();await page.getByText('分析范围已确认 · 6 个样本',{exact:true}).waitFor();
  let scope=inspections.findLast(r=>r.payload.upstream_artifact_id);
  assert.deepEqual(scope.payload.comparison,['02','01']);assert.equal(scope.payload.upstream_artifact_id,'通路来源-2:go-bp:0');
  await output().fill('保留浸润比较');
  await verify.click();await page.getByText('分析范围已确认 · 6 个样本',{exact:true}).waitFor();
  await taskPopup('通路来源-1',page.getByRole('link',{name:'查看来源任务 通路来源-1',exact:true}));
  assert.equal(await radio.isChecked(),true);
  await page.getByRole('button',{name:'刷新来源',exact:true}).click();await radio.waitFor();assert.equal(await radio.isChecked(),true);
  assert.equal(await page.getByText('分析范围已确认 · 6 个样本',{exact:true}).count(),0);
  assert.equal(await output().inputValue(),'保留浸润比较');
  await verify.click();await page.getByText('分析范围已确认 · 6 个样本',{exact:true}).waitFor();
  scope=inspections.findLast(r=>r.payload.upstream_artifact_id);assert.deepEqual(scope.payload.comparison,['02','01']);
  await shot('desktop-pathway');await mobile('mobile-pathway');
  console.log('PASS pathway duplicate choices, real scope verification, refresh invalidates confirmation, direction preserved, independent task link, mobile');
  assert.equal(writes.length,0,JSON.stringify(writes));assert.equal(errors.length,0,JSON.stringify(errors));
  assert(reads.every(r=>r.project==='source-selection-project'&&r.dataset==='Set1'),JSON.stringify(reads));
  const evidence={differential:{total:differential.candidates.length,available:2},pathway:{total:pathway.candidates.length,available:2},pep:{total:pep.candidates.length,available:pep.candidates.filter(c=>c.status==='available').length},reads,writes,inspections,pageErrors:errors};
  await fs.writeFile(path.join(out,'browser-results.json'),JSON.stringify(evidence,null,2));console.log('PASS source selection real API browser validation');
 }catch(error){await shot('browser-failure');await fs.writeFile(path.join(out,'browser-failure.html'),await page.content());throw error;}
 finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
