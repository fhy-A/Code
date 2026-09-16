const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const {chromium, expect} = require('@playwright/test');
const {startIsolatedHost, getActiveChildCount} = require('./isolated-host.cjs');
const sha = value => crypto.createHash('sha256').update(value).digest('hex');

async function main() {
  const evidence=await fs.mkdtemp(path.join(os.tmpdir(),'code042-task-review-'));
  console.log(`EVIDENCE ${evidence}`);
  const host=await startIsolatedHost({disableRoutingV2:true});
  let browser,context,cleanup,page;
  const checks=[],errors=[],routes=[],themeSamples=[];
  const themeOnly=process.argv.includes('--theme-colors');
  const duplicateOnly=process.argv.includes('--duplicate-refs');
  const totalsOnly=process.argv.includes('--card-totals');
  const deleteOnly=process.argv.includes('--delete-evidence');
  const toolbarOnly=process.argv.includes('--toolbar-only');
  const api=async(url,body,method="POST")=>{
    const response=await fetch(host.ready.codeUrl+url,body?{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});
    assert(response.ok,`${response.status} ${url}: ${await response.clone().text()}`);return response.json();
  };
  try {
    if(toolbarOnly) {
      await fs.writeFile(path.join(host.projectDir,'toolbar.py'),'print("toolbar fixture")\n');
      await fs.writeFile(path.join(host.projectDir,'toolbar.md'),'# Toolbar fixture\n\nMarkdown preview modes.\n');
    }
    const a=await api('/api/sessions',{title:'Recorded changes A',cwd:host.projectDir});
    const b=await api('/api/sessions',{title:'Recorded changes B',cwd:host.projectDir});
    const binding=await api('/api/preview/context',{sessionId:a.id});
    const records=[],messages=[];
    await fs.mkdir(path.join(host.dataDir,'agent-runs'),{recursive:true});
    for(const [index,status] of ['completed','failed','cancelled'].entries()) {
      const id=String(index+1).repeat(32),diff=index===0?'--- a/demo.txt\n+++ b/demo.txt\n@@ -1,9 +1,9 @@\n first\n second\n-old\n+<script>never_execute()</script>\n fourth\n fifth\n sixth\n seventh\n eighth\n ninth\n@@ -20,3 +20,3 @@\n twenty\n-old21\n+updated21\n twentyTwo\n':'--- a/demo.txt\n+++ b/demo.txt\n@@ -1 +1 @@\n-old\n+<script>never_execute()</script>\n';
      const actual=path.join(host.projectDir,'demo.txt').toLowerCase();
      const receipt={schema:'code-file-change-receipt/v1',canonicalPath:actual,fileKey:sha(JSON.stringify(actual)),kind:'update',entityKind:'file',operationId:'op-1',diffSemantics:'normalized-lines',diffSha256:sha(diff),bodyState:'diff'};
      const record={version:7,id,sessionId:a.id,status,runKind:'foreground',clientRequestId:`request-${index}`,reviewBinding:{schema:'code-run-review-binding/v1',dataSourceId:binding.dataSourceId,sessionId:a.id,sessionInstanceId:binding.sessionInstanceId,rootRunId:id,rootClientRequestId:`request-${index}`,originMessageId:`message-${index}`,originRoot:host.projectDir},toolExecutions:{'call-1':{name:'write_file',status:'completed',operationId:'op-1',arguments:'PRIVATE ARGUMENT MUST NOT LEAK',result:{ok:true,action:'write_file',replayed:false,diff,fileChange:receipt}}},result:{},steerReceipts:[]};
      if(index===0) {
        for(const [n,name] of ['demo.txt','deleted.txt','src/app.js','notes.md','src/components/review/very-long-folder-name/styles.css'].entries()) {
          const target=path.join(host.projectDir,name).toLowerCase(),operationId=`extra-${n}`,deleted=name==='deleted.txt';
          record.toolExecutions[operationId]={name:deleted?'delete_file':'write_file',status:'completed',operationId,
            result:{ok:true,action:deleted?'delete_file':'write_file',replayed:false,...(!deleted?{diff}:{}),fileChange:{...receipt,canonicalPath:target,fileKey:sha(JSON.stringify(target)),operationId,kind:deleted?'delete':'update',bodyState:deleted?'not-retained':'diff',diffSha256:deleted?null:sha(diff)}}};
        }
      }
      if(status==='cancelled')record.toolExecutions['lost-call']={name:'run_command',status:'cancelled',result:{ok:false}};
      if((totalsOnly||deleteOnly) && index===0) {
        record.toolExecutions={};
        const operations=[['notes.md','create','--- a/notes.md\n+++ b/notes.md\n@@ -0,0 +1,3 @@\n+one\n+two\n+three\n'],
          ['notes.md','update','--- a/notes.md\n+++ b/notes.md\n@@ -1,3 +1,3 @@\n-one\n-two\n+ONE\n+TWO\n three\n'],
          ['temporary.txt','create','--- a/temporary.txt\n+++ b/temporary.txt\n@@ -0,0 +1 @@\n+temporary\n'],['temporary.txt','delete',null]];
        for(const [n,[name,kind,body]] of operations.entries()) {
          const target=path.join(host.projectDir,name).toLowerCase(),operationId=`total-${n}`,deleted=kind==='delete';
          record.toolExecutions[operationId]={name:deleted?'delete_file':'write_file',status:'completed',operationId,
            result:{ok:true,action:deleted?'delete_file':'write_file',replayed:false,...(!deleted?{diff:body}:{}),fileChange:{...receipt,canonicalPath:target,fileKey:sha(JSON.stringify(target)),operationId,kind,bodyState:deleted?'not-retained':'diff',diffSha256:deleted?null:sha(body)}}};
        }
      }
      await fs.writeFile(path.join(host.dataDir,'agent-runs',`${id}.json`),JSON.stringify(record));records.push(record);
      messages.push({role:'user',content:`Task ${status}`,meta:{recordedChangeReview:{rootRunId:id,recordedFileCount:999,incomplete:false}}},{role:'assistant',content:`Terminal ${status}`,meta:{agentRunId:id,_agentRunTerminal:true,_responseTime:'1.2s',_usage:{input:100,output:24},...(duplicateOnly?{recordedChangeReview:{rootRunId:id,recordedFileCount:777,incomplete:false}}:{})}});
    }
    const proposalDiff='--- a/proposal.js\n+++ b/proposal.js\n@@ -1,6 +1,6 @@\n first\n-old\n+<script>proposal_safe()</script>\n third\n fourth\n fifth\n sixth\n@@ -20,3 +20,3 @@\n twenty\n-old21\n+updated21\n twentyTwo\n';
    if(!deleteOnly&&!totalsOnly&&!themeOnly&&!duplicateOnly) {
      for(const [index,extra] of [{},{applied:true},{outcome:'failed'},{action:'write_file'},{},{}].entries()) messages.push({role:'tool-result',content:index===3?Array(48).fill('<b>raw file text</b>').join('\n'):index===4?'@@ invalid diff\n'+Array(45).fill('<b>raw diff text</b>').join('\n'):index===5?'@@ -0,0 +1,45 @@\n'+Array(45).fill('+new line').join('\n'):proposalDiff,meta:{pendingEditId:'visual-proposal-'+index,action:'propose_edit',path:path.join(host.projectDir,'proposal.js'),...extra}});
    }
    if(deleteOnly) {
      const fixture=await host.command('seed-code042-delete-review',{sessionId:a.id},10000);
      assert(fixture.privateEvidenceRetained && fixture.publicProjectionClean);
      records[0].id=fixture.runId;messages[0].meta.recordedChangeReview.rootRunId=fixture.runId;messages[1].meta.agentRunId=fixture.runId;
      checks.push('actual isolated write/apply/write/delete persisted in Run; public Run excludes private evidence');
    }
    const current=await api(`/api/sessions/${a.id}`);
    await api(`/api/sessions/${a.id}`,{title:'Recorded changes A',messages,expectedRevision:current.revision},'PUT');
    browser=await chromium.launch({headless:true});
    for(const runtime of ['bundle','classic']) {
      const initialRouteCount=routes.length;
      context=await browser.newContext({viewport:{width:1280,height:900},serviceWorkers:'block'});
      let gate=null,fileGate=null,fileHeld=false,summaryRequests=0,fileRequests=0;
      await context.route('**/*',async route=>{
        const url=new URL(route.request().url());
        try {
          if(!['127.0.0.1','localhost','::1'].includes(url.hostname))return await route.abort();
          if(url.pathname==='/api/image-routes/refresh')return await route.fulfill({json:{version:1,routes:[],ok:true}});
          if(url.pathname==='/api/code/sync-keys')return await route.fulfill({json:{tokens:[],keys:{}}});
          if(url.pathname.endsWith('/file-changes')){summaryRequests++;if(gate)await gate;}
          if(url.pathname==='/api/preview/file')fileRequests++;
          if(fileGate && url.pathname==='/api/preview/file'){fileHeld=true;await fileGate;}
          await route.continue();
        }catch(error){errors.push({url:url.pathname,error:String(error)});}
      });
      await context.addInitScript(({id,token})=>{
        window.marked={Renderer:class{},setOptions(){},parse:text=>String(text)};
        localStorage.setItem('code-key-config','[]');localStorage.setItem('code-platform-auth',JSON.stringify({token,userId:'42',username:'fixture'}));
        if(!sessionStorage.getItem('review-seeded')){localStorage.setItem('code-lang','en');localStorage.setItem('code-last-session',id);sessionStorage.setItem('review-seeded','1');}
        localStorage.setItem('code-foreground-view','session');localStorage.setItem('code-expanded-project-sessions',JSON.stringify({__unassigned_sessions__:true}));
      },{id:a.id,token:host.platformToken});
      page=await context.newPage();page.on('pageerror',error=>errors.push(String(error)));
      page.on('response',async response=>{if(response.url().includes('/file-changes'))routes.push({url:response.url(),status:response.status(),body:await response.text().catch(()=>null)});});
      await page.goto(host.ready.codeUrl+(runtime==='classic'?'/dist/frontend/index.classic.html':'/'));
      await page.waitForLoadState('networkidle');
      await expect(page.locator('[data-recorded-review]')).toHaveCount(3);
      await expect(page.locator('.recorded-change-summary').first()).not.toContainText('Files recorded:');
      assert(!await page.locator('.workbench').evaluate(el=>el.classList.contains('preview-open')));
      checks.push(`${runtime}: three terminal/history entries without automatic focus`);
      assert.equal(routes.length,initialRouteCount);
      await page.locator('[data-review-load]').first().click();
      const firstCard=page.locator('[data-review-card]').first();
      if(toolbarOnly) {
        const toolbar=page.locator('.preview-head .preview-actions'),tabs=page.locator('#previewTabs [role=tab]'),current=page.locator('#previewTabs [aria-selected=true]');
        const file=name=>page.locator(`.file-item[data-path="${name}"]`);
        const tab=name=>tabs.filter({hasText:name});
        await expect(page.locator('#closePreview')).toHaveCount(0);
        await file('toolbar.py').click();await expect(page.locator('#filePreview')).toContainText('print("toolbar fixture")');
        await expect(toolbar).toBeVisible();await expect(page.locator('#refreshPreview')).toBeEnabled();await expect(page.locator('#copyPreview')).toBeEnabled();
        const beforeRefresh=fileRequests;await page.locator('#refreshPreview').click();await expect.poll(()=>fileRequests).toBeGreaterThan(beforeRefresh);
        await expect(page.locator('#filePreview')).toContainText('toolbar fixture');
        await page.locator('#togglePreview').click();await expect(page.locator('.workbench')).not.toHaveClass(/preview-open/);await expect(page.locator('#togglePreview')).toBeFocused();
        await page.locator('#togglePreview').click();await expect(page.locator('#filePreview')).toContainText('toolbar fixture');await expect(tabs).toHaveCount(1);
        checks.push(`${runtime}: toolbar close removed; Python refresh/copy retained; global collapse/reopen keeps file and focus`);
        await file('toolbar.md').click({modifiers:['Control']});await expect(tabs).toHaveCount(2);await expect(page.locator('#filePreview')).toHaveClass(/markdown-preview/);
        await expect(page.locator('#previewModeActions button')).toHaveCount(2);await expect(toolbar).toBeVisible();
        await page.locator('#previewModeActions button').last().click();await expect(page.locator('#filePreview')).toHaveClass(/code-preview/);
        await page.locator('#previewModeActions button').first().click();await expect(page.locator('#filePreview')).toHaveClass(/markdown-preview/);
        await firstCard.locator('.recorded-change-heading [data-recorded-review]').click();await expect(tabs).toHaveCount(3);await expect(page.locator('.review-operation')).toHaveCount(6);await expect(toolbar).toBeHidden();
        const gap=await page.locator('.preview-head').evaluate(head=>head.getBoundingClientRect().bottom-head.querySelector('#previewTabs').getBoundingClientRect().bottom);assert(gap<=2,`empty toolbar gap: ${gap}`);
        // Check the status-only CSS branch without simulating a new product action.
        await page.locator('#previewStatus').evaluate(el=>{el.textContent='fixture loading status';el.hidden=false;});await expect(toolbar).toBeVisible();
        await page.locator('#previewStatus').evaluate(el=>{el.textContent='';el.hidden=true;});await expect(toolbar).toBeHidden();
        checks.push(`${runtime}: Markdown modes preserved; review has no empty toolbar; status-only row remains visible when needed`);
        for(const [width,language,theme] of [[1280,'zh','light'],[390,'en','dark']]) {
          await page.setViewportSize({width,height:900});
          await page.evaluate(({language,theme})=>{document.querySelector(`[data-settings-lang="${language}"]`).click();document.querySelector(`.theme-opt[data-theme="${theme}"]`).click();},{language,theme});
          for(const [name,kind] of [['toolbar.py','python'],['toolbar.md','markdown'],[language==='zh'?'审查':'Review','review']]) {
            await tab(name).click();await expect(current).toHaveText(name);await expect(page.locator('#closePreview')).toHaveCount(0);
            if(kind==='review')await expect(toolbar).toBeHidden();else await expect(toolbar).toBeVisible();
            if(kind==='python'){await expect(page.locator('#refreshPreview')).toBeEnabled();await expect(page.locator('#copyPreview')).toBeEnabled();}
            if(kind==='markdown')await expect(page.locator('#previewModeActions button')).toHaveCount(2);
            await page.screenshot({animations:'disabled',path:path.join(evidence,`${runtime}-${width}-${language}-${theme}-toolbar-${kind}.png`)});
          }
        }
        await page.setViewportSize({width:1280,height:900});await tab('toolbar.md').click();
        await page.locator('.preview-tab.active .preview-tab-close').click();await expect(tabs).toHaveCount(2);await expect(tab('toolbar.py')).toHaveCount(1);await expect(page.locator('[data-preview-tab=review]')).toHaveCount(1);
        await tab('toolbar.py').click();await page.locator('[data-preview-tab=review]').locator('..').locator('.preview-tab-close').click();await expect(tabs).toHaveCount(1);await expect(current).toHaveText('toolbar.py');await expect(page.locator('#filePreview')).toContainText('toolbar fixture');
        await page.locator('.preview-tab.active .preview-tab-close').click();await expect(tabs).toHaveCount(0);await expect(page.locator('.workbench')).not.toHaveClass(/preview-open/);await expect(page.locator('#togglePreview')).toBeFocused();
        checks.push(`${runtime}: wide/narrow Chinese/English toolbar screenshots; file and review tab close affect only their own tab, last close restores global focus`);
        await context.close();context=null;continue;
      }
      if(totalsOnly||deleteOnly) {
        await expect(firstCard.locator('.recorded-change-file')).toHaveCount(2);
        for(const lang of ['en','zh']) {
          await page.evaluate(lang=>document.querySelector(`[data-settings-lang="${lang}"]`).click(),lang);
          for(const mode of ['light','dark']) {
            await page.evaluate(mode=>document.querySelector(`.theme-opt[data-theme="${mode}"]`).click(),mode);
            await expect(firstCard.locator('.recorded-total')).toHaveText(deleteOnly?'+6−3':'+6−2*');
            await expect(firstCard.locator('.recorded-total')).toHaveAttribute('aria-label',deleteOnly?/6.*3/:/6.*2/);
            if(!deleteOnly)await expect(firstCard.locator('.recorded-total')).toHaveAttribute('title',lang==='zh'?/未计入/:/excluded/);
            await expect(firstCard).not.toContainText(/累计|Cumulative/);
            await expect(firstCard.locator('.recorded-change-file').first()).toContainText('+5');
            await expect(firstCard.locator('.recorded-change-file').first()).toContainText('−2');
            if(deleteOnly){await expect(firstCard.locator('.recorded-change-file').last()).toContainText('+1');await expect(firstCard.locator('.recorded-change-file').last()).toContainText('−1');}
            else await expect(firstCard.locator('.recorded-change-file').last()).toContainText(lang==='zh'?'已删除 · 行数未知':'Deleted · Lines unknown');
            await page.locator('#messageList').hover();await page.mouse.wheel(0,-2000);await firstCard.scrollIntoViewIfNeeded();await page.mouse.move(1200,20);await page.waitForTimeout(150);
            await page.screenshot({animations:'disabled',path:path.join(evidence,`${runtime}-${lang}-${mode}-totals.png`)});
            checks.push(`${runtime}: ${lang} ${mode} verified notes/create/delete totals ${deleteOnly?'+6/-3':'+6/-2*'} without visible cumulative label`);
          }
        }
        await page.locator('#toggleSidebar').click();await page.setViewportSize({width:390,height:844});await firstCard.scrollIntoViewIfNeeded();await page.waitForTimeout(150);
        assert(await firstCard.evaluate(el=>el.scrollWidth<=el.clientWidth&&el.getBoundingClientRect().right<=innerWidth));
        await page.screenshot({animations:'disabled',path:path.join(evidence,`${runtime}-zh-narrow-dark-totals.png`)});
        if(deleteOnly){
          await firstCard.locator('.recorded-change-file').last().click();
          await expect(page.locator('.review-operation-section').filter({has:page.locator('.review-operation[aria-expanded=true]')}).locator('.review-file-icon')).toHaveAttribute('aria-label','删除');
          await expect(page.locator('.review-detail .diff-remove .diff-gutter')).toHaveText('−');
          await expect(page.locator('.review-detail')).toContainText('temporary');
          await page.screenshot({animations:'disabled',path:path.join(evidence,`${runtime}-zh-narrow-delete-diff.png`)});
          await page.setViewportSize({width:1280,height:900});await page.locator('#toggleSidebar').click();
          await page.screenshot({animations:'disabled',path:path.join(evidence,`${runtime}-zh-delete-diff.png`)});
          const publicRun=await api(`/api/agent/runs/${records[0].id}`);assert(!JSON.stringify(publicRun).includes('_codeReviewDelete'));
          const saved=await api(`/api/sessions/${a.id}`);assert(!JSON.stringify(saved).includes('_codeReviewDelete'));
          checks.push(`${runtime}: card selects actual historical deletion diff; public Run and persisted Session omit private evidence`);
        }
        await context.close();context=null;continue;
      }
      await expect(firstCard.locator('.recorded-change-file')).toHaveCount(3);
      await expect(firstCard.locator('.recorded-file-count')).toHaveText(' · 5 files');
      if(themeOnly) {
        await page.evaluate(()=>document.querySelector('[data-settings-lang="zh"]').click());
        for(const [size,viewport] of [['desktop',{width:1280,height:900}],['narrow',{width:390,height:844}]]) {
          if(size==='narrow')await page.locator('#toggleSidebar').click();
          await page.setViewportSize(viewport);
          for(const mode of ['light','dark']) {
            await page.evaluate(mode=>document.querySelector(`.theme-opt[data-theme="${mode}"]`).click(),mode);
            await expect(page.locator('html')).toHaveAttribute('data-theme-mode',mode);
            const expected=mode==='dark'?['rgb(101, 214, 154)','rgb(242, 132, 137)']:['rgb(22, 130, 73)','rgb(198, 77, 83)'];
            await expect(firstCard.locator('.review-additions').first()).toHaveCSS('color',expected[0]);
            await expect(firstCard.locator('.review-deletions').first()).toHaveCSS('color',expected[1]);
            themeSamples.push({runtime,size,...await firstCard.evaluate(el=>({mode:document.documentElement.dataset.themeMode,bodyFallback:document.body.classList.contains('theme-dark'),additions:getComputedStyle(el.querySelector('.review-additions')).color,deletions:getComputedStyle(el.querySelector('.review-deletions')).color}))});
            await page.locator('#messageList').hover();await page.mouse.wheel(0,-2000);await firstCard.scrollIntoViewIfNeeded();
            await page.mouse.move(viewport.width-10,20);await page.waitForTimeout(150);
            assert(await firstCard.evaluate(el=>el.scrollWidth<=el.clientWidth&&el.getBoundingClientRect().left>=0&&el.getBoundingClientRect().right<=innerWidth));
            await page.screenshot({animations:'disabled',path:path.join(evidence,`${runtime}-zh-${size}-${mode}-colors.png`)});
            checks.push(`${runtime}: ${size} ${mode} uses official theme signal and verified computed statistics colors`);
          }
        }
        await context.close();context=null;continue;
      }
      await expect(firstCard).not.toContainText('Cumulative');
      await expect(firstCard).toContainText('Deleted · Lines unknown');
      await expect(firstCard.locator('.recorded-total')).toHaveText('+10−10*');
      await expect(firstCard.locator('.recorded-change-file').first()).toContainText('+4');
      assert(!await page.locator('.workbench').evaluate(el=>el.classList.contains('preview-open')));
      assert(await firstCard.evaluate(el=>el.previousElementSibling.matches('.msg.assistant') && Boolean(el.previousElementSibling.querySelector('.msg-footer')) && el.nextElementSibling.matches('.msg.user')));
      await firstCard.locator('[data-review-expand]').click();await expect(firstCard.locator('.recorded-change-file')).toHaveCount(5);
      await firstCard.locator('[data-review-expand]').click();await expect(firstCard.locator('.recorded-change-file')).toHaveCount(3);
      await firstCard.locator('.recorded-change-file').nth(1).click();
      await expect(page.locator('.review-operation[aria-expanded=true]')).toHaveCount(1);
      await expect(page.locator('.review-detail')).toContainText('not retained');
      checks.push(`${runtime}: verified first-three card after final/footer before next request; cumulative edits, unknown deletion, expand/collapse and row selection`);
      if(duplicateOnly) {
        await expect(page.locator(`[data-review-card="${records[0].id}"]`)).toHaveCount(1);
        await page.reload();await expect(page.locator('[data-review-card]')).toHaveCount(3);
        await expect(page.locator('.recorded-change-file')).toHaveCount(0);
        const before=summaryRequests;
        await page.locator('[data-review-load]').first().evaluate(el=>{el.click();el.click();});
        await expect(firstCard.locator('.recorded-change-file')).toHaveCount(3);assert.equal(summaryRequests,before+1);
        await firstCard.locator('[data-review-expand]').click();await expect(firstCard.locator('.recorded-change-file')).toHaveCount(5);
        await firstCard.locator('[data-review-expand]').click();await expect(firstCard.locator('.recorded-change-file')).toHaveCount(3);
        assert(!await page.locator('.workbench').evaluate(el=>el.classList.contains('preview-open')));
        checks.push(`${runtime}: distinct persisted duplicate refs reload, single cold request and real expand/collapse remain bound to the visible card`);
        await context.close();context=null;continue;
      }
      await page.locator('.file-item[data-path="fixture.txt"]').click();
      await expect(page.locator('#previewTabs [role=tab]')).toHaveCount(2);
      let releaseFile;fileGate=new Promise(resolve=>releaseFile=resolve);
      await page.locator('.file-item[data-path="h4-propose-edit-fixture.txt"]').click({modifiers:['Control']});
      await expect.poll(()=>fileHeld).toBe(true);
      await page.locator('[data-recorded-review]').first().click();
      await expect(page.locator('.review-operation')).toHaveCount(6);
      fileGate=null;releaseFile();
      await page.waitForTimeout(100);
      await expect(page.locator('[data-preview-tab=review]')).toHaveText('Review');
      await expect(page.locator('#previewTabs')).toBeVisible();
      checks.push(`${runtime}: late explicit project open cannot replace review mode`);
      for(const record of records) {
        await page.locator(`[data-recorded-review="${record.id}"]`).first().click();
        await expect(page.locator('.review-operation')).toHaveCount(Object.keys(record.toolExecutions).filter(key=>key!=='lost-call').length);
        assert.equal(await page.locator('#filePreview img,#filePreview iframe').count(),0);
        if(await page.locator('.review-operation').first().getAttribute('aria-expanded')!=='true')await page.locator('.review-operation').first().click();
        await expect(page.locator('.review-operation-section').first().locator('.review-detail')).toContainText('<script>never_execute()</script>');
        assert.equal(await page.locator('#filePreview script').count(),0);
        await expect(page.locator('#filePreview')).not.toContainText('PRIVATE ARGUMENT');
      }
      checks.push(`${runtime}: completed/failed/cancelled review, escaped historical diff and whitelist`);
      await page.screenshot({animations:'disabled',path:path.join(evidence,`${runtime}-en-review.png`)});
      const count=routes.length;await page.waitForTimeout(3300);assert.equal(routes.length,count);
      checks.push(`${runtime}: historical review has no polling`);
      await page.locator('#previewTabs [role=tab]').first().click();
      await expect(page.locator('#previewTabs [role=tab]')).toHaveCount(3);
      await expect(page.locator('#filePreview')).not.toHaveClass(/recorded-review/);
      await page.locator('[data-preview-tab=review]').click();
      await expect(page.locator('.review-operation')).toHaveCount(1);
      checks.push(`${runtime}: single renderer switches back to preserved project tabs`);
      // A stale revision must reject details instead of substituting newer data.
      const last=records[2];last.toolExecutions['lost-call'].status=last.toolExecutions['lost-call'].status==='cancelled'?'failed':'cancelled';
      await fs.writeFile(path.join(host.dataDir,'agent-runs',`${last.id}.json`),JSON.stringify(last));
      await page.locator('.review-operation').click();await page.locator('.review-operation').click();
      await expect(page.locator('.review-detail')).toContainText('cannot be verified');
      checks.push(`${runtime}: stale revision rejects detail`);
      await page.evaluate(()=>document.querySelector('[data-settings-lang="zh"]').click());
      await expect(page.locator('[data-preview-tab=review]')).toHaveText('审查');
      await page.evaluate(()=>document.querySelector('[data-settings-lang="en"]').click());
      await expect(page.locator('[data-preview-tab=review]')).toHaveText('Review');
      await page.reload();
      await page.locator('[data-recorded-review]').first().click();
      await expect(page.locator('[data-preview-tab=review]')).toHaveText('Review');
      await page.evaluate(()=>document.querySelector('[data-settings-lang="zh"]').click());
      await expect(page.locator('[data-preview-tab=review]')).toHaveText('审查');
      checks.push(`${runtime}: immediate language switch and persisted English after reload`);
      await page.reload();
      await expect(page.locator('.recorded-change-file')).toHaveCount(0);
      await page.locator('[data-review-load]').first().click();
      await expect(page.locator('.recorded-change-file')).toHaveCount(3);
      await page.locator('[data-recorded-review]').first().click();await expect(page.locator('[data-preview-tab=review]')).toHaveText('审查');
      if(await page.locator('.review-operation').first().getAttribute('aria-expanded')!=='true')await page.locator('.review-operation').first().click();await expect(page.locator('.review-detail')).toContainText('never_execute');
      await page.locator('#togglePreview').click();
      await page.locator('#messageList').hover();await page.mouse.wheel(0,-2000);
      await firstCard.scrollIntoViewIfNeeded();await page.waitForTimeout(200);
      await page.mouse.move(1100,20);
      await page.screenshot({animations:'disabled',path:path.join(evidence,`${runtime}-zh-desktop-card.png`)});
      await firstCard.locator('[data-review-expand]').click();
      await page.screenshot({animations:'disabled',path:path.join(evidence,`${runtime}-zh-expanded-card.png`)});
      await firstCard.locator('[data-review-expand]').click();
      await page.evaluate(()=>document.querySelector('.theme-opt[data-theme="dark"]').click());
      await page.screenshot({animations:'disabled',path:path.join(evidence,`${runtime}-zh-dark-card.png`)});
      await page.evaluate(()=>document.querySelector('.theme-opt[data-theme="light"]').click());
      await page.locator('#toggleSidebar').click();
      await page.setViewportSize({width:390,height:844});await firstCard.scrollIntoViewIfNeeded();await page.waitForTimeout(200);await page.screenshot({animations:'disabled',path:path.join(evidence,`${runtime}-zh-narrow-review.png`)});
      assert(await firstCard.evaluate(el=>el.scrollWidth<=el.clientWidth&&el.getBoundingClientRect().left>=0&&el.getBoundingClientRect().right<=innerWidth));
      await page.evaluate(()=>document.querySelector('.theme-opt[data-theme="dark"]').click());
      await page.screenshot({animations:'disabled',path:path.join(evidence,`${runtime}-zh-narrow-dark-review.png`)});
      await page.setViewportSize({width:1280,height:900});
      await page.locator('#toggleSidebar').click();
      await page.locator('[data-recorded-review]').first().click();
      await expect(page.locator('[data-review-task]')).toHaveCount(0);
      const beforeTaskSelection=summaryRequests;
      await page.locator(`[data-recorded-review="${records[1].id}"]`).first().click();
      await expect(page.locator('.review-operation')).toHaveCount(1);
      await expect(page.locator('#filePreview')).toHaveAttribute('data-review-view',records[1].id);
      assert.equal(summaryRequests,beforeTaskSelection+1);
      await page.locator(`[data-recorded-review="${records[0].id}"]`).first().click();
      await expect(page.locator('#filePreview')).toHaveAttribute('data-review-view',records[0].id);
      await expect(page.locator('.review-operation')).toHaveCount(6);
      for(const index of [0,1,2]){const op=page.locator('.review-operation').nth(index);if(await op.getAttribute('aria-expanded')!=='true')await op.click();}
      await expect(page.locator('.review-detail')).toHaveCount(3);
      await expect(page.locator('.review-detail').nth(1)).toContainText('never_execute');
      await expect(page.locator('.review-detail').nth(2)).toContainText('未留存');
      const toggle=page.locator('[data-review-action="toggle"]').first();await toggle.focus();await page.keyboard.press('Enter');
      await expect(page.locator('.review-operation[aria-expanded=true]')).toHaveCount(2);await expect(toggle).toBeFocused();await page.keyboard.press('Space');
      await expect(page.locator('.review-operation[aria-expanded=true]')).toHaveCount(3);
      for(const [width,lang,theme] of [[1280,'zh','light'],[1280,'en','dark'],[390,'zh','dark'],[390,'en','light']]){
        await page.setViewportSize({width,height:900});
        if(width===1280){const handle=await page.locator('#previewResizer').boundingBox();await page.mouse.move(handle.x+handle.width/2,150);await page.mouse.down();await page.mouse.move(width-460,150,{steps:8});await page.mouse.up();}
        await page.evaluate(({lang,theme})=>{document.querySelector(`[data-settings-lang="${lang}"]`).click();document.querySelector(`.theme-opt[data-theme="${theme}"]`).click();document.querySelector('#filePreview').scrollTop=0;},{lang,theme});
        await expect(page.locator('html')).toHaveAttribute('data-theme-mode',theme);
        await expect(page.locator('[data-preview-tab=review]')).toHaveCount(1);
        await expect(page.locator('#filePreview.recorded-review')).toBeVisible();
        await expect(page.locator('.review-operation[aria-expanded=true]')).toHaveCount(3);
        await expect(page.locator('.compact-diff-gap[data-omitted-lines="15"]')).toHaveCount(2);
        await expect(page.locator('.review-detail .diff-header,.review-detail .diff-hunk')).toHaveCount(0);
        assert(await page.locator('.review-operation-row').evaluateAll(rows=>rows.every(row=>{const box=row.getBoundingClientRect();return [...row.querySelectorAll('.review-operation-stats,.review-row-action')].every(el=>{const r=el.getBoundingClientRect();return r.left>=box.left&&r.right<=box.right+1;});})));
        await expect(page.locator('#previewTitle, #previewMeta, #previewLanguage, #previewWorkspaceModes')).toHaveCount(0);
        await expect(page.locator('#refreshPreview, #copyPreview').filter({visible:true})).toHaveCount(0);
        await expect(page.locator('#closePreview')).toHaveCount(0);await expect(page.locator('.preview-head .preview-actions')).toBeHidden();
        await page.screenshot({animations:'disabled',path:path.join(evidence,`${runtime}-${width}-${lang}-${theme}-continuous-review.png`)});
      }
      checks.push(`${runtime}: unified mixed tabs, each old card opens its own round without task selector, continuous review and four actual theme/viewport variants`);
      await page.setViewportSize({width:1280,height:900});await page.locator('#togglePreview').click();
      await expect(page.locator('.edit-suggestion')).toHaveCount(6);
      assert.equal(await page.locator('.edit-suggestion').first().locator('[data-copy-text]').getAttribute('data-copy-text'),proposalDiff.trim());
      await expect(page.locator('.edit-suggestion').first().locator('.apply-edit-btn')).toHaveAttribute('data-edit-id','visual-proposal-0');
      for(const proposal of await page.locator('.edit-suggestion').all()) await proposal.locator('[data-edit-diff-toggle]').click();
      await expect(page.locator('.edit-suggestion .compact-diff')).toHaveCount(5);
      await expect(page.locator('.edit-suggestion .compact-diff-gap[data-omitted-lines="16"]')).toHaveCount(3);
      await expect(page.locator('.edit-suggestion script')).toHaveCount(0);
      await expect(page.locator('.edit-suggestion').nth(1).locator('.tool-edit-status')).toHaveClass(/is-applied/);
      await expect(page.locator('.edit-suggestion').nth(2).locator('.tool-edit-status')).toHaveClass(/is-rejected/);
      for(const [index,count] of [[3,48],[4,46],[5,45]]) {
        const proposal=page.locator('.edit-suggestion').nth(index),block=proposal.locator('.diff-block,.write-file-preview'),button=proposal.locator('.diff-expand-btn');
        await expect(block).toHaveClass(/is-collapsed/);await expect(button).toContainText(String(count));await button.click();await expect(block).toHaveClass(/is-expanded/);await button.click();await expect(block).toHaveClass(/is-collapsed/);await expect(button).toContainText(String(count));await button.click();await expect(block).toHaveClass(/is-expanded/);
      }
      for(const [width,lang,theme] of [[1280,'zh','light'],[390,'en','dark']]) {
        if(width===390)await page.locator('#toggleSidebar').click();
        await page.setViewportSize({width,height:900});await page.evaluate(({lang,theme})=>{document.querySelector(`[data-settings-lang="${lang}"]`).click();document.querySelector(`.theme-opt[data-theme="${theme}"]`).click();},{lang,theme});
        await page.waitForTimeout(200);await page.locator('#messageList').hover();await page.mouse.wheel(0,-10000);await page.waitForTimeout(100);
        await page.locator('.edit-suggestion').first().evaluate(el=>el.scrollIntoView({block:'start',behavior:'instant'}));await page.waitForTimeout(200);
        const proposalBox=await page.locator('.edit-suggestion').first().boundingBox();assert(proposalBox.y>=40&&proposalBox.y<250&&proposalBox.x>=0&&proposalBox.x+proposalBox.width<=width+1,JSON.stringify(proposalBox));
        await page.screenshot({animations:'disabled',path:path.join(evidence,`${runtime}-${width}-${lang}-${theme}-ordinary-diff.png`)});
      }
      checks.push(`${runtime}: ordinary pending/applied/failed proposals share compact multihunk presentation; raw write remains escaped with functional long-content disclosure`);
      await page.setViewportSize({width:1280,height:900});await page.locator('#toggleSidebar').click();
      await page.setViewportSize({width:1280,height:900});await page.evaluate(()=>{document.querySelector('[data-settings-lang="zh"]').click();document.querySelector('.theme-opt[data-theme="light"]').click();});
      let release;gate=new Promise(resolve=>release=resolve);
      await page.locator('[data-recorded-review]').last().click();
      await page.locator(`.session-main[data-session-id="${b.id}"]`).click();
      gate=null;release();
      await expect(page.locator('#previewTabs [role=tab]')).toHaveCount(0);
      await expect(page.locator('#filePreview')).not.toContainText('never_execute');
      assert(!await page.locator('.workbench').evaluate(el=>el.classList.contains('preview-open')));
      checks.push(`${runtime}: delayed cross-session summary cannot restore old content`);
      await expect(page.locator('[data-review-card]')).toHaveCount(0);
      // sessions.loadSession deliberately ignores user switches within 300ms.
      await page.waitForTimeout(350);
      await page.locator(`.session-main[data-session-id="${a.id}"]`).click();
      await expect(page.locator('[data-review-card]')).toHaveCount(3);
      await page.reload();
      await expect(page.locator('[data-review-load]')).toHaveCount(3);
      const beforeCold=summaryRequests;
      gate=new Promise(resolve=>release=resolve);
      await page.locator('[data-review-load]').first().evaluate(el=>{el.click();el.click();});
      await expect.poll(()=>summaryRequests).toBe(beforeCold+1);
      await expect(page.locator('[data-review-load]').first()).toBeDisabled();
      await page.waitForTimeout(350);
      await page.locator(`.session-main[data-session-id="${b.id}"]`).click();gate=null;release();
      await expect(page.locator('[data-review-card]')).toHaveCount(0);
      await page.waitForTimeout(350);
      await page.locator(`.session-main[data-session-id="${a.id}"]`).click();
      await expect(page.locator('[data-review-card]')).toHaveCount(3);
      await page.reload();
      gate=new Promise(resolve=>release=resolve);
      await page.locator('[data-review-load]').first().click();
      await expect(page.locator('[data-review-load]').first()).toContainText('点击重试',{timeout:4500});
      await expect(page.locator('.recorded-change-file')).toHaveCount(0);
      gate=null;release();
      checks.push(`${runtime}: cold load deduplicates clicks, rejects cross-session late response and times out without inventing file counts`);
      await context.close();context=null;
    }
    assert.deepEqual(errors,[]);
  } catch(error) {
    if(page&&!page.isClosed())await page.screenshot({animations:'disabled',path:path.join(evidence,'failure.png')}).catch(()=>{});
    if(page&&!page.isClosed())await fs.writeFile(path.join(evidence,'failure-state.json'),JSON.stringify(await page.evaluate(()=>({cards:[...document.querySelectorAll('[data-review-card]')].map(el=>({id:el.dataset.reviewCard,text:el.textContent})),preview:document.querySelector('#filePreview')?.textContent})),null,2)).catch(()=>{});
    throw error;
  } finally {
    if(context)await context.close();if(browser)await browser.close();cleanup=await host.stop();
    await fs.writeFile(path.join(evidence,'result.json'),JSON.stringify({checks,errors,routes,themeSamples,cleanup},null,2));
    assert(cleanup.rootRemoved&&cleanup.childExited);assert.deepEqual(cleanup.cleanupErrors,[]);assert.deepEqual(cleanup.portsClosed,[true,true]);assert.equal(getActiveChildCount(),0);
  }
  console.log(JSON.stringify({ok:true,evidence,checks}));
}
main().catch(error=>{console.error(error.stack||error);process.exitCode=1;});
