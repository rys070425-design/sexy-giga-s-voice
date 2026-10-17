package io.github.rys070425design.universalvoicemobile;

/** Two readable sentences; a delayed final can correct only its own card. */
public final class CaptionLedger {
    public record Card(long utterance,int revision,String original,String translated,boolean complete) {}
    private Card current,previous;
    public Card current(){return current;}
    public Card previous(){return previous;}
    public void clear(){current=previous=null;}
    public boolean offer(Card card) {
        if(card.translated()==null||card.translated().isBlank())return false;
        if(current==null){current=card;return true;}
        if(card.utterance()>current.utterance()){previous=current;current=card;return true;}
        if(card.utterance()==current.utterance()) {
            if(card.revision()<current.revision()||current.complete()&&!card.complete())return false;
            current=card;return true;
        }
        if(previous!=null&&card.utterance()==previous.utterance()&&card.complete()
                &&card.revision()>=previous.revision()){previous=card;return true;}
        return false;
    }
}
