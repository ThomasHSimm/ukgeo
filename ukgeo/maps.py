"""
Map visualisation for ukgeo geocoding results.
Requires folium: pip install folium or pip install ukgeo[maps]
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional, Union
import polars as pl


# Colour scheme
COLOURS = {
    "High": "#2ecc71",   # green
    "Medium": "#f39c12",   # orange
    "Low": "#e74c3c",   # red
    "unresolved": "#95a5a6",  # grey
}

LEVEL_LABELS = {
    1: "Level 1 — regex/postcode",
    2: "Level 2 — OS Names",
    3: "Level 3 — OS Names API",
    4: "Level 4 — LLM",
}


def plot_results(
    results: Union[pl.DataFrame, list[dict]],
    output_path: Optional[Union[str, Path]] = None,
    title: str = "ukgeo geocoding results",
    zoom_start: int = 6,
    centre: tuple[float, float] = (54.0, -2.0),
) -> "folium.Map":
    """
    Plot geocoding results on an interactive folium map.

    Args:
        results:     polars DataFrame from geocode_batch(), or list of GeoResult.as_dict()
        output_path: if given, save HTML to this path
        title:       map title shown in top-left
        zoom_start:  initial zoom level (6 = whole GB)
        centre:      initial map centre (lat, lon)

    Returns:
        folium.Map object (display in Jupyter with just the variable name)

    Example:
        geo = Geocoder()
        df = geo.geocode_batch(["LS1 1BA", "M62 Junction 26", "Spaghetti Junction Birmingham"])
        m = plot_results(df, output_path="results.html")
    """
    try:
        import folium
        from folium.plugins import MarkerCluster
    except ImportError:
        raise ImportError(
            "folium is required for map output. "
            "Install with: pip install folium  or  pip install ukgeo[maps]"
        )

    # Normalise input to list of dicts
    if isinstance(results, pl.DataFrame):
        rows = results.to_dicts()
    else:
        rows = [r.as_dict() if hasattr(r, "as_dict") else r for r in results]

    # Build map
    m = folium.Map(location=centre, zoom_start=zoom_start, tiles="CartoDB positron")

    # Title
    title_html = f"""
    <div style="position: fixed; top: 10px; left: 50px; z-index: 1000;
                background: white; padding: 8px 14px; border-radius: 4px;
                box-shadow: 0 1px 5px rgba(0,0,0,0.3); font-family: sans-serif;">
        <b>{title}</b>
    </div>
    """
    m.get_root().html.add_child(folium.Element(title_html))

    # Legend
    legend_html = """
    <div style="position: fixed; bottom: 30px; left: 30px; z-index: 1000;
                background: white; padding: 10px 14px; border-radius: 4px;
                box-shadow: 0 1px 5px rgba(0,0,0,0.3); font-family: sans-serif;
                font-size: 13px; line-height: 1.8;">
        <b>Confidence</b><br>
        <span style="color:#2ecc71">●</span> High<br>
        <span style="color:#f39c12">●</span> Medium<br>
        <span style="color:#e74c3c">●</span> Low<br>
        <span style="color:#95a5a6">●</span> Unresolved
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    # Stats
    total = len(rows)
    resolved = sum(1 for r in rows if r.get("lat") is not None)
    by_conf = {}
    for r in rows:
        c = r.get("confidence") or "unresolved"
        by_conf[c] = by_conf.get(c, 0) + 1

    stats_html = f"""
    <div style="position: fixed; top: 10px; right: 10px; z-index: 1000;
                background: white; padding: 8px 14px; border-radius: 4px;
                box-shadow: 0 1px 5px rgba(0,0,0,0.3); font-family: sans-serif;
                font-size: 12px; line-height: 1.8;">
        <b>Results</b><br>
        Resolved: {resolved}/{total} ({100*resolved//max(total,1)}%)<br>
        High: {by_conf.get('High', 0)}<br>
        Medium: {by_conf.get('Medium', 0)}<br>
        Low: {by_conf.get('Low', 0)}<br>
        Unresolved: {total - resolved}
    </div>
    """
    m.get_root().html.add_child(folium.Element(stats_html))

    # Use marker cluster for large datasets
    use_cluster = total > 100
    layer = MarkerCluster(name="Results") if use_cluster else m

    for row in rows:
        lat = row.get("lat")
        lon = row.get("lon")
        inp = row.get("input", "")
        conf = row.get("confidence") or "unresolved"
        interpreted = row.get("interpreted_as") or "unresolved"
        level = row.get("level_resolved")
        notes = row.get("notes") or ""

        colour = COLOURS.get(conf, COLOURS["unresolved"])
        level_label = LEVEL_LABELS.get(level, "unresolved")

        if lat is not None and lon is not None:
            popup_html = f"""
            <div style="font-family: sans-serif; font-size: 13px; min-width: 200px;">
                <b>{inp}</b><br>
                <hr style="margin: 4px 0">
                <b>Interpreted as:</b> {interpreted}<br>
                <b>Confidence:</b> {conf}<br>
                <b>Level:</b> {level_label}<br>
                <b>Coords:</b> {lat:.5f}, {lon:.5f}<br>
                <small style="color: #888">{notes}</small>
            </div>
            """
            marker = folium.CircleMarker(
                location=[lat, lon],
                radius=7,
                color=colour,
                fill=True,
                fill_color=colour,
                fill_opacity=0.8,
                popup=folium.Popup(popup_html, max_width=280),
                tooltip=f"{inp} → {interpreted} ({conf})",
            )
            if use_cluster:
                marker.add_to(layer)
            else:
                marker.add_to(m)
        else:
            # Unresolved — skip (no coordinates to plot)
            pass

    if use_cluster:
        layer.add_to(m)

    # Auto-fit bounds to resolved points
    resolved_points = [
        [r["lat"], r["lon"]] for r in rows
        if r.get("lat") is not None and r.get("lon") is not None
    ]
    if resolved_points:
        m.fit_bounds(resolved_points)

    if output_path:
        m.save(str(output_path))
        print(f"Map saved to {output_path}")

    return m


def plot_batch_summary(
    results: pl.DataFrame,
    output_path: Optional[Union[str, Path]] = None,
) -> "folium.Map":
    """
    Convenience wrapper — plots with a summary title showing resolve rate.
    """
    total = len(results)
    resolved = results["lat"].drop_nulls().len()
    title = f"ukgeo results — {resolved}/{total} resolved ({100*resolved//max(total,1)}%)"
    return plot_results(results, output_path=output_path, title=title)
