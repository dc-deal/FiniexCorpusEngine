from backend.ingestion import subject_check


def test_a_sentence_that_lists_what_the_front_matter_names_is_flagged_and_a_sentence_of_the_subject_is_not():
    # found 23 Nov 2026: such a sentence sent no client to a book of systematic entry and exit tests
    listed = 'Trading strategies, with the software its front matter names, among them TradeStation, Visual C++ and MESA.'
    assert subject_check.flags(listed) == ['names the front matter', 'names 3 products: mesa, tradestation, visual c++']
    assert subject_check.flags('Systematic tests of entries and exits on a portfolio of futures, built in TradeStation.') == []
    assert subject_check.flags(None) == ['no sentence']
