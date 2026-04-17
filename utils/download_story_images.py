import os
import requests
import urllib.parse
from PIL import Image
from io import BytesIO


def download_image(prompt, filename):
    # Use Pollinations AI free tier, no API key needed
    encoded_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=600&height=400&nologo=true"
    print(f"Downloading {filename}...")
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        # Ensure the image is valid by opening it with PIL
        img = Image.open(BytesIO(response.content)).convert("RGB")

        filepath = os.path.join("res", "img", filename)
        img.save(filepath, "PNG")
        print(f"Saved: {filepath}")
    except Exception as e:
        print(f"Failed to download {filename}: {e}")


def main():
    os.makedirs(os.path.join("res", "img"), exist_ok=True)

    prompts = {
        # Cat Story (Wait, we already have cat_sun and cat_bird which look good,
        # but let's complete the set if they want unified style? No, user liked
        # the beautiful cat ones but let's fetch the rest)
        "cat_play.png": "Beautiful minimalist children's book illustration of a cute cat playfully catching a falling leaf, vibrant colors, premium, no text",
        "cat_garden.png": "Beautiful minimalist children's book illustration of two small cats running in a pretty garden, vibrant colors, premium, no text",

        # Mountain Story
        "mountain_sunny.png": "Beautiful minimalist children's book illustration of a bright sunny day with a clear blue sky, vibrant colors, premium, no text",
        "mountain_climb.png": "Beautiful minimalist children's book illustration of a big green mountain to climb, vibrant colors, premium, no text",
        "mountain_trees.png": "Beautiful minimalist children's book illustration of many lush pine trees on a mountain, vibrant colors, premium, no text",
        "mountain_happy.png": "Beautiful minimalist children's book illustration of a happy serene nature scene, vibrant colors, premium, no text",

        # Friend Story
        "friend_1.png": "Beautiful minimalist children's book illustration of two best friends holding hands, vibrant colors, premium, no text",
        "friend_2.png": "Beautiful minimalist children's book illustration of two kids walking to school together, vibrant colors, premium, no text",
        "friend_3.png": "Beautiful minimalist children's book illustration of two kids happily eating red apples, vibrant colors, premium, no text",

        # Morning Story
        "morning_1.png": "Beautiful minimalist children's book illustration of a bright yellow sun rising over the horizon, vibrant colors, premium, no text",
        "morning_2.png": "Beautiful minimalist children's book illustration of a person drinking a fresh glass of water, bright morning light, vibrant colors, premium, no text",
        "morning_3.png": "Beautiful minimalist children's book illustration of a very happy glowing smiley face or feeling of joy, vibrant colors, premium, no text",
    }

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        for filename, prompt in prompts.items():
            futures.append(executor.submit(download_image, prompt, filename))
        concurrent.futures.wait(futures)

    print("All image downloads completed.")


if __name__ == "__main__":
    main()
