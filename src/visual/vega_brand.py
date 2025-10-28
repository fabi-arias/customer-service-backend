# src/visual/vega_brand.py
CELESTE_RANGE = ["#9ECCDB","#0498C8","#007DA6","#025C7A","#023D52"]


def vega_config_brand():
    return {
        # Paletas por tipo de escala
        "range": {
            "category": CELESTE_RANGE,  # para color nominal (categorías, agentes, canales)
            "ordinal":  CELESTE_RANGE,  # para escalas ordinales
            "ramp": ["#9ECCDB", "#025875"],  # para cuantitativas (de claro a oscuro)
            "heatmap": ["#9ECCDB", "#C8F0FF", "#8AD9F8", "#4EC3F0", "#1BA8DD", "#0084B0", "#00516E"]
        },
        # Colores/estilos por tipo de marca (fallback si no hay color por campo)
        "bar":  {"color": "#00A9E0"},
        "line": {"color": "#00A9E0"},
        "area": {"color": "#00A9E0"},
        "point": {"filled": True, "color": "#00A9E0"},
        # Estética general
        "axis": {
            "labelFontSize": 12, "titleFontSize": 13,
            "labelColor": "#132933", "titleColor": "#212121"
        },
        "view": {"stroke": "transparent"}
    }
