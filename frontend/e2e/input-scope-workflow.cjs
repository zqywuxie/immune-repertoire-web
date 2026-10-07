// Real isolated API: stale optional inputs must not block an unrelated analysis.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
async function main() {
  const base=process.env.E2E_BASE_URL,output=process.env.E2E_OUTPUT_DIR;
  assert(base&&output,'Requires isolated API and artifact directory');
  await fs.mkdir(output,{recursive:true});
  const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
  const errors=[],checks=[];let submissions=0;
  try {
    const context=await browser.newContext({viewport:{width:1440,height:1000}});
    for (const [project,tool,kind,label] of [
      ['scope-profile-project','profile','profile','样本指标表'],
      ['scope-expression-project','expression','transcriptome','转录组'],
    ]) {
      const response=await context.request.post(`${base}/api/script-hub/data-selection/inspect`,{data:{project_id:project,asset_set:'Set1',input_types:[kind]}});
      assert.equal(response.status(),200,await response.text());
      const quality=await response.json();
      assert.deepEqual(quality.input_quality.errors,[]);
      assert.deepEqual(quality.input_quality.inputs.map(input=>input.kind),[kind]);
      const blocked=await context.request.post(`${base}/api/script-hub/data-selection/inspect`,{data:{project_id:project,asset_set:'Set1',input_types:[kind==='profile'?'transcriptome':'profile']}});
      assert.equal(blocked.status(),400,'Consumed stale inputs must still be rejected');
      const page=await context.newPage();
      page.on('pageerror',error=>errors.push(String(error)));
      page.on('request',request=>{
        if(request.method()==='POST'&&/\/(jobs|batches|run)$/.test(new URL(request.url()).pathname))submissions++;
        if(request.url().endsWith('/api/script-hub/data-selection/inspect'))checks.push(request.postDataJSON().input_types);
      });
      await page.goto(`${base}/analysis/tools/${tool}?project=${project}&asset_set=Set1`);
      if (process.env.E2E_DEBUG === '1') {
        await page.waitForTimeout(10000);
        console.log(JSON.stringify({project,body:await page.locator('body').innerText(),errors,checks}));
        await page.screenshot({path:path.join(output,`${tool}-debug.png`),fullPage:true});
        return;
      }
      await page.getByRole('heading',{name:'配置参数与分组',exact:true}).waitFor({timeout:60000});
      assert((await page.getByRole('region',{name:'本次分析数据'}).textContent()).includes(`核验范围：${label}`));
      const sources=page.getByRole('group',{name:'本次分析输入',exact:true});
      assert((await sources.textContent()).includes(`-${kind}.csv`));
      assert(!(await sources.textContent()).includes(kind==='profile'?'转录组':'样本指标表'),'Unconsumed input is displayed in the parameter summary');
      assert(!(await sources.textContent()).includes('/tmp/uploads/'),'The source summary should show a readable filename');
      await page.screenshot({path:path.join(output,`${tool}-desktop.png`),fullPage:true});
      await page.getByRole('button',{name:'更换或检查数据',exact:true}).click();
      await page.getByRole('heading',{name:'选择或上传数据',exact:true}).waitFor();
      const selector=page.locator('label').filter({hasText:'原始数据文件'}).locator('select');
      console.log('Reviewing '+tool+' mapping');
      await selector.locator('option').nth(1).waitFor({state:'attached'});
      const options=await selector.locator('option').allTextContents();
      assert.equal(options.length,2,'Mapping should show only one consumed original file');
      assert(options[1].includes(`-${kind}.csv`));
      assert.equal(await page.getByText('无法读取样本指标表，请检查文件路径后重试。',{exact:true}).count(),0);
      await page.getByRole('button',{name:'下一步',exact:true}).click();
      await page.getByRole('heading',{name:'配置参数与分组',exact:true}).waitFor();
      await page.setViewportSize({width:390,height:844});
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Mobile viewport overflows');
      await page.screenshot({path:path.join(output,`${tool}-mobile.png`),fullPage:true});
      await page.reload();
      await page.getByRole('heading',{name:'配置参数与分组',exact:true}).waitFor({timeout:60000});
      await page.close();
    }
    assert.equal(submissions,0,'Input inspection must not start analysis');
    assert.deepEqual(errors,[]);
    assert(checks.some(scope=>JSON.stringify(scope)==='["profile"]'));
    assert(checks.some(scope=>JSON.stringify(scope)==='["transcriptome"]'));
    assert(checks.every(scope=>scope?.length===1),'An unrelated input leaked into inspection');
    await fs.writeFile(path.join(output,'summary.json'),JSON.stringify({checks,submissions,errors,viewport:390},null,2));
    console.log('PASS: two real projects, unrelated stale inputs isolated, consumed stale inputs rejected, scoped mapping, refresh, mobile, no analysis submitted');
  } finally {await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
