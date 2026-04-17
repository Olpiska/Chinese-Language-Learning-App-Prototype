"""
utils/pinyin_utils.py
----------------------
Utilities for working with Pinyin, Chinese characters, and tone mappings.
Contains a small but extensible vocabulary of Chinese words for the exercises.
"""

import json
import os

# Tone number to symbol mapping (for vowel 'a')
TONE_MARKS = {
    'a': ['ā', 'á', 'ǎ', 'à', 'a'],
    'e': ['ē', 'é', 'ě', 'è', 'e'],
    'i': ['ī', 'í', 'ǐ', 'ì', 'i'],
    'o': ['ō', 'ó', 'ǒ', 'ò', 'o'],
    'u': ['ū', 'ú', 'ǔ', 'ù', 'u'],
}

# Tone descriptions used by the AI feedback system
TONE_DESCRIPTIONS = {
    1: {
        "name": "First Tone (阴平 yīnpíng)",
        "description": "High and level. Imagine singing a long, flat high note.",
        "example_pinyin": "mā",
        "example_character": "妈",
        "example_meaning": "mother",
        "pitch_shape": "flat_high"
    },
    2: {
        "name": "Second Tone (阳平 yángpíng)",
        "description": "Rising. Like asking 'What?' in English — your pitch goes up.",
        "example_pinyin": "má",
        "example_character": "麻",
        "example_meaning": "hemp / numb",
        "pitch_shape": "rising"
    },
    3: {
        "name": "Third Tone (上声 shǎngshēng)",
        "description": "Falling then rising. It dips down low before coming back up.",
        "example_pinyin": "mǎ",
        "example_character": "马",
        "example_meaning": "horse",
        "pitch_shape": "dipping"
    },
    4: {
        "name": "Fourth Tone (去声 qùshēng)",
        "description": "Sharp falling. Like saying 'No!' with force — pitch drops fast.",
        "example_pinyin": "mà",
        "example_character": "骂",
        "example_meaning": "to scold",
        "pitch_shape": "falling"
    },
    5: {
        "name": "Neutral Tone (轻声 qīngshēng)",
        "description": "Short and light. It has no fixed pitch; just say it briefly.",
        "example_pinyin": "ma",
        "example_character": "吗",
        "example_meaning": "question particle",
        "pitch_shape": "neutral"
    }
}

