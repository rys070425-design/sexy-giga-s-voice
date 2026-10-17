package io.github.rys070425design.universalvoicemobile;
import androidx.lifecycle.ViewModel;
/** Text stays only in process RAM, not SavedStateHandle or saved instance state. */
public final class ConversationState extends ViewModel {
    public final CaptionLedger captions=new CaptionLedger();
    public String failedOriginal="";
}
