package io.github.rys070425design.universalvoicemobile;

import android.Manifest;
import android.content.Context;
import android.os.Looper;
import android.os.Handler;
import android.speech.RecognitionListener;
import android.view.View;
import android.widget.TextView;
import androidx.test.core.app.ApplicationProvider;
import java.time.Duration;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.LooperMode;
import static org.junit.Assert.*;
import static org.robolectric.Shadows.shadowOf;

@RunWith(RobolectricTestRunner.class) @Config(sdk=35) @LooperMode(LooperMode.Mode.PAUSED)
public class MainActivityTest {
    static final class FakeTranslator implements OnDeviceTranslator {
        TranslationPump.Result result;String pair;boolean closed;
        public void configure(String from,String to){pair=from+":"+to;}
        public void prepare(boolean wifi,Preparation cb){cb.ready();}
        public void checkDownloaded(Preparation cb){cb.ready();}
        public boolean isReady(){return true;}
        public void translate(String text,TranslationPump.Result cb){result=cb;}
        public void close(){closed=true;}
    }
    public static class TestActivity extends MainActivity {
        final FakeTranslator translator=new FakeTranslator();RecognitionListener callbacks;int starts,destroys;
        @Override protected OnDeviceTranslator createTranslator(){return translator;}
        @Override protected boolean offlineAvailable(){return true;}
        @Override protected boolean systemSpeechAvailable(){return true;}
        @Override protected SpeechLoop createSpeechLoop(SpeechLoop.Listener listener){
            return new SpeechLoop(new Handler(Looper.getMainLooper()),(offline,cb)->{
                callbacks=cb;return new SpeechLoop.Client(){
                    public void listen(android.content.Intent intent){starts++;}public void cancel(){}public void destroy(){destroys++;}
                };
            },listener);
        }
    }
    @Before public void prefs(){
        Context context=ApplicationProvider.getApplicationContext();context.getSharedPreferences("settings",0).edit().clear().putString("target","ko").putString("source","en").commit();
        shadowOf((android.app.Application)context).grantPermissions(Manifest.permission.RECORD_AUDIO);
    }
    private ActivityController<TestActivity> open(){return Robolectric.buildActivity(TestActivity.class).setup().visible();}
    private TextView text(TestActivity a,int id){return a.findViewById(id);}
    @Test public void targetKoreanLocalizesInterfaceAndNoTranscriptStateSaved(){
        var c=open();TestActivity a=c.get();assertEquals("en:ko",a.translator.pair);
        assertEquals("한국어",text(a,R.id.target).getText().toString());assertFalse(text(a,R.id.caption).isSaveEnabled());
        assertTrue(a.getString(R.string.stop).contains("중지"));c.pause().stop().destroy();
    }
    @Test public void leavingStopsMicrophoneAndIgnoresLateTranslations(){
        var c=open();TestActivity a=c.get();a.findViewById(R.id.listen).performClick();assertEquals(1,a.starts);
        a.callbacks.onResults(SpeechLoopTest.result("Hello"));TranslationPump.Result late=a.translator.result;
        c.pause();late.success("안녕하세요");shadowOf(Looper.getMainLooper()).idleFor(Duration.ofSeconds(2));
        assertEquals(1,a.starts);assertTrue(a.destroys>0);assertFalse(text(a,R.id.caption).getText().toString().contains("안녕하세요"));
        c.resume();assertEquals(1,a.starts);c.pause().stop().destroy();assertTrue(a.translator.closed);
    }
    @Test public void finalCaptionAndPreviousAreBothReadable(){
        var c=open();TestActivity a=c.get();a.findViewById(R.id.listen).performClick();
        a.callbacks.onResults(SpeechLoopTest.result("Hello"));a.translator.result.success("안녕하세요");
        shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMillis(180));a.callbacks.onResults(SpeechLoopTest.result("Thank you"));a.translator.result.success("감사합니다");
        assertEquals("감사합니다",text(a,R.id.caption).getText().toString());assertEquals("안녕하세요",text(a,R.id.previous).getText().toString());
        assertEquals(View.VISIBLE,text(a,R.id.previous).getVisibility());assertEquals("Thank you",text(a,R.id.original).getText().toString());c.pause().stop().destroy();
    }
    @Test public void translationFailureStopsMicrophoneAndPreservesOriginal(){
        var c=open();TestActivity a=c.get();a.findViewById(R.id.listen).performClick();a.callbacks.onResults(SpeechLoopTest.result("Please help"));
        a.translator.result.failure();shadowOf(Looper.getMainLooper()).idleFor(Duration.ofSeconds(3));
        assertEquals("Please help",text(a,R.id.original).getText().toString());assertEquals(1,a.starts);assertEquals(View.INVISIBLE,a.findViewById(R.id.level).getVisibility());c.pause().stop().destroy();
    }
    @Test public void sameLanguageDoesNotStartRecognition(){
        Context context=ApplicationProvider.getApplicationContext();context.getSharedPreferences("settings",0).edit().putString("source","ko").commit();
        var c=open();TestActivity a=c.get();assertFalse(a.findViewById(R.id.listen).isEnabled());assertEquals(0,a.starts);c.pause().stop().destroy();
    }
    @Test public void englishTargetUsesEnglishInterface(){
        Context context=ApplicationProvider.getApplicationContext();context.getSharedPreferences("settings",0).edit().putString("target","en").putString("source","ko").commit();
        var c=open();assertEquals("Stop listening",c.get().getString(R.string.stop));assertEquals("ko:en",c.get().translator.pair);c.pause().stop().destroy();
    }
}
