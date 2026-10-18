import os

from flask import render_template


def index():
    return render_template(
        "index.html",
        map_tile_url=os.getenv("MAP_TILE_URL", "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"),
        map_attribution=os.getenv("MAP_TILE_ATTRIBUTION", "&copy; OpenStreetMap contributors"),
    )
