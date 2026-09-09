const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os');
const {chromium,expect}=require('@playwright/test');
const {startIsolatedHost,getActiveChildCount}=require('./isolated-host.cjs');
const {createContext,createAudit,waitForRuntime}=require('./execution-trace-skill-model-reminder-selfcheck.cjs');
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFUlEQVR4nGNUqPjwn4GBgYEJRIAwACXYAoumRkB8AAAAAElFTkSuQmCC','base64');
async function scenario(browser,host,runtime,theme,width,dir){
  const audit=createAudit(),context=await createContext(browser,host,runtime,audit,{width,theme,language:runtime==='bundle'?'zh':'en'}),counts={},requests=[],errors=[];
  let release;const gate=new Promise(resolve=>release=resolve);
  // Expose existing closures only; product logic and rendering remain unchanged.
  await context.route(/\/(?:app\.js|code\.bundle\.js)$/,async route=>{
    const response=await route.fetch(),source=await response.text();
    const needle='function bindExtLinkFavicons() {';assert(source.includes(needle));
    await route.fulfill({response,body:source.replace(needle,'window.__faviconUI = {bind:bindExtLinkFavicons, tooltip:bindTooltips, contextMenu:bindLinkContextMenus, cache:_faviconCache}; '+needle)});
  });
  await context.route('**/api/favicon?*',async route=>{
    const url=new URL(route.request().url()),name=url.searchParams.get('host');counts[name]=(counts[name]||0)+1;
    const count=counts[name];requests.push({host:name,count,origin:url.origin,path:url.pathname,time:Date.now()});await gate;
    if(name==='retry.test'&&count===1)return route.fulfill({status:503,headers:{'Retry-After':'1','Cache-Control':'no-store'},body:''});
    if(name==='missing.test')return route.fulfill({status:404,headers:{'Cache-Control':'no-store'},body:''});
    if(name==='network.test'&&count===1)return route.abort('failed');
    if(name==='badimage.test')return route.fulfill({status:200,contentType:'image/png',body:'not an image'});
    return route.fulfill({status:200,contentType:'image/png',body:png});
  });
  const page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));
  const key=`${runtime}-${theme}-${width}`;
  try{
    await page.goto(new URL(runtime==='bundle'?'/':'/dist/frontend/index.classic.html',host.ready.codeUrl).href);await waitForRuntime(page,runtime);await page.waitForLoadState('networkidle');
    const install=async()=>page.evaluate(()=>{
      const renderer=Code.ui.markdown.createMarkdownFeature().renderer;
      const names=['success.test','retry.test','missing.test','badimage.test','network.test','retry.test'];
      const html=names.map(name=>'<p>'+renderer.link({href:'https://'+name+'/path',text:'https://'+name+'/path'})+'</p>').join('')+'<p><a class="path-file-card" data-path="C:/fixture/readme.txt" title="C:/fixture/readme.txt">readme.txt</a></p>';
      document.querySelector('.chat-pane').classList.remove('empty-chat');
      document.getElementById('messageList').innerHTML=window.__toolNameFeature.projectMessages([{role:'assistant',content:html}],{hasActiveRun:false});
      window.__faviconUI.bind();window.__faviconUI.tooltip();window.__faviconUI.contextMenu();
      window.__retryNode=document.querySelector('a[href="https://retry.test/path"] .link-ext-icon');
      return [...document.querySelectorAll('a.ext-link .link-ext-icon')].map(el=>{const r=el.getBoundingClientRect();return {width:r.width,height:r.height}});
    });
    const before=await install(),links=page.locator('a.ext-link');await expect(links).toHaveCount(6);await expect(links.locator('svg')).toHaveCount(6);
    const retry=links.nth(1);await retry.focus();await expect(page.locator('.sb-path-tooltip')).toHaveText('https://retry.test/path');assert.equal(await retry.getAttribute('title'),null);
    await page.screenshot({path:path.join(dir,key+'-before.png')});release();
    await expect(links.nth(0).locator('img')).toHaveCount(1);await expect(retry.locator('img')).toHaveCount(1);await expect(links.nth(4).locator('img')).toHaveCount(1);await expect(links.nth(5).locator('img')).toHaveCount(1);
    await expect(links.nth(2).locator('svg')).toHaveCount(1);await expect(links.nth(3).locator('svg')).toHaveCount(1);
    assert.deepEqual(counts,{'success.test':1,'retry.test':2,'missing.test':1,'badimage.test':1,'network.test':2});
    const after=await page.evaluate(()=>({sameNode:window.__retryNode===document.querySelector('a[href="https://retry.test/path"] .link-ext-icon'),geometry:[...document.querySelectorAll('a.ext-link .link-ext-icon')].map(el=>{const r=el.getBoundingClientRect();return {width:r.width,height:r.height}}),overflow:document.documentElement.scrollWidth>innerWidth}));
    assert(after.sameNode);assert.deepEqual(after.geometry,before);assert(!after.overflow);
    const retries=requests.filter(r=>r.host==='retry.test');assert(retries[1].time-retries[0].time>=1000);
    await page.locator('.path-file-card').hover();await expect(page.locator('.sb-path-tooltip')).toHaveCount(1);await expect(page.locator('.sb-path-tooltip')).toHaveText('C:/fixture/readme.txt');assert.equal(await page.locator('.path-file-card').getAttribute('title'),null);
    await page.evaluate(()=>{
      window.__faviconCopied=[];window.__faviconActivated=[];
      Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async value=>{window.__faviconCopied.push(value)}}});
      document.querySelector('a.ext-link').addEventListener('click',event=>{event.preventDefault();window.__faviconActivated.push(event.currentTarget.href)});
    });
    await links.nth(0).click({button:'right'});await page.locator('.file-ctx-menu [data-action="copy-link"]').click();
    await expect.poll(()=>page.evaluate(()=>window.__faviconCopied)).toEqual(['https://success.test/path']);
    await links.nth(0).focus();await page.keyboard.press('Enter');assert.deepEqual(await page.evaluate(()=>window.__faviconActivated),['https://success.test/path']);
    assert.equal(await links.nth(0).getAttribute('target'),'_blank');assert.equal(await links.nth(0).getAttribute('rel'),'noopener');
    await page.screenshot({path:path.join(dir,key+'-after.png')});
    await page.reload();await waitForRuntime(page,runtime);await page.waitForLoadState('networkidle');await install();await expect(page.locator('a.ext-link').nth(0).locator('img')).toHaveCount(1);
    assert.deepEqual(errors,[]);assert.deepEqual(audit.blockedWrites,[]);
    assert(requests.every(r=>r.origin===new URL(host.ready.codeUrl).origin&&r.path==='/api/favicon'));
    return {runtime,theme,width,counts,requests,geometry:before,originalNodeRecovered:true,tooltip:true,contextCopy:true,keyboardActivation:true,refresh:true,errors};
  }finally{release();await context.close();}
}
async function main(){
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),'code045-r018-ui-')),host=await startIsolatedHost({disableRoutingV2:true});let browser,result={dir,cases:[]};
  try{browser=await chromium.launch({headless:true});for(const runtime of ['bundle','classic'])for(const theme of ['light','dark'])for(const width of [1280,390]){
    if(process.argv.includes("--quick") && !((runtime==="bundle"&&theme==="dark"&&width===390)||(runtime==="classic"&&theme==="light"&&width===1280)))continue;
    result.cases.push(await scenario(browser,host,runtime,theme,width,dir));console.log(`${runtime} ${theme} ${width} passed`);
  }const m=await host.metrics();assert.equal(m.chatRequests.length,0);assert.equal(m.toolExecutions.length,0);assert.equal(m.production.agentRuns.length,0);result.effects={modelRequests:0,tools:0,agentRuns:0};result.ok=true;
  }catch(e){result.ok=false;result.error=String(e.stack);process.exitCode=1;}
  finally{if(browser)await browser.close();const c=await host.stop();result.cleanup={childExited:c.childExited,portsClosed:c.portsClosed,rootRemoved:c.rootRemoved,errors:c.cleanupErrors,activeChildren:getActiveChildCount()};if(!c.childExited||!c.rootRemoved||!c.portsClosed.every(Boolean)||c.cleanupErrors.length||getActiveChildCount()){result.ok=false;process.exitCode=1;}await fs.writeFile(path.join(dir,'result.json'),JSON.stringify(result,null,2));}
  console.log(JSON.stringify(result));
}
main().catch(e=>{console.error(e);process.exitCode=1});
