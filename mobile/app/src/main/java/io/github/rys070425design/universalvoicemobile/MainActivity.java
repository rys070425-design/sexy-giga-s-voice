package io.github.rys070425design.universalvoicemobile;

import android.Manifest;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.res.Configuration;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.speech.SpeechRecognizer;
import android.view.View;
import android.view.WindowManager;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.lifecycle.ViewModelProvider;
import com.google.android.material.button.MaterialButton;
import com.google.android.material.dialog.MaterialAlertDialogBuilder;
import com.google.android.material.materialswitch.MaterialSwitch;
import com.google.android.material.snackbar.Snackbar;
import java.io.IOException;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public class MainActivity extends AppCompatActivity {
    private static final int MICROPHONE_REQUEST=10;
    private final Handler main=new Handler(Looper.getMainLooper());
    private SharedPreferences preferences;
    private String sourceLanguage,targetLanguage;
    private boolean offline,foreground,preparing,destroyed;
    private long intentEpoch,preparationEpoch,lastDraftTime;
    private long lastRenderedUtterance=Long.MIN_VALUE;
    private Runnable pendingDraft;
    private CaptionLedger ledger;
    private ConversationState conversation;
    private OnDeviceTranslator backend;
    private TranslationPump pump;
    private SpeechLoop speech;
    private SpeechRecognizer downloadRecognizer;
    private TextView caption,previous,original,status,badge;
    private MaterialButton source,target,listen,prepare;
    private ProgressBar level;

    @Override protected void attachBaseContext(Context base) {
        SharedPreferences prefs=base.getSharedPreferences("settings",MODE_PRIVATE);
        String chosen=prefs.getString("target",null);
        if(chosen==null){chosen=Languages.defaultTarget();prefs.edit().putString("target",chosen).apply();}
        Configuration configuration=new Configuration(base.getResources().getConfiguration());
        configuration.setLocale(Locale.forLanguageTag(chosen.equals("ko")?"ko":"en"));
        super.attachBaseContext(base.createConfigurationContext(configuration));
    }
    @Override protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);setContentView(R.layout.activity_main);
        preferences=getSharedPreferences("settings",MODE_PRIVATE);
        targetLanguage=Languages.get(preferences.getString("target","en")).code();
        sourceLanguage=Languages.get(preferences.getString("source",targetLanguage.equals("en")?"ko":"en")).code();
        offline=preferences.getBoolean("offline",true);
        conversation=new ViewModelProvider(this).get(ConversationState.class);ledger=conversation.captions;
        caption=findViewById(R.id.caption);previous=findViewById(R.id.previous);original=findViewById(R.id.original);
        // Keep conversation text in RAM only, including Android view-state snapshots.
        caption.setSaveEnabled(false);previous.setSaveEnabled(false);original.setSaveEnabled(false);
        status=findViewById(R.id.status);badge=findViewById(R.id.mode_badge);
        source=findViewById(R.id.source);target=findViewById(R.id.target);listen=findViewById(R.id.listen);prepare=findViewById(R.id.prepare);level=findViewById(R.id.level);
        View root=findViewById(R.id.root);
        ViewCompat.setOnApplyWindowInsetsListener(root,(view,insets)->{
            Insets safe=insets.getInsets(WindowInsetsCompat.Type.systemBars()|WindowInsetsCompat.Type.displayCutout());
            view.setPadding(dp(22)+safe.left,safe.top,dp(22)+safe.right,safe.bottom);return insets;
        });
        ViewCompat.requestApplyInsets(root);
        boolean dark=(getResources().getConfiguration().uiMode&Configuration.UI_MODE_NIGHT_MASK)==Configuration.UI_MODE_NIGHT_YES;
        androidx.core.view.WindowCompat.getInsetsController(getWindow(),root).setAppearanceLightStatusBars(!dark);
        androidx.core.view.WindowCompat.getInsetsController(getWindow(),root).setAppearanceLightNavigationBars(!dark);
        backend=createTranslator();
        pump=new TranslationPump((text,result)->backend.translate(text,result),new TranslationPump.Listener(){
            public void caption(CaptionLedger.Card card){if(!destroyed&&ledger.offer(card)){conversation.failedOriginal="";renderCaptions();}}
            public void error(String raw){if(!destroyed){conversation.failedOriginal=raw;stopListening(R.string.translation_error);renderCaptions();}}
            public void overflow(){if(!destroyed)showStatus(R.string.processing_delay);}
        });
        speech=createSpeechLoop(new SpeechLoop.Listener(){
            public void words(long utterance,int revision,String text,boolean complete){recognize(utterance,revision,text,complete);}
            public void failed(int error){speechFailed(error);}
            public void level(float rms){level.setProgress(Math.max(0,Math.min(100,(int)((rms+2)*9))));}
        });
        source.setOnClickListener(view->chooseLanguage(true));target.setOnClickListener(view->chooseLanguage(false));
        findViewById(R.id.swap).setOnClickListener(view->changeLanguages(targetLanguage,sourceLanguage));
        findViewById(R.id.settings).setOnClickListener(view->showSettings());
        findViewById(R.id.privacy).setOnClickListener(view->showPrivacy());
        findViewById(R.id.attribution).setOnClickListener(view->openUrl("https://translate.google.com"));
        listen.setOnClickListener(view->{if(speech.isActive())stopListening(R.string.paused);else requestStart();});
        prepare.setOnClickListener(view->showPreparation(false));
        updateLanguages();renderCaptions();
    }
    private int dp(int value){return Math.round(getResources().getDisplayMetrics().density*value);}
    protected OnDeviceTranslator createTranslator(){return new MlKitBackend(this);}
    protected SpeechLoop createSpeechLoop(SpeechLoop.Listener listener){return new SpeechLoop(this,listener);}
    private void updateLanguages() {
        source.setText(Languages.get(sourceLanguage).name());target.setText(Languages.get(targetLanguage).name());
        badge.setText(offline?R.string.offline_badge:R.string.system_badge);
        caption.setTextLocale(Locale.forLanguageTag(targetLanguage));original.setTextLocale(Locale.forLanguageTag(sourceLanguage));
        if(Languages.same(sourceLanguage,targetLanguage)){showStatus(R.string.same_language);listen.setEnabled(false);prepare.setEnabled(false);return;}
        listen.setEnabled(true);prepare.setEnabled(true);
        try {
            backend.configure(sourceLanguage,targetLanguage);
            long token=++preparationEpoch;
            backend.checkDownloaded(new OnDeviceTranslator.Preparation(){
                public void ready(){if(!destroyed&&token==preparationEpoch&&!speech.isActive()){prepare.setText(R.string.packs_ready);}}
                public void failed(){}
            });
        } catch(RuntimeException error){showStatus(R.string.packs_failed);}
        if(offline&&!offlineAvailable())showStatus(R.string.offline_unavailable);
    }
    protected boolean offlineAvailable(){return Build.VERSION.SDK_INT>=31&&SpeechRecognizer.isOnDeviceRecognitionAvailable(this);}
    protected boolean systemSpeechAvailable(){return SpeechRecognizer.isRecognitionAvailable(this);}
    private void chooseLanguage(boolean choosingSource) {
        stopListening(R.string.paused);
        String[] names=Languages.ALL.stream().map(Languages.Entry::name).toArray(String[]::new);
        String chosen=choosingSource?sourceLanguage:targetLanguage;int selected=0;
        for(int index=0;index<Languages.ALL.size();index++)if(Languages.ALL.get(index).code().equals(chosen))selected=index;
        new MaterialAlertDialogBuilder(this).setTitle(choosingSource?R.string.source_language:R.string.target_language)
            .setSingleChoiceItems(names,selected,(dialog,index)->{
                String code=Languages.ALL.get(index).code();dialog.dismiss();
                changeLanguages(choosingSource?code:sourceLanguage,choosingSource?targetLanguage:code);
            }).setNegativeButton(R.string.cancel,null).show();
    }
    private void changeLanguages(String from,String to) {
        stopListening(R.string.paused);preparationEpoch++;preparing=false;
        boolean uiChanges=targetLanguage.equals("ko")!=to.equals("ko");sourceLanguage=from;targetLanguage=to;
        preferences.edit().putString("source",from).putString("target",to).apply();ledger.clear();conversation.failedOriginal="";
        if(uiChanges){recreate();return;}
        prepare.setEnabled(true);prepare.setText(R.string.prepare);updateLanguages();renderCaptions();
    }
    private void showPreparation(boolean startAfter) {
        if(Languages.same(sourceLanguage,targetLanguage)){showStatus(R.string.same_language);return;}
        stopListening(R.string.paused);
        MaterialSwitch wifi=new MaterialSwitch(this);wifi.setText(R.string.wifi_only);wifi.setChecked(preferences.getBoolean("wifi",true));
        wifi.setPadding(dp(20),dp(8),dp(16),0);
        new MaterialAlertDialogBuilder(this).setTitle(R.string.download_title).setMessage(R.string.download_body)
            .setView(wifi).setNegativeButton(R.string.cancel,null).setPositiveButton(R.string.download,(dialog,which)->{
                preferences.edit().putBoolean("wifi",wifi.isChecked()).apply();prepareModels(startAfter,wifi.isChecked());
            }).show();
    }
    private void prepareModels(boolean startAfter,boolean wifiOnly) {
        preparing=true;prepare.setEnabled(false);prepare.setText(R.string.download_waiting);showStatus(R.string.preparing);
        long token=++preparationEpoch;long request=intentEpoch;
        backend.prepare(wifiOnly,new OnDeviceTranslator.Preparation(){
            public void ready(){
                if(destroyed||token!=preparationEpoch)return;
                preparing=false;prepare.setEnabled(true);prepare.setText(R.string.packs_ready);showStatus(R.string.ready);
                if(startAfter&&foreground&&request==intentEpoch)requestStart();
            }
            public void failed(){
                if(destroyed||token!=preparationEpoch)return;
                preparing=false;prepare.setEnabled(true);prepare.setText(R.string.prepare);showStatus(R.string.packs_failed);
            }
        });
    }
    private void requestStart() {
        if(!foreground||destroyed)return;
        if(offline&&!offlineAvailable()){showStatus(R.string.offline_unavailable);return;}
        if(!offline&&!systemSpeechAvailable()){showStatus(R.string.speech_unavailable);return;}
        if(Languages.same(sourceLanguage,targetLanguage)){showStatus(R.string.same_language);return;}
        if(preparing){showStatus(R.string.preparing);return;}
        if(!backend.isReady()){showPreparation(true);return;}
        if(checkSelfPermission(Manifest.permission.RECORD_AUDIO)!=PackageManager.PERMISSION_GRANTED){
            showStatus(R.string.permission_needed);requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO},MICROPHONE_REQUEST);return;
        }
        pump.reset();intentEpoch++;lastDraftTime=0;speech.start(Languages.get(sourceLanguage).speechTag(),offline);
        if(speech.isActive()){
            showStatus(R.string.listening);listen.setText(R.string.stop);level.setVisibility(View.VISIBLE);
            if(preferences.getBoolean("awake",true))getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        }
    }
    private void recognize(long utterance,int revision,String text,boolean complete) {
        if(!foreground||!speech.isActive())return;
        if(pendingDraft!=null){main.removeCallbacks(pendingDraft);pendingDraft=null;}
        if(complete){pump.offer(utterance,revision,text,true);return;}
        long now=android.os.SystemClock.uptimeMillis();long epoch=intentEpoch;
        Runnable update=()->{
            pendingDraft=null;
            if(foreground&&speech.isActive()&&epoch==intentEpoch){lastDraftTime=android.os.SystemClock.uptimeMillis();pump.offer(utterance,revision,text,false);}
        };
        if(now-lastDraftTime>=700)update.run();else{pendingDraft=update;main.postDelayed(update,700-(now-lastDraftTime));}
    }
    private void stopListening(int message) {
        intentEpoch++;
        if(pendingDraft!=null){main.removeCallbacks(pendingDraft);pendingDraft=null;}
        if(speech!=null)speech.stop();if(pump!=null)pump.reset();
        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        if(listen!=null)listen.setText(R.string.google_action);
        if(level!=null){level.setVisibility(View.INVISIBLE);level.setProgress(0);}
        if(status!=null)showStatus(message);
    }
    private void speechFailed(int error) {
        stopListening(R.string.speech_error);
        if(error==SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE||error==SpeechRecognizer.ERROR_LANGUAGE_NOT_SUPPORTED){
            showStatus(R.string.speech_language_missing);
            Snackbar.make(findViewById(R.id.root),R.string.speech_language_missing,Snackbar.LENGTH_LONG)
                .setAction(R.string.prepare_speech,view->prepareSpeechModel()).show();
        } else if(error==SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS)permissionDenied();
        else if(error==SpeechRecognizer.ERROR_NETWORK||error==SpeechRecognizer.ERROR_NETWORK_TIMEOUT)showStatus(R.string.network_error);
    }
    private void prepareSpeechModel() {
        stopListening(R.string.paused);
        if(Build.VERSION.SDK_INT<33||!offlineAvailable()){showStatus(R.string.speech_download_unavailable);return;}
        if(downloadRecognizer!=null)downloadRecognizer.destroy();
        try {
            downloadRecognizer=SpeechRecognizer.createOnDeviceSpeechRecognizer(this);
            downloadRecognizer.setRecognitionListener(new android.speech.RecognitionListener(){
                public void onReadyForSpeech(Bundle bundle){} public void onBeginningOfSpeech(){}
                public void onRmsChanged(float rms){} public void onBufferReceived(byte[] buffer){}
                public void onEndOfSpeech(){} public void onError(int code){}
                public void onResults(Bundle bundle){} public void onPartialResults(Bundle bundle){}
                public void onEvent(int type,Bundle bundle){}
            });
            // Retain this non-listening instance so its bind/request can complete.
            downloadRecognizer.triggerModelDownload(SpeechLoop.intent(Languages.get(sourceLanguage).speechTag(),true));
            showStatus(R.string.speech_download_requested);
        } catch(RuntimeException error){showStatus(R.string.speech_download_unavailable);}
    }
    @Override public void onRequestPermissionsResult(int request,@NonNull String[] permissions,@NonNull int[] grants) {
        super.onRequestPermissionsResult(request,permissions,grants);
        if(request==MICROPHONE_REQUEST){
            if(grants.length>0&&grants[0]==PackageManager.PERMISSION_GRANTED){if(foreground)requestStart();}
            else permissionDenied();
        }
    }
    private void permissionDenied(){
        showStatus(R.string.permission_denied);
        Snackbar.make(findViewById(R.id.root),R.string.permission_denied,Snackbar.LENGTH_LONG)
            .setAction(R.string.open_app_settings,view->startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,Uri.parse("package:"+getPackageName())))).show();
    }
    private void showStatus(int message){status.setText(message);}
    private void renderCaptions() {
        CaptionLedger.Card current=ledger.current(),older=ledger.previous();
        caption.setText(current==null?getString(R.string.empty_caption):current.translated());
        caption.setTextSize(preferences.getBoolean("large",false)?36:29);
        previous.setVisibility(older==null?View.GONE:View.VISIBLE);previous.setText(older==null?"":older.translated());
        original.setVisibility(preferences.getBoolean("original",true)?View.VISIBLE:View.GONE);
        original.setText(!conversation.failedOriginal.isEmpty()?conversation.failedOriginal:current==null?getString(R.string.empty_original):current.original());
        if(current!=null&&current.utterance()!=lastRenderedUtterance){
            lastRenderedUtterance=current.utterance();long id=current.utterance();
            caption.post(()->{
                if(!destroyed&&ledger.current()!=null&&ledger.current().utterance()==id)
                    caption.requestRectangleOnScreen(new android.graphics.Rect(0,0,caption.getWidth(),Math.min(caption.getHeight(),dp(240))),true);
            });
        }
    }
    private MaterialSwitch setting(int title,String key,boolean defaultValue) {
        MaterialSwitch control=new MaterialSwitch(this);control.setText(title);control.setChecked(preferences.getBoolean(key,defaultValue));
        control.setPadding(dp(20),dp(6),dp(20),dp(6));control.setMinHeight(dp(56));
        control.setOnCheckedChangeListener((button,checked)->{preferences.edit().putBoolean(key,checked).apply();renderCaptions();});return control;
    }
    private void showSettings() {
        stopListening(R.string.paused);
        LinearLayout choices=new LinearLayout(this);choices.setOrientation(LinearLayout.VERTICAL);
        choices.addView(setting(R.string.show_original,"original",true));choices.addView(setting(R.string.large_text,"large",false));choices.addView(setting(R.string.keep_awake,"awake",true));
        MaterialButton mode=new MaterialButton(this,null,com.google.android.material.R.attr.materialButtonOutlinedStyle);
        mode.setText(offline?R.string.on_device:R.string.system_speech);mode.setAllCaps(false);
        LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,dp(60));params.setMargins(dp(20),dp(12),dp(20),0);choices.addView(mode,params);
        TextView note=new TextView(this);note.setText(R.string.mode_explanation);note.setTextSize(12);note.setPadding(dp(20),dp(12),dp(20),dp(12));choices.addView(note);
        mode.setOnClickListener(view->{
            if(!offline){offline=true;preferences.edit().putBoolean("offline",true).apply();mode.setText(R.string.on_device);badge.setText(R.string.offline_badge);}
            else new MaterialAlertDialogBuilder(this).setTitle(R.string.system_speech).setMessage(R.string.system_consent)
                .setNegativeButton(R.string.cancel,null).setPositiveButton(R.string.use_service,(dialog,which)->{
                    offline=false;preferences.edit().putBoolean("offline",false).apply();mode.setText(R.string.system_speech);badge.setText(R.string.system_badge);
                }).show();
        });
        android.widget.ScrollView settingsScroll=new android.widget.ScrollView(this);settingsScroll.addView(choices);
        new MaterialAlertDialogBuilder(this).setTitle(R.string.settings).setView(settingsScroll).setPositiveButton(R.string.close,null)
            .setNeutralButton(R.string.clear,(dialog,which)->{ledger.clear();conversation.failedOriginal="";renderCaptions();})
            .setNegativeButton(R.string.prepare_speech,(dialog,which)->prepareSpeechModel()).show();
    }
    private void showPrivacy() {
        stopListening(R.string.paused);String message=getString(R.string.privacy_body);
        try(var input=getAssets().open("translation-notice.txt");var output=new ByteArrayOutputStream()){
            byte[] buffer=new byte[4096];int count;
            while((count=input.read(buffer))!=-1)output.write(buffer,0,count);
            message+="\n\n"+new String(output.toByteArray(),StandardCharsets.UTF_8);
        }
        catch(IOException ignored){}
        new MaterialAlertDialogBuilder(this).setTitle(R.string.privacy_title).setMessage(message).setPositiveButton(R.string.close,null).show();
    }
    private void openUrl(String url){stopListening(R.string.paused);try{startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(url)));}catch(android.content.ActivityNotFoundException ignored){}}
    @Override protected void onResume(){super.onResume();foreground=true;}
    @Override protected void onPause(){foreground=false;stopListening(R.string.background_paused);super.onPause();}
    @Override protected void onDestroy(){
        destroyed=true;preparationEpoch++;stopListening(R.string.paused);main.removeCallbacksAndMessages(null);
        if(downloadRecognizer!=null)downloadRecognizer.destroy();if(backend!=null)backend.close();super.onDestroy();
    }
}
