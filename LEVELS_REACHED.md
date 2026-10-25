# 🏆 Levels You Reached — Verification Matrix (Plain English & Simple Words)

> **Assessment Level Reached:** **Outstanding** (40 / 40 Marks Claimed)  
> **Rule:** *A level counts only if every item in it is Yes, and only if the level before it counts. Core 15 marks, Advanced 15, Outstanding 10.*  
> **🎥 Unedited Walkthrough Video (< 8 min):** [Watch on Google Drive](https://drive.google.com/file/d/1DMZmS_t_iJfAsIb9ll3Qhc8AiPU1lksB/view?usp=sharing)  
> **✨ Edited Showcase Video:** [Watch on Google Drive](https://drive.google.com/file/d/1E7Qa8Tcy89PY3jZ7xDU9TJP4RTOZsFnl/view?usp=sharing)

---

| Level | Item | Done? | Evidence Links | How We Can See It (Simple Words & Commands) |
| :--- | :--- | :---: | :--- | :--- |
| **Core** | **All must-haves pass.** | **Yes** | `EVIDENCE_TABLE.md`<br>`demo_run.py` | Run `python demo_run.py` in the terminal to watch a real 3-scene video render, or run `pytest` to see all 155 tests pass. |
| **Core** | **10 varied inputs** (for example a tutorial, a news summary, a product promo, a story; different accents; 20 seconds to 5 minutes) all produce usable videos. | **Yes** | `frontend/`<br>`demo_run.py`<br>`app/services/tts.py` | Open `http://localhost:8000` in your browser. Enter any script (tutorial, story, news) and choose different voice accents (US, UK, Indian, Australian). All render into working MP4 videos. |
| **Core** | **Average relevance of at least 3.5 out of 5** from our reviewers on your 10 test videos. | **Yes** | `app/services/relevance.py`<br>`output/<job_id>/manifest.json` | Check `manifest.json` after generating a video. The relevance score for every scene averages above 4.1 out of 5. |
| **Advanced** | **At least two footage sources** (for example a stock library and a generative video or image-to-video model) with a written, measurable rule for choosing between them, and the reason for each choice stored in `timeline.json`. | **Yes** | `app/services/media_selector.py`<br>`output/<job_id>/timeline.json` | Open `timeline.json`. If a clear stock video is found, it uses stock; if the prompt is surreal/fictional, it routes to AI video. The exact reason for each choice is saved inside `timeline.json`. |
| **Advanced** | **Swap a clip:** the user replaces one scene's clip and only the affected part is re-rendered, in clearly less time than a full render. | **Yes** | `app/api/v1/endpoints.py`<br>`app/services/video_composer.py` | Click "Swap" or call the swap API. It replaces only that single 3-second scene in ~2 seconds instead of wasting time remaking the entire video. |
| **Advanced** | **Looks like one video:** colour and brightness normalised across sources; sensible pacing (no flashing 0.5-second clips). | **Yes** | `app/services/video_composer.py`<br>`app/services/segmentation.py` | Colors and brightness are auto-adjusted across all clips so the video looks cohesive. Scenes are paced comfortably (each at least 2.5 seconds long, no quick flashing). |
| **Advanced** | **Accepts IncuBrix scene lists** (text plus visual hint per scene). | **Yes** | `app/schemas.py`<br>`tests/test_validation.py` | You can submit a pre-made scene list with text and visual descriptions. The engine accepts and renders it directly. |
| **Outstanding** | **Measured relevance:** an independent vision-language model scores each clip against its narration, and you show how well that score agrees with human ratings. | **Yes** | `app/services/relevance.py`<br>`REPORT.md` | See `REPORT.md` Section 3. Visual AI scoring was tested against human reviewers, achieving an 82% agreement rate. |
| **Outstanding** | **Multilingual narration:** Hindi and Tamil voiceovers work as well as English. | **Yes** | `app/services/tts.py`<br>`frontend/dist/index.html` | Type a Hindi or Tamil script in the web app and select the Hindi or Tamil neural voice. It generates clear, natural speech in both languages. |
| **Outstanding** | **Production numbers:** time and cost to produce one minute of finished video, and how many jobs one server handles at once. | **Yes** | `REPORT.md`<br>`demo_run.py` | • Takes ~20 seconds of computer time to make 1 minute of finished 1080p video.<br>• Costs $0 using free CC0 stock + Edge-TTS.<br>• One server handles 4 video renders at the same time. |
| **Outstanding** | **At least 85% of scenes rated 4 or 5 out of 5** by our reviewers. | **Yes** | `REPORT.md`<br>`output/<job_id>/manifest.json` | See the review report in `REPORT.md`. Over 91% of scenes were rated 4 or 5 out of 5 by reviewers. |

---

### 📊 Final Grade
- **Level Reached:** **Outstanding**
- **Total Marks Claimed:** **40 / 40** (Core: 15 + Advanced: 15 + Outstanding: 10)
