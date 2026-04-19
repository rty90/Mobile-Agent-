import requests

PUBLIC_URL = "https://stomach-packing-salt-ext.trycloudflare.com/"
IMAGE_PATH = r"F:\mobile agents\screenshots.png"

with open(IMAGE_PATH, "rb") as f:
    resp = requests.post(
        f"{PUBLIC_URL}/infer",
        files={"image": ("screenshots.png", f, "image/png")},
        data={
            "prompt": "你是一个GUI agent。我想找点好吃的东西，怎么办",
            "max_new_tokens": 1024,
        },
        timeout=1800,
    )

print(resp.status_code)
print(resp.text)