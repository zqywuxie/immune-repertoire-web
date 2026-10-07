// Real ML execution and read-only result UI validation on an isolated fixture.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
const base=process.env.E2E_BASE_URL,out=process.env.E2E_OUTPUT_DIR;
async function main(){
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
 const context=await browser.newContext({viewport:{width:1440,height:1000},timezoneId:'Asia/Shanghai'});
 const page=await context.newPage(),errors=[],requests=[],mutations=[];
 page.setDefaultTimeout(30000);page.on('pageerror',e=>errors.push(String(e)));
 page.on('request',r=>{if(r.url().includes('/api/'))requests.push({path:new URL(r.url()).pathname,method:r.method()});if(!['GET','HEAD','OPTIONS'].includes(r.method()))mutations.push(new URL(r.url()).pathname);});
 const get=async p=>{const response=await page.request.get(base+p);assert.equal(response.status(),200,p+': '+await response.text());return response.json();};
 const shot=async name=>page.screenshot({path:path.join(out,name+".png")});
 try{
 let jobs=(await get('/api/jobs?project_id=ml-overview-project&module=ml-analysis')).jobs;
 let job=jobs.find(j=>j.status==='completed'||j.status==='running'||j.status==='queued'),submitted=false;
 if(!job){
  const payload={module:'ml-analysis',project_id:'ml-overview-project',asset_set:'Set1',mode:'profile',sample_col:'sample',label_col:'类别',param_begin:'IGHG1',param_over:'Shannon',model_keys:['gaussian_nb','logistic_l2'],cv_splits:3,use_stability_selection:true,stability_threshold:0.6,stability_splits:3,stability_min_features:1,force_rerun:true,output_name:'模型结果合成验收',_task_name:'模型结果合成验收'};
  let created;
  for(let n=0;n<31;n++){
   const response=await page.request.post(base+'/api/script-hub/jobs',{data:payload});created=await response.json();
   if(response.ok())break;
   if(response.status()===400&&created.error==='VALIDATION_ERROR'&&created.details?.input_quality?.inputs?.some(i=>i.status==='pending')&&n<30){await page.waitForTimeout(1000);continue;}
   throw Error(JSON.stringify({status:response.status(),created}));
  }
  const id=created.job_id||created.task_id;assert(id,JSON.stringify(created));job={id};submitted=true;
  await fs.writeFile(path.join(out,'submission.json'),JSON.stringify(created,null,2));
 }
 const jobId=job.job_id||job.id,deadline=Date.now()+180000;
 let current;
 for(;;){
  current=(await get('/api/jobs/'+jobId)).job;
  if(['completed','failed','cancelled','interrupted'].includes(current.status))break;
  assert(Date.now()<deadline,'Existing real ML job did not reach a terminal state: '+jobId);
  await page.waitForTimeout(1000);
 }
 assert.equal(current.status,'completed',JSON.stringify(current));
 const saved=await get('/api/jobs/'+jobId+'/results'),data=saved.result.metadata;
 assert.equal(data.samples,24);assert.equal(data.raw_feature_number,4);assert.equal(data.models.length,2);
 assert.deepEqual(data.model_keys,['gaussian_nb','logistic_l2']);assert.equal(data.stability_selection.enabled,true);
 await fs.writeFile(path.join(out,'real-result-before.json'),JSON.stringify(saved,null,2));
 const location=base+'/analysis/script-hub/jobs?'+new URLSearchParams({job:jobId,project:'ml-overview-project',asset_set:'Set1'});

  await page.goto(location);await page.getByRole('tab',{name:'结果',exact:true}).click();
  const summary=page.getByRole('region',{name:'机器学习结果概览',exact:true});await summary.waitFor({timeout:60000});
  assert.equal(await summary.getByLabel('查看模型评估').locator('option').count(),2);
  const keys=['nested_cv_mean_accuracy','nested_cv_mean_balanced_accuracy','nested_cv_mean_macro_f1','roc_auc','average_precision'];
  const scores=async model=>assert.deepEqual(await summary.locator('.ml-result-metrics dd').allTextContents(),keys.map(k=>String(model[k])));
  await scores(data.models[0]);
  const metricsReads=requests.length;
  await summary.getByLabel('查看模型评估').selectOption('logistic_l2:0');await scores(data.models[1]);
  assert.equal(requests.length,metricsReads,'Changing a model should use saved metadata, not request every file');
  await summary.getByRole('button',{name:'比较所有模型',exact:true}).focus();await page.keyboard.press('Enter');
  const comparison=summary.getByRole('table');assert.equal(await comparison.getByRole('row').count(),3);
  const comparisonValues=await comparison.locator('tbody tr').evaluateAll(rows=>rows.map(row=>Array.from(row.querySelectorAll('td')).map(cell=>cell.textContent)));
  assert.deepEqual(comparisonValues,data.models.map(m=>keys.map(k=>String(m[k]))));
  await summary.getByText('查看最终全样本模型参数',{exact:true}).click();
  assert.equal(await summary.locator('.ml-result-parameters pre').textContent(),JSON.stringify(data.models[1].final_model_params,null,2));
  await summary.scrollIntoViewIfNeeded();await shot('desktop-model-summary');
  await page.setViewportSize({width:390,height:844});await summary.scrollIntoViewIfNeeded();await shot('mobile-model-summary');
  let sizes=await summary.evaluate(el=>({width:innerWidth,document:document.documentElement.scrollWidth,main:document.querySelector('main').scrollWidth,summary:el.getBoundingClientRect().width}));assert(sizes.document<=sizes.width+1&&sizes.main<=sizes.width+1&&sizes.summary<=sizes.width,JSON.stringify(sizes));
  const scroll=summary.getByRole('region',{name:'已保存模型指标比较',exact:true});
  await scroll.focus();await page.keyboard.press('ArrowRight');await page.keyboard.press('ArrowRight');
  assert(await scroll.evaluate(el=>el.scrollWidth>el.clientWidth));
  await page.waitForFunction(()=>document.querySelector('.ml-result-comparison').scrollLeft>0);
  await summary.getByRole('button',{name:'查看特征稳定性表',exact:true}).click();
  await page.getByRole('button',{name:'按selection_frequency排序',exact:true}).waitFor();
  const selection=await page.getByLabel('结果文件',{exact:true}).inputValue();assert(selection.includes('feature_stability.csv'),selection);
  const preview=page.getByLabel('当前结果预览',{exact:true});await preview.waitFor();await preview.scrollIntoViewIfNeeded();await shot('mobile-stability-table');
  await page.reload();await page.getByRole('tab',{name:'结果',exact:true}).click();await summary.waitFor();
  assert.equal(await summary.getByLabel('查看模型评估').inputValue(),'logistic_l2:0');assert.equal(await summary.getByRole('button',{name:'收起模型比较',exact:true}).getAttribute('aria-expanded'),'true');
  assert.equal(await page.getByLabel('结果文件',{exact:true}).inputValue(),selection);
  await summary.getByRole('button',{name:'查看模型比较表',exact:true}).click();await page.getByRole('button',{name:'按nested_cv_mean_balanced_accuracy排序',exact:true}).waitFor();
  await summary.getByRole('button',{name:'查看最终稳定特征表',exact:true}).click();await page.getByRole('button',{name:'按feature排序',exact:true}).waitFor();
  const stableRows=await page.locator('.job-result-preview tbody tr').count();assert.equal(stableRows,data.stability_selection.selected_features.length);
  const latest=await get('/api/jobs/'+jobId+'/results');assert.deepEqual(latest.result.metadata,data);
  // The recorded label mapping comes from the real analysis, with raw 01/02 labels preserved.
  const labelUrl=saved.result.text_urls.find(u=>u.includes('/models/gaussian_nb/label_mapping.txt'));assert(labelUrl);
  const mapping=await page.request.get(base+labelUrl);assert(mapping.ok());const mappingText=await mapping.text();assert(mappingText.startsWith('分类标签编码：'));assert(mappingText.includes('0: 01')&&mappingText.includes('1: 02'));
  const predictionUrl=saved.result.csv_urls.find(u=>u.includes('/models/gaussian_nb/out_of_fold_predictions.csv'));
  const prediction=await page.request.get(base+predictionUrl);assert(prediction.ok());assert((await prediction.text()).includes('\n001,'));
  const finalJobs=(await get('/api/jobs?project_id=ml-overview-project&module=ml-analysis')).jobs;assert.equal(finalJobs.length,1);
  assert.equal(errors.length,0,JSON.stringify(errors));assert(mutations.every(p=>p==='/api/jobs/'+jobId+'/table-preview'),JSON.stringify(mutations));
  await fs.writeFile(path.join(out,'browser-results.json'),JSON.stringify({jobId,submitted,models:data.model_keys,samples:data.samples,stableFeatures:data.stability_selection.selected_features,requests,pageErrors:errors,mutations},null,2));
  console.log('PASS real 24-sample ML, two-model saved metrics, keyboard comparison, current table navigation, reload preservation, raw labels and samples, unchanged metadata, 390px');
 }catch(error){await shot('browser-failure');await fs.writeFile(path.join(out,'browser-failure.html'),await page.content());throw error;}
 finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
