"""Configuration for the capstone data generator.

Reads from environment variables or a local .env file. See .env.example.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["gemini", "openrouter", "ollama"]


class Settings(BaseSettings):
    """Runtime settings for corpus generation.

    The generator is provider-agnostic by design: the same prompts run against
    Gemini AI Studio (free tier), OpenRouter, or a local Ollama model. Teams
    that hit a rate limit on one provider can switch with a single env var.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="DATAGEN_", extra="ignore"
    )

    provider: Provider = "gemini"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-latest"
    # Used automatically when the primary model keeps returning 429/503.
    # Flash-Lite sits in a separate free-tier quota bucket and is overloaded
    # far less often. Set to "" to disable.
    gemini_fallback_model: str = "gemini-flash-lite-latest"

    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct"

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    # Reproducibility. Every team that runs with the same seed gets a byte
    # identical corpus, which is what makes a common grading rubric possible.
    seed: int = 42

    # Corpus sizing. The defaults match the sealed-corpus convention used in
    # the internship assignments: small enough to index on a laptop, large
    # enough that retrieval quality actually varies with your chunking choices.
    corpus_docs: int = 50
    intake_records: int = 200
    eval_items: int = 20

    output_dir: Path = Path("./data")

    # Generation controls
    max_retries: int = 8
    max_backoff: int = 60  # seconds; cap for a single exponential-backoff wait
    # Minimum gap between Gemini calls. Free-tier Flash allows ~10 requests
    # per minute; pacing at 6s avoids most 429s instead of recovering from them.
    min_request_interval: float = 6.0
    request_timeout: int = 120
    temperature: float = 0.9

    # Hard ceiling on intake batches. Without this, a model that keeps
    # returning empty arrays loops forever and drains the quota.
    max_intake_attempts: int = 30

    # Skip corpus documents already written, so a crashed run resumes.
    resume: bool = True

    # Reproduce v1.0.0's table bytes, which came from a second, redundant RNG
    # draw. Kept on by default so mid-project teams are not disrupted; turn it
    # off with --fresh-table-rng on new work.
    legacy_table_rng: bool = True


settings = Settings()
