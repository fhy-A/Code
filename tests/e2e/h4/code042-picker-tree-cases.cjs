const assert=require('node:assert/strict');
const {expect}=require('@playwright/test');
module.exports=async(page,{changeRoot,projectRoot,subRoot})=>{
 const checks=[],plus=page.locator('#previewNewTab'),query=page.locator('[data-picker-query]'),active=page.locator('[data-preview-tab][aria-selected=true]');
 const row=path=>page.locator(`[data-picker-path="${path}"]`);
 const hold=()=>page.evaluate(()=>{window.__treeHeld=[];window.__pickerApi=async(url,opts,original)=>{const data=await original(url,{...opts,signal:undefined});if(!url.startsWith('/api/preview/files?'))return data;return new Promise((resolve,reject)=>window.__treeHeld.push({data,resolve,reject,aborted:()=>opts.signal.aborted}));};});
 const release=async index=>{await page.evaluate(i=>window.__treeHeld[i].resolve(window.__treeHeld[i].data),index);await page.waitForTimeout(30);};
 await plus.click();await expect(row('sub')).toBeVisible();
 await hold();await row('sub').click();await expect.poll(()=>page.evaluate(()=>window.__treeHeld.length)).toBe(1);await row('sub').click();assert(await page.evaluate(()=>window.__treeHeld[0].aborted()));await row('sub').click();await expect.poll(()=>page.evaluate(()=>window.__treeHeld.length)).toBe(2);await release(0);await expect(row('sub/deep')).toHaveCount(0);await release(1);await expect(row('sub/deep')).toBeVisible();checks.push('collapse/reopen binds each directory request: late cancelled A cannot fill B or collapse/reopen the node');
 await hold();await row('sibling').click();await expect.poll(()=>page.evaluate(()=>window.__treeHeld.length)).toBe(1);await page.evaluate(()=>window.__treeHeld[0].reject(new Error('fixture directory failure')));await expect(page.locator('[data-picker-retry-path="sibling"]')).toBeVisible();await page.evaluate(()=>window.__pickerApi=null);await page.locator('[data-picker-retry-path="sibling"]').click();await expect(row('sibling/peer.txt')).toBeVisible();checks.push('failed directory leaves siblings intact and retries only its own metadata');
 await hold();await row('sub/deep').click();await expect.poll(()=>page.evaluate(()=>window.__treeHeld.length)).toBe(1);await query.fill('alpha');await expect.poll(()=>page.evaluate(()=>window.__treeHeld.length)).toBe(2);await release(0);await expect(row('sub/deep/grand.txt')).toHaveCount(0);await release(1);await page.evaluate(()=>window.__pickerApi=null);await query.fill('');await expect(row('sub/deep/grand.txt')).toBeVisible();await expect(row('sibling/peer.txt')).toBeVisible();checks.push('search cancels pending tree expansion; late tree does not replace results; clearing search resumes only previously expanded nodes');
 await row('sub/deep').click();await hold();await row('sub/deep').click();await expect.poll(()=>page.evaluate(()=>window.__treeHeld.length)).toBe(1);const closed=await active.getAttribute('data-preview-tab');await page.locator('.preview-tab.active .preview-tab-close').click();await release(0);await expect(page.locator(`[data-preview-tab="${closed}"]`)).toHaveCount(0);await page.evaluate(()=>window.__pickerApi=null);checks.push('closing a blank cancels its directory request and late metadata cannot recreate the tab');
 await plus.click();await expect(row('sub')).toBeVisible();await hold();await row('sub').click();await expect.poll(()=>page.evaluate(()=>window.__treeHeld.length)).toBe(1);const oldRootTab=await active.getAttribute('data-preview-tab');await changeRoot(subRoot);await release(0);await expect(page.locator(`[data-preview-tab="${oldRootTab}"]`)).toHaveCount(0);await page.evaluate(()=>window.__pickerApi=null);await plus.click();await expect(row('child.txt')).toBeVisible();await expect(row('alpha.txt')).toHaveCount(0);await changeRoot(projectRoot);checks.push('root change cancels pending directory expansion, drops old blank tree and uses only the new root; isolated config restored');
 // Synthetic, context-validated metadata isolates frontend budgets; never open
 // synthetic files or claim these payloads are physical filesystem evidence.
 await page.evaluate(()=>{
  window.__budget={large:false,hold:false,held:[],issued:0,active:0,peak:0};
  window.__pickerApi=async(url,opts,original)=>{
   if(!url.startsWith('/api/preview/files?'))return original(url,opts);
   const request=new URL(url,location.href),path=request.searchParams.get('path'),base=new URL(url,location.href);base.searchParams.set('path','');
   const data=await original(base.pathname+base.search,{...opts,signal:undefined}),budget=window.__budget;
   const root=data.root.replaceAll('\\','/');
   const items=Array.from({length:200},(_,i)=>{const name=path?(budget.large?'x'.repeat(240):'f')+String(i)+'.txt':'d'+i;return {name,path:path?path+'/'+name:name,absolutePath:root+'/'+(path?path+'/':'')+name,type:path?'file':'dir',fileKey:'a'.repeat(64)};});
   const result={...data,path,items,limited:false};
   if(!path||!budget.hold)return result;
   budget.issued++;budget.active++;budget.peak=Math.max(budget.peak,budget.active);
   try{return await new Promise(resolve=>budget.held.push({resolve:()=>resolve(result),aborted:()=>opts.signal.aborted}));}finally{budget.active--;}
  };
 });
 await plus.click();await expect(row('d0')).toBeVisible();const first=await active.getAttribute('data-preview-tab');
 for(let i=0;i<4;i++){await row('d'+i).click();await expect(row('d'+i+'/f0.txt')).toBeVisible();}
 await page.locator('.preview-picker-results').evaluate(el=>el.scrollTop=600);await query.fill('temporary-search');await expect(row('d0')).toHaveCount(0);await query.fill('');await expect(row('d0/f0.txt')).toBeVisible();await expect.poll(()=>page.locator('.preview-picker-results').evaluate(el=>el.scrollTop)).toBe(600);checks.push('fixed search input and independent results scroller preserve tree scroll through actual search/clear keyboard input');
 await plus.click();await expect(row('d0')).toBeVisible();
 for(let i=0;i<3;i++){await row('d'+i).click();await expect(row('d'+i+'/f0.txt')).toBeVisible();}
 await row('d3').click();await expect(page.locator('[data-picker-retry-path="d3"]')).toBeVisible();await expect(row('d3/f0.txt')).toHaveCount(0);await expect(page.locator('.preview-tree-status')).toContainText('limit');
 await page.locator(`[data-preview-tab="${first}"]`).locator('..').locator('.preview-tab-close').click();await page.locator('[data-picker-retry-path="d3"]').click();await expect(row('d3/f0.txt')).toBeVisible();checks.push('2000-node retention budget is shared across blank tabs; closing another blank releases capacity and exact directory retry succeeds');
 await page.locator('.preview-tab.active .preview-tab-close').click();await page.evaluate(()=>window.__budget.large=true);await plus.click();await expect(row('d0')).toBeVisible();
 let byteLimitAt=0;
 for(let i=0;i<9;i++){await row('d'+i).click();await expect.poll(()=>page.locator(`[data-picker-retry-path="d${i}"]`).count().then(async count=>count||await page.locator(`[data-picker-path^="d${i}/"]`).count())).toBeGreaterThan(0);if(await page.locator(`[data-picker-retry-path="d${i}"]`).count()){byteLimitAt=i;break;}}
 assert(byteLimitAt>0&&byteLimitAt<8,'byte budget must stop before node limit');checks.push('2MiB retained tree estimate stops long-name metadata before the node-count limit');
 await page.locator('.preview-tab.active .preview-tab-close').click();await page.evaluate(()=>{window.__budget.large=false;window.__budget.hold=true;});await plus.click();await expect(row('d0')).toBeVisible();
 for(let i=0;i<20;i++)await row('d'+i).click();await expect.poll(()=>page.evaluate(()=>window.__budget.issued)).toBe(2);assert.equal(await page.evaluate(()=>window.__budget.peak),2);await expect(page.locator('[data-picker-retry-path="d18"]')).toBeVisible();await expect(page.locator('[data-picker-retry-path="d19"]')).toBeVisible();
 await row('').click();await expect(row('d0')).toHaveCount(0);assert(await page.evaluate(()=>window.__budget.held.every(item=>item.aborted())));await page.evaluate(()=>{window.__budget.hold=false;for(const held of window.__budget.held)held.resolve();});await page.waitForTimeout(50);assert.equal(await page.evaluate(()=>window.__budget.issued),2);await expect(row('')).toHaveAttribute('aria-expanded','false');checks.push('2 in-flight and 16 queued expansions bounded; root collapse cancels active jobs and removes queued jobs without late resurrection');
 await row('').click();await expect(row('d0')).toBeVisible();await page.evaluate(()=>window.__budget.hold=true);for(let i=0;i<3;i++)await row('d'+i).click();await expect(page.locator('[data-picker-retry-path="d2"]')).toBeVisible({timeout:8000});assert.equal(await page.evaluate(()=>window.__budget.issued),4);assert(await page.evaluate(()=>window.__budget.held.every(item=>item.aborted())));await page.evaluate(()=>{for(const held of window.__budget.held)held.resolve();});checks.push('five-second directory deadline includes queue wait; queued timeout never starts a late request');
 await page.evaluate(()=>window.__pickerApi=null);await page.locator('.preview-tab.active .preview-tab-close').click();return checks;
};
