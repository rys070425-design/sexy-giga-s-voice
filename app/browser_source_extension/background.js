async function report() {
  const {key,enabled=true}=await chrome.storage.local.get(['key','enabled']);
  if (!key) return {ok:false,message:'앱의 웹사이트 이름 연결에서 코드를 복사해 주세요.'};
  const tabs=enabled ? await chrome.tabs.query({audible:true}) : [];
  const hosts=[...new Set(tabs.filter(t=>!t.incognito && !t.mutedInfo?.muted).map(t=>{
    try { const url=new URL(t.url);return ['https:','http:'].includes(url.protocol)?url.hostname:''; }
    catch (_) { return ''; }
  }).filter(Boolean))].slice(0,8);
  const browser=navigator.userAgent.includes('Edg/')?'edge':'chrome';
  try {
    const response=await fetch('http://127.0.0.1:43861/source',{
      method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+key},
      body:JSON.stringify({browser,hosts}),signal:AbortSignal.timeout(1500)
    });
    return {ok:response.ok,message:response.ok?'연결됨 · '+(hosts.join(', ')||'재생 대기'):'연결 코드를 확인해 주세요.'};
  } catch (_) { return {ok:false,message:'Universal Voice KR 앱을 먼저 켜 주세요.'}; }
}
chrome.tabs.onUpdated.addListener((_id,change)=>{if ('audible' in change || 'mutedInfo' in change || 'url' in change || 'status' in change) report();});
chrome.tabs.onRemoved.addListener(()=>report());
chrome.tabs.onReplaced.addListener(()=>report());
chrome.alarms.onAlarm.addListener(alarm=>{if(alarm.name==='source-heartbeat')report();});
chrome.runtime.onInstalled.addListener(()=>{chrome.alarms.create('source-heartbeat',{periodInMinutes:.5});report();});
chrome.runtime.onStartup.addListener(()=>{chrome.alarms.create('source-heartbeat',{periodInMinutes:.5});report();});
chrome.runtime.onMessage.addListener((message,_sender,reply)=>{if(message.type==='report'){report().then(reply);return true;}});
