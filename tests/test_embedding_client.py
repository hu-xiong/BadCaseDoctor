from unittest.mock import MagicMock, patch

from memory.embedding_client import EmbeddingClient, EmbeddingConfig, is_dashscope_multimodal_embedding_model


def test_multimodal_model_detection():
    assert is_dashscope_multimodal_embedding_model("tongyi-embedding-vision-plus-2026-03-06")
    assert is_dashscope_multimodal_embedding_model("qwen3-vl-embedding")
    assert not is_dashscope_multimodal_embedding_model("text-embedding-v4")


@patch("dashscope.MultiModalEmbedding.call")
def test_embed_batch_uses_dashscope_for_vision_model(mock_call):
    mock_call.return_value = MagicMock(
        status_code=200,
        output={"embeddings": [{"embedding": [0.1, 0.2]}, {"embedding": [0.3, 0.4]}]},
    )
    client = EmbeddingClient(
        EmbeddingConfig(
            api_key="sk-test",
            model="tongyi-embedding-vision-plus-2026-03-06",
        )
    )
    vecs = client.embed_batch(["hello", "world"])
    assert vecs == [[0.1, 0.2], [0.3, 0.4]]
    mock_call.assert_called_once()


@patch("memory.embedding_client.EmbeddingClient._embed_openai_compatible")
def test_embed_batch_uses_openai_for_text_model(mock_openai):
    mock_openai.return_value = [[0.5]]
    client = EmbeddingClient(
        EmbeddingConfig(api_key="sk-test", model="text-embedding-v4", base_url="http://x")
    )
    vecs = client.embed_batch(["hello"])
    assert vecs == [[0.5]]
    mock_openai.assert_called_once()
