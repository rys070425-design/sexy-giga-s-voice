package io.github.rys070425design.universalvoicemobile;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import android.content.Context;
import android.os.Bundle;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.json.JSONObject;
import org.json.JSONArray;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.nio.charset.StandardCharsets;
import static org.junit.Assert.*;

/** Actual ML Kit model smoke test; no microphone or fabricated ASR accuracy score. */
@RunWith(AndroidJUnit4.class)
public class TranslationDeviceTest {
    @Test public void downloadedModelTranslatesOwnedExamplesInBothDirections() throws Exception {
        var instrumentation=InstrumentationRegistry.getInstrumentation();Context context=instrumentation.getTargetContext();
        AtomicReference<MlKitBackend> ref=new AtomicReference<>();CountDownLatch prepared=new CountDownLatch(1);AtomicReference<String> failure=new AtomicReference<>();
        long preparationStarted=System.nanoTime();
        instrumentation.runOnMainSync(()->{
            MlKitBackend backend=new MlKitBackend(context);ref.set(backend);backend.configure("en","ko");
            backend.prepare(false,new OnDeviceTranslator.Preparation(){public void ready(){prepared.countDown();}public void failed(){failure.set("model preparation failed");prepared.countDown();}});
        });
        assertTrue("Model preparation timed out",prepared.await(240,TimeUnit.SECONDS));assertNull(failure.get());
        JSONArray examples=new JSONArray();
        try {
            for(String phrase:new String[]{"Could you speak a little more slowly?","Where is the nearest subway station?","I do not eat peanuts.","Please call me when you arrive.","This is more expensive than I expected."}) {
                CountDownLatch done=new CountDownLatch(1);AtomicReference<String> output=new AtomicReference<>();long started=System.nanoTime();
                instrumentation.runOnMainSync(()->ref.get().translate(phrase,new TranslationPump.Result(){public void success(String text){output.set(text);done.countDown();}public void failure(){done.countDown();}}));
                assertTrue("Translation timed out",done.await(30,TimeUnit.SECONDS));assertNotNull(output.get());assertFalse(output.get().isBlank());assertNotEquals(phrase,output.get());
                examples.put(new JSONObject().put("source",phrase).put("translation",output.get()).put("inference_ms",(System.nanoTime()-started)/1_000_000));
            }
            CountDownLatch reverseReady=new CountDownLatch(1);
            instrumentation.runOnMainSync(()->{ref.get().configure("ko","en");ref.get().checkDownloaded(new OnDeviceTranslator.Preparation(){public void ready(){reverseReady.countDown();}public void failed(){failure.set("cached reverse model unavailable");reverseReady.countDown();}});});
            assertTrue(reverseReady.await(60,TimeUnit.SECONDS));assertNull(failure.get());
            CountDownLatch reversed=new CountDownLatch(1);AtomicReference<String> reverseOutput=new AtomicReference<>();
            instrumentation.runOnMainSync(()->ref.get().translate("조금 천천히 말해 주세요.",new TranslationPump.Result(){public void success(String text){reverseOutput.set(text);reversed.countDown();}public void failure(){reversed.countDown();}}));
            assertTrue(reversed.await(30,TimeUnit.SECONDS));assertNotNull(reverseOutput.get());
            JSONObject report=new JSONObject().put("actual_mlkit_inference",true).put("actual_microphone_or_asr_test",false)
                .put("environment","Android 35 x86_64 headless emulator; no host audio")
                .put("examples",examples).put("reverse_translation",reverseOutput.get())
                .put("total_test_ms",(System.nanoTime()-preparationStarted)/1_000_000);
            try(var out=context.openFileOutput("mobile-validation.json",Context.MODE_PRIVATE)){out.write(report.toString(2).getBytes(StandardCharsets.UTF_8));}
            Bundle status=new Bundle();status.putString("stream","Actual ML Kit EN/KO model: 5 forward + 1 reverse examples passed. No ASR accuracy test.\n");instrumentation.sendStatus(0,status);
        } finally {instrumentation.runOnMainSync(()->ref.get().close());}
    }
}
