// Production UI + real Profile task. Only selected status requests suffer a network fault.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
async function main(){
 const base=process.env.E2E_BASE_URL,out=process.env.E2E_OUTPUT_DIR;
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],submissions=[];
 let snapshot,disconnected=false,faults=0,jobId;
 page.setDefaultTimeout(30000);
 page.on('pageerror',error=>errors.push(String(error)));
 page.on('request',request=>{
  if(request.method()==='POST'&&new URL(request.url()).pathname==='/api/script-hub/jobs')submissions.push(request.postDataJSON());
 });
 try{
  assert.equal((await (await page.request.get(base+'/api/auth/me')).json()).auth_mode,'internal');
  await page.route(/\/api\/script-hub\/task\/[^/?]+$/,async route=>{
   if(snapshot&&disconnected){faults++;await route.abort('connectionreset');return;}
   let response=await route.fetch();
   let task=await response.json();
   // Read real snapshots while the first request is pending; never invent a stage.
   for(let attempt=0;!snapshot&&task.status==='queued'&&Number(task.progress)===0&&attempt<50;attempt++){
    await new Promise(done=>setTimeout(done,40));
    response=await route.fetch();task=await response.json();
   }
   if(!snapshot&&['queued','running'].includes(task.status)){snapshot=task;disconnected=true;}
   await route.fulfill({response});
  });
  await page.goto(base+'/analysis/tools/profile?project=execution-reconnect-project&asset_set=Set1');
  await page.getByText('指标分组箱线图',{exact:true}).waitFor({timeout:60000});
  const groupSelect=page.locator('select').filter({has:page.locator('option').filter({hasText:'选择分组列'})});
  await groupSelect.selectOption('group');
  await page.getByRole('button',{name:'添加',exact:true}).click();
  await page.getByRole('button',{name:'全部分组',exact:true}).click();
  await page.getByLabel('指标起始列',{exact:true}).selectOption('TRA_Shannon');
  await page.getByLabel('指标结束列',{exact:true}).selectOption(process.env.E2E_PARAM_END||'TRB_Shannon');
  await page.getByRole('button',{name:'下一步',exact:true}).click();
  const submitted=page.waitForResponse(response=>new URL(response.url()).pathname==='/api/script-hub/jobs'&&response.request().method()==='POST');
  await page.getByRole('button',{name:'开始分析',exact:true}).click();
  const response=await submitted;assert.equal(response.status(),200,await response.text());
  jobId=(await response.json()).task_id;
  const notice=page.getByRole('status',{name:'任务状态连接',exact:true});
  await notice.waitFor();
  assert(snapshot,'No real nonterminal snapshot received');
  assert.equal(Number(await page.getByRole('progressbar').getAttribute('aria-valuenow')),snapshot.progress);
  assert.match(await notice.innerText(),/最后读取时间/);
  const taskLink=page.getByRole('link',{name:'查看任务',exact:true});
  assert.equal(new URL(await taskLink.getAttribute('href'),base).searchParams.get('job'),jobId);
  assert.equal(submissions.length,1);
  assert.equal(await page.getByRole('button',{name:'开始分析',exact:true}).count(),0);
  const details=page.getByText(/执行日志（最近/).locator('..');
  assert.equal(await details.getAttribute('open'),null);
  await page.screenshot({path:path.join(out,'reconnecting-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.screenshot({path:path.join(out,'reconnecting-mobile.png'),fullPage:true});
  disconnected=false;
  await page.getByRole('button',{name:'查看报告',exact:true}).waitFor({timeout:60000});
  const task=await (await page.request.get(base+'/api/script-hub/task/'+jobId)).json();
  assert.equal(task.status,'completed');
  assert(task.result.png_urls.length>0);
  await notice.waitFor({state:'detached'});
  assert.equal(submissions.length,1);
  assert.equal(new URL(page.url()).searchParams.get('job'),jobId);
  assert.equal(task.result.metadata.filtered_row_count,12);
  const csv=await page.request.get(base+task.result.csv_urls[0]);assert.equal(csv.status(),200);
  const count=faults;
  await page.reload();
  await page.getByRole('link',{name:'打开交互报告',exact:true}).waitFor({timeout:30000});
  assert.equal(submissions.length,1);
  assert.equal(faults,count);
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(out,'browser-results.json'),JSON.stringify({
   passed:true,jobId,lastRealProgress:snapshot.progress,networkFaults:faults,
   submissionCount:submissions.length,completed:true,reportReload:true,
   realComputation:true,viewport:[1440,390],pageErrors:errors
  },null,2));
  console.log('PASS: real Profile task reconnects without resubmission, retains recorded progress, produces real result and reloads.');
 }catch(error){
  await fs.writeFile(path.join(out,'browser-failure.json'),JSON.stringify({url:page.url(),text:await page.locator('body').innerText(),snapshot,jobId,pageErrors:errors},null,2));
  await page.screenshot({path:path.join(out,'browser-failure.png'),fullPage:true});throw error;
 }finally{await browser.close();}
}
main().catch(error=>{console.error(error);process.exit(1);});
