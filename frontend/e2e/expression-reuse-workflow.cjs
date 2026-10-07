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
    const resume = process.env.E2E_RESUME_UPSTREAM;
    let project;
    const ids = ['01','02'].flatMap(group=>Array.from({length:4},(_,i)=>`tpm_${group}_${String(i+1).padStart(3,'0')}`));
    if (resume) {
      const task = await (await context.request.get(`${base}/api/script-hub/task/${resume}`)).json();
      assert.equal(task.status,'completed');
      project = {id:task.project_id};
      await page.goto(`${base}/analysis/tools/expression?project=${project.id}&asset_set=Set1&job=${resume}`);
    } else {
    await page.goto(`${base}/analysis/center`);
    await page.getByRole('button',{name:'新建项目',exact:true}).click();
    await page.getByPlaceholder('项目名称').fill(`结果复用验收-${Date.now()}`);
    const created = page.waitForResponse(response => response.url().endsWith('/api/projects') && response.request().method()==='POST');
    await page.getByRole('button',{name:'保存',exact:true}).click();
    const creation = await created;
    assert(creation.ok(), await creation.text());
    project = await creation.json();
    const file = (name,text)=>({name,mimeType:'text/csv',buffer:Buffer.from(text)});
    const pep = ids.map((id,i)=>file(`${id}__TRB.csv`,`CDR3(pep),V,J,copy\nCASSLGQETQYF,TRBV1,TRBJ2-1,${i+1}\nCASSIRSSYEQYF,TRBV2,TRBJ1-1,2\n`));
    const profile = 'sample,group,IGHA1,TRB_Percent,IGH_Percent\n'+ids.map((id,i)=>`${id},${i<4?'01':'02'},${i+1},${30+i},${70-i}`).join('\n');
    const deconv = 'Mixture,T cells,B cells\n'+ids.map((id,i)=>`${id},${0.1+i*0.1},${0.9-i*0.08}`).join('\n');
    const expression = 'gene_symbol,'+ids.join(',')+'\n'+'TP53 EGFR CD3D CD3E CD3G CD247 CD4 CD8A CD8B LCK ZAP70 LAT LCP2 ITK FYN PTPRC CD28 CTLA4 ICOS PDCD1 IL2 IL2RA IL2RB JAK1'.split(' ').map((gene,g)=>gene+','+ids.map((_,i)=>50+g*3+(g%4===0&&i>=4?70:0)+((g+i*7)%11)).join(',')).join('\n');
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

    }
    const selected = ids.filter((_,i)=>i!==3&&i!==7);
    async function configureTool() {
      await page.getByRole('heading',{name:'配置参数与分组',exact:true}).waitFor({timeout:240000});
      assert.equal(await page.getByText('页面出现错误',{exact:true}).count(),0);
      await page.getByRole('region',{name:'本次分析数据',exact:true}).waitFor();
      assert.equal(await page.getByRole('button',{name:'开始分析',exact:true}).count(),0);

    }
    async function submit() {
      await page.getByRole('button',{name:'下一步',exact:true}).click();
      const submitted=page.waitForResponse(response=>response.url().endsWith('/api/script-hub/jobs')&&response.request().method()==='POST');
      await page.getByRole('button',{name:'开始分析',exact:true}).click();
      const response=await submitted;
      assert(response.ok(),await response.text());
      const {task_id,reused_result}=await response.json();
      await page.getByRole('button',{name:'查看报告',exact:true}).waitFor({timeout:240000});
      const task=await (await context.request.get(`${base}/api/script-hub/task/${task_id}`)).json();
      assert.equal(task.status,'completed',task.detail);
      if(reused_result) assert.equal(task.result.reused_result,true);
      else assert.equal(task.payload.queue_backend,'redis');
      return task;
    }
    let upstream;
    if (resume) upstream=await (await context.request.get(`${base}/api/script-hub/task/${resume}`)).json();
    else {
    await page.goto(`${base}/analysis/tools/expression?project=${project.id}&asset_set=Set1`);
    await configureTool();
    await page.getByRole('button',{name:'01 / tpm_01_004',exact:true}).click();
    await page.getByRole('button',{name:'02 / tpm_02_004',exact:true}).click();
    await page.getByRole('button',{name:'交换 01_vs_02 的比较方向',exact:true}).click();
    await page.getByLabel('p 值阈值',{exact:true}).fill('1e-300');
    await page.getByLabel('对数倍数变化阈值',{exact:true}).fill('0');
    await page.getByPlaceholder('默认使用任务名称').fill('六样本反向差异表达');
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.join(artifacts,'expression-mobile.png'),fullPage:true});
    await page.setViewportSize({width:1440,height:1000});
    await page.screenshot({path:path.join(artifacts,'expression-configured.png'),fullPage:true});
    upstream=await submit();
    }
    assert.deepEqual(upstream.result.metadata.selected_expression_samples,selected);
    const link=page.getByRole('region',{name:'继续分析',exact:true}).getByRole('link',{name:'GO / KEGG 富集',exact:true});
    await link.waitFor({timeout:60000});
    const url=new URL(await link.getAttribute('href'),base);
    assert.equal(url.searchParams.get('project'),project.id);
    assert.equal(url.searchParams.get('asset_set'),'Set1');
    const artifactId=url.searchParams.get('upstream_artifact');
    assert(artifactId);
    await link.click();
    await configureTool();
    await page.getByLabel('来源差异表达结果',{exact:true}).waitFor();
    assert.equal(await page.getByLabel('输入方式',{exact:true}).inputValue(),'deg');
    assert.equal(await page.getByLabel('来源差异表达结果',{exact:true}).inputValue(),artifactId);
    await page.getByRole('checkbox',{name:'运行基因集富集分析',exact:true}).uncheck();
    await page.getByPlaceholder('默认使用任务名称').fill(`直接复用六样本差异结果-${Date.now()}`);
    await page.screenshot({path:path.join(artifacts,'enrichment-configured.png'),fullPage:true});
    const downstream=await submit();
    assert.equal(downstream.result.metadata.reused_differential_results,true);
    assert.equal(downstream.result.metadata.do_gsea,false);
    assert.deepEqual(downstream.result.metadata.selected_expression_samples,selected);
    assert.equal(downstream.result.metadata.sample_count,6);
    assert.equal(downstream.result.metadata.logfc_cutoff,0);
    assert.equal(downstream.payload.upstream_input.artifact_id,artifactId);
    assert.equal(downstream.payload.upstream_input.source_job_id,upstream.task_id);
    const degUrl=task=>task.result.csv_urls.find(url=>decodeURIComponent(url).includes('DEG_02_vs_01.csv'));
    assert(degUrl(upstream));assert(degUrl(downstream));
    const original=await context.request.get(`${base}${degUrl(upstream)}`);
    const reused=await context.request.get(`${base}${degUrl(downstream)}`);
    assert(original.ok()&&reused.ok());
    assert((await original.body()).equals(await reused.body()),'Reused DEG differs from original');
    const report=await context.request.get(`${base}${downstream.result.viewer_url}`);
    assert(report.ok());
    assert.match(await report.text(),/沿用来源比较、实际样本范围与筛选标记/);
    assert.match(await report.text(),/本次未运行 GSEA/);
    const downloading=page.waitForEvent('download');
    await page.getByRole('button',{name:/打包下载所选/}).click();
    const download=await downloading;
    assert.equal(await download.failure(),null);
    await download.saveAs(path.join(artifacts,'enrichment-results.zip'));
    const resultSelect=page.getByLabel('结果文件',{exact:true});
    const degOption=await resultSelect.locator('option').evaluateAll(options=>options.map(option=>option.value).find(value=>decodeURIComponent(value).includes('DEG_02_vs_01.csv')));
    assert(degOption);
    await resultSelect.selectOption(degOption);
    await page.getByRole('columnheader',{name:'gene_symbol',exact:true}).waitFor();
    await page.reload();
    await page.getByLabel('结果文件',{exact:true}).waitFor({timeout:60000});
    assert(decodeURIComponent(await page.getByLabel('结果文件',{exact:true}).inputValue()).includes('DEG_02_vs_01.csv'));
    await page.getByRole('columnheader',{name:'gene_symbol',exact:true}).waitFor();
    await page.screenshot({path:path.join(artifacts,'restored-table.png'),fullPage:true});
    assert.deepEqual(pageErrors,[]);
    await fs.writeFile(path.join(artifacts,'summary.json'),JSON.stringify({project_id:project.id,upstream_task_id:upstream.task_id,downstream_task_id:downstream.task_id,artifact_id:artifactId,selected,upstream:upstream.result.metadata,downstream:downstream.result.metadata},null,2));
    console.log('PASS: four input uploads, six expression columns, reverse comparison, real native R/RQ, continue-analysis context, registered DEG reuse, identical DEG, download, history');
  } finally {await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
