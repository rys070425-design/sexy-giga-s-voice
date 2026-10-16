chrome.storage.local.get(['key','enabled'],data=>{document.querySelector('#key').value=data.key||'';document.querySelector('#enabled').checked=data.enabled!==false;});
document.querySelector('#save').addEventListener('click',async()=>{
  const key=document.querySelector('#key').value.trim();
  if(key.length<20){document.querySelector('#state').textContent='연결 코드를 확인해 주세요.';return;}
  await chrome.storage.local.set({key,enabled:document.querySelector('#enabled').checked});
  const result=await chrome.runtime.sendMessage({type:'report'});
  document.querySelector('#state').textContent=result.message;
});
