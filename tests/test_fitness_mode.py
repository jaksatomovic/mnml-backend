"""
test FITNESS mode (JSON text)

FITNESS modetext Python text JSON text (core/modes/builtin/fitness.json)，
text json_content.py text，text json_renderer.py text。
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
from core.json_content import generate_json_mode_content
from core.json_renderer import render_json_mode

load_dotenv()


async def main():
    print("Testing FITNESS mode (JSON definition)...")

    fitness_path = os.path.join(
        os.path.dirname(__file__), "..", "core", "modes", "builtin", "fitness.json"
    )
    with open(fitness_path, "r", encoding="utf-8") as f:
        mode_def = json.load(f)

    content = await generate_json_mode_content(
        mode_def,
        date_str="2/14 Sat",
        weather_str="sunny 15°C",
        llm_provider="deepseek",
        llm_model="deepseek-chat",
    )

    print(f"Generated content:")
    print(f"  Workout: {content.get('workout_name', '')} ({content.get('duration', '')})")
    print(f"  Exercises: {len(content.get('exercises', []))} items")
    print(f"  Tip: {content.get('tip', '')[:50]}...")

    img, _ = render_json_mode(
        mode_def, content,
        date_str="2/14 Sat",
        weather_str="sunny 15°C",
        battery_pct=85,
        weather_code=0,
        time_str="14:30",
    )

    img.save("test_fitness_output.png")
    print("✓ Saved to test_fitness_output.png")


if __name__ == "__main__":
    asyncio.run(main())