# Vocabulary organized by difficulty level
VOCABULARY = {
    "beginner": [
        {"character": "你好", "pinyin": "nǐ hǎo", "meaning": "Hello", "tones": [3, 3]},
        {"character": "谢谢", "pinyin": "xiè xie", "meaning": "Thank you", "tones": [4, 5]},
        {"character": "水",   "pinyin": "shuǐ",   "meaning": "Water",     "tones": [3]},
        {"character": "吃",   "pinyin": "chī",     "meaning": "Eat",       "tones": [1]},
        {"character": "好",   "pinyin": "hǎo",     "meaning": "Good",      "tones": [3]},
        {"character": "大",   "pinyin": "dà",      "meaning": "Big",       "tones": [4]},
        {"character": "来",   "pinyin": "lái",     "meaning": "Come",      "tones": [2]},
        {"character": "妈",   "pinyin": "mā",      "meaning": "Mother",    "tones": [1]},
        {"character": "一",   "pinyin": "yī",      "meaning": "One",       "tones": [1]},
        {"character": "二",   "pinyin": "èr",      "meaning": "Two",       "tones": [4]},
        {"character": "三",   "pinyin": "sān",     "meaning": "Three",     "tones": [1]},
        {"character": "四",   "pinyin": "sì",      "meaning": "Four",      "tones": [4]},
        {"character": "五",   "pinyin": "wǔ",      "meaning": "Five",      "tones": [3]},
        {"character": "六",   "pinyin": "liù",     "meaning": "Six",       "tones": [4]},
        {"character": "七",   "pinyin": "qī",      "meaning": "Seven",     "tones": [1]},
        {"character": "八",   "pinyin": "bā",      "meaning": "Eight",     "tones": [1]},
        {"character": "九",   "pinyin": "jiǔ",     "meaning": "Nine",      "tones": [3]},
        {"character": "十",   "pinyin": "shí",     "meaning": "Ten",       "tones": [2]},
        {"character": "人",   "pinyin": "rén",     "meaning": "Person",    "tones": [2]},
        {"character": "山",   "pinyin": "shān",    "meaning": "Mountain",  "tones": [1]},
        {"character": "口",   "pinyin": "kǒu",     "meaning": "Mouth",     "tones": [3]},
        {"character": "天",   "pinyin": "tiān",    "meaning": "Sky/Day",   "tones": [1]},
        {"character": "我",   "pinyin": "wǒ",      "meaning": "I/Me",      "tones": [3]},
        {"character": "你",   "pinyin": "nǐ",      "meaning": "You",       "tones": [3]},
        {"character": "他",   "pinyin": "tā",      "meaning": "He/Him",    "tones": [1]},
        {"character": "不",   "pinyin": "bù",      "meaning": "No/Not",    "tones": [4]},
        {"character": "是",   "pinyin": "shì",     "meaning": "Is/Am/Are", "tones": [4]},
        {"character": "在",   "pinyin": "zài",     "meaning": "At/In",     "tones": [4]},
    ],
    "intermediate": [
        {"character": "银行", "pinyin": "yín háng", "meaning": "Bank",           "tones": [2, 2]},
        {"character": "漂亮", "pinyin": "piào liang", "meaning": "Beautiful",     "tones": [4, 5]},
        {"character": "学习", "pinyin": "xué xí",   "meaning": "Study",         "tones": [2, 2]},
        {"character": "朋友", "pinyin": "péng yǒu", "meaning": "Friend",        "tones": [2, 3]},
        {"character": "喜欢", "pinyin": "xǐ huān",  "meaning": "To like",       "tones": [3, 1]},
        {"character": "中国", "pinyin": "zhōng guó", "meaning": "China",        "tones": [1, 2]},
        {"character": "苹果", "pinyin": "píng guǒ", "meaning": "Apple",         "tones": [2, 3]},
        {"character": "商店", "pinyin": "shāng diàn", "meaning": "Store",       "tones": [1, 4]},
        {"character": "衣服", "pinyin": "yī fu",    "meaning": "Clothes",       "tones": [1, 5]},
        {"character": "今天", "pinyin": "jīn tiān", "meaning": "Today",         "tones": [1, 1]},
        {"character": "明天", "pinyin": "míng tiān", "meaning": "Tomorrow",     "tones": [2, 1]},
        {"character": "昨天", "pinyin": "zuó tiān", "meaning": "Yesterday",     "tones": [2, 1]},
        {"character": "高兴", "pinyin": "gāo xìng", "meaning": "Happy",         "tones": [1, 4]},
        {"character": "再见", "pinyin": "zài jiàn", "meaning": "Goodbye",       "tones": [4, 4]},
        {"character": "老师", "pinyin": "lǎo shī",  "meaning": "Teacher",       "tones": [3, 1]},
        {"character": "学生", "pinyin": "xué sheng", "meaning": "Student",      "tones": [2, 5]},
        {"character": "电脑", "pinyin": "diàn nǎo", "meaning": "Computer",      "tones": [4, 3]},
        {"character": "电视", "pinyin": "diàn shì", "meaning": "Television",    "tones": [4, 4]},
        {"character": "分钟", "pinyin": "fēn zhōng", "meaning": "Minute",       "tones": [1, 1]},
        {"character": "东西", "pinyin": "dōng xi",  "meaning": "Thing/Stuff",   "tones": [1, 5]},
    ],
    "advanced": [
        {"character": "环境", "pinyin": "huán jìng",  "meaning": "Environment",  "tones": [2, 4]},
        {"character": "经济", "pinyin": "jīng jì",    "meaning": "Economy",      "tones": [1, 4]},
        {"character": "发展", "pinyin": "fā zhǎn",    "meaning": "Development",  "tones": [1, 3]},
        {"character": "文化", "pinyin": "wén huà",    "meaning": "Culture",      "tones": [2, 4]},
        {"character": "图书馆", "pinyin": "tú shū guǎn", "meaning": "Library",   "tones": [2, 1, 3]},
        {"character": "办公室", "pinyin": "bàn gōng shì", "meaning": "Office",  "tones": [4, 1, 4]},
        {"character": "火车站", "pinyin": "huǒ chē zhàn", "meaning": "Train Station", "tones": [3, 1, 4]},
        {"character": "飞机场", "pinyin": "fēi jī chǎng", "meaning": "Airport", "tones": [1, 1, 3]},
        {"character": "服务员", "pinyin": "fú wù yuán", "meaning": "Waiter/Server", "tones": [2, 4, 2]},
        {"character": "对不起", "pinyin": "duì bu qǐ", "meaning": "Sorry",     "tones": [4, 5, 3]},
        {"character": "没关系", "pinyin": "méi guān xi", "meaning": "It's okay", "tones": [2, 1, 5]},
        {"character": "打电话", "pinyin": "dǎ diàn huà", "meaning": "Make phone call", "tones": [3, 4, 4]},
        {"character": "看电影", "pinyin": "kàn diàn yǐng", "meaning": "Watch movie", "tones": [4, 4, 3]},
        {"character": "为什么", "pinyin": "wèi shén me", "meaning": "Why",      "tones": [4, 2, 5]},
        {"character": "不知道", "pinyin": "bù zhī dào", "meaning": "Don't know", "tones": [4, 1, 4]},
        {"character": "听不懂", "pinyin": "tīng bù dǒng", "meaning": "Can't understand", "tones": [1, 4, 3]},
        {"character": "信用卡", "pinyin": "xìn yòng kǎ", "meaning": "Credit card", "tones": [4, 4, 3]},
        {"character": "出租车", "pinyin": "chū zū chē", "meaning": "Taxi",      "tones": [1, 1, 1]},
        {"character": "自行车", "pinyin": "zì xíng chē", "meaning": "Bicycle",  "tones": [4, 2, 1]},
        {"character": "大熊猫", "pinyin": "dà xióng māo", "meaning": "Giant Panda", "tones": [4, 2, 1]},
    ]
}

