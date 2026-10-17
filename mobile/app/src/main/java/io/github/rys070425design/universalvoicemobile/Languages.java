package io.github.rys070425design.universalvoicemobile;

import java.util.List;
import java.util.Locale;

public final class Languages {
    public record Entry(String code, String name, String speechTag) {}
    public static final List<Entry> ALL = List.of(
        new Entry("en","English","en-US"),new Entry("ko","한국어","ko-KR"),
        new Entry("es","Español","es-ES"),new Entry("pt","Português","pt-PT"),
        new Entry("pt-BR","Português (Brasil)","pt-BR"),new Entry("ru","Русский","ru-RU"),
        new Entry("pl","Polski","pl-PL"),new Entry("tr","Türkçe","tr-TR"),
        new Entry("de","Deutsch","de-DE"),new Entry("fr","Français","fr-FR"),
        new Entry("zh","中文（简体）","zh-CN"),new Entry("ja","日本語","ja-JP"),
        new Entry("it","Italiano","it-IT"),new Entry("ar","العربية","ar-SA"),
        new Entry("uk","Українська","uk-UA"),new Entry("nl","Nederlands","nl-NL"),
        new Entry("id","Bahasa Indonesia","id-ID"),new Entry("hi","हिन्दी","hi-IN"),
        new Entry("cs","Čeština","cs-CZ"),new Entry("sv","Svenska","sv-SE"),
        new Entry("vi","Tiếng Việt","vi-VN"),new Entry("th","ไทย","th-TH"),
        new Entry("tl","Filipino","fil-PH"),new Entry("ro","Română","ro-RO"),
        new Entry("fa","فارسی","fa-IR"));
    private Languages() {}
    public static Entry get(String code) {
        for (Entry language:ALL) if(language.code().equals(code))return language;
        return ALL.get(0);
    }
    public static String translationCode(String code) {return code.equals("pt-BR")?"pt":code;}
    public static boolean same(String a,String b) {return translationCode(a).equals(translationCode(b));}
    public static String defaultTarget() {
        String code=Locale.getDefault().getLanguage();
        return ALL.stream().anyMatch(e->e.code().equals(code))?code:"en";
    }
}
