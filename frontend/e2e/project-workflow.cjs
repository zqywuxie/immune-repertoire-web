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
    await page.goto(`${base}/analysis/center`);
    await page.getByRole('button',{name:'新建项目',exact:true}).click();
    await page.getByPlaceholder('项目名称').fill(`流程验收-${Date.now()}`);
    const created = page.waitForResponse(response => response.url().endsWith('/api/projects') && response.request().method()==='POST');
    await page.getByRole('button',{name:'保存',exact:true}).click();
    const creation = await created;
    assert(creation.ok(), await creation.text());
    const project = await creation.json();
    const ids = Array.from({length:8},(_,i)=>`S${String(i+1).padStart(2,'0')}`);
    const file = (name,text)=>({name,mimeType:'text/csv',buffer:Buffer.from(text)});
    const pep = ids.map((id,i)=>file(`${id}__TRB.csv`,`CDR3(pep),V,J,copy\nCASSLGQETQYF,TRBV1,TRBJ2-1,${i+1}\nCASSIRSSYEQYF,TRBV2,TRBJ1-1,2\n`));
    const profile = 'sample,group,IGHA1,TRB_Percent,IGH_Percent\n'+ids.map((id,i)=>`${id},${i<4?'01':'02'},${i+1},${30+i},${70-i}`).join('\n');
    const deconv = 'Mixture,T cells,B cells\n'+ids.map((id,i)=>`${id},${0.1+i*0.1},${0.9-i*0.08}`).join('\n');
    const expression = 'gene_symbol,'+ids.join(',')+'\n'+Array.from({length:60},(_,g)=>'TEST'+g+','+ids.map((_,i)=>50+g*3+(g%4===0&&i>=4?70:0)+((g+i*7)%11)).join(',')).join('\n');
    const inputs = page.locator('input[type=file]');
    await inputs.nth(0).setInputFiles(pep);
    await inputs.nth(1).setInputFiles(file('profile.csv',profile));
    await inputs.nth(2).setInputFiles(file('expression.csv',expression));
    await inputs.nth(3).setInputFiles(file('deconv.csv',deconv));
    await page.getByRole('button',{name:'保存数据',exact:true}).click();
    await page.getByText('数据已保存，可以选择下方分析。',{exact:true}).waitFor({timeout:60000});
    const assets = await (await context.request.get(`${base}/api/projects/${project.id}/assets`)).json();
    assert.equal(assets.assets.length,11);
    assert.deepEqual([...new Set(assets.assets.map(asset=>asset.asset_type))].sort(),['deconvolution','pep','profile','transcriptome']);
    await page.goto(`${base}/analysis/tools/infiltration?project=${project.id}&asset_set=Set1`);
    await page.getByRole('button',{name:'确认数据',exact:true}).click();
    await page.getByRole('button',{name:'检查数据',exact:true}).click();
    const next = page.getByRole('button',{name:'下一步',exact:true});
    for(let attempt=0;attempt<90;attempt++) {
      await page.getByRole('button',{name:'重新检查',exact:true}).waitFor({timeout:30000});
      assert.equal(await page.getByText('页面出现错误',{exact:true}).count(),0);
      if(await next.isEnabled()) break;
      await page.waitForTimeout(3000);
      await page.getByRole('button',{name:'重新检查',exact:true}).click();
    }
    assert(await next.isEnabled(),'Input validation did not complete');
    await next.click();
    await page.getByRole('radio',{name:'相对比例',exact:true}).check();
    await page.getByLabel('分组列',{exact:true}).selectOption('group');
    await page.getByRole('button',{name:'01 / S04',exact:true}).click();
    await page.getByRole('button',{name:'02 / S08',exact:true}).click();
    await page.getByPlaceholder('默认使用分析名称').fill('六样本浸润验收');
    await page.getByRole('button',{name:'核对分析范围',exact:true}).click();
    await page.getByText('分析范围已确认 · 6 个样本',{exact:true}).waitFor();
    await page.screenshot({path:path.join(artifacts,'configured.png'),fullPage:true});
    await next.click();
    const submitted = page.waitForResponse(response=>response.url().endsWith('/api/script-hub/jobs')&&response.request().method()==='POST');
    await page.getByRole('button',{name:'开始分析',exact:true}).click();
    const submission = await submitted;
    assert(submission.ok(),await submission.text());
    const {task_id:jobId} = await submission.json();
    await page.getByRole('button',{name:'查看报告',exact:true}).waitFor({timeout:120000});
    const task = await (await context.request.get(`${base}/api/script-hub/task/${jobId}`)).json();
    assert.equal(task.status,'completed');
    assert.equal(task.payload.queue_backend,'redis');
    assert.deepEqual(task.result.metadata.selected_infiltration_samples,['S01','S02','S03','S05','S06','S07']);
    assert.deepEqual(task.result.metadata.group_counts,{'01':3,'02':3});
    assert.equal(task.result.metadata.output_name,'六样本浸润验收');
    // A real native form download streams the archive without replacing the page.
    const downloading = page.waitForEvent('download');
    await page.getByRole('button',{name:/打包下载所选/}).click();
    const download = await downloading;
    assert.equal(await download.failure(),null);
    await download.saveAs(path.join(artifacts,'selected-results.zip'));
    assert.equal((await fs.readFile(path.join(artifacts,'selected-results.zip'))).subarray(0,2).toString(),'PK');
    await page.getByText('分析记录与复现参数',{exact:true}).click();
    const manifestUrl = await page.getByRole('link',{name:'下载分析记录 JSON',exact:true}).getAttribute('href');
    const manifest = JSON.parse(decodeURIComponent(manifestUrl.split(',').slice(1).join(',')));
    assert.deepEqual(manifest.runs[0].job.payload.config_json.selected_infiltration_samples,task.result.metadata.selected_infiltration_samples);
    assert.equal(manifest.runs[0].job.payload.runtime.system,'Linux');
    assert.equal(manifest.runs[0].job.payload.input_assets.length,2);
    await page.reload();
    await page.getByRole('link',{name:'打开交互报告',exact:true}).waitFor({timeout:60000});
    const opening = context.waitForEvent('page');
    await page.getByRole('link',{name:'打开交互报告',exact:true}).click();
    const report = await opening;
    await report.waitForLoadState();
    assert.match(await report.locator('body').innerText(),/本次分析 6 个实际匹配样本/);
    assert.match(await report.locator('body').innerText(),/01：3 个样本/);
    await report.close();
    const resultSelect = page.locator('select').last();
    const csv = resultSelect.locator('option').filter({hasText:'input.csv'});
    await resultSelect.selectOption(await csv.getAttribute('value'));
    await page.getByRole('columnheader',{name:'sample',exact:true}).waitFor();
    assert.equal(await page.getByRole('cell',{name:'S04',exact:true}).count(),0);
    assert.equal(await page.getByRole('cell',{name:'S08',exact:true}).count(),0);
    assert.equal(await page.getByRole('cell',{name:'S01',exact:true}).count(),1);
    const body = await page.locator('main').innerText();
    assert.doesNotMatch(body,/Viewer|Plots|Metadata/);
    for(const url of [task.result.zip_url,...task.result.csv_urls,...task.result.png_urls]) {
      const response=await context.request.get(`${base}${url}`);
      assert(response.ok(),`${url}: ${response.status()}`);
    }
    await page.setViewportSize({width:390,height:844});
    const width = await page.evaluate(()=>({client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth}));
    assert.equal(width.client,width.scroll);
    await page.screenshot({path:path.join(artifacts,'history-mobile.png'),fullPage:true});
    assert.deepEqual(pageErrors,[]);
    await fs.writeFile(path.join(artifacts,'summary.json'),JSON.stringify({project_id:project.id,job_id:jobId,samples:task.result.metadata.selected_infiltration_samples,groups:task.result.metadata.group_counts,width},null,2));
    console.log('PASS: four input uploads, pending inspection, six-sample RQ execution, manifest, archive download, report, history, table and mobile layout');
  } finally {await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
