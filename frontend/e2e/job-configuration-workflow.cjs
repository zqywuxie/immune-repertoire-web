// Production frontend and actual read-only job APIs; synthetic snapshots, no computations.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
async function main(){
 const base=process.env.E2E_BASE_URL,out=process.env.E2E_OUTPUT_DIR;
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
 const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[],mutations=[];
 page.on('pageerror',e=>errors.push(String(e)));page.on('request',r=>{if(new URL(r.url()).pathname.startsWith('/api/')&&r.method()!=='GET'&&r.method()!=='HEAD')mutations.push(r.method()+' '+r.url())});
 await page.route('**/api/auth/me',r=>r.fulfill({contentType:'application/json',body:'{"auth_mode":"internal","username":"内部验收","role":"user"}'}));
 await page.route('**/api/jobs/modules',r=>r.fulfill({contentType:'application/json',body:'{"success":true,"modules":[]}'}));
 async function open(id){
  await page.goto(base+'/analysis/script-hub/jobs?job='+id);
  await page.getByRole('tab',{name:'配置',exact:true}).waitFor();await page.getByRole('tab',{name:'配置',exact:true}).click();
  await page.getByRole('region',{name:'任务配置摘要',exact:true}).waitFor();
 }
 await open('job-legacy');
 const config=page.getByRole('region',{name:'任务配置摘要',exact:true});
 await config.getByText('表达矩阵.csv',{exact:true}).waitFor();await config.getByText('浸润分数.csv',{exact:true}).waitFor();
 assert.equal(await config.locator('details[open]').count(),0);assert.equal(await config.getByText('0',{exact:true}).count(),2);
 await config.getByText('前组：病例组 / A；后组：对照组 B',{exact:true}).waitFor();
 assert.equal(await config.getByText('样本-1999',{exact:true}).count(),0);
 await config.getByRole('button',{name:'查看完整名单'}).click();await config.getByText('样本-1999',{exact:true}).waitFor();
 assert((await config.locator('.job-configuration-list-values').evaluateAll(nodes=>Math.max(...nodes.map(el=>el.clientHeight))))<=220);
 await config.getByRole('button',{name:'收起完整名单'}).click();
 await page.screenshot({path:path.join(out,'desktop-configuration.png'),fullPage:true});
 const summary=config.getByText('完整技术参数',{exact:true});await summary.focus();await page.keyboard.press('Enter');
 await config.getByText(/keep-original/).waitFor();
 await config.getByRole('link',{name:'查看来源任务'}).click();await page.waitForURL(url=>url.searchParams.get('job')==='job-source');
 await page.reload();await page.getByRole('tab',{name:'配置',exact:true}).click();
 await page.getByText('前置克隆共享',{exact:true}).waitFor();
 await open('job-generic');await config.getByText('克隆 表.csv',{exact:true}).waitFor();await config.getByText('热力图',{exact:true}).waitFor();await config.getByText('CDR3_AA',{exact:true}).waitFor();
 await open('job-batch');await config.getByText('依赖：第 1 项',{exact:true}).waitFor();await config.getByText('使用第 1 项的分析产物',{exact:true}).waitFor();
 const children=config.getByText('查看本项保存的条件',{exact:true});await children.nth(1).click();await config.getByText('基因使用频率',{exact:true}).waitFor();
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(out,'mobile-batch-configuration.png'),fullPage:true});
 let sizes=await page.evaluate(()=>({width:innerWidth,document:document.documentElement.scrollWidth}));assert(sizes.document<=sizes.width+1,JSON.stringify(sizes));
 await open('job-missing');await config.getByText('未记录数据集',{exact:true}).waitFor();assert.equal(await config.getByText('邻居数',{exact:true}).count(),0);
 await page.screenshot({path:path.join(out,'mobile-missing-configuration.png'),fullPage:true});
 sizes=await page.evaluate(()=>({width:innerWidth,document:document.documentElement.scrollWidth}));assert(sizes.document<=sizes.width+1,JSON.stringify(sizes));
 const actual=await (await page.request.get(base+'/api/jobs/job-legacy')).json();
 assert.equal(actual.job.payload.config_json.pvalue_threshold,0);assert.equal(actual.job.payload.future_parameter,'keep-original');assert.equal(actual.job.payload.config_json.selected_samples.length,2000);
 assert.deepEqual(mutations,[]);assert.deepEqual(errors,[]);
 await fs.writeFile(path.join(out,'browser-summary.json'),JSON.stringify({scope:'real read-only Flask job endpoints; synthetic snapshots',normalizedValues:true,inputNames:true,rawCollapsed:true,sampleList:2000,listHeightLimit:220,sourceNavigationAndReload:true,genericNested:true,batchOrderAndDependency:true,missingMetadata:true,sizes,mutations,errors},null,2));
 await browser.close();console.log(JSON.stringify({passed:true,sizes,mutations,errors}));
}
main().catch(e=>{console.error(e);process.exit(1)});
