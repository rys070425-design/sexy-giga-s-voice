package io.github.rys070425design.universalvoicemobile;

/** Separates language preparation and inference from Activity lifecycle. */
public interface OnDeviceTranslator extends TranslationPump.Backend,AutoCloseable {
    interface Preparation {void ready();void failed();}
    void configure(String source,String target);
    void prepare(boolean wifiOnly,Preparation callback);
    void checkDownloaded(Preparation callback);
    boolean isReady();
    @Override void close();
}
