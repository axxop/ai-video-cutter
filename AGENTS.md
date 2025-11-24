# Repository Guidelines

This repository assembles short-form videos by pairing SRT subtitles, narration audio, and timeline metadata, then composing clips via ffmpeg and DeepSeek-assisted selection. Keep contributions concise, reproducible, and safe around media assets and API keys.

## Project Structure & Module Organization
- `video_compressor.py`: Main pipeline; parses SRTs, asks DeepSeek for best line ranges, trims source video, adds narration/subtitles, and stitches `video_clips/` into the final output.
- `scripts/analyze_transcript.py`: Utility to inspect raw transcript JSON (see `microvideo_data/`); adjust the hardcoded file path before running.
- Data inputs: `origin_videos/` (source MP4), `srts/` (original subtitles), `voice_text/` & `examples_voice_text/` (reference narration), `prompts/1.md` (LLM prompt guide).
- Outputs: `video_clips/` (generated clips + `clips_info.json`), `p_tts_output/` and `conan_tts_output/` (TTS audio), `srts/` for aligned subtitle variants; large binaries stay out of Git (`.gitignore` already excludes rendered clips).

## Build, Test, and Development Commands
- Prereqs: Python 3.10+, ffmpeg on PATH, DeepSeek API key (`export DEEPSEEK_API_KEY=...`). Install deps: `python3 -m venv .venv && source .venv/bin/activate && pip install -U pip openai`.
- Run composer: `python video_compressor.py timeline.json srts/source.srt origin_videos/source.mp4 -o final_video.mp4 --clip-dir video_clips -w 4`. Outputs clips and `video_clips/clips_info.json` before muxing the final MP4.
- Inspect transcripts: edit the path in `scripts/analyze_transcript.py`, then `python scripts/analyze_transcript.py`.

## Coding Style & Naming Conventions
- Python with 4-space indents, type hints, and short docstrings; reuse logging style already present (console prints with status icons).
- Prefer `snake_case` for variables/functions and descriptive filenames (`timeline.json`, `*_transcript_raw.json`). Keep prompts and data notes in Markdown.

## Testing Guidelines
- No automated tests yet; validate changes by running the composer on a small sample timeline/SRT/video and confirming the final MP4 and `clips_info.json` are produced without ffmpeg errors.
- Check that computed durations roughly match narration lengths and that subtitle alignment is sensible. Avoid committing generated media; keep sample assets minimal.

## Commit & Pull Request Guidelines
- Follow the existing short, conventional prefixes (`feat:`, `refactor:`, `Add ...`). Use imperative tone and keep messages under ~72 chars.
- PRs should include: scope summary, commands run, and links/paths to produced artifacts (e.g., `video_clips/clips_info.json`, final video). Note any timeline or prompt changes and list remaining risks or manual steps.

## Security & Configuration Tips
- Do not commit API keys; pass via environment or a local `.env` that stays untracked. If adding config options, prefer env vars over hardcoding.
- Large raw videos and generated outputs belong in local storage or object buckets, not in Git. Extend `.gitignore` if you introduce new output directories.
