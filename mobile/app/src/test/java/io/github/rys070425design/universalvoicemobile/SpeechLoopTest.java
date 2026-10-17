package io.github.rys070425design.universalvoicemobile;

import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.LooperMode;
import static org.junit.Assert.*;
import static org.robolectric.Shadows.shadowOf;

@RunWith(RobolectricTestRunner.class) @Config(sdk=35) @LooperMode(LooperMode.Mode.PAUSED)
public class SpeechLoopTest {
    static class Harness implements SpeechLoop.Factory,SpeechLoop.Client,SpeechLoop.Listener {
        RecognitionListener callbacks;int starts,destroyed,errors,words;Intent intent;long lastId;boolean offline;
        final SpeechLoop loop=new SpeechLoop(new Handler(Looper.getMainLooper()),this,this);
        public SpeechLoop.Client create(boolean local,RecognitionListener listener){offline=local;callbacks=listener;return this;}
        public void listen(Intent value){intent=value;starts++;}public void cancel(){}public void destroy(){destroyed++;}
        public void words(long id,int revision,String text,boolean complete){words++;lastId=id;}
        public void failed(int code){errors++;}public void level(float value){}
    }
    static Bundle result(String text){Bundle b=new Bundle();b.putStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION,new ArrayList<>(List.of(text)));return b;}
    void tick(long milliseconds){shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMillis(milliseconds));}
    @Test public void intentRequestsCorrectLanguageAndExplicitOfflineMode(){
        Harness h=new Harness();h.loop.start("en-US",true);assertTrue(h.offline);
        assertEquals("en-US",h.intent.getStringExtra(RecognizerIntent.EXTRA_LANGUAGE));assertTrue(h.intent.getBooleanExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE,false));
        assertTrue(h.intent.getBooleanExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS,false));h.loop.stop();
    }
    @Test public void stoppingCancelsRetryAndLateCallbacks(){
        Harness h=new Harness();h.loop.start("en-US",true);RecognitionListener old=h.callbacks;
        old.onError(SpeechRecognizer.ERROR_NO_MATCH);h.loop.stop();tick(2000);old.onResults(result("late"));
        assertEquals(1,h.starts);assertEquals(0,h.words);assertFalse(h.loop.isActive());assertEquals(1,h.destroyed);
    }
    @Test public void oldServiceCannotInjectIntoNewSession(){
        Harness h=new Harness();h.loop.start("en-US",true);RecognitionListener old=h.callbacks;h.loop.start("ko-KR",true);
        old.onResults(result("stale"));h.callbacks.onPartialResults(result("현재"));assertEquals(1,h.words);h.loop.stop();
    }
    @Test public void finalRestartsOnceAndUsesNewUtteranceId(){
        Harness h=new Harness();h.loop.start("en-US",true);h.callbacks.onResults(result("first"));long first=h.lastId;
        h.callbacks.onResults(result("duplicate"));assertEquals(1,h.words);tick(180);assertEquals(2,h.starts);
        h.callbacks.onResults(result("second"));assertTrue(h.lastId>first);h.loop.stop();tick(1000);assertEquals(2,h.starts);
    }
    @Test public void busyErrorsStopAfterTwoRetries(){
        Harness h=new Harness();h.loop.start("en-US",true);h.callbacks.onError(SpeechRecognizer.ERROR_RECOGNIZER_BUSY);tick(700);
        h.callbacks.onError(SpeechRecognizer.ERROR_RECOGNIZER_BUSY);tick(1400);h.callbacks.onError(SpeechRecognizer.ERROR_RECOGNIZER_BUSY);tick(5000);
        assertEquals(3,h.starts);assertEquals(1,h.errors);assertFalse(h.loop.isActive());
    }
    @Test public void permissionErrorNeverRetries(){
        Harness h=new Harness();h.loop.start("en-US",true);h.callbacks.onError(SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS);tick(5000);
        assertEquals(1,h.starts);assertEquals(1,h.errors);assertFalse(h.loop.isActive());
    }
    @Test public void silenceCanRetryWithoutShowingErrors(){
        Harness h=new Harness();h.loop.start("en-US",true);h.callbacks.onError(SpeechRecognizer.ERROR_SPEECH_TIMEOUT);tick(450);
        assertEquals(2,h.starts);assertEquals(0,h.errors);h.loop.stop();
    }
}
