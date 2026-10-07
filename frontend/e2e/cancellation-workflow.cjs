// Isolated internal API, Redis/Mongo, real RQ workers and production frontend.
// Seed: eight synthetic PEP/Profile samples in project cancel-synthetic.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
async function main(){
 const base=process.env.E2E_BASE_URL,output=process.env.E2E_OUTPUT_DIR;
 assert(base&&output);await fs.mkdir(output,{recursive:true});
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(String(e)));
 page.on('dialog',dialog=>dialog.accept());
 async function api(url,method='GET',data){const response=await context.request.fetch(base+url,{method,data});let body;try{body=await response.json()}catch{}return {code:response.status(),body};}
 async function job(id){const response=await api('/api/jobs/'+id);assert.equal(response.code,200,JSON.stringify(response));return response.body.job;}
 async function until(id,predicate,timeout=180000){const end=Date.now()+timeout;let current;while(Date.now()<end){current=await job(id);if(predicate(current))return current;assert(!['failed','interrupted'].includes(current.status),JSON.stringify(current));await page.waitForTimeout(100);}throw new Error('Timed out: '+JSON.stringify(current));}
 async function standaloneCancellation(matrix,project){
 // Cancel a standalone real analysis while its runtime is loading.
 const standalone=await api('/api/script-hub/jobs','POST',{module:'umapin',project_id:project,asset_set:'Set1',data_path:matrix.path,category_col:'Category',sample_column:'sample',n_neighbors:3,n_epochs:20000,min_dist:0,output_name:'单项取消验收',force_rerun:true});
 assert.equal(standalone.code,200,JSON.stringify(standalone));const standaloneId=standalone.body.job_id||standalone.body.task_id;
 await until(standaloneId,j=>j.status==='running'&&j.progress>=25);
 const standaloneAccepted=await api('/api/script-hub/jobs/'+standaloneId+'/cancel','POST');
 assert.equal(standaloneAccepted.code,200);assert.equal(standaloneAccepted.body.job.status,'running');assert(standaloneAccepted.body.job.cancel_requested);
 const standalonePolled=await api('/api/script-hub/task/'+standaloneId);assert.equal(standalonePolled.body.status,'running');assert.equal(standalonePolled.body.completed_at,null);
 assert.equal((await api('/api/jobs/'+standaloneId+'/retry','POST')).code,409);
 assert.equal((await api('/api/jobs/'+standaloneId+'?delete_results=1','DELETE')).code,409);
 const standaloneStopped=await until(standaloneId,j=>j.status==='cancelled');assert(standaloneStopped.completed_at);assert.deepEqual(standaloneStopped.result,{});
 return {standaloneId,accepted:standaloneAccepted.body.job,polled:standalonePolled.body,stopped:standaloneStopped};
 }
 const project=process.env.E2E_PROJECT || 'cancel-synthetic';
 if(process.env.E2E_SNAPSHOT_JOB){
  const id=process.env.E2E_SNAPSHOT_JOB;
  await page.goto(`${base}/analysis/script-hub/jobs?project=${project}&q=${id}&job=${id}`);
  await page.getByText('结束时间',{exact:true}).waitFor();
  await page.getByText('计算已停止，任务已取消。',{exact:true}).first().waitFor();
  assert(!/\b(?:AM|PM|Completed|Task started)\b/.test(await page.locator('body').innerText()));
  await page.screenshot({path:path.join(output,'final-progress-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});await page.reload();await page.getByText('结束时间',{exact:true}).waitFor();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1));
  await page.screenshot({path:path.join(output,'final-progress-mobile.png'),fullPage:true});
  assert.deepEqual(errors,[]);console.log(JSON.stringify({job:id,checks:'final Chinese progress details, native cancelled record, mobile layout',errors}));await browser.close();return;
 }
 if(process.env.E2E_STANDALONE_ONLY){
  const candidates=await api(`/api/script-hub/pep-cache-candidates?project_id=${project}&asset_set=Set1&cache_type=umapin`);
  assert.equal(candidates.code,200);const matrix=candidates.body.candidates.find(c=>c.status==='available'&&c.path.endsWith('/df_VJ_all.csv'));assert(matrix);
  const standalone=await standaloneCancellation(matrix,project);assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(output,'standalone-summary.json'),JSON.stringify({standalone,errors},null,2));
  console.log(JSON.stringify({standalone:standalone.standaloneId,checks:'native standalone cancellation and non-mutating polling',errors}));await browser.close();return;
 }
 const submitted=await api('/api/script-hub/batches','POST',{project_id:project,asset_set:'Set1',items:[
  {module:'pep-analysis',payload:{group_fields:['group'],selected_chains:['TRB'],optional_steps:[],force_rerun:true}},
  {module:'umapin',upstream_from:0,depends_on:[0],payload:{category_col:'Category',sample_column:'sample',n_neighbors:3,n_epochs:500,min_dist:0,output_name:'取消验收降维',force_rerun:true}},
  {module:'profile',payload:{grouptype_fields:['group'],param_begin:'signal',param_over:'signal',force_rerun:true}}
 ]});
 assert.equal(submitted.code,202,JSON.stringify(submitted));const id=submitted.body.job_id;
 await page.goto(`${base}/analysis/script-hub/jobs?project=${project}&q=${id}&job=${id}`);
 let child;
 await until(id,asyncUnused=>{const items=asyncUnused.payload.items;child=items[1]?.job_id;return Boolean(child)});
 await until(child,j=>j.status==='running'&&j.progress>=40);
 const before=await job(id);assert.equal(before.payload.items[0].status,'completed');
 const cancelResponse=page.waitForResponse(r=>r.url().endsWith('/api/jobs/'+id+'/cancel')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'取消任务',exact:true}).click();
 const accepted=await (await cancelResponse).json();assert.equal(accepted.job.status,'running');assert.equal(accepted.job.cancel_requested,true);assert.equal(accepted.job.completed_at,null);
 const pendingButton=page.getByRole('button',{name:'正在取消…',exact:true});await pendingButton.waitFor();assert(await pendingButton.isDisabled());
 assert.equal(await page.getByRole('button',{name:'重试任务',exact:true}).count(),0);
 assert.equal(await page.getByRole('button',{name:'删除任务',exact:true}).count(),0);
 assert.equal((await api('/api/jobs/'+id+'/retry','POST')).code,409);
 assert.equal((await api('/api/jobs/'+id+'?delete_results=1','DELETE')).code,409);
 const observed=[];
 for(let i=0;i<3;i++){const parent=await job(id),task=await api('/api/script-hub/task/'+child);assert.equal(parent.status,'running');assert.equal(task.body.status,'running');assert.equal(task.body.completed_at,null);observed.push({parent:parent.status,child:task.body.status,progress:task.body.progress});}
 await page.screenshot({path:path.join(output,'batch-cancelling.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});await page.reload();await pendingButton.waitFor();assert(await pendingButton.isDisabled());
 await page.screenshot({path:path.join(output,'cancelling-mobile.png'),fullPage:true});
 const finished=await until(id,j=>j.status==='cancelled');
 const items=finished.payload.items;assert.deepEqual(items.map(x=>x.status),['completed','cancelled','cancelled']);assert(!items[2].job_id);
 const first=await job(items[0].job_id);assert.equal(first.status,'completed');assert(first.result.zip_url);
 const zip=await context.request.get(base+first.result.zip_url);assert.equal(zip.status(),200);assert((await zip.body()).length>100);
 const stopped=await job(child);assert.equal(stopped.status,'cancelled');assert(stopped.completed_at);assert.notEqual(stopped.progress,100);assert.deepEqual(stopped.result,{});
 const pendingTask=await api('/api/script-hub/task/'+child);assert.equal(pendingTask.body.status,'cancelled');
 await page.setViewportSize({width:1440,height:1000});await page.reload();await page.getByRole('button',{name:'重试任务',exact:true}).waitFor();
 await page.screenshot({path:path.join(output,'batch-cancelled.png'),fullPage:true});
 const candidates=await api(`/api/script-hub/pep-cache-candidates?project_id=${project}&asset_set=Set1&cache_type=umapin`);
 assert.equal(candidates.code,200);const matrix=candidates.body.candidates.find(c=>c.job_id===items[0].job_id&&c.status==='available'&&c.path.endsWith('/df_VJ_all.csv'));assert(matrix,JSON.stringify(candidates));
 // A fresh native task proves that cancellation released the execution slot.
 const normal=await api('/api/script-hub/jobs','POST',{module:'umapin',project_id:project,asset_set:'Set1',data_path:matrix.path,category_col:'Category',sample_column:'sample',param_begin:matrix.feature_begin || '',param_over:matrix.feature_over || '',n_neighbors:3,n_epochs:20,min_dist:0,output_name:'取消后正常降维',force_rerun:true});
 assert.equal(normal.code,200,JSON.stringify(normal));const normalId=normal.body.job_id||normal.body.task_id;
 const completed=await until(normalId,j=>j.status==='completed');assert.equal(completed.result.metadata.sample_count,8);
 const coordinates=await context.request.get(base+completed.result.csv_urls[0]);assert.equal(coordinates.status(),200);const csv=(await coordinates.text()).trim().split(/\r?\n/);assert.equal(csv.length,9);
 const standaloneResult=await standaloneCancellation(matrix,project);
 assert.deepEqual(errors,[]);
 await fs.writeFile(path.join(output,'summary.json'),JSON.stringify({batch_id:id,child_id:child,accepted:accepted.job,observed,final_items:items,upstream_download_bytes:(await zip.body()).length,normal_job_id:normalId,normal_metadata:completed.result.metadata,standalone:standaloneResult,errors},null,2));
 console.log(JSON.stringify({batch:id,cancelled_child:child,normal:normalId,standalone:standaloneResult.standaloneId,checks:'native batch cancellation, polling, refresh, operation guards, preserved upstream, fresh UMAP',errors}));
 await browser.close();
}
main().catch(e=>{console.error(e);process.exitCode=1});
