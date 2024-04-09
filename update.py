import pandas as pd
import requests
from fake_useragent import UserAgent

CUT_DESCRIPTION = 50


def get_json(subreddit, verbose=False):
    url = f"https://www.reddit.com/r/{subreddit}/about.json"
    response = requests.get(url, headers={"User-Agent": UserAgent().random})
    if verbose:
        print(f"Status code: {response.status_code}")
        print(f"Response content: {response.content}")
    return response.json()


df = pd.read_csv("subreddits.csv").assign(
    created_utc=(lambda x: pd.to_datetime(x["created_utc"]))
)

for i, row in df.iterrows():
    print(f"{i}/{len(df)} - reading r/{row['name']}")

    data = get_json(row["name"], verbose=False)

    if "data" not in data:
        df.loc[i, "reason"] = data["reason"]
        continue

    if "created_utc" in data["data"]:
        df.loc[i, "created_utc"] = pd.to_datetime(data["data"]["created_utc"], unit="s")

    if "subscribers" in data["data"]:
        df.loc[i, "subscribers"] = data["data"]["subscribers"]

    if "description" in data["data"]:
        df.loc[i, "description"] = data["data"]["description"][
            :CUT_DESCRIPTION
        ].replace("\n", " ")

df.to_csv("subreddits.csv", index=False)


# Now generate a markdown table with the information and save it as README.md

df_readme = (
    df.copy()
    .query("reason.isna()", engine="python")
    .dropna(subset=["subscribers", "created_utc"])
    .sort_values("subscribers", ascending=False)
)

today_date = pd.Timestamp.now().strftime("%Y-%m-%d")

with open("README.md", "w") as f:
    f.write(
        f"""
# Awesome Italian Reddit  [![Awesome](https://cdn.rawgit.com/sindresorhus/awesome/d7305f38d29fed78fa85652e3a63e154dd8e8829/media/badge.svg)](https://github.com/sindresorhus/awesome)

Updated with `python update.py` on {today_date}.

| Name | Subscribers | Date Creation | Description | Stats |
|------|-------------|---------------|-------------|-------|
"""
    )
    for i, row in df_readme.iterrows():
        name = row["name"]
        nsubs = int(row["subscribers"]) if not pd.isnull(row["subscribers"]) else ""
        date = row["created_utc"].date() if not pd.isnull(row["created_utc"]) else ""
        description = row["description"] if not pd.isnull(row["description"]) else ""
        f.write(
            f"| [r/{name}](https://www.reddit.com/r/{name}/) | {nsubs} | {date} | {description} | [stats](https://subredditstats.com/r/{name}) |\n"
        )
