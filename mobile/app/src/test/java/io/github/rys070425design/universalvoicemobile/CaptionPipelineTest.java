package io.github.rys070425design.universalvoicemobile;

import org.junit.Test;
import static org.junit.Assert.*;
import java.util.ArrayList;
import java.util.List;

public class CaptionPipelineTest {
    private CaptionLedger.Card card(long id,int rev,String text,boolean done){return new CaptionLedger.Card(id,rev,text,text,done);}
    @Test public void finalCannotBeReplacedByDraft(){
        CaptionLedger ledger=new CaptionLedger();ledger.offer(card(1,2,"final",true));
        assertFalse(ledger.offer(card(1,3,"draft",false)));assertEquals("final",ledger.current().translated());
    }
    @Test public void lateFinalCorrectsPreviousWithoutReplacingCurrent(){
        CaptionLedger ledger=new CaptionLedger();ledger.offer(card(1,1,"old draft",false));ledger.offer(card(2,1,"new",false));
        assertTrue(ledger.offer(card(1,2,"old final",true)));
        assertEquals("new",ledger.current().translated());assertEquals("old final",ledger.previous().translated());
    }
    @Test public void staleAndBlankCaptionsAreRejected(){
        CaptionLedger ledger=new CaptionLedger();ledger.offer(card(2,3,"new",false));
        assertFalse(ledger.offer(card(2,2,"older",false)));assertFalse(ledger.offer(card(1,1,"very old",true)));
        assertFalse(ledger.offer(card(3,1,"  ",true)));ledger.clear();assertNull(ledger.current());assertNull(ledger.previous());
    }
    static class Harness implements TranslationPump.Backend,TranslationPump.Listener {
        final List<String> requests=new ArrayList<>(),errors=new ArrayList<>();
        final List<TranslationPump.Result> callbacks=new ArrayList<>();final List<CaptionLedger.Card> shown=new ArrayList<>();int overflow;
        final TranslationPump pump=new TranslationPump(this,this);
        public void translate(String text,TranslationPump.Result result){requests.add(text);callbacks.add(result);}
        public void caption(CaptionLedger.Card card){shown.add(card);}
        public void error(String text){errors.add(text);}
        public void overflow(){overflow++;}
        void success(int index,String value){callbacks.get(index).success(value);}
    }
    @Test public void rapidDraftsConflateAndFinalTakesPriority(){
        Harness h=new Harness();h.pump.offer(1,1,"a",false);h.pump.offer(1,2,"ab",false);h.pump.offer(1,3,"abc",false);
        h.pump.offer(1,4,"final",true);h.pump.offer(2,1,"next",false);h.success(0,"obsolete");
        assertTrue(h.shown.isEmpty());assertEquals(List.of("a","final"),h.requests);
        h.success(1,"translated");assertTrue(h.shown.get(0).complete());assertEquals(List.of("a","final","next"),h.requests);
    }
    @Test public void resetDiscardsOldResultButUnblocksNewWork(){
        Harness h=new Harness();h.pump.offer(1,1,"old",true);h.pump.reset();h.pump.offer(2,1,"new",true);
        h.success(0,"old translation");assertTrue(h.shown.isEmpty());assertEquals(2,h.requests.size());
        h.success(1,"new translation");assertEquals(2,h.shown.get(0).utterance());
    }
    @Test public void repeatedSentenceIsShownForEachUtteranceAndCached(){
        Harness h=new Harness();h.pump.offer(1,1,"hello",true);h.success(0,"안녕");h.pump.offer(2,1,"hello",true);
        assertEquals(1,h.requests.size());assertEquals(2,h.shown.size());assertEquals(2,h.shown.get(1).utterance());
    }
    @Test public void queueIsBoundedUnderSlowInference(){
        Harness h=new Harness();h.pump.offer(1,1,"first",true);
        for(int i=2;i<=20;i++)h.pump.offer(i,1,"sentence "+i,true);
        assertEquals(4,h.pump.pendingCount());assertEquals(15,h.overflow);h.success(0,"first");
        assertEquals("sentence 17",h.requests.get(1));
    }
    @Test public void failureRetainsOriginalAndStaleFailureIsIgnored(){
        Harness h=new Harness();h.pump.offer(1,1,"original",true);h.callbacks.get(0).failure();assertEquals(List.of("original"),h.errors);
        h.pump.offer(2,1,"stale",true);h.pump.reset();h.callbacks.get(1).failure();assertEquals(1,h.errors.size());
    }
    @Test public void duplicateCallbacksDoNotPublishTwice(){
        Harness h=new Harness();h.pump.offer(1,1,"hello",true);h.success(0,"안녕");h.success(0,"duplicate");assertEquals(1,h.shown.size());
    }
    @Test public void regionalPortugueseUsesSameTranslationPack(){assertTrue(Languages.same("pt","pt-BR"));assertEquals("pt",Languages.translationCode("pt-BR"));}
}
