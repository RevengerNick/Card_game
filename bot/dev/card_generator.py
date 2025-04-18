import random
from faker import Faker

from bot.Classes.db_manager import card_manager
from bot.card_database import RARITY_WEIGHTS

fake = Faker()

PHOTO_IDS = [
    "AgACAgIAAxkBAAIU52f70W55hcDTdQj05bpcvKRiQ87PAAKr7TEbOA7ZS96RJgrwky0RAQADAgADcwADNgQ",
    "AgACAgIAAxkBAAIU5mf70W6Fri6Hz5rZRYX_VsZcAaKuAAKq7TEbOA7ZS4Ec534JrZBzAQADAgADcwADNgQ",
    "AgACAgIAAxkBAAIU5Gf70W5KtKSCAtdTRLKkAxt4b4-ZAAKo7TEbOA7ZSyoAATwkKrhZvAEAAwIAA3MAAzYE",
    "AgACAgIAAxkBAAIU4mf70V_sBhn8BLNXI43usgp8sDnhAAKu7TEbOA7ZS7E0bzruyHK8AQADAgADcwADNgQ",
    "AgACAgIAAxkBAAIU5Wf70W7WCP4KtOJJXPT2OQYvx8VLAAKp7TEbOA7ZS2DOI8x2WXRuAQADAgADcwADNgQ",
    "AgACAgIAAxkBAAIU6Gf70W4odWqdQk-Jrmt97FN6PEdJAAKs7TEbOA7ZS85jNpGmeMXjAQADAgADcwADNgQ",
    "AgACAgIAAxkBAAIU6Wf70W67i1cZR1mTBrHFSIadUiNuAAKt7TEbOA7ZS923E5xl9JLsAQADAgADcwADNgQ"
]

def weighted_rarity():
    names = list(RARITY_WEIGHTS.keys())
    weights = list(RARITY_WEIGHTS.values())
    return random.choices(names, weights=weights, k=1)[0]

def generate_random_cards(amount):
    for _ in range(amount):

        name = fake.first_name() + " " + fake.last_name()
        rarity = weighted_rarity()

        base_attack = random.randint(500, 1500)
        base_health = random.randint(1000, 2000)
        multiplier = {
            "common": 1,
            "rare": 2,
            "epic": 3,
            "legendary": 5,
            "mythical": 10
        }.get(rarity, 1)

        attack = int(base_attack * multiplier)
        health = int(base_health * multiplier)
        value = int((attack + health) / 2)

        photo_id = random.choice(PHOTO_IDS)

        card_manager.add_card(name=name, rarity=rarity, attack=attack, health=health, value=value, image_path=photo_id)

if __name__ == "__main__":
    generate_random_cards(20)  # Пример: сгенерировать 20 карт