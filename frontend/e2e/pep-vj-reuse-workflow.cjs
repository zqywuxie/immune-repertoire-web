// Run inside a Playwright container against an isolated internal application stack.
// Requires E2E_BASE_URL; creates one synthetic project and leaves cleanup to that stack.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');

async function main() {
  const base = process.env.E2E_BASE_URL;
  assert(base, 'E2E_BASE_URL must point to an isolated internal test stack');
  const artifacts = process.env.E2E_OUTPUT_DIR || '/tmp/workflow-artifacts';
  await fs.mkdir(artifacts, {recursive:true});
  const browser = await chromium.launch({
    executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/usr/bin/chromium',
    args:['--no-sandbox'],
  });
  try {
    const context = await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
    const principal = await (await context.request.get(`${base}/api/auth/me`)).json();
    assert.equal(principal.auth_mode, 'internal');
    const page = await context.newPage();
    const pageErrors = [];
    page.on('pageerror', error => pageErrors.push(String(error)));
    async function configureTool() {
      await page.getByRole('button',{name:'确认数据',exact:true}).click();
      await page.getByRole('button',{name:'检查数据',exact:true}).click();
      const next=page.getByRole('button',{name:'下一步',exact:true});
      for(let attempt=0;attempt<90;attempt++) {
        await page.getByRole('button',{name:'重新检查',exact:true}).waitFor({timeout:30000});
        assert.equal(await page.getByText('页面出现错误',{exact:true}).count(),0);
        if(await next.isEnabled()) break;
        await page.waitForTimeout(3000);
        await page.getByRole('button',{name:'重新检查',exact:true}).click();
      }
      assert(await next.isEnabled(),'Input validation did not complete');
      await next.click();
    }
    async function submit() {
      await page.getByRole('button',{name:'下一步',exact:true}).click();
      const submitted=page.waitForResponse(response=>response.url().endsWith('/api/script-hub/jobs')&&response.request().method()==='POST');
      await page.getByRole('button',{name:'开始分析',exact:true}).click();
      let response;
      try {response=await submitted;} catch(error) {await page.screenshot({path:path.join(artifacts,'failed-submit.png'),fullPage:true});console.log(await page.locator('main').innerText());throw error;}
      assert(response.ok(),await response.text());
      const {task_id,reused_result}=await response.json();
      await page.getByRole('button',{name:'查看报告',exact:true}).waitFor({timeout:240000});
      const task=await (await context.request.get(`${base}/api/script-hub/task/${task_id}`)).json();
      assert.equal(task.status,'completed',task.detail);
      if(reused_result) assert.equal(task.result.reused_result,true);
      else assert.equal(task.payload.queue_backend,'redis');
      return task;
    }

    const project={id:process.env.E2E_PROJECT_ID};
    assert(project.id,'Use only a synthetic project in the isolated test stack');
    const selected=['01','02'].flatMap(group=>Array.from({length:3},(_,i)=>`tpm_${group}_${String(i+1).padStart(3,'0')}__TRB.csv`));
    let upstream;
    const resume=process.env.E2E_RESUME_UPSTREAM;
    if(resume) {
      upstream=await (await context.request.get(`${base}/api/script-hub/task/${resume}`)).json();
      assert.equal(upstream.status,'completed');
      assert.equal(upstream.project_id,project.id);
      await page.goto(`${base}/analysis/tools/sharing?project=${project.id}&asset_set=Set1&job=${resume}`);
    } else {
    await page.goto(`${base}/analysis/tools/sharing?project=${project.id}&asset_set=Set1`);
    await configureTool();
    const groupSelect=page.getByRole('combobox').filter({has:page.getByRole('option',{name:'选择分组列',exact:true})});
    await groupSelect.selectOption('group');
    await page.getByRole('button',{name:'添加',exact:true}).click();
    await page.getByRole('button',{name:'01 (4)',exact:true}).waitFor();
    await page.getByRole('button',{name:'全部分组',exact:true}).click();
    await page.getByRole('button',{name:'tpm_01_001',exact:true}).waitFor();
    for(const step of ['5','6','7','8']) await page.getByRole('button',{name:new RegExp(`^步骤 ${step} 可选`)}).click();
    await page.getByPlaceholder('默认使用任务名称').fill('共享结果来源验收');
    await page.screenshot({path:path.join(artifacts,'pep-configured.png'),fullPage:true});
    upstream=await submit();
    }
    const candidatesResponse=await context.request.get(`${base}/api/script-hub/pep-cache-candidates?project_id=${project.id}&asset_set=Set1&cache_type=volcano`);
    assert(candidatesResponse.ok(),await candidatesResponse.text());
    const candidates=(await candidatesResponse.json()).candidates.filter(candidate=>candidate.status==='available'&&candidate.job_id===upstream.task_id&&candidate.path.includes('/usage_cate/'));
    const candidate=candidates.find(candidate=>candidate.usage_type==='1VJusage');
    assert(candidate,JSON.stringify(candidates));
    const link=page.getByRole('region',{name:'继续分析',exact:true}).getByRole('link',{name:'V/J 使用差异',exact:true});
    await link.first().waitFor();
    const urls=await link.evaluateAll(links=>links.map(link=>link.getAttribute('href')));
    const target=urls.find(url=>new URL(url,base).searchParams.get('upstream_artifact')===candidate.artifact_id);
    assert(target,JSON.stringify({urls,candidate}));
    await page.locator(`a[href=${JSON.stringify(target)}]`).click();
    await configureTool();
    assert.equal(await page.getByLabel('选择前置分析结果',{exact:true}).inputValue(),candidate.artifact_id);
    await page.getByRole('button',{name:'01 / tpm_01_004__TRB.csv',exact:true}).click();
    await page.getByRole('button',{name:'02 / tpm_02_004__TRB.csv',exact:true}).click();
    await page.getByRole('button',{name:'交换 01 与 02 的比较方向',exact:true}).click();
    await page.getByPlaceholder('默认使用任务名称').fill('六样本反向基因使用差异');
    await page.screenshot({path:path.join(artifacts,'vj-configured.png'),fullPage:true});
    const downstream=await submit();
    assert.deepEqual(downstream.result.metadata.selected_samples,selected);
    assert.equal(downstream.result.metadata.sample_count,6);
    assert.equal(downstream.payload.upstream_input.source_job_id,upstream.task_id);
    assert.equal(downstream.payload.upstream_input.artifact_id,candidate.artifact_id);
    assert.deepEqual(downstream.payload.config_json.comparisons,[['02','01']]);
    for(const url of [...downstream.result.csv_urls,downstream.result.zip_url,downstream.result.viewer_url]) {
      const response=await context.request.get(`${base}${url}`);
      assert(response.ok(),`${url}: ${response.status()}`);
    }
    await fs.writeFile(path.join(artifacts,'summary.json'),JSON.stringify({project_id:project.id,upstream_task_id:upstream.task_id,downstream_task_id:downstream.task_id,artifact_id:candidate.artifact_id,selected,metadata:downstream.result.metadata},null,2));
    assert.deepEqual(pageErrors,[]);
    console.log('PASS: real PEP/RQ, explicit registered usage artifact, linked context, six actual samples, reverse comparison, native results and retrieval');
  } finally {await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
