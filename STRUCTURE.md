neurocut/
├── app/
│   ├── main.py                 # FastAPI entry point
│   ├── api/
│   │   └── routes.py           # Endpoints (/upload, /status, /download)
│   ├── core/
│   │   ├── config.py           # Pydantic settings, env vars
│   │   └── llm.py              # Gemini client setup
│   ├── services/
│   │   ├── media_processor.py  # FFmpeg logic (downscale, extract audio)
│   │   ├── transcriber.py      # Faster-whisper logic
│   │   ├── ai_analyzer.py      # LLM prompting and JSON parsing
│   │   └── xml_generator.py    # Jinja2 XML rendering
│   ├── templates/
│   │   └── fcp7_template.xml.j2 # Base FCP7 XML template
│   └── utils/
│       └── timecode.py         # Helpers to convert seconds to HH:MM:SS:FF
├── frontend/                   # React SPA (Vite + Tailwind + Headless UI)
│   ├── src/
│   │   ├── components/         # UI components (glassmorphism, gradients, noise)
│   │   ├── hooks/             # useJobRunner — job launch and status polling
│   │   ├── lib/              # API client, types, formatting
│   │   └── App.tsx           # Root component
│   ├── Dockerfile            # Multi-stage: build + nginx
│   └── nginx.conf
├── storage/                    # Temp folder for uploads/proxies (gitignored)
├── .env                        # API keys
├── .gitignore
└── requirements.txt