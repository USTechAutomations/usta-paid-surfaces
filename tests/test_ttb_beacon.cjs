const fs=require('fs'),vm=require('vm'),assert=require('assert');
const code=fs.readFileSync(__dirname+'/../scripts/click_beacon.js','utf8');
function run(nav,family='ttb') {const calls=[];let handler;vm.runInNewContext(code,{navigator:nav,document:{currentScript:{getAttribute:()=>'/feeds/click/ttb.gif'},addEventListener:(_,h)=>handler=h},fetch:(u,o)=>calls.push([u,o])});if(handler)handler({target:{closest:()=>({getAttribute:()=>family})}});return calls;}
assert.equal(run({}).length,1);assert.equal(run({})[0][0],'/feeds/click/ttb.gif?f=ttb');
assert.equal(run({webdriver:true})[0][0],'/feeds/click/ttb.gif?f=ttb&probe=1');
assert.equal(run({doNotTrack:'1'}).length,0);assert.equal(run({globalPrivacyControl:true}).length,0);assert.equal(run({},'grid').length,0);
console.log('6 beacon assertions pass');
