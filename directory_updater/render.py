"""Render the public directory using only the CSV's cached metadata."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import html

from .dataset import parse_timestamp


REPOSITORY = "https://github.com/danieleongari/awesome-italian-reddit"
PAGE = "https://danieleongari.github.io/awesome-italian-reddit/"


def subscriber_count(value):
    if not value:
        return None
    try:
        count = Decimal(value)
        if not count.is_finite() or count < 0 or count != count.to_integral_value():
            raise ValueError
        return int(count)
    except (InvalidOperation, ValueError):
        raise ValueError(f"Invalid cached subscriber count: {value!r}.") from None


def render(rows):
    entries = []
    timestamps = []
    for row in rows:
        if row.get("updated_utc"):
            timestamps.append(parse_timestamp(row["updated_utc"]))
        count = subscriber_count(row.get("subs"))
        if row.get("reason") or count is None:
            continue
        created = parse_timestamp(row["created_utc"]).date().isoformat() if row.get("created_utc") else ""
        entries.append((count, row["name"], created, row.get("description", ""), row.get("tag", "")))
    entries.sort(key=lambda row: (-row[0], row[1].lower()))
    today = datetime.now(timezone.utc).date().isoformat()
    freshness = (
        f"Latest successful API fetch: {max(timestamps).astimezone(timezone.utc):%Y-%m-%d %H:%M UTC} "
        "(individual entries may be older)."
        if timestamps else "The last API fetch date is unknown; cached figures may be outdated."
    )
    markdown = [
        "# Awesome Italian Reddit\n",
        f"Directory generated on {today} from `subreddits.csv`. {freshness}\n",
        f"Browse the [webpage]({PAGE}). See [update instructions](UPDATING.md) for setup and GitHub Actions.\n",
        "| N | Name | Subs | Date Creation | Description |",
        "|---|------|------|---------------|-------------|",
    ]
    table = []
    for rank, (count, name, created, description, tag) in enumerate(entries, 1):
        text = " ".join(description.split())
        md_text = html.escape(text, quote=False).replace("\\", "\\\\").replace("|", "&#124;")
        for char in "`*_[]":
            md_text = md_text.replace(char, "\\" + char)
        markdown.append(f"| {rank} | [r/{name}](https://www.reddit.com/r/{name}/) | {count} | {created} | {md_text} |")
        table.append(
            f'<tr><td>{rank}</td><td><a href="https://www.reddit.com/r/{name}/">r/{name}</a></td>'
            f'<td>{html.escape(tag)}</td><td>{count}</td><td>{created}</td><td>{html.escape(text)}</td></tr>'
        )
    page = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Awesome Italian Reddit</title>
<style>
body {max-width: 1100px; margin: 2rem auto; padding: 0 1rem; font-family: system-ui, sans-serif; line-height: 1.5}
h1 {text-align: center} table {width: 100%; border-collapse: collapse}
th, td {padding: .5rem; text-align: left; border-bottom: 1px solid #ddd}
td:nth-child(4) {text-align: right} th button {font: inherit; cursor: pointer; border: 0; background: none}
input {font: inherit; padding: .4rem; margin-bottom: 1rem} .table-wrap {overflow-x: auto}
</style>
</head>
<body>
<h1>Awesome Italian Reddit</h1>
'''
    page += f'<p><a href="{REPOSITORY}">GitHub repository</a> · Directory generated on {today}. {html.escape(freshness)}</p>\n'
    page += '''<label for="search">Filter communities: </label><input id="search" type="search">
<div class="table-wrap"><table id="directory">
<thead><tr>'''
    for title in ("N", "Subreddit", "Tag", "Subs", "Date Creation", "Description"):
        page += f'<th scope="col"><button type="button">{title}</button></th>'
    page += "</tr></thead>\n<tbody>\n" + "\n".join(table) + "\n</tbody></table></div>\n"
    page += '''<script>
const table = document.querySelector('#directory');
const body = table.tBodies[0];
document.querySelector('#search').addEventListener('input', event => {
  const query = event.target.value.toLocaleLowerCase();
  for (const row of body.rows) row.hidden = !row.textContent.toLocaleLowerCase().includes(query);
});
let sortedColumn = 3, ascending = false;
for (const [column, button] of [...table.querySelectorAll('th button')].entries()) {
  button.addEventListener('click', () => {
    ascending = column === sortedColumn ? !ascending : true;
    sortedColumn = column;
    const rows = [...body.rows].sort((a, b) => {
      const left = a.cells[column].textContent, right = b.cells[column].textContent;
      const compared = column === 0 || column === 3 ? Number(left) - Number(right) : left.localeCompare(right);
      return ascending ? compared : -compared;
    });
    body.append(...rows);
    for (const header of table.querySelectorAll('th')) header.removeAttribute('aria-sort');
    button.parentElement.setAttribute('aria-sort', ascending ? 'ascending' : 'descending');
  });
}
table.querySelectorAll('th')[3].setAttribute('aria-sort', 'descending');
</script>
</body>
</html>
'''
    return "\n".join(markdown) + "\n", page
