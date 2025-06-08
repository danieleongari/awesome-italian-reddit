import sys
import pandas as pd
import requests
from fake_useragent import UserAgent
import time

CUT_DESCRIPTION = 50


def get_json(subreddit, verbose=False):
    url = f"https://www.reddit.com/r/{subreddit}/about.json"
    response = requests.get(url, headers={"User-Agent": UserAgent().random})
    if verbose:
        print(f"Status code: {response.status_code}")
        print(f"Response content: {response.content}")
    return response.json()


df = (
    pd.read_csv("subreddits.csv")
    .assign(created_utc=(lambda x: pd.to_datetime(x["created_utc"])))
    .sort_values(
        by="name", key=lambda col: col.str.lower()
    )  # sort by name, case insensitive
    .reset_index(drop=True)
)

assert df[
    "name"
].is_unique, f"Subreddits names must be unique, delete: {df['name'][df['name'].duplicated()].tolist()}"

# If the argument --skip-scraping is passed, skip scraping the subreddits
if "--skip-scraping" not in sys.argv and "-ss" not in sys.argv:
    for i, row in df.iterrows():
        # if specified, skip already scraped subreddits
        if ("--only-new" in sys.argv or "-on" in sys.argv) and pd.notnull(
            row["created_utc"]
        ):
            continue

        print(f"{i}/{len(df)} - reading r/{row['name']}")

        data = get_json(row["name"], verbose=False)

        if "data" not in data:
            if "reason" not in data:
                raise ValueError(
                    str(data)
                )  # typical: {'message': 'Too Many Requests', 'error': 429}
            df.loc[i, "reason"] = data["reason"]
            print(" >>> Error:", df.loc[i, "reason"])
            continue
        df.loc[i, "reason"] = None

        if "created_utc" in data["data"]:
            df.loc[i, "created_utc"] = pd.to_datetime(
                data["data"]["created_utc"], unit="s"
            )

        if "subscribers" in data["data"]:
            df.loc[i, "subscribers"] = data["data"]["subscribers"]

        if "description" in data["data"]:
            df.loc[i, "description"] = data["data"]["description"][
                :CUT_DESCRIPTION
            ].replace("\n", " ")

        time.sleep(10)  # avoid Too Many Requests

df.to_csv("subreddits.csv", index=False)


# Generate Markdown @ README.md

df_readme = (
    df.query("reason.isna()", engine="python")
    .dropna(subset=["subscribers", "created_utc"])
    .sort_values("subscribers", ascending=False)
    .reset_index(drop=True)
    .astype({"subscribers": int})
    .fillna("")
)

today_date = pd.Timestamp.now().strftime("%Y-%m-%d")

with open("README.md", "w") as f:
    f.write(
        f"""
# Awesome Italian Reddit  [![Awesome](https://cdn.rawgit.com/sindresorhus/awesome/d7305f38d29fed78fa85652e3a63e154dd8e8829/media/badge.svg)](https://github.com/sindresorhus/awesome)

Updated with `python update.py` on {today_date}. Browse the [webpage](https://danieleongari.github.io/awesome-italian-reddit/).

| N | Name | Subscribers | Date Creation | Description |
|---|------|-------------|---------------|-------------|
"""
    )
    for i, row in df_readme.iterrows():
        name = row["name"]
        nsubs = int(row["subscribers"]) if not pd.isnull(row["subscribers"]) else ""
        date = row["created_utc"].date() if not pd.isnull(row["created_utc"]) else ""
        description = row["description"] if not pd.isnull(row["description"]) else ""
        f.write(
            f"| {i+1} | [r/{name}](https://www.reddit.com/r/{name}/) | [{nsubs}](https://subredditstats.com/r/{name}) | {date} | {description} |\n"
        )

# Generate HTML page @ docs/index.html

df_html = (
    df_readme
    .assign(
        Subreddit=lambda x: x["name"].apply(
            lambda x: f'<a href="https://www.reddit.com/r/{x}/">r/{x}</a>'
        )
    )
    .assign(**{"Date Creation": lambda x: x["created_utc"].dt.strftime("%Y-%m-%d")})
    .assign(
        Stats=lambda x: x["name"].apply(
            lambda x: f'<a href="https://subredditstats.com/r/{x}">&#9827;</a>'
        )
    )
    .assign(
        N=lambda x: x.index + 1
    )
    .rename(
        columns={
            "subscribers": "Subscribers",
            "description": "Description",
            "tag": "TAG",
        }
    )
    [
        [
            "N", # 1
            "Subreddit",  # 2
            "TAG",  # 3
            "Subscribers",  # 4
            "Date Creation",  # 5
            "Description",  # 6
            "Stats",  # 7
        ]
    ]
)


with open("docs/index.html", "w") as f:
    f.write(
        """
    <!DOCTYPE html>
    <html>
    <head>
        <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.11.3/css/jquery.dataTables.css">
        <script type="text/javascript" charset="utf8" src="https://code.jquery.com/jquery-3.5.1.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/1.11.3/js/jquery.dataTables.js"></script>
        <style>
            body {
                max-width: 1000px;
                margin: auto;
            }
            h1 {
                text-align: center;
            }
            #table_id td:nth-child(4) {
                text-align: right;
            }
            #table_id td:nth-child(5), #table_id td:nth-child(7){
                text-align: center;
            }
        </style>
        <script type="text/javascript" charset="utf8">
        $(document).ready( function () {
            $('#table_id').DataTable({
                "pageLength": """
        + str(len(df_readme))
        + """,
                "info": false,
                "paging": false,
                "order": [[3, 'desc']]
            });
        } );
        </script>
    </head>
    <body>
        <h1>Awesome Italian SubReddits</h1>
        <p><a href="https://github.com/danieleongari/awesome-italian-reddit">Link to GitHub script</a>,
    """
        + f"last update on {today_date}.</p>"
    )

    # Convert DataFrame to HTML table
    f.write(df_html.to_html(index=False, table_id="table_id", escape=False))

    f.write(
        """
    </body>
    </html>
    """
    )
