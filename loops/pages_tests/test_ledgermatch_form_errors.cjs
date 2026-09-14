const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(process.argv[2],'utf8');
const code=[...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(x=>x[1]).find(x=>x.includes("var form = document.getElementById('cm-form')"));assert(code);
function setup(response){const nodes={};const button={disabled:false};let handler,calls=0;function node(id){return nodes[id]||(nodes[id]={value:id==='cm-domain'?'fixture.invalid':id==='cm-rows'?'INV1,10':'',textContent:'',classList:{add(){},remove(){}},setAttribute(){},removeAttribute(){},querySelector(){return button},addEventListener(name,fn){handler=fn}})}
vm.runInNewContext(code,{document:{getElementById:node},fetch:()=>{calls++;return response()},Error});return{nodes,button,submit:()=>handler({preventDefault(){}}),calls:()=>calls}}
async function tick(){await new Promise(r=>setImmediate(r))}
(async()=>{
for(const status of [400,402,403,503]){let t=setup(()=>Promise.resolve({ok:false,json:()=>Promise.resolve({error:'Actionable refusal '+status})}));t.submit();await tick();assert.equal(t.nodes['cm-error'].textContent,'Actionable refusal '+status);assert.equal(t.button.disabled,false)}
let t=setup(()=>Promise.resolve({ok:false,json:()=>Promise.resolve({error:'<img src=x onerror=alert(1)>'})}));t.submit();await tick();assert.equal(t.nodes['cm-error'].textContent,'<img src=x onerror=alert(1)>');assert.equal(t.nodes['cm-error'].innerHTML,undefined);
for(const response of [()=>Promise.reject(new TypeError('fetch failed')),()=>Promise.resolve({ok:false,json:()=>Promise.reject(new Error('not JSON'))}),()=>Promise.resolve({ok:true,json:()=>Promise.resolve({ok:true})})]){t=setup(response);t.submit();await tick();assert(t.nodes['cm-error'].textContent.includes('Could not reach'));assert.equal(t.button.disabled,false)}
let resolve;t=setup(()=>new Promise(r=>resolve=r));t.submit();t.submit();assert.equal(t.calls(),1);assert.equal(t.button.disabled,true);resolve({ok:true,json:()=>Promise.resolve({ok:true,b_link:'https://fixture.invalid/b',ws_id:'workspace',a_edit_id:'private'})});await tick();assert.equal(t.button.disabled,false);assert.equal(t.nodes['cm-b-link'].textContent,'https://fixture.invalid/b');t.submit();assert.equal(t.calls(),2);
console.log('9 form behavior scenarios passed');})().catch(e=>{console.error(e.message);process.exit(1)});
