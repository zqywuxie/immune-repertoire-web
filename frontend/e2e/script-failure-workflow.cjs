const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
async function main(){
 const base=process.env.E2E_BASE_URL,out=process.env.E2E_OUTPUT_DIR;
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
 page.setDefaultTimeout(20000);page.on('pageerror',error=>errors.push(String(error)));
 try{
  // Only bootstrap data is isolated; job/detail/SSE/status endpoints stay real.
  await page.route('**/api/auth/me',r=>r.fulfill({contentType:'application/json',body:JSON.stringify({auth_mode:'internal',username:'内部验收',role:'user'})}));
  await page.route('**/api/projects',r=>r.fulfill({contentType:'application/json',body:'{"projects":[]}'}));
  await page.route('**/api/jobs/modules',r=>r.fulfill({contentType:'application/json',body:'{"success":true,"modules":[]}'}));
  await page.goto(base+'/analysis/script-hub/jobs?status=failed&job=script-native-failure');
  await page.getByText('最后记录进度：10%',{exact:true}).waitFor();
  const progress=page.locator('.job-progress-panel');
  assert.equal(await progress.getByRole('progressbar').getAttribute('aria-valuenow'),'10');
  assert.equal(await progress.locator('details[open]').count(),0);
  const recorded=progress.locator('summary').filter({hasText:'进度记录'});
  await recorded.focus();await page.keyboard.press('Enter');
  assert.equal(await progress.locator('ol > li').count(),2);
  assert(await progress.getByText('指标分组分析',{exact:true}).isVisible());
  await page.screenshot({path:path.join(out,'native-failure-desktop.png'),fullPage:true});
  await page.reload();await page.getByText('最后记录进度：10%',{exact:true}).waitFor();
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.screenshot({path:path.join(out,'native-failure-mobile.png'),fullPage:true});
  await page.goto(base+'/analysis/script-hub/jobs?status=failed&job=script-submit-failure');
  await page.getByText('最后记录进度：0%',{exact:true}).waitFor();
  assert.equal(await page.locator('.job-progress-panel').getByRole('progressbar').getAttribute('aria-valuenow'),'0');
  const native=await page.request.get(base+'/api/script-hub/task/script-native-failure');
  const initial=await page.request.get(base+'/api/script-hub/jobs/script-submit-failure');
  assert.equal(native.status(),200);assert.equal(initial.status(),200);
  assert.equal((await native.json()).progress,10);
  assert.equal((await initial.json()).job.progress,0);
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(out,'browser-results.json'),JSON.stringify({
   passed:true,nativeFailureProgress:10,submissionFailureProgress:0,
   realStatusApis:true,historyCount:2,reloadPreservesFailure:true,
   viewport:[1440,390],pageErrors:errors,
  },null,2));
  console.log('PASS: native Profile failure stays at 10%, submission failure at 0%, real task APIs, original history, reload and mobile layout.');
 }catch(error){
  await fs.writeFile(path.join(out,'browser-failure.json'),JSON.stringify({url:page.url(),text:await page.locator('body').innerText(),pageErrors:errors},null,2));
  await page.screenshot({path:path.join(out,'browser-failure.png'),fullPage:true});
  throw error;
 }finally{await browser.close();}
}
main().catch(error=>{console.error(error);process.exit(1);});
