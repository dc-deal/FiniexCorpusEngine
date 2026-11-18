from backend.providers import provider_check


def test_a_key_in_an_error_message_is_cut_to_its_first_characters():
    message = 'Incorrect API key provided: sk-proj-' + 'abcdefghijklmnop1234. Check your key.'
    redacted = provider_check.redact(message)
    assert 'abcdefghijklmnop1234' not in redacted
    assert redacted.startswith('Incorrect API key provided: sk-proj')


def test_only_missing_provider_keys_are_taken_from_an_extra_env_file(tmp_path):
    extra = tmp_path / '.env'
    extra.write_text('CORPUS_OPENAI_API_KEY=from-extra\nOPENROUTER_API_KEY=other\nDATABASE_URL=secret\n'
                     'OPENAI_API_KEY=another-app-s\n', encoding='utf-8')
    environ = {'OPENROUTER_API_KEY': 'own'}
    taken = provider_check.take_missing_keys(extra, environ)
    assert taken == ['CORPUS_OPENAI_API_KEY']
    # nothing else, and never another app's OPENAI_API_KEY: this project has its own (278.a)
    assert environ == {'OPENROUTER_API_KEY': 'own', 'CORPUS_OPENAI_API_KEY': 'from-extra'}


def test_cosine_is_one_for_the_same_direction_and_zero_for_orthogonal_vectors():
    assert abs(provider_check.cosine([1.0, 2.0, 3.0], [2.0, 4.0, 6.0]) - 1.0) < 1e-12
    assert provider_check.cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
