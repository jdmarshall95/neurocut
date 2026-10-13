from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_GEMINI_MODEL_PRIORITY = [
    # Text-out models for montage (transcript + shot timeline, no video upload).
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "NeuroCut"
    debug: bool = False
    suppress_poll_access_logs: bool = True

    gemini_api_key: str = ""
    gemini_model: str = ""
    gemini_model_priority: list[str] = Field(default_factory=lambda: list(DEFAULT_GEMINI_MODEL_PRIORITY))
    gemini_temperature: float = 0.2
    gemini_max_retries: int = 2
    gemini_rate_limit_wait_sec: float = 20.0
    gemini_transient_backoff_multiplier: float = 1.5
    gemini_video_wait_timeout_sec: float = 300.0
    gemini_video_poll_interval_sec: float = 2.0

    # LLM provider for AI montage analysis: gemini | deepseek | auto
    # auto = Gemini first, fallback to DeepSeek when all Gemini models fail
    llm_provider: str = "auto"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_temperature: float = 0.2

    api_cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:8501", "http://127.0.0.1:8501"]
    )

    # Phase 14: Adobe Premiere Pro plugin API
    plugin_enabled: bool = True
    plugin_allow_any_local_path: bool = False
    plugin_allowed_roots: list[str] = Field(default_factory=list)
    plugin_copy_media_to_storage: bool = False
    plugin_cors_allow_all: bool = True

    storage_dir: Path = Field(default=Path("storage"))
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"

    default_fps: float = 30.0
    proxy_height: int = 480
    audio_sample_rate: int = 16000
    audio_channels: int = 1

    # Phase 15: stitched "turnkey" clip render
    render_crf: int = 20
    render_preset: str = "medium"
    render_audio_bitrate: str = "160k"

    # Phase 16/17: burned-in subtitles
    subtitle_font_size: int = 16
    subtitle_primary_color: str = "&H00FFFFFF"  # ASS BGR: white
    subtitle_outline_color: str = "&H00000000"  # black
    subtitle_outline: int = 2
    # Mask style behind text: 1 = outline, 3 = opaque box behind text.
    subtitle_border_style: int = 1
    subtitle_margin_v: int = 40
    subtitle_crf: int = 20
    subtitle_preset: str = "medium"
    subtitle_font_name: str = "Manrope"
    # Proofreading (orthography + punctuation) engine:
    #   silero -> local Silero Text Enhancement (torch, offline, free)
    #   gemini -> Gemini API (paid)
    #   auto   -> silero if torch is available, else gemini
    #   none   -> disabled
    proofread_engine: str = "silero"
    proofread_language: str = "en"
    # Karaoke-style chunking: split phrases into 1..N words timed to speech
    subtitle_auto_chunk: bool = True
    subtitle_max_words: int = 3
    subtitle_char_ratio: float = 0.6  # glyph width as a fraction of font size
    subtitle_side_margin: int = 40  # horizontal safe margin (px per side)

    whisper_model: str = "base"
    whisper_device: str = "auto"
    whisper_compute_type: str = "default"
    whisper_language: str | None = None
    whisper_vad_filter: bool = True
    whisper_log_every_n_segments: int = 1

    # Phase 12: standalone STT service
    stt_cache_enabled: bool = True
    transcripts_cache_dirname: str = "transcripts"
    use_video_for_llm: bool = False
    skip_stt_if_transcript_provided: bool = True

    # Phase 13: pluggable STT engine (whisper | silero | gigaam | auto)
    stt_engine: str = "whisper"
    silero_language: str = "en"
    silero_device: str = "cpu"

    # GigaAM offline STT via sherpa-onnx
    gigaam_model_dir: Path = Field(
        default=Path("storage/models/gigaam-ru")
    )
    gigaam_vad_model: Path = Field(
        default=Path("storage/models/silero_vad.onnx")
    )
    gigaam_num_threads: int = 2
    gigaam_max_segment_sec: float = 20.0

    @field_validator("stt_engine", mode="before")
    @classmethod
    def _normalize_stt_engine(cls, value: Any) -> str:
        if not value:
            return "whisper"
        engine = str(value).strip().lower()
        if engine not in {"whisper", "silero", "gigaam", "auto"}:
            return "whisper"
        return engine

    @property
    def gigaam_model_path(self) -> Path:
        return (self.gigaam_model_dir / "model.int8.onnx").resolve()

    @property
    def gigaam_tokens_path(self) -> Path:
        return (self.gigaam_model_dir / "tokens.txt").resolve()

    @property
    def gigaam_vad_path(self) -> Path:
        return self.gigaam_vad_model.resolve()

    scene_threshold: float = 0.3
    min_scene_duration_sec: float = 0.8
    # Lightweight proxy for FFmpeg scene detection (low res + low fps, no audio).
    scene_proxy_filename: str = "proxy_scenes.mp4"
    scene_proxy_height: int = 240
    scene_proxy_fps: float = 12.0
    scene_proxy_crf: int = 34
    scene_proxy_preset: str = "ultrafast"

    @field_validator("plugin_allowed_roots", mode="before")
    @classmethod
    def _parse_plugin_allowed_roots(cls, value: Any) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def resolved_plugin_allowed_roots(self) -> list[Path]:
        return [Path(item).expanduser().resolve() for item in self.plugin_allowed_roots]

    @field_validator("gemini_model_priority", mode="before")
    @classmethod
    def _parse_gemini_model_priority(cls, value: Any) -> list[str]:
        if value is None or value == "":
            return list(DEFAULT_GEMINI_MODEL_PRIORITY)
        if isinstance(value, str):
            models = [item.strip() for item in value.split(",") if item.strip()]
            return models or list(DEFAULT_GEMINI_MODEL_PRIORITY)
        return value

    @property
    def resolved_gemini_models(self) -> list[str]:
        models: list[str] = []
        if self.gemini_model.strip():
            models.append(self.gemini_model.strip())
        for model in self.gemini_model_priority:
            if model not in models:
                models.append(model)
        return models or list(DEFAULT_GEMINI_MODEL_PRIORITY)

    @property
    def resolved_llm_provider(self) -> str:
        pref = self.llm_provider.strip().lower()
        if pref == "deepseek":
            return "deepseek"
        if pref == "gemini":
            return "gemini"
        # auto
        if self.deepseek_api_key.strip() and not self.gemini_api_key.strip():
            return "deepseek"
        return "gemini"

    @property
    def llm_deepseek_fallback_enabled(self) -> bool:
        pref = self.llm_provider.strip().lower()
        return pref in {"", "auto"} and bool(self.deepseek_api_key.strip())

    @property
    def resolved_analysis_model_label(self) -> str:
        if self.resolved_llm_provider == "deepseek":
            return self.deepseek_model
        models = self.resolved_gemini_models
        return models[0] if models else "gemini"

    @property
    def storage_path(self) -> Path:
        return self.storage_dir.resolve()

    @property
    def transcripts_cache_path(self) -> Path:
        return self.storage_path / self.transcripts_cache_dirname

    def ensure_storage(self) -> Path:
        self.storage_path.mkdir(parents=True, exist_ok=True)
        return self.storage_path

    def ensure_transcripts_cache(self) -> Path:
        cache_dir = self.transcripts_cache_path
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir


@lru_cache
def get_settings() -> Settings:
    return Settings()
