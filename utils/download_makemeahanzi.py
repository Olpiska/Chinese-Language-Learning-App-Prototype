import os
import requests


def main():
    os.makedirs(os.path.join("res", "data"), exist_ok=True)

    graphics_url = "https://raw.githubusercontent.com/skishore/makemeahanzi/master/graphics.txt"
    dict_url = "https://raw.githubusercontent.com/skishore/makemeahanzi/master/dictionary.txt"

    graphics_file = "res/data/graphics.txt"
    dict_file = "res/data/dictionary.txt"

    print("Downloading graphics.txt (Stroke data)...")
    try:
        r = requests.get(graphics_url)
        with open(graphics_file, 'wb') as f:
            f.write(r.content)
        print("Success: graphics.txt")
    except Exception as e:
        print(f"Failed to download graphics.txt: {e}")

    print("Downloading dictionary.txt (Pinyin & Meaning)...")
    try:
        r = requests.get(dict_url)
        with open(dict_file, 'wb') as f:
            f.write(r.content)
        print("Success: dictionary.txt")
    except Exception as e:
        print(f"Failed to download dictionary.txt: {e}")


if __name__ == "__main__":
    main()
