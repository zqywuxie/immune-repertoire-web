// Docker Chromium against an isolated internal API/RQ stack and a synthetic eight-sample project.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
async function main(){
 const base=process.env.E2E_BASE_URL,output=process.env.E2E_OUTPUT_DIR,project=process.env.E2E_PROJECT_ID;
 assert(base&&output&&project,'Use an isolated stack, explicit synthetic project and artifact directory');
 await fs.mkdir(output,{recursive:true});
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  let submission;
  if(process.env.E2E_RESUME_TASK) submission={task_id:process.env.E2E_RESUME_TASK};
  else {
  const response=await context.request.post(`${base}/api/script-hub/jobs`,{data:{
   module:'pep-analysis',project_id:project,asset_set:'Set1',selected_chains:['TRB'],group_fields:['group'],grouptype_fields:['group'],
   selected_group_values:{group:['A','B']},selected_samples_by_group:{group:{A:['001','002','003','004'],B:['005','006','007','008']}},
   optional_steps:['5','6','7','8'],pvalue_threshold:1,force_rerun:true,
  }});
  assert(response.ok(),await response.text());
  submission=await response.json();
  }
  console.log('PEP task '+submission.task_id);
  let task;const deadline=Date.now()+240000;
  do{
   task=await (await context.request.get(`${base}/api/script-hub/task/${submission.task_id}`)).json();
   if(['completed','failed','cancelled','interrupted'].includes(task.status))break;
   await new Promise(resolve=>setTimeout(resolve,1000));
  }while(Date.now()<deadline);
  assert.equal(task.status,'completed',JSON.stringify(task));
  assert.equal(task.payload.queue_backend,'redis');
  assert(!task.result.reused_result,'Report must come from fresh computation');
  const page=await context.newPage(),errors=[];
  page.on('pageerror',error=>errors.push(String(error)));
  await page.goto(base+task.result.viewer_url);
  await page.getByRole('heading',{name:'克隆共享分析结果',exact:true}).waitFor();
  const category=page.getByLabel('图表分类');
  await category.waitFor();
  const options=await category.locator('option').evaluateAll(options=>options.map(o=>({value:o.value,label:o.textContent})));
  console.log('Category options '+JSON.stringify(options));
  assert(options.some(option=>option.value==='Differential heatmaps'&&option.label==='差异热图'));
  assert(options.some(option=>option.value==='CDR3 arrangement heatmaps'&&option.label==='CDR3 排列热图'));
  for(const label of ['分组字段','链型','使用类型','图表类型'])assert(await page.getByLabel(label).isVisible());
  const visibleCards=()=>page.locator('.plot-card:visible');
  assert(await visibleCards().count()>0);
  await page.waitForFunction(()=>[...document.querySelectorAll('.plot-card:not(.is-hidden) img')].every(img=>img.complete&&img.naturalWidth>0));
  await page.screenshot({path:path.join(output,'pep-report-desktop.png')});
  await category.selectOption('CDR3 arrangement heatmaps');
  assert(await page.getByLabel('链型').isVisible());
  for(const label of ['分组字段','使用类型','图表类型'])assert(await page.getByLabel(label).isHidden());
  assert(await visibleCards().count()>0);
  await category.selectOption('Unique CDR3 heatmaps');
  await page.getByLabel('图表类型').selectOption('heatmap');
  assert.equal(await visibleCards().count(),0);
  await page.getByText('当前筛选条件下没有图表，请调整分类、链型或其他条件。',{exact:true}).waitFor();
  await page.getByRole('button',{name:'显示本类全部图表',exact:true}).click();
  assert(await visibleCards().count()>0);
  assert((await page.getByRole('status').textContent()).endsWith(' 张图'));
  await page.screenshot({path:path.join(output,'pep-filters-recovered.png')});
  for(const summary of ['共享克隆矩阵','基因使用矩阵','差异热图数据','CDR3 分类数据','CDR3 分类比例数据']){
   await page.locator('summary').filter({hasText:summary}).first().click();
  }
  const first=page.locator('.download-grid a').first();
  const table=await context.request.get(base+await first.getAttribute('href'));assert(table.ok());
  const zip=await context.request.get(base+task.result.zip_url);assert(zip.ok());
  await fs.writeFile(path.join(output,'result.zip'),await zip.body());
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Mobile report overflow');
  await page.screenshot({path:path.join(output,'pep-report-mobile.png'),fullPage:true});
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(output,'summary.json'),JSON.stringify({project,task_id:submission.task_id,status:task.status,queue:task.payload.queue_backend,
   options,images:task.result.viewer_items.length,chains:task.result.metadata.selected_chains,optional_steps:task.result.metadata.optional_steps_run,
   category_keys:task.result.viewer_items.map(item=>item.section),download_verified:true,filter_recovery:true,mobile_verified:true,errors},null,2));
  console.log('PASS: fresh native PEP report, Chinese labels, unchanged category keys, chain-only filters, empty recovery, downloads and 390px layout');
 }finally{await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
