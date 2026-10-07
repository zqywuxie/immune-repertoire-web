// Run against an isolated internal API, two RQ workers and the production frontend.
// Synthetic seed projects: combo-independent, scope-profile-project.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
async function main(){
 const base=process.env.E2E_BASE_URL,output=process.env.E2E_OUTPUT_DIR;
 assert(base&&output,'Requires an isolated API and artifact directory');
 await fs.mkdir(output,{recursive:true});
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
 const errors=[],checks=[],submissions=[];let batch;
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  const page=await context.newPage();
  page.on('pageerror',e=>errors.push(String(e)));
  page.on('request',r=>{if(r.url().endsWith('/data-selection/inspect'))checks.push(r.postDataJSON());if(r.method()==='POST'&&/\/api\/script-hub\/(jobs|batches)$/.test(r.url()))submissions.push(r.postDataJSON());});
  const choose=name=>page.getByRole('button',{name:'配置 '+name,exact:true}).click();
  const remove=name=>page.getByRole('button',{name:'移除 '+name,exact:true}).click();
  const next=()=>page.getByRole('button',{name:'下一步',exact:true});
  const review=()=>page.getByRole('region',{name:'本次分析数据',exact:true});
  async function open(project){
   await page.goto(`${base}/analysis/script-hub?project=${project}&asset_set=Set1`);
   await next().click();
   await page.getByRole('heading',{name:'选择分析与配置参数',exact:true}).waitFor();
  }
  async function ready(){await page.getByText(/本次输入已核验/).waitFor({timeout:60000});await next().waitFor();}
  await open('scope-profile-project');
  assert.equal(checks.length,0,'No analyses selected, no data inspection');
  await choose('组库指标与分组比较');await ready();
  assert(await next().isDisabled(),'Missing metrics must block configuration advance');
  assert((await page.getByRole('region',{name:'运行前参数检查'}).textContent()).includes('请选择'));
  assert.deepEqual(checks.at(-1).input_types,['profile']);
  await choose('差异分析');
  await page.getByText('本次输入需要处理',{exact:false}).waitFor({timeout:60000});
  assert(await next().isDisabled());
  assert.deepEqual(checks.at(-1).input_types,['profile','transcriptome']);
  await remove('差异分析');await ready();
  assert.deepEqual(checks.at(-1).input_types,['profile']);
  await page.screenshot({path:path.join(output,'unrelated-input-recovered.png'),fullPage:true});

  await open(process.env.E2E_COMBO_PROJECT || 'combo-independent');
  await choose('组库指标与分组比较');await ready();
  await choose('组库图表');await ready();
  assert.deepEqual(checks.at(-1).input_types,['pep','profile']);
  assert.deepEqual(checks.at(-1).alignment_groups,[]);
  assert.equal(await page.getByRole('checkbox',{name:/我已核对样本匹配情况/}).count(),0);
  await choose('优势克隆分析');
  await page.getByRole('checkbox',{name:/我已核对样本匹配情况/}).waitFor({timeout:60000});
  assert.deepEqual(checks.at(-1).input_types,['pep','profile']);
  assert.deepEqual(checks.at(-1).alignment_groups,[['pep','profile']]);
  assert(await next().isDisabled());
  await page.getByRole('checkbox',{name:/我已核对样本匹配情况/}).check();
  assert(await next().isDisabled(),'Parameter checks still require module configuration');
  await page.screenshot({path:path.join(output,'joint-input-review.png'),fullPage:true});
  await remove('优势克隆分析');await ready();
  assert.deepEqual(checks.at(-1).alignment_groups,[]);
  assert.equal(await page.getByRole('checkbox',{name:/我已核对样本匹配情况/}).count(),0);
  await remove('组库图表');await ready();
  await choose('组库指标与分组比较');
  const groupSelect=page.locator('select').filter({has:page.locator('option[value="group"]')}).first();
  await groupSelect.selectOption('group');
  await page.getByRole('button',{name:'添加',exact:true}).click();
  await page.getByRole('button',{name:'全部分组',exact:true}).click();
  await page.getByRole('button',{name:'001',exact:true}).waitFor();
  await page.getByLabel('指标起始列',{exact:true}).selectOption('metric');
  await page.getByLabel('指标结束列',{exact:true}).selectOption('metric');
  const verifiedBeforeParameterChange=checks.length;
  await page.getByLabel('指标结束列',{exact:true}).selectOption('');
  await page.getByRole('region',{name:'运行前参数检查'}).getByText('请选择要比较的指标范围。',{exact:true}).waitFor();
  assert(await next().isDisabled(),'Empty metric range blocks execution');
  await page.getByRole('button',{name:'补充参数：组库指标与分组比较',exact:true}).click();
  await page.waitForFunction(()=>document.activeElement?.getAttribute('aria-label')==='组库指标与分组比较参数配置');
  await page.screenshot({path:path.join(output,'missing-metric-focused.png'),fullPage:true});
  await page.getByLabel('指标结束列',{exact:true}).selectOption('metric');
  assert(await next().isEnabled(),'Correcting parameters restores advance');
  assert.equal(checks.length,verifiedBeforeParameterChange,'Parameter edits retain valid input inspection');

  await choose('差异分析');await ready();
  assert.deepEqual(checks.at(-1).input_types,['profile','transcriptome']);
  assert.deepEqual(checks.at(-1).alignment_groups,[]);
  assert((await review().textContent()).includes('独立分析按各自样本范围运行。'));
  assert.equal(await page.getByRole('checkbox',{name:/我已核对样本匹配情况/}).count(),0);
  const sources=page.getByRole('group',{name:'本次分析输入',exact:true});
  assert((await sources.textContent()).includes('combo-independent-transcriptome.csv'));
  assert(!(await sources.textContent()).includes('combo-independent-profile.csv'));

  const parameterReview=page.getByRole('region',{name:'运行前参数检查'});
  await page.getByRole('button',{name:'01_vs_02',exact:true}).click();
  await parameterReview.getByText('请至少选择一个组间比较。',{exact:true}).waitFor();
  assert(await next().isDisabled(),'Empty comparison blocks execution');
  await page.getByRole('button',{name:'补充参数：差异分析',exact:true}).click();
  await page.waitForFunction(()=>document.activeElement?.getAttribute('aria-label')==='差异分析参数配置');
  await page.screenshot({path:path.join(output,'missing-comparison-focused.png'),fullPage:true});
  await page.getByRole('button',{name:'01_vs_02',exact:true}).click();
  assert(await next().isEnabled());
  const expressionForm=page.getByRole('region',{name:'差异分析参数配置'});
  await expressionForm.getByRole('button',{name:'清空',exact:true}).click();
  assert(await next().isDisabled(),'Empty expression sample selection blocks execution');
  await expressionForm.getByRole('button',{name:'全部样本',exact:true}).click();
  await page.getByRole('button',{name:'01_vs_02',exact:true}).click();
  assert(await next().isEnabled());
  assert.equal(submissions.length,0,'Configuring and fixing inputs never auto-starts computation');

  await page.getByRole('button',{name:'01 / tpm_01_004',exact:true}).click();
  await page.getByRole('button',{name:'02 / tpm_02_004',exact:true}).click();
  await page.getByLabel('p 值阈值',{exact:true}).fill('1e-300');
  await page.getByLabel('对数倍数变化阈值',{exact:true}).fill('0');
  assert(await next().isEnabled(),'Filled required configuration enables execution');
  await page.screenshot({path:path.join(output,'independent-inputs-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Mobile overflow');
  await page.screenshot({path:path.join(output,'independent-inputs-mobile.png'),fullPage:true});
  await page.setViewportSize({width:1440,height:1000});
  await next().click();
  const submitted=page.waitForResponse(r=>r.url().endsWith('/api/script-hub/batches')&&r.request().method()==='POST').catch(()=>null);
  await page.getByRole('button',{name:'运行所选模块',exact:true}).click();
  const response=await submitted;
  if(!response){console.log('Submission page: '+await page.locator('body').innerText());throw new Error('No batch submission');}
  assert(response.ok(),await response.text());
  batch=await response.json();
  console.log('Batch submitted '+batch.job_id);
  const deadline=Date.now()+240000;let parent;
  do{
   parent=(await (await context.request.get(`${base}/api/jobs/${batch.job_id}`)).json()).job;
   if(['completed','failed','cancelled','interrupted'].includes(parent.status))break;
   await page.waitForTimeout(1000);
  }while(Date.now()<deadline);
  assert.equal(parent.status,'completed',JSON.stringify(parent));
  assert.equal(parent.payload.queue_backend,'redis');
  const children=[];
  for(const item of parent.payload.items){
   const child=await (await context.request.get(`${base}/api/script-hub/task/${item.job_id}`)).json();
   assert.equal(child.status,'completed',child.detail);
   for(const url of [child.result.zip_url,child.result.viewer_url]){const result=await context.request.get(base+url);assert(result.ok(),url);}
   children.push(child);
  }
  const expression=children.find(child=>child.module==='volcano');
  assert.deepEqual(expression.result.metadata.selected_expression_samples,['01','02'].flatMap(g=>[1,2,3].map(i=>`tpm_${g}_${String(i).padStart(3,'0')}`)));
  assert.equal(expression.result.metadata.sample_count,6);
  const profile=children.find(child=>child.module==='profile');
  assert(profile);
  await page.getByRole('button',{name:'查看结果',exact:true}).click();
  await page.screenshot({path:path.join(output,'batch-results.png'),fullPage:true});
  console.log('Result URL '+page.url());
  await fs.writeFile(path.join(output,'summary.json'),JSON.stringify({batch:batch.job_id,parent_status:parent.status,children:children.map(child=>({id:child.task_id,module:child.module,status:child.status,metadata:child.result.metadata})),checks,errors,configuration_gate_verified:true,submissions:submissions.length,url:page.url()},null,2));
  await page.reload();
  await page.getByText('查看项目分析历史，按条件检索并打开结果。',{exact:true}).waitFor({timeout:60000});
  console.log('Restored URL '+page.url());
  const restoredJob=new URL(page.url()).searchParams.get('job');
  await page.getByRole('region',{name:'任务结果',exact:true}).getByText(restoredJob,{exact:true}).waitFor({timeout:60000});
  assert(new URL(page.url()).searchParams.get('batch')===batch.job_id);
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(output,'summary.json'),JSON.stringify({batch:batch.job_id,parent_status:parent.status,children:children.map(child=>({id:child.task_id,module:child.module,status:child.status,metadata:child.result.metadata})),checks,errors,configuration_gate_verified:true,submissions:submissions.length},null,2));
  console.log('PASS: scope recovery, same-union joint matching, distinct independent sample IDs, six-column expression, native RQ batch in a two-worker stack, results/download/refresh/mobile');
 }finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
