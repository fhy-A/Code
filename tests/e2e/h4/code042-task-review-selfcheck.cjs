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
  const api=async(url,body,method="POST")=>{
    const response=await fetch(host.ready.codeUrl+url,body?{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});
    assert(response.ok,`${response.status} ${url}: ${await response.clone().text()}`);return response.json();
  };
  try {
    const a=await api('/api/sessions',{title:'Recorded changes A',cwd:host.projectDir});
    const b=await api('/api/sessions',{title:'Recorded changes B',cwd:host.projectDir});
    const binding=await api('/api/preview/context',{sessionId:a.id});
    const records=[],messages=[];
    await fs.mkdir(path.join(host.dataDir,'agent-runs'),{recursive:true});
    for(const [index,status] of ['completed','failed','cancelled'].entries()) {
      const id=String(index+1).repeat(32),diff='--- a/demo.txt\n+++ b/demo.txt\n@@ -1 +1 @@\n-old\n+<script>never_execute()</script>\n';
      const actual=path.join(host.projectDir,'demo.txt').toLowerCase();
      const receipt={schema:'code-file-change-receipt/v1',canonicalPath:actual,fileKey:sha(JSON.stringify(actual)),kind:'update',entityKind:'file',operationId:'op-1',diffSemantics:'normalized-lines',diffSha256:sha(diff),bodyState:'diff'};
      const record={version:7,id,sessionId:a.id,status,runKind:'foreground',clientRequestId:`request-${index}`,reviewBinding:{schema:'code-run-review-binding/v1',dataSourceId:binding.dataSourceId,sessionId:a.id,sessionInstanceId:binding.sessionInstanceId,rootRunId:id,rootClientRequestId:`request-${index}`,originMessageId:`message-${index}`,originRoot:host.projectDir},toolExecutions:{'call-1':{name:'write_file',status:'completed',operationId:'op-1',arguments:'PRIVATE ARGUMENT MUST NOT LEAK',result:{ok:true,action:'write_file',replayed:false,diff,fileChange:receipt}}},result:{},steerReceipts:[]};
      if(index===0) {
        for(const [n,name] of ['demo.txt','deleted.txt','src/app.js','notes.md','styles.css'].entries()) {
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
      let gate=null,fileGate=null,fileHeld=false,summaryRequests=0;
      await context.route('**/*',async route=>{
        const url=new URL(route.request().url());
        try {
          if(!['127.0.0.1','localhost','::1'].includes(url.hostname))return await route.abort();
          if(url.pathname==='/api/image-routes/refresh')return await route.fulfill({json:{version:1,routes:[],ok:true}});
          if(url.pathname==='/api/code/sync-keys')return await route.fulfill({json:{tokens:[],keys:{}}});
          if(url.pathname.endsWith('/file-changes')){summaryRequests++;if(gate)await gate;}
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
      await expect(page.locator('[data-recorded-review]')).toHaveCount(3);
      await expect(page.locator('.recorded-change-summary').first()).not.toContainText('Files recorded:');
      assert(!await page.locator('.workbench').evaluate(el=>el.classList.contains('preview-open')));
      checks.push(`${runtime}: three terminal/history entries without automatic focus`);
      assert.equal(routes.length,initialRouteCount);
      await page.locator('[data-review-load]').first().click();
      const firstCard=page.locator('[data-review-card]').first();
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
            await page.screenshot({path:path.join(evidence,`${runtime}-${lang}-${mode}-totals.png`)});
            checks.push(`${runtime}: ${lang} ${mode} verified notes/create/delete totals ${deleteOnly?'+6/-3':'+6/-2*'} without visible cumulative label`);
          }
        }
        await page.locator('#toggleSidebar').click();await page.setViewportSize({width:390,height:844});await firstCard.scrollIntoViewIfNeeded();await page.waitForTimeout(150);
        assert(await firstCard.evaluate(el=>el.scrollWidth<=el.clientWidth&&el.getBoundingClientRect().right<=innerWidth));
        await page.screenshot({path:path.join(evidence,`${runtime}-zh-narrow-dark-totals.png`)});
        if(deleteOnly){
          await firstCard.locator('.recorded-change-file').last().click();
          await expect(page.locator('.review-operation.active')).toContainText('删除');
          await expect(page.locator('.review-detail')).toContainText('-');
          await expect(page.locator('.review-detail')).toContainText('temporary');
          await page.screenshot({path:path.join(evidence,`${runtime}-zh-narrow-delete-diff.png`)});
          await page.setViewportSize({width:1280,height:900});await page.locator('#toggleSidebar').click();
          await page.screenshot({path:path.join(evidence,`${runtime}-zh-delete-diff.png`)});
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
            await page.screenshot({path:path.join(evidence,`${runtime}-zh-${size}-${mode}-colors.png`)});
            checks.push(`${runtime}: ${size} ${mode} uses official theme signal and verified computed statistics colors`);
          }
        }
        await context.close();context=null;continue;
      }
      await expect(firstCard).not.toContainText('Cumulative');
      await expect(firstCard).toContainText('Deleted · Lines unknown');
      await expect(firstCard.locator('.recorded-total')).toHaveText('+5−5*');
      await expect(firstCard.locator('.recorded-change-file').first()).toContainText('+2');
      assert(!await page.locator('.workbench').evaluate(el=>el.classList.contains('preview-open')));
      assert(await firstCard.evaluate(el=>el.previousElementSibling.matches('.msg.assistant') && Boolean(el.previousElementSibling.querySelector('.msg-footer')) && el.nextElementSibling.matches('.msg.user')));
      await firstCard.locator('[data-review-expand]').click();await expect(firstCard.locator('.recorded-change-file')).toHaveCount(5);
      await firstCard.locator('[data-review-expand]').click();await expect(firstCard.locator('.recorded-change-file')).toHaveCount(3);
      await firstCard.locator('.recorded-change-file').nth(1).click();
      await expect(page.locator('.review-operation.active')).toHaveCount(1);
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
      await expect(page.locator('#previewTabs [role=tab]')).toHaveCount(1);
      let releaseFile;fileGate=new Promise(resolve=>releaseFile=resolve);
      await page.locator('.file-item[data-path="h4-propose-edit-fixture.txt"]').click({modifiers:['Control']});
      await expect.poll(()=>fileHeld).toBe(true);
      await page.locator('[data-recorded-review]').first().click();
      await expect(page.locator('.review-operation')).toHaveCount(6);
      fileGate=null;releaseFile();
      await page.waitForTimeout(100);
      await expect(page.locator('#previewTitle')).toHaveText('Recorded task changes');
      await expect(page.locator('#previewTabs')).toBeHidden();
      checks.push(`${runtime}: late explicit project open cannot replace review mode`);
      for(const record of records) {
        await page.locator(`[data-recorded-review="${record.id}"]`).first().click();
        await expect(page.locator('.review-operation')).toHaveCount(Object.keys(record.toolExecutions).filter(key=>key!=='lost-call').length);
        assert.equal(await page.locator('#filePreview img,#filePreview iframe').count(),0);
        await page.locator('.review-operation').first().click();
        await expect(page.locator('.review-detail')).toContainText('<script>never_execute()</script>');
        assert.equal(await page.locator('#filePreview script').count(),0);
        await expect(page.locator('#filePreview')).not.toContainText('PRIVATE ARGUMENT');
      }
      checks.push(`${runtime}: completed/failed/cancelled review, escaped historical diff and whitelist`);
      await page.screenshot({path:path.join(evidence,`${runtime}-en-review.png`)});
      const count=routes.length;await page.waitForTimeout(3300);assert.equal(routes.length,count);
      checks.push(`${runtime}: historical review has no polling`);
      await page.locator('[data-preview-view=files]').click();
      await expect(page.locator('#previewTabs [role=tab]')).toHaveCount(2);
      await expect(page.locator('#filePreview')).not.toHaveClass(/recorded-review/);
      await page.locator('[data-preview-view=changes]').click();
      await expect(page.locator('.review-operation')).toHaveCount(1);
      checks.push(`${runtime}: single renderer switches back to preserved project tabs`);
      // A stale revision must reject details instead of substituting newer data.
      const last=records[2];last.toolExecutions['lost-call'].status=last.toolExecutions['lost-call'].status==='cancelled'?'failed':'cancelled';
      await fs.writeFile(path.join(host.dataDir,'agent-runs',`${last.id}.json`),JSON.stringify(last));
      await page.locator('.review-operation').click();
      await expect(page.locator('.review-detail')).toContainText('cannot be verified');
      checks.push(`${runtime}: stale revision rejects detail`);
      await page.evaluate(()=>document.querySelector('[data-settings-lang="zh"]').click());
      await expect(page.locator('#previewTitle')).toHaveText('本轮已记录改动');
      await page.evaluate(()=>document.querySelector('[data-settings-lang="en"]').click());
      await expect(page.locator('#previewTitle')).toHaveText('Recorded task changes');
      await page.reload();
      await page.locator('[data-recorded-review]').first().click();
      await expect(page.locator('#previewTitle')).toHaveText('Recorded task changes');
      await page.evaluate(()=>document.querySelector('[data-settings-lang="zh"]').click());
      await expect(page.locator('#previewTitle')).toHaveText('本轮已记录改动');
      checks.push(`${runtime}: immediate language switch and persisted English after reload`);
      await page.reload();
      await expect(page.locator('.recorded-change-file')).toHaveCount(0);
      await page.locator('[data-review-load]').first().click();
      await expect(page.locator('.recorded-change-file')).toHaveCount(3);
      await page.locator('[data-recorded-review]').first().click();await expect(page.locator('#previewTitle')).toHaveText('本轮已记录改动');
      await page.locator('.review-operation').first().click();await expect(page.locator('.review-detail')).toContainText('never_execute');
      await page.locator('#closePreview').click();
      await page.locator('#messageList').hover();await page.mouse.wheel(0,-2000);
      await firstCard.scrollIntoViewIfNeeded();await page.waitForTimeout(200);
      await page.mouse.move(1100,20);
      await page.screenshot({path:path.join(evidence,`${runtime}-zh-desktop-card.png`)});
      await firstCard.locator('[data-review-expand]').click();
      await page.screenshot({path:path.join(evidence,`${runtime}-zh-expanded-card.png`)});
      await firstCard.locator('[data-review-expand]').click();
      await page.evaluate(()=>document.querySelector('.theme-opt[data-theme="dark"]').click());
      await page.screenshot({path:path.join(evidence,`${runtime}-zh-dark-card.png`)});
      await page.evaluate(()=>document.querySelector('.theme-opt[data-theme="light"]').click());
      await page.locator('#toggleSidebar').click();
      await page.setViewportSize({width:390,height:844});await firstCard.scrollIntoViewIfNeeded();await page.waitForTimeout(200);await page.screenshot({path:path.join(evidence,`${runtime}-zh-narrow-review.png`)});
      assert(await firstCard.evaluate(el=>el.scrollWidth<=el.clientWidth&&el.getBoundingClientRect().left>=0&&el.getBoundingClientRect().right<=innerWidth));
      await page.evaluate(()=>document.querySelector('.theme-opt[data-theme="dark"]').click());
      await page.screenshot({path:path.join(evidence,`${runtime}-zh-narrow-dark-review.png`)});
      await page.setViewportSize({width:1280,height:900});
      await page.locator('#toggleSidebar').click();
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
    if(page&&!page.isClosed())await page.screenshot({path:path.join(evidence,'failure.png')}).catch(()=>{});
    throw error;
  } finally {
    if(context)await context.close();if(browser)await browser.close();cleanup=await host.stop();
    await fs.writeFile(path.join(evidence,'result.json'),JSON.stringify({checks,errors,routes,themeSamples,cleanup},null,2));
    assert(cleanup.rootRemoved&&cleanup.childExited);assert.deepEqual(cleanup.cleanupErrors,[]);assert.deepEqual(cleanup.portsClosed,[true,true]);assert.equal(getActiveChildCount(),0);
  }
  console.log(JSON.stringify({ok:true,evidence,checks}));
}
main().catch(error=>{console.error(error.stack||error);process.exitCode=1;});
