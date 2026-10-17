package io.github.rys070425design.universalvoicemobile;

import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.widget.TextView;
import androidx.lifecycle.ViewModelProvider;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.lang.reflect.Method;
import static org.junit.Assert.*;

/** Screen fixtures are labelled as authored captions, not microphone output. */
@RunWith(AndroidJUnit4.class)
public class DeviceUiTest {
    @Test public void koreanAndEnglishScreensKeepControlsAccessible() throws Exception {
        var instrumentation=InstrumentationRegistry.getInstrumentation();Context context=instrumentation.getTargetContext();
        for(String target:new String[]{"ko","en"}) {
            context.getSharedPreferences("settings",0).edit().putString("target",target).putString("source",target.equals("ko")?"en":"ko").commit();
            MainActivity activity=(MainActivity)instrumentation.startActivitySync(new Intent(context,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TASK));
            try {
                instrumentation.waitForIdleSync();
                instrumentation.runOnMainSync(()->{
                    ConversationState state=new ViewModelProvider(activity).get(ConversationState.class);
                    state.captions.offer(new CaptionLedger.Card(100,1,"Where is the nearest subway station?",target.equals("ko")?"가장 가까운 지하철역은 어디에 있나요?":"Where is the nearest subway station?",true));
                    state.captions.offer(new CaptionLedger.Card(101,1,"Could you speak a little more slowly?",target.equals("ko")?"조금 더 천천히 말씀해 주실 수 있나요?":"Could you speak a little more slowly?",true));
                    try{Method render=MainActivity.class.getDeclaredMethod("renderCaptions");render.setAccessible(true);render.invoke(activity);}catch(Exception error){throw new AssertionError(error);}
                    assertTrue(activity.findViewById(R.id.listen).isShown());assertTrue(activity.findViewById(R.id.listen).getHeight()>0);
                    assertTrue(((TextView)activity.findViewById(R.id.caption)).getText().length()>0);
                    assertFalse(activity.findViewById(R.id.caption).isSaveEnabled());
                    android.graphics.Rect rect=new android.graphics.Rect();assertTrue(activity.findViewById(R.id.listen).getGlobalVisibleRect(rect));
                    assertTrue("Start/stop button must remain on screen",rect.bottom<=activity.findViewById(R.id.root).getHeight());
                });
                instrumentation.waitForIdleSync();
                instrumentation.runOnMainSync(()->{
                    android.graphics.Rect visible=new android.graphics.Rect();TextView caption=activity.findViewById(R.id.caption);
                    assertTrue("Latest caption must be in the readable viewport",caption.getGlobalVisibleRect(visible));
                    assertTrue("At least two text lines remain visible",visible.height()>=Math.min(caption.getHeight(),caption.getLineHeight()*2));
                });
                Bitmap image=instrumentation.getUiAutomation().takeScreenshot();assertNotNull(image);
                try(var stream=context.openFileOutput("ui-fixture-"+target+".png",Context.MODE_PRIVATE)){assertTrue(image.compress(Bitmap.CompressFormat.PNG,100,stream));}image.recycle();
            } finally {instrumentation.runOnMainSync(activity::finish);instrumentation.waitForIdleSync();}
        }
    }
}
