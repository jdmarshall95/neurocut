# Changelog

All notable changes to NeuroCut will be documented here.

Format inspired by [Keep a Changelog](https://keepachangelog.com/).
This project aims to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Open-source release kit: MIT LICENSE, CONTRIBUTING, CoC, SECURITY
- GitHub issue/PR templates and lightweight CI
- Developer docs under `docs/`
- Scene-detection proxy (`proxy_scenes.mp4`, low FPS) used on every montage job
- Docker resource limits, GPU compose override, Prometheus metrics, structured logging

### Changed

- Default montage path prefers text-out Gemini models + shot timeline (no video upload by default)
- Public LICENSE switched to MIT for simpler redistribution