# Stroke data for common characters (simplified path descriptions for UI rendering)
# Format: list of strokes, each stroke is a list of (x, y) waypoints (0-100 coordinate space)
STROKE_DATA = {
    "一": [[(15, 50), (30, 49), (50, 50), (70, 51), (85, 50)]],
    "二": [
        [(25, 35), (40, 34), (60, 36), (75, 35)],  # Top shorter line
        [(15, 65), (35, 64), (55, 66), (85, 65)]   # Bottom longer line
    ],
    "三": [
        [(20, 25), (45, 24), (70, 26), (80, 25)],
        [(25, 50), (45, 49), (65, 51), (75, 50)],
        [(15, 75), (40, 74), (65, 76), (85, 75)]
    ],
    "人": [
        [(50, 20), (40, 40), (28, 65), (20, 85)],  # Left leg (curved)
        [(50, 45), (65, 65), (80, 85)]              # Right leg
    ],
    "大": [
        [(15, 45), (50, 46), (85, 45)],           # Horizontal bar
        [(50, 20), (42, 45), (32, 70), (20, 90)],  # Left leg (curved)
        [(50, 46), (68, 70), (85, 90)]             # Right leg
    ],
    "山": [[(50, 10), (50, 90)], [(15, 35), (15, 90)], [(85, 35), (85, 90)]],
    "口": [
        [(20, 20), (80, 20)],  # top
        [(80, 20), (80, 80)],  # right
        [(20, 80), (80, 80)],  # bottom
        [(20, 20), (20, 80)],  # left
    ],
    "水": [
        [(50, 10), (50, 90)],
        [(50, 40), (20, 70)],
        [(50, 40), (80, 70)],
        [(50, 55), (15, 90)],
    ],
}


def get_tone_info(tone_number: int) -> dict:
    """Returns the full description dict for a given tone number (1-5)."""
    return TONE_DESCRIPTIONS.get(tone_number, TONE_DESCRIPTIONS[5])


def get_vocabulary(level: str = "beginner") -> list:
    """Returns the vocabulary list for the given difficulty level."""
    return VOCABULARY.get(level, VOCABULARY["beginner"])


_MMH_DATA = None
_MMH_DICT = []


def _load_mmh_data():
    global _MMH_DATA, _MMH_DICT
    if _MMH_DATA is not None:
        return
    _MMH_DATA = {}
    _MMH_DICT = []

    from utils.config import resource_path
    graphics_path = resource_path(os.path.join("res", "data", "graphics.txt"))
    if os.path.exists(graphics_path):
        with open(graphics_path, "r", encoding="utf-8") as f:
            for line in f:
                item = json.loads(line)
                _MMH_DATA[item["character"]] = item["medians"]

    dict_path = resource_path(os.path.join("res", "data", "dictionary.txt"))
    if os.path.exists(dict_path):
        with open(dict_path, "r", encoding="utf-8") as f:
            for line in f:
                item = json.loads(line)
                # Ensure the character has stroke data before adding to searchable dict
                if item["character"] in _MMH_DATA:
                    _MMH_DICT.append(item)


def search_dictionary(query: str) -> list:
    """
    Search English definitions and return a list of matching character dicts:
    [{'character': '猫', 'pinyin': ['māo'], 'definition': 'cat, feline'}, ...]
    Returns up to 10 results.
    """
    _load_mmh_data()
    results: list[dict] = []
    query = query.lower().strip()
    if not query:
        return results

    for item in _MMH_DICT:
        # Search within definitions (e.g., 'one; a, an')
        defi = item.get("definition", "").lower()
        # Direct word match is better
        words = defi.replace(";", "").replace(",", "").split()
        if query in words or query in defi:
            results.append(item)
            if len(results) >= 15:
                break
    return results


def get_stroke_data(character: str) -> list:
    """
    Returns stroke waypoint data for a given character.
    Returns an empty list if the character is not in our local database.
    """
    _load_mmh_data()
    if _MMH_DATA and character in _MMH_DATA:
        medians = _MMH_DATA[character]
        scaled_strokes = []
        for stroke in medians:
            scaled_stroke = []
            for point in stroke:
                x, y = point
                # MMH uses 1024x1024, convert to 0-100 percentage
                scaled_stroke.append((x / 10.24, y / 10.24))
            scaled_strokes.append(scaled_stroke)
        return scaled_strokes

    return STROKE_DATA.get(character, [])
