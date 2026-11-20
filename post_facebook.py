"""Daily maths post agent for the "Beyond the Equation" Facebook Page (no Meta developer account).

  python post_facebook.py generate   -> Gemini writes problem, Pillow draws poster,
                                        saves posters/<date>.png and payload.json
  python post_facebook.py send       -> sends payload.json to a Make.com webhook,
                                        which publishes it to your Facebook Page

Env vars:
  GEMINI_API_KEY    (generate)
  MAKE_WEBHOOK_URL  (send)
  GITHUB_REPOSITORY, GITHUB_REF_NAME  (set automatically by GitHub Actions)
  GEMINI_MODEL      optional, default gemini-2.5-flash
"""
import datetime
import json
import os
import textwrap
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
HISTORY = HERE / "history.json"
POSTERS = HERE / "posters"
PAYLOAD = HERE / "payload.json"
def pick_model():
    wanted = os.environ.get("GEMINI_MODEL")
    if wanted:
        return wanted
    r = requests.get(
        "https://generativelanguage.googleapis.com/v1beta/models",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
        params={"pageSize": 200},
        timeout=30,
    )
    r.raise_for_status()
    names = [
        m["name"].split("/")[-1]
        for m in r.json().get("models", [])
        if "generateContent" in m.get("supportedGenerationMethods", [])
    ]
    import re
    stable = []
    for n in names:
        m = re.fullmatch(r"gemini-(\d+(?:\.\d+)?)-flash", n)
        if m:
            stable.append((float(m.group(1)), n))
    if stable:
        chosen = max(stable)[1]
    else:
        chosen = next(n for n in names if "flash" in n)
    print("Using model:", chosen)
    return chosen

TOPICS = [
    "Expanding and factorising algebraic expressions",
    "Solving linear equations",
    "Quadratic equations (factorising / formula)",
    "Simultaneous equations",
    "Indices and surds",
    "Percentages and ratio",
    "Fractions and decimals",
    "Pythagoras' theorem",
    "Trigonometry in right-angled triangles",
    "Sine and cosine rules",
    "Circle theorems",
    "Area and volume",
    "Arithmetic and geometric sequences",
    "Probability",
    "Mean, median, mode and averages",
    "Inequalities",
    "Functions and inverse functions",
    "Straight line graphs and gradients",
    "Vectors",
    "Standard form",
]


def load_history():
    try:
        return json.loads(HISTORY.read_text())
    except Exception:
        return []


def generate_content(topic, recent):
    prompt = f"""You write daily posts for a maths channel called "Beyond the Equation"
aimed at O Level / IGCSE students.

Topic today: {topic}
Do NOT repeat these recent problems: {recent[-30:]}

Return ONLY JSON with these keys:
  "title":    short catchy title (max 6 words)
  "problem":  one exam-style question, plain text, max 220 characters,
              write maths with plain characters like x^2, sqrt(), /, no LaTeX
  "answer":   the final answer only
  "solution": numbered worked solution, max 600 characters, plain text
  "caption":  Facebook caption, 2-3 friendly lines, ends with
              "Try it in the comments! Solution pinned below." and 3 hashtags
Make sure the maths is correct."""
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{pick_model()}:generateContent",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        },
        timeout=90,
    )
    r.raise_for_status()
    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


def font(size, bold=False):
    names = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ]
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_poster(data, topic, path):
    W = H = 1080
    img = Image.new("RGB", (W, H), "#0f1b3d")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 14], fill="#ffb703")
    d.text((60, 50), "BEYOND THE EQUATION", font=font(34, True), fill="#ffb703")
    d.text((60, 100), topic.upper()[:45], font=font(26), fill="#8ecae6")
    d.text((60, 190), data["title"], font=font(62, True), fill="white")

    # shrink the problem text until it fits the box
    size = 54
    while size > 26:
        f = font(size)
        lines = textwrap.wrap(data["problem"], width=int(900 / (size * 0.58)))
        if len(lines) * (size + 14) < 560:
            break
        size -= 4
    y = 320
    for line in lines:
        d.text((60, y), line, font=f, fill="#e9f1ff")
        y += size + 14

    d.rounded_rectangle([60, 940, 1020, 1020], radius=20, fill="#ffb703")
    d.text((90, 957), "Solution in the comments  ->", font=font(40, True), fill="#0f1b3d")
    img.save(path)


def generate():
    history = load_history()
    today = datetime.date.today()
    topic = TOPICS[today.toordinal() % len(TOPICS)]
    data = generate_content(topic, [h["problem"] for h in history])
    POSTERS.mkdir(exist_ok=True)
    img_name = f"{today}.png"
    make_poster(data, topic, POSTERS / img_name)

    repo = os.environ.get("GITHUB_REPOSITORY", "USER/REPO")
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    payload = {
        "image_url": f"https://raw.githubusercontent.com/{repo}/{branch}/posters/{img_name}",
        "caption": data["caption"],
        "solution": f"Answer: {data['answer']}\n\n{data['solution']}",
    }
    PAYLOAD.write_text(json.dumps(payload, indent=2))
    history.append({"date": str(today), "topic": topic, "problem": data["problem"]})
    HISTORY.write_text(json.dumps(history[-200:], indent=2))
    print("Problem:", data["problem"])
    print("Answer:", data["answer"])
    print("Poster:", POSTERS / img_name)


def send():
    payload = json.loads(PAYLOAD.read_text())
    r = requests.post(os.environ["MAKE_WEBHOOK_URL"], json=payload, timeout=60)
    print("Webhook status:", r.status_code, r.text[:200])
    r.raise_for_status()


if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "generate"
    {"generate": generate, "send": send}[mode]()
