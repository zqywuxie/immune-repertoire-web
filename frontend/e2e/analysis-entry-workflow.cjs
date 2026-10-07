// Read-only interaction acceptance against an existing synthetic project.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
async function main() {
  const base=process.env.E2E_BASE_URL,previous=process.env.E2E_STORAGE_SUMMARY;
  assert(base&&previous,'Requires an isolated stack and synthetic workflow summary');
  const {project_id}=JSON.parse(await fs.readFile(previous,'utf8'));
  const artifacts=process.env.E2E_OUTPUT_DIR||'/tmp/analysis-entry';
  await fs.mkdir(artifacts,{recursive:true});
  const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
  try {
    const context=await browser.newContext({viewport:{width:1440,height:1000}});
    const project=await (await context.request.get(`${base}/api/projects/${project_id}`)).json();
    const page=await context.newPage();
    const errors=[];let submissions=0;
    page.on('pageerror',error=>errors.push(String(error)));
    page.on('request',request=>{if(request.method()==='POST'&&request.url().endsWith('/api/script-hub/jobs'))submissions++;});
    await page.goto(`${base}/analysis/tools/expression?project=${project_id}&asset_set=Set1`);
    await page.getByRole('heading',{name:'配置参数与分组',exact:true}).waitFor({timeout:60000});
    await page.getByText(`当前项目：${project.name} · 数据集：Set1`,{exact:true}).waitFor();
    await page.getByRole('region',{name:'本次分析数据',exact:true}).waitFor();
    await page.screenshot({path:path.join(artifacts,'desktop.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.join(artifacts,'mobile.png'),fullPage:true});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),'Page overflows mobile viewport');
    await page.getByRole('button',{name:'更换或检查数据',exact:true}).click();
    await page.getByRole('heading',{name:'选择或上传数据',exact:true}).waitFor();
    await page.waitForTimeout(4000);
    assert.equal(await page.getByRole('heading',{name:'配置参数与分组',exact:true}).count(),0);
    await page.getByRole('button',{name:'下一步',exact:true}).click();
    await page.getByRole('heading',{name:'配置参数与分组',exact:true}).waitFor();
    await page.reload();
    await page.getByRole('heading',{name:'配置参数与分组',exact:true}).waitFor({timeout:60000});
    await page.getByText(`当前项目：${project.name} · 数据集：Set1`,{exact:true}).waitFor();
    assert.equal(submissions,0,'Reading/changing input context must not start computation');
    assert.deepEqual(errors,[]);
    await fs.writeFile(path.join(artifacts,'summary.json'),JSON.stringify({project_id,project_name:project.name,asset_set:'Set1',submissions,viewport:390},null,2));
    console.log('PASS: verified project enters configuration, current context shown, input review stays open, refresh restores context, mobile layout, no computation started');
  } finally {await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
