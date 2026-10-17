package io.github.rys070425design.universalvoicemobile;

import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import java.util.ArrayList;
import java.util.concurrent.atomic.AtomicLong;

/** Explicit foreground listening. Stop destroys the service and pending retries. */
public final class SpeechLoop implements AutoCloseable {
    private static final AtomicLong IDS=new AtomicLong();
    public interface Listener {void words(long utterance,int revision,String text,boolean complete);void failed(int error);void level(float rms);}
    public interface Client {void listen(Intent intent);void cancel();void destroy();}
    public interface Factory {Client create(boolean onDevice,RecognitionListener listener);}
    private final Handler main;
    private final Factory factory;
    private final Listener listener;
    private Client client;
    private boolean active,inTurn;
    private String language;
    private boolean onDevice;
    private long generation,utterance;
    private int revision,retryCount;
    private Runnable restart;
    public SpeechLoop(Context context,Listener listener) {
        this(new Handler(Looper.getMainLooper()),(offline,callbacks)->{
            SpeechRecognizer recognizer=offline&&Build.VERSION.SDK_INT>=31?
                SpeechRecognizer.createOnDeviceSpeechRecognizer(context):SpeechRecognizer.createSpeechRecognizer(context);
            recognizer.setRecognitionListener(callbacks);
            return new Client(){
                public void listen(Intent intent){recognizer.startListening(intent);}
                public void cancel(){recognizer.cancel();}
                public void destroy(){recognizer.destroy();}
            };
        },listener);
    }
    SpeechLoop(Handler handler,Factory factory,Listener listener){main=handler;this.factory=factory;this.listener=listener;}
    public boolean isActive(){return active;}
    public void start(String language,boolean onDevice) {
        stop();this.language=language;this.onDevice=onDevice;active=true;retryCount=0;
        long token=generation;
        try{client=factory.create(onDevice,new Callbacks(token));begin();}
        catch(RuntimeException error){stop();listener.failed(SpeechRecognizer.ERROR_CLIENT);}
    }
    static Intent intent(String language,boolean offline) {
        return new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE,language)
            .putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS,true)
            .putExtra(RecognizerIntent.EXTRA_MAX_RESULTS,1)
            .putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE,offline);
    }
    private void begin() {
        if(!active||client==null)return;
        utterance=IDS.incrementAndGet();revision=0;inTurn=true;
        try{client.listen(intent(language,onDevice));}
        catch(RuntimeException error){stop();listener.failed(SpeechRecognizer.ERROR_CLIENT);}
    }
    private void schedule(long delay) {
        inTurn=false;if(!active)return;
        if(restart!=null)main.removeCallbacks(restart);
        long token=generation;restart=()->{if(active&&generation==token)begin();};main.postDelayed(restart,delay);
    }
    public void stop() {
        active=false;inTurn=false;generation++;
        if(restart!=null){main.removeCallbacks(restart);restart=null;}
        if(client!=null){Client old=client;client=null;try{old.cancel();}catch(RuntimeException ignored){}
            try{old.destroy();}catch(RuntimeException ignored){}}
    }
    @Override public void close(){stop();}
    private final class Callbacks implements RecognitionListener {
        private final long token;
        Callbacks(long token){this.token=token;}
        private boolean valid(){return active&&generation==token&&inTurn;}
        private void text(Bundle result,boolean complete) {
            if(!valid())return;
            ArrayList<String> texts=result.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
            if(texts!=null&&!texts.isEmpty()&&!texts.get(0).isBlank()){
                retryCount=0;listener.words(utterance,++revision,texts.get(0),complete);
            }
            if(complete)schedule(180);
        }
        @Override public void onResults(Bundle results){text(results,true);}
        @Override public void onPartialResults(Bundle results){text(results,false);}
        @Override public void onError(int error) {
            if(!valid())return;
            if(error==SpeechRecognizer.ERROR_NO_MATCH||error==SpeechRecognizer.ERROR_SPEECH_TIMEOUT){schedule(450);return;}
            if(error==SpeechRecognizer.ERROR_RECOGNIZER_BUSY&&retryCount++<2){schedule(700L*retryCount);return;}
            stop();listener.failed(error);
        }
        @Override public void onRmsChanged(float rmsdB){if(valid())listener.level(rmsdB);}
        @Override public void onReadyForSpeech(Bundle params){}
        @Override public void onBeginningOfSpeech(){}
        @Override public void onBufferReceived(byte[] buffer){}
        @Override public void onEndOfSpeech(){}
        @Override public void onEvent(int type,Bundle params){}
    }
}
