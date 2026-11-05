// Exercise the actual Electron host address guard without launching a browser.
const fs=require('node:fs'),vm=require('node:vm'),net=require('node:net');
const source=fs.readFileSync(__dirname+'/desktop/main.cjs','utf8');
const start=source.indexOf('function privateIP('),end=source.indexOf('remoteSession.webRequest',start);
if(start<0||end<0)throw Error('Address guard not found');
const privateIP=vm.runInNewContext(source.slice(start,end)+';privateIP',{net});
const cases=[['192.0.66.161',false],['151.101.134.132',false],['192.168.1.1',true],['192.0.0.1',true],['127.0.0.1',true],['10.0.0.1',true],['172.16.1.1',true],['169.254.169.254',true],['100.64.0.1',true],['::1',true],['fc00::1',true],['fe80::1',true],['2606:4700:4700::1111',false]];
const checks=cases.map(([address,blocked])=>({address,expected_blocked:blocked,ok:privateIP(address)===blocked}));
fs.writeFileSync(__dirname+'/reports/browser-address-checks.json',JSON.stringify({checks},null,2));
if(checks.some(c=>!c.ok))throw Error('Address boundary regression');
console.log(JSON.stringify({passed:checks.length}));
