// Production frontend in Docker; synthetic API fixtures verify UI behavior only.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
async function main(){
 const base=process.env.E2E_BASE_URL,output=process.env.E2E_OUTPUT_DIR;
 assert(base&&output);await fs.mkdir(output,{recursive:true});
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 const page=await context.newPage(),errors=[],reads=[];page.on('pageerror',e=>errors.push(String(e)));
 const id='result-preview-synthetic';
 const job={id,job_id:id,module:'profile',status:'completed',stage:'分析完成',progress:100,project_id:'preview-project',payload:{asset_set:'Set1'},created_at:'2026-10-03T00:00:00Z',started_at:'2026-10-03T00:00:01Z',completed_at:'2026-10-03T00:00:02Z',updated_at:'2026-10-03T00:00:02Z'};
 const outputs=[{kind:'html',label:'分析报告',url:'/fixture/report.html'},
 {kind:'png',label:'分组图表',url:'/fixture/plot.png'},
 {kind:'png',label:'读取失败后可恢复的图表',url:'/fixture/retry.png'},
 {kind:'png',label:'TRB 病例与对照差异图',url:'/fixture/TRB_病例_vs_对照_volcano.png'},
 {kind:'png',label:'TRA 病例与对照差异图',url:'/fixture/TRA_病例_vs_对照_volcano.png'},
 {kind:'csv',label:'样本坐标与统计精度.csv',url:'/fixture/points.csv'},
 {kind:'json',label:'计算参数与输入来源',url:'/fixture/parameters.json'},
 {kind:'json',label:'大型结构化文件',url:'/fixture/large.json'},
 {kind:'json',label:'空结构化文件',url:'/fixture/empty.json'},
 {kind:'json',label:'格式不完整的结构化文件',url:'/fixture/invalid.json'},
 {kind:'zip',label:'完整结果包',url:'/fixture/results.zip'}];
 const extraCount=Number(process.env.E2E_EXTRA_OUTPUTS||0);
 outputs.push(...Array.from({length:extraCount},(_,i)=>({kind:'png',label:'额外图表 '+i,url:'/fixture/unused-'+i+'.png'})));
 const rows=Array.from({length:32},(_,i)=>[String(i+1).padStart(3,'0'),i%2?'研究组':'对照组','1.00000000001e-9']);
 const svg='<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800" viewBox="0 0 1200 800"><rect width="1200" height="800" fill="white"/><text x="600" y="70" text-anchor="middle" font-size="34">合成分组图表：预览交互验收</text><path d="M130 120V660H1100" stroke="#94a3b8" fill="none"/><text x="600" y="740" font-size="28">UMAP1</text>'+Array.from({length:8},(_,i)=>'<circle cx="'+(240+i*105)+'" cy="'+(220+(i%3)*110)+'" r="18" fill="'+(i<4?'#4b77d1':'#a07cd8')+'"/>').join('')+'</svg>';
 let retryReads=0,parameterReads=0;
 const metadataText='{"输入来源": "合成上传", "样本数":32, "mtime_ns":1790983155444449151, "value":1.00000000001e-9}';
 await page.route('**/api/**',async route=>{
  const url=new URL(route.request().url()),p=url.pathname;reads.push(p);
  let body={success:true};
  if(p==='/api/auth/me')body={auth_mode:'internal',username:'内部共享',role:'user'};
  else if(p==='/api/projects')body={success:true,projects:[{id:'preview-project',name:'合成结果浏览验收'}]};
  else if(p==='/api/jobs/modules')body={success:true,modules:[]};
  else if(p==='/api/jobs')body={success:true,jobs:[job],counts:{completed:1},total:1,has_more:false};
  else if(p==='/api/jobs/'+id)body={success:true,job};
  else if(p==='/api/jobs/'+id+'/results')body={success:true,job,status:'completed',outputs,assets:[],result:{comparisons:[{group1:'病例',group2:'对照'}]}};
  else if(p==='/api/jobs/'+id+'/events')return route.fulfill({contentType:'text/event-stream',body:'event: completed\ndata: '+JSON.stringify({success:true,job,status:'completed'})+'\n\n'});
  else if(p==='/api/jobs/'+id+'/table-preview'){
   const data=route.request().postDataJSON(),matches=rows.filter(row=>!data.query||row.some(v=>v.includes(data.query)));
   body={success:true,columns:['sample','分组','精度'],rows:matches.slice(data.offset,data.offset+data.limit),offset:data.offset,limit:data.limit,total_rows:rows.length,matched_rows:matches.length};
  }
  await route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
 });
 await page.route('**/fixture/**',async route=>{
  const p=new URL(route.request().url()).pathname;reads.push(p);
  if(p.endsWith('report.html'))return route.fulfill({contentType:'text/html',body:'<html lang="zh-CN"><meta charset="utf-8"><h2>分析结果概览</h2><p>此报告用于结果浏览交互验收。</p></html>'});
  if(p.endsWith('parameters.json')){
   if(++parameterReads===1)return route.fulfill({status:404,headers:{'cache-control':'no-store'},body:''});
   return route.fulfill({contentType:'application/json',headers:{'cache-control':'no-store'},body:metadataText});
  }
  if(p.endsWith('large.json'))return route.fulfill({contentType:'application/json',body:'{"large":"'+'a'.repeat(3*1024*1024)+'UNREAD_TAIL"}'});
  if(p.endsWith('empty.json'))return route.fulfill({contentType:'application/json',body:''});
  if(p.endsWith('invalid.json'))return route.fulfill({contentType:'application/json',body:'{"unfinished":'});
  if(p.endsWith('retry.png')&&++retryReads===1)return route.fulfill({status:404,headers:{'cache-control':'no-store'},body:''});
  if(p.endsWith('.png'))return route.fulfill({contentType:'image/svg+xml',headers:{'cache-control':'no-store'},body:svg});
  return route.fulfill({body:'synthetic download'});
 });
 const rootUrl=base+'/analysis/script-hub/jobs?job='+id;
 await page.goto(rootUrl);
 const figureTab=page.getByRole('tab',{name:/图表与报告/});await figureTab.waitFor();
 assert.equal(await figureTab.getAttribute('aria-selected'),'true');
 assert(!reads.some(p=>p.endsWith('/table-preview')||p.endsWith('parameters.json')));
 const gallery=page.getByLabel('图表与报告列表',{exact:true});
 assert.equal(await gallery.getByRole('button').count(),Math.min(outputs.filter(o=>['png','html'].includes(o.kind)).length,12));
 assert.equal(reads.filter(p=>p.includes('/unused-')).length,0);
 await page.getByLabel('分析内容',{exact:true}).selectOption({label:'差异比较'});
 await page.getByLabel('受体链',{exact:true}).selectOption({label:'TRB'});
 await page.getByLabel('组间比较',{exact:true}).selectOption({label:'病例 与 对照'});
 assert.equal(await gallery.getByRole('button').count(),1);
 await gallery.getByRole('button',{name:/TRB 病例与对照差异图/}).click();
 await page.reload();await gallery.waitFor();
 assert.equal(await page.getByLabel('受体链',{exact:true}).inputValue(),'TRB');
 assert.equal(await gallery.getByRole('button').count(),1);
 assert.equal(await gallery.getByRole('button').getAttribute('aria-pressed'),'true');
 await page.setViewportSize({width:390,height:844});
 await gallery.getByRole('button').focus();await page.keyboard.press('Enter');
 assert.equal(await page.evaluate(()=>document.activeElement.getAttribute('aria-label')),'当前结果预览');
 await page.getByRole('button',{name:'返回图表列表',exact:true}).click();
 assert.equal(await page.evaluate(()=>document.activeElement.getAttribute('aria-pressed')),'true');
 const gallerySizes=await page.evaluate(()=>({width:innerWidth,document:document.documentElement.scrollWidth}));
 assert(gallerySizes.document<=gallerySizes.width+1,JSON.stringify(gallerySizes));
 await page.screenshot({path:path.join(output,'mobile-filtered-gallery.png'),fullPage:true});
 await page.setViewportSize({width:1440,height:1000});
 await page.getByRole('button',{name:'清除筛选',exact:true}).click();
 await page.getByLabel('查找图表或报告',{exact:true}).fill('不存在的图表');
 await page.getByText('没有匹配的结果，请调整或清除筛选。',{exact:true}).waitFor();
 await page.getByRole('button',{name:'清除筛选',exact:true}).click();
 let thumbnailReads=0;
 if(extraCount>=24){
  await page.getByRole('navigation',{name:'图表列表分页'}).getByRole('button',{name:'下一页',exact:true}).click();
  assert.equal(reads.filter(p=>p.includes('/unused-')).length,0);
  const thumbnailResponse=page.waitForResponse(r=>r.url().includes('/unused-'));
  await page.getByLabel('显示缩略图',{exact:true}).check();
  await gallery.getByRole('button').last().scrollIntoViewIfNeeded();
  await thumbnailResponse;
  await page.waitForFunction(()=>document.querySelectorAll('.result-browser-thumbnail img').length===12&&Array.from(document.querySelectorAll('.result-browser-thumbnail img')).every(i=>i.complete));
  thumbnailReads=reads.filter(p=>p.includes('/unused-')).length;
  assert(thumbnailReads>0&&thumbnailReads<=12,thumbnailReads);
  await page.screenshot({path:path.join(output,'desktop-thumbnail-gallery.png'),fullPage:true});
  await page.getByLabel('显示缩略图',{exact:true}).uncheck();
  await page.getByRole('navigation',{name:'图表列表分页'}).getByRole('button',{name:'上一页',exact:true}).click();
 }

 await page.getByRole('button',{name:/^分组图表/}).click();
 await page.getByRole('button',{name:'放大查看',exact:true}).waitFor();
 await page.waitForFunction(()=>Array.from(document.querySelectorAll('button')).some(b=>b.textContent.trim()==='放大查看'&&!b.disabled));
 await page.getByRole('button',{name:'放大查看',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'图表放大查看'});await dialog.waitFor();
 await dialog.getByRole('button',{name:'放大图表',exact:true}).click();
 assert.equal(await dialog.getByLabel('缩放比例').textContent(),'150%');
 assert(await dialog.locator('.result-image-viewport').evaluate(e=>e.scrollWidth>e.clientWidth));
 await page.screenshot({path:path.join(output,'desktop-expanded.png'),fullPage:true});
 await page.keyboard.press('Escape');assert.equal(await dialog.count(),0);
 assert.equal(await page.evaluate(()=>document.activeElement.textContent.trim()),'放大查看');
 await page.getByRole('button',{name:/^读取失败后可恢复的图表/}).click();
 await page.getByRole('alert').filter({hasText:'图片加载失败'}).waitFor();
 await page.getByRole('button',{name:'重新加载',exact:true}).click();
 await page.waitForFunction(()=>Array.from(document.querySelectorAll('button')).some(b=>b.textContent.trim()==='放大查看'&&!b.disabled));
 assert(retryReads>=2);
 await page.getByRole('tab',{name:/数据表/}).click();
 await page.getByRole('cell',{name:'001',exact:true}).waitFor();
 assert(await page.getByRole('cell',{name:'1.00000000001e-9',exact:true}).count()>0);
 await page.getByRole('tabpanel',{name:'数据表',exact:true}).getByRole('button',{name:'下一页',exact:true}).click();await page.getByRole('cell',{name:'032',exact:true}).waitFor();
 await page.reload();await page.getByRole('tab',{name:/数据表/}).waitFor();
 assert.equal(await page.getByRole('tab',{name:/数据表/}).getAttribute('aria-selected'),'true');
 assert((await page.getByLabel('结果文件',{exact:true}).inputValue()).includes('points.csv'));
 await page.getByRole('tab',{name:'分析详情',exact:true}).click();
 await page.getByText('分析记录与复现参数',{exact:true}).waitFor();
 await page.getByRole('alert').filter({hasText:'结果文件不存在或已移除'}).waitFor();
 await page.getByRole('button',{name:'重新加载',exact:true}).click();
 await page.getByText('"输入来源": "合成上传"',{exact:false}).waitFor();
 assert.equal(await page.getByLabel('文件原文',{exact:true}).textContent(),metadataText);
 assert.equal(parameterReads,2);
 await page.getByLabel('结果文件',{exact:true}).selectOption({label:'JSON · 大型结构化文件'});
 await page.getByText(/仅预览前 2 MB/).waitFor();
 const previewBytes=await page.getByLabel('文件原文',{exact:true}).evaluate(e=>new TextEncoder().encode(e.textContent).byteLength);
 assert(previewBytes<=2*1024*1024);
 assert(!(await page.getByLabel('文件原文',{exact:true}).textContent()).includes('UNREAD_TAIL'));
 await page.setViewportSize({width:390,height:844});
 const largeDetailsSizes=await page.evaluate(()=>({width:innerWidth,document:document.documentElement.scrollWidth,preview:document.querySelector('.text-result-preview pre').getBoundingClientRect().height}));
 assert(largeDetailsSizes.document<=largeDetailsSizes.width+1&&largeDetailsSizes.preview<=401,JSON.stringify(largeDetailsSizes));
 await page.screenshot({path:path.join(output,'mobile-large-structured-preview.png'),fullPage:true});
 await page.getByLabel('结果文件',{exact:true}).selectOption({label:'JSON · 空结构化文件'});
 await page.getByText('结构化数据文件为空。',{exact:true}).waitFor();
 assert.equal(await page.getByLabel('文件原文',{exact:true}).count(),0);
 await page.getByLabel('结果文件',{exact:true}).selectOption({label:'JSON · 格式不完整的结构化文件'});
 await page.getByText(/文件内容无法按 JSON 解析/).waitFor();
 assert.equal(await page.getByLabel('文件原文',{exact:true}).textContent(),'{"unfinished":');
 await page.setViewportSize({width:390,height:844});
 const detailsSizes=await page.evaluate(()=>({width:innerWidth,document:document.documentElement.scrollWidth}));
 assert(detailsSizes.document<=detailsSizes.width+1,JSON.stringify(detailsSizes));
 await page.screenshot({path:path.join(output,'mobile-structured-preview.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});
 await page.getByRole('tab',{name:/图表与报告/}).click();
 await page.getByRole('button',{name:/^分组图表/}).click();
 await page.waitForFunction(()=>Array.from(document.querySelectorAll('button')).some(b=>b.textContent.trim()==='放大查看'&&!b.disabled));
 await page.getByRole('button',{name:'放大查看',exact:true}).click();
 await page.getByRole('dialog',{name:'图表放大查看'}).waitFor();
 await page.getByRole('button',{name:'放大图表',exact:true}).click();
 const sizes=await page.evaluate(()=>({width:innerWidth,document:document.documentElement.scrollWidth,modal:document.querySelector('[role="dialog"]>div').getBoundingClientRect().width}));
 assert(sizes.document<=sizes.width+1,JSON.stringify(sizes));
 await page.screenshot({path:path.join(output,'mobile-expanded.png'),fullPage:true});
 await page.getByRole('button',{name:'关闭',exact:true}).click();
 await page.screenshot({path:path.join(output,'mobile-result.png'),fullPage:true});
 assert.deepEqual(errors,[]);
 assert.equal(reads.filter(p=>p.includes('/unused-')).length,thumbnailReads);
 assert.equal(await page.getByText('任务状态连接已断开。',{exact:true}).count(),0);
 await fs.writeFile(path.join(output,'summary.json'),JSON.stringify({large_details_sizes:largeDetailsSizes,structured_preview_bytes:previewBytes,structured_retry:parameterReads,raw_numeric_text:true,empty_and_invalid_files:true,details_sizes:detailsSizes,sections:true,extra_outputs:extraCount,unselected_image_requests_before_thumbnails:0,thumbnail_requests:thumbnailReads,gallery:true,chain_comparison_filter:true,keyboard_preview_return:true,loads_on_selection:true,restored_selection:true,image_retry:retryReads,zoom:true,escape_focus:true,sizes,errors,scope:'production frontend with synthetic API fixtures; no analysis execution'},null,2));
 await browser.close();console.log(JSON.stringify({passed:true,sizes,retryReads,errors}));
}
main().catch(e=>{console.error(e);process.exit(1)});
