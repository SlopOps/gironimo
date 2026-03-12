#!/usr/bin/env python3
"""
Vision Agent - UI validation via screenshots
"""

import base64
import requests
import sys
import time
import os
from pathlib import Path

# Add parent to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import URLS, MODELS, Console, TEMP_DIR


def main():
    if len(sys.argv) < 3:
        print("Usage: vision.py screenshot.png 'instructions'")
        sys.exit(1)

    img_path = sys.argv[1]
    instructions = sys.argv[2]

    if not Path(img_path).exists():
        print(f"Screenshot not found: {img_path}")
        sys.exit(1)

    # Check vision server
    try:
        r = requests.get(f"{URLS['vision']}/v1/models", timeout=5)
        if r.status_code != 200:
            raise Exception()
    except:
        print(f"Vision server not reachable at {URLS['vision']}")
        print(f"Check: ssh {os.getenv('DGX_HOST', 'localhost')} sudo systemctl status vllm-vision")
        sys.exit(1)

    # Encode image
    with open(img_path, "rb") as f:
        b64_image = base64.b64encode(f.read()).decode()

    Console.llm_call(MODELS['vision'])

    start = time.time()

    # Call vision model
    r = requests.post(
        f"{URLS['vision']}/v1/chat/completions",
        json={
            "model": MODELS['vision'],
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_image}"}},
                {"type": "text", "text": instructions}
            ]}]
        },
        timeout=60
    )
    r.raise_for_status()

    duration = time.time() - start

    result = r.json()
    content = result['choices'][0]['message']['content']

    # Show result
    print(f"\nVision Analysis ({duration:.1f}s):")
    print("-" * 50)
    print(content)
    print("-" * 50)

    # Save result to TEMP_DIR
    vision_result_path = TEMP_DIR / "vision_result.txt"
    with open(vision_result_path, 'w') as f:
        f.write(content)


if __name__ == "__main__":
    main()
