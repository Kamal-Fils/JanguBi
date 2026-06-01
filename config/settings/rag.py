from config.env import env

GEMINI_API_KEY = env.str("GEMINI_API_KEY", default="")
# RAG stand-by: embeddings disabled by default (no budget for Gemini API).
# Re-enable by setting PGVECTOR_ENABLED=True + GEMINI_API_KEY in .env.
EMBEDDING_PROVIDER = env.str("EMBEDDING_PROVIDER", default="stub")
PGVECTOR_ENABLED = env.bool("PGVECTOR_ENABLED", default=False)