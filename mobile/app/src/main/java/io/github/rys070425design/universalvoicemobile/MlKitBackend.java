package io.github.rys070425design.universalvoicemobile;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import com.google.mlkit.common.model.DownloadConditions;
import com.google.mlkit.common.model.RemoteModelManager;
import com.google.mlkit.nl.translate.TranslateRemoteModel;
import com.google.android.gms.tasks.Tasks;
import com.google.android.gms.tasks.Task;
import java.util.ArrayList;
import java.util.List;
import com.google.mlkit.nl.translate.TranslateLanguage;
import com.google.mlkit.nl.translate.Translation;
import com.google.mlkit.nl.translate.Translator;
import com.google.mlkit.nl.translate.TranslatorOptions;

public final class MlKitBackend implements OnDeviceTranslator {
    private final Handler main=new Handler(Looper.getMainLooper());
    private Translator translator;
    private long generation;
    private boolean ready;
    private String pair="";
    public MlKitBackend(Context ignored) {}
    public boolean isReady(){return ready;}
    public void configure(String source,String target) {
        String newPair=Languages.translationCode(source)+":"+Languages.translationCode(target);
        if(pair.equals(newPair)&&translator!=null)return;
        close();pair=newPair;
        String from=TranslateLanguage.fromLanguageTag(Languages.translationCode(source));
        String to=TranslateLanguage.fromLanguageTag(Languages.translationCode(target));
        if(from==null||to==null)throw new IllegalArgumentException("Unsupported translation language");
        translator=Translation.getClient(new TranslatorOptions.Builder().setSourceLanguage(from).setTargetLanguage(to).build());
    }
    public void prepare(boolean wifiOnly,Preparation callback) {
        if(translator==null){callback.failed();return;}
        long token=generation;
        DownloadConditions.Builder conditions=new DownloadConditions.Builder();
        if(wifiOnly)conditions.requireWifi();
        translator.downloadModelIfNeeded(conditions.build())
            .addOnSuccessListener(unused-> {
                if(token!=generation)return;
                // Initialize inference before opening the microphone.
                translator.translate("1").addOnSuccessListener(value->{
                    if(token==generation){ready=true;callback.ready();}
                }).addOnFailureListener(error->{if(token==generation)callback.failed();});
            }).addOnFailureListener(error->{if(token==generation)callback.failed();});
    }
    public void checkDownloaded(Preparation callback) {
        long token=generation;List<Task<Boolean>> checks=new ArrayList<>();
        for(String code:pair.split(":"))if(!code.equals("en"))
            checks.add(RemoteModelManager.getInstance().isModelDownloaded(new TranslateRemoteModel.Builder(code).build()));
        Tasks.<Boolean>whenAllSuccess(checks).addOnSuccessListener(results->{
            if(token!=generation)return;
            if(results.stream().allMatch(Boolean::booleanValue))prepare(false,callback);else callback.failed();
        }).addOnFailureListener(error->{if(token==generation)callback.failed();});
    }
    @Override public void translate(String text,TranslationPump.Result callback) {
        if(!ready||translator==null){callback.failure();return;}
        long token=generation;
        translator.translate(text).addOnSuccessListener(value->main.post(()->{
            if(token==generation)callback.success(value);else callback.failure();
        })).addOnFailureListener(error->main.post(callback::failure));
    }
    @Override public void close() {
        generation++;ready=false;
        if(translator!=null){translator.close();translator=null;}
    }
}
