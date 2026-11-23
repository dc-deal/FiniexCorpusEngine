from backend.chat import app_config


def test_the_settings_name_a_router_model_and_the_retrieval_switches():
    config = app_config.load()
    # since 23 Nov 2026 (issue #3) Anthropic's model, named bare; an OpenRouter id names its maker (provider/model)
    assert config['router']['provider'] == 'anthropic' and '/' not in config['router']['model']
    assert config['router']['reasoning_effort'] in (None, 'minimal', 'low', 'medium', 'high')
    assert config['router']['max_tokens'] >= 1000  # a low budget is the content-null trap
    assert isinstance(config['retrieval']['shelf_filter'], bool)
    assert isinstance(config['retrieval']['multi_query'], bool)
    assert isinstance(config['retrieval']['concept_query'], bool)
    assert config['retrieval']['k'] > 0 and config['multi_query']['versions'] > 0


def test_the_chat_asks_the_search_server_for_no_more_passages_than_it_serves():
    # The chat's knowledge turn asks semantic_search for k passages; above the server's bound every such turn would fail.
    from backend.search import search_server

    assert 1 <= app_config.load()['retrieval']['k'] <= search_server.MAX_HITS


def test_the_example_questions_are_kept_once_for_every_interface_and_each_is_a_valid_question():
    # In the config rather than in an interface's code, so every interface shows the same ones (decision 100.a).
    from backend.chat import chat_turn

    answer = app_config.load()['answer']
    assert len(answer['examples']) >= 3
    for example in answer['examples']:
        assert chat_turn.validate_question(example, answer['max_question_characters']) == example


def test_the_relevance_floor_is_a_similarity_and_the_keyword_switch_a_flag():
    retrieval_settings = app_config.load()['retrieval']
    assert isinstance(retrieval_settings['keyword_search'], bool)
    assert isinstance(retrieval_settings['bm25_on_keywords'], bool)
    assert 0 < retrieval_settings['relevance_floor'] < 1  # a cosine similarity
