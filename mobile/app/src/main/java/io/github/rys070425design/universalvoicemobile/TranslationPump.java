package io.github.rys070425design.universalvoicemobile;

import java.util.ArrayDeque;
import java.util.LinkedHashMap;
import java.util.Map;

/** Main-thread pump: one inference in flight, four finals and one latest draft. */
public final class TranslationPump {
    public interface Result {void success(String text);void failure();}
    public interface Backend {void translate(String text,Result result);}
    public interface Listener {void caption(CaptionLedger.Card card);void error(String original);void overflow();}
    private record Request(long generation,long utterance,int revision,String text,boolean complete) {}
    private final Backend backend;
    private final Listener listener;
    private final ArrayDeque<Request> finals=new ArrayDeque<>();
    private final Map<Long,Integer> completed=new LinkedHashMap<>();
    private final LinkedHashMap<String,String> cache=new LinkedHashMap<>(64,.75f,true);
    private Request draft,inFlight;
    private long generation=0;
    public TranslationPump(Backend backend,Listener listener){this.backend=backend;this.listener=listener;}
    public void reset(){generation++;finals.clear();draft=null;completed.clear();cache.clear();}
    public int pendingCount(){return finals.size()+(draft==null?0:1);}
    public void offer(long utterance,int revision,String text,boolean complete) {
        text=text==null?"":text.strip();if(text.isEmpty())return;
        Request request=new Request(generation,utterance,revision,text,complete);
        if(complete) {
            if(completed.containsKey(utterance)&&completed.get(utterance)>=revision)return;
            completed.put(utterance,revision);
            while(completed.size()>64)completed.remove(completed.keySet().iterator().next());
            if(draft!=null&&draft.utterance()==utterance)draft=null;
            if(finals.size()==4){finals.removeFirst();listener.overflow();}
            finals.addLast(request);
        } else {
            if(completed.containsKey(utterance))return;
            if(draft!=null&&draft.utterance()==utterance&&draft.text().equals(text))return;
            draft=request;
        }
        drain();
    }
    private void drain() {
        if(inFlight!=null)return;
        Request next=finals.pollFirst();
        if(next==null){next=draft;draft=null;}
        if(next==null)return;
        Request request=next;inFlight=request;
        String saved=cache.get(request.text());
        if(saved!=null){finish(request,saved,false);return;}
        try {
            backend.translate(request.text(),new Result(){
                @Override public void success(String text){finish(request,text,false);}
                @Override public void failure(){finish(request,"",true);}
            });
        } catch(RuntimeException error){finish(request,"",true);}
    }
    private void finish(Request request,String translated,boolean failed) {
        if(inFlight!=request)return;
        inFlight=null;
        if(request.generation()==generation) {
            if(failed)listener.error(request.text());
            else if(translated!=null&&!translated.isBlank()) {
                cache.put(request.text(),translated);
                while(cache.size()>64)cache.remove(cache.keySet().iterator().next());
                if(request.complete()||!completed.containsKey(request.utterance()))
                    listener.caption(new CaptionLedger.Card(request.utterance(),request.revision(),request.text(),translated,request.complete()));
            }
        }
        drain();
    }
}
