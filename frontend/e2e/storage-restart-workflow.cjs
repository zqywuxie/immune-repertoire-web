// Run only against the isolated stack used by expression-reuse-workflow.cjs.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');

async function main() {
  const base = process.env.E2E_BASE_URL;
  const previous = process.env.E2E_STORAGE_SUMMARY;
  assert(base && previous, 'Requires isolated stack URL and the previous workflow summary');
  const old = JSON.parse(await fs.readFile(previous, 'utf8'));
  const artifacts = process.env.E2E_OUTPUT_DIR || '/tmp/storage-restart';
  await fs.mkdir(artifacts, {recursive:true});
  const browser = await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
  try {
    const context = await browser.newContext({viewport:{width:1440,height:1000}});
    const request = context.request;
    const principal = await (await request.get(`${base}/api/auth/me`)).json();
    assert.equal(principal.auth_mode, 'internal');
    const getTask = async id => {
      const response = await request.get(`${base}/api/script-hub/task/${id}`);
      assert(response.ok(), await response.text());
      return response.json();
    };
    const before = await getTask(old.downstream_task_id);
    const upstream = await getTask(old.upstream_task_id);
    assert.equal(before.status, 'completed');
    assert.match(before.result.output_base, /^\/storage\/分析 结果\/zhengqinyun\/\d{8}_\d{6}\/go-kegg-enrichment\/go-kegg-enrichment_[a-f0-9]{12}$/);
    const initial = await (await request.get(`${base}/api/projects/${old.project_id}/assets`)).json();
    const originals = initial.assets.filter(asset=>asset.asset_type!=='processed_result');
    assert.equal(originals.length, 11);
    for (const asset of originals) {
      assert.match(asset.storage_path, /^\/storage\/上传 数据\/zhengqinyun\/\d{8}_\d{6}__[a-f0-9]{8}\//);
      const response = await request.get(`${base}/api/assets/${asset.id}/download`);
      assert(response.ok(), await response.text());
      assert((await response.body()).length>0);
    }
    const reusedCsv = before.result.csv_urls.find(url=>decodeURIComponent(url).includes('DEG_02_vs_01.csv'));
    const csv = await request.get(`${base}${reusedCsv}`);
    assert(csv.ok());
    assert((await csv.text()).includes('gene_symbol'));
    const archive = await request.get(`${base}${before.result.zip_url}`);
    assert(archive.ok());
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error=>errors.push(String(error)));
    await page.goto(`${base}/analysis/tools/go-kegg?project=${old.project_id}&asset_set=Set1&job=${old.downstream_task_id}`);
    await page.getByLabel('结果文件',{exact:true}).waitFor({timeout:60000});
    await page.screenshot({path:path.join(artifacts,'recreated-result.png'),fullPage:true});
    assert.deepEqual(errors, []);

    const created = await request.post(`${base}/api/projects`,{data:{name:`独立挂载重建验收-${Date.now()}`}});
    assert(created.ok(),await created.text());
    const other = await created.json();
    const text = 'sample,group,metric\n'+['01','02'].flatMap(group=>Array.from({length:4},(_,i)=>`S${group}${i+1},${group},${Number(group)*10+i}`)).join('\n');
    const uploaded = await request.post(`${base}/api/projects/${other.id}/assets`, {multipart:{
      asset_type:'profile',metadata:JSON.stringify({asset_set:'Set1'}),
      files:{name:'profile.csv',mimeType:'text/csv',buffer:Buffer.from(text)},
    }});
    assert(uploaded.ok(),await uploaded.text());
    const assetData = await (await request.get(`${base}/api/projects/${other.id}/assets`)).json();
    const otherAsset = assetData.assets.find(asset=>asset.asset_type==='profile');
    assert(otherAsset);
    let validation = otherAsset.metadata?.validation?.status;
    for(let attempt=0;validation==='pending' && attempt<90;attempt++) {
      await page.waitForTimeout(2000);
      const checked = await (await request.get(`${base}/api/projects/${other.id}/assets`)).json();
      validation = checked.assets.find(asset=>asset.id===otherAsset.id)?.metadata?.validation?.status;
    }
    assert.equal(validation,'valid');
    const submitted = await request.post(`${base}/api/script-hub/profile/run`,{data:{
      project_id:other.id,asset_set:'Set1',grouptype_fields:['group'],
      param_begin:'metric',param_over:'metric',force_rerun:true,
    }});
    assert(submitted.ok(),await submitted.text());
    const submittedTask = await submitted.json();
    let newTask;
    for(let attempt=0;attempt<120;attempt++) {
      newTask = await getTask(submittedTask.task_id);
      if(['completed','failed','cancelled','interrupted'].includes(newTask.status)) break;
      await page.waitForTimeout(2000);
    }
    assert.equal(newTask.status,'completed',JSON.stringify(newTask));
    assert.equal(newTask.payload.queue_backend,'redis');
    assert.match(newTask.result.output_base,/^\/storage\/分析 结果\/zhengqinyun\/\d{8}_\d{6}\/boxplot\/boxplot_[a-f0-9]{12}$/);
    const report = await request.get(`${base}${newTask.result.viewer_url}`);
    assert(report.ok());
    const deleted = await request.delete(`${base}/api/projects/${old.project_id}`);
    assert(deleted.ok(),await deleted.text());
    assert.equal((await request.get(`${base}/api/script-hub/task/${old.upstream_task_id}`)).status(),404);
    assert.equal((await request.get(`${base}/api/script-hub/task/${old.downstream_task_id}`)).status(),404);
    const otherDownload = await request.get(`${base}/api/assets/${otherAsset.id}/download`);
    assert(otherDownload.ok());
    assert.equal(await otherDownload.text(),text);
    assert((await request.get(`${base}${newTask.result.viewer_url}`)).ok());
    await fs.writeFile(path.join(artifacts,'summary.json'),JSON.stringify({
      deleted_project_id:old.project_id,deleted_upload_paths:originals.map(asset=>asset.storage_path),
      deleted_output_paths:[before.result.output_base,upstream.result.output_base],
      preserved_project_id:other.id,preserved_upload_path:otherAsset.storage_path,
      new_task_id:submittedTask.task_id,new_output_path:newTask.result.output_base,
    },null,2));
    console.log('PASS: rebuilt image without source mount, history and original downloads, fresh native RQ task, project deletion and sibling preservation');
  } finally {await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
