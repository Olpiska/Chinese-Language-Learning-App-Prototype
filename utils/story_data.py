"""
utils/story_data.py
--------------------
Database of simple Chinese stories for beginners.
Each story includes Chinese characters, Pinyin, and English translations.
"""

STORIES = [
    {
        "id": "little_cat",
        "title": "Little Cat's Day",
        "title_zh": "小猫的一天",
        "difficulty": "Beginner",
        "pages": [
            {
                "zh": "小猫在阳光下睡觉。",
                "py": "Xiǎomāo zài yángguāng xià shuìjiào.",
                "en": "The little cat is sleeping under the sun.",
                "illustration": "res/img/cat_sun.png"
            },
            {
                "zh": "它看见一只小鸟。",
                "py": "Tā kànjiàn yīzhǐ xiǎoniǎo.",
                "en": "It sees a little bird.",
                "illustration": "res/img/cat_bird.png"
            },
            {
                "zh": "小猫想和它玩。",
                "py": "Xiǎomāo xiǎng hé tā wán.",
                "en": "The little cat wants to play with it.",
                "illustration": "res/img/cat_play.png"
            },
            {
                "zh": "它们在花园里跑。",
                "py": "Tāmen zài huāyuán lǐ pǎo.",
                "en": "They are running in the garden.",
                "illustration": "res/img/cat_garden.png"
            }
        ]
    },
    {
        "id": "mountain_trip",
        "title": "A Trip to the Mountain",
        "title_zh": "去爬山",
        "difficulty": "Beginner",
        "pages": [
            {
                "zh": "今天天气很好。",
                "py": "Jīntiān tiānqì hěn hǎo.",
                "en": "Today's weather is very good.",
                "illustration": "res/img/mountain_sunny.png"
            },
            {
                "zh": "我们去爬大山。",
                "py": "Wǒmen qù pá dàshān.",
                "en": "We are going to climb a big mountain.",
                "illustration": "res/img/mountain_climb.png"
            },
            {
                "zh": "山上有很多树。",
                "py": "Shānshàng yǒu hěnduō shù.",
                "en": "There are many trees on the mountain.",
                "illustration": "res/img/mountain_trees.png"
            },
            {
                "zh": "我们很高兴。",
                "py": "Wǒmen hěn gāoxìng.",
                "en": "We are very happy.",
                "illustration": "res/img/mountain_happy.png"
            }
        ]
    },
    {
        "id": "my_friend",
        "title": "My Good Friend",
        "title_zh": "我的好朋友",
        "difficulty": "Beginner",
        "pages": [
            {
                "zh": "这是我的好朋友。",
                "py": "Zhè shì wǒ de hǎo péngyǒu.",
                "en": "This is my good friend.",
                "illustration": "res/img/friend_1.png"
            },
            {
                "zh": "我们每天一起上学。",
                "py": "Wǒmen měitiān yīqǐ shàngxué.",
                "en": "We go to school together every day.",
                "illustration": "res/img/friend_2.png"
            },
            {
                "zh": "我们喜欢吃苹果。",
                "py": "Wǒmen xǐhuān chī píngguǒ.",
                "en": "We like to eat apples.",
                "illustration": "res/img/friend_3.png"
            }
        ]
    },
    {
        "id": "morning_routine",
        "title": "Good Morning",
        "title_zh": "早上好",
        "difficulty": "Beginner",
        "pages": [
            {
                "zh": "太阳出来了。",
                "py": "Tàiyáng chūlái le.",
                "en": "The sun has come out.",
                "illustration": "res/img/morning_1.png"
            },
            {
                "zh": "我喝了一杯水。",
                "py": "Wǒ hē le yī bēi shuǐ.",
                "en": "I drank a cup of water.",
                "illustration": "res/img/morning_2.png"
            },
            {
                "zh": "我很开心。",
                "py": "Wǒ hěn kāixīn.",
                "en": "I am very happy.",
                "illustration": "res/img/morning_3.png"
            }
        ]
    }

]


def get_stories():
    return STORIES
