# src/database/data_management_api.py
from fastapi import FastAPI, HTTPException, Depends, Header, Query
from fastapi.responses import StreamingResponse
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional
from visual.vega_brand import vega_config_brand


# imports del proyecto
src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))
from database.db_utils import get_db_connection

# Crear FastAPI app para gestión de datos
data_app = FastAPI(
    title="Data Management API",
    description="API para gestión completa de datos: insertar, consultar, exportar y analizar tickets de servicio al cliente",
    version="1.0.0"
)

# Función de autenticación
def verify_api_key(x_api_key: str = Header(None)):
    api_key = os.getenv("INGEST_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="API key not configured")
    if x_api_key != api_key:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return x_api_key

@data_app.get("/health")
def health():
    """Endpoint de salud de la API."""
    return {"status": "ok", "service": "data-management-api"}

@data_app.get("/stats")
def get_stats():
    """Obtiene estadísticas básicas de tickets en la base de datos."""
    try:
        conn = get_db_connection()
        with conn, conn.cursor() as cur:
            # Contar total de tickets
            cur.execute("SELECT COUNT(*) FROM resolved_tickets")
            total_tickets = cur.fetchone()[0]
            
            # Contar por categoría
            cur.execute("""
                SELECT category, COUNT(*) as count 
                FROM resolved_tickets 
                WHERE category IS NOT NULL 
                GROUP BY category 
                ORDER BY count DESC
            """)
            categories = cur.fetchall()
            
            return {
                "success": True,
                "total_tickets": total_tickets,
                "categories": [{"category": cat[0], "count": cat[1]} for cat in categories]
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@data_app.post("/tickets/batch")
def ingest_batch(
    tickets: List[dict],
    api_key: str = Depends(verify_api_key)
):
    """Endpoint para insertar tickets resueltos en batch."""
    if not tickets:
        raise HTTPException(status_code=400, detail="Lista de tickets vacía")

    inserted, skipped, errors = 0, 0, []
    
    try:
        conn = get_db_connection()
        with conn, conn.cursor() as cur:
            for i, ticket in enumerate(tickets):
                try:
                    # Validar campos requeridos
                    if not ticket.get("hubspot_ticket_id"):
                        errors.append(f"Ticket {i}: hubspot_ticket_id es requerido")
                        skipped += 1
                        continue

                    cur.execute("""
                        INSERT INTO resolved_tickets (
                          hubspot_ticket_id,
                          subject,
                          content,
                          created_at,
                          closed_at,
                          itinerary_number,
                          source,
                          category,
                          subcategory,
                          resolution,
                          owner_id,          -- NUEVO
                          owner_name,        -- NUEVO
                          case_key,
                          raw_hubspot
                        )
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                        ON CONFLICT (hubspot_ticket_id) DO NOTHING
                    """, (
                        ticket["hubspot_ticket_id"],
                        ticket.get("subject"),
                        ticket.get("content"),
                        ticket.get("created_at"),
                        ticket.get("closed_at"),
                        ticket.get("itinerary_number", "N/A"),
                        ticket.get("source", "Email"),
                        ticket.get("category", "Consulta General"),
                        ticket.get("subcategory", "Consulta"),
                        ticket.get("resolution"),
                        ticket.get("owner_id"),          # <-- nuevo
                        ticket.get("owner_name"),        # <-- nuevo
                        ticket.get("case_key"),
                        json.dumps(ticket.get("raw_hubspot", {})),
                    ))
                    inserted += cur.rowcount  # 1 insertado, 0 duplicado

                except Exception as e:
                    skipped += 1
                    error_msg = f"Ticket {ticket.get('hubspot_ticket_id', f'#{i}')}: {str(e)}"
                    errors.append(error_msg)
                    print(f"❌ {error_msg}")

        response = {
            "success": True,
            "inserted": inserted,
            "skipped": skipped,
            "total_processed": len(tickets)
        }
        if errors:
            response["errors"] = errors
        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error de conexión: {str(e)}")

@data_app.get("/tickets/export")
def export_resolved_tickets(
    since: Optional[str] = Query(None, description="ISO8601 o 'YYYY-MM-DD'"),
    limit: int = Query(5000, description="Límite de registros"),
    api_key: str = Depends(verify_api_key)
):
    """
    Exporta tickets resueltos en formato NDJSON (una línea por documento).
    """
    # default: últimos 30 días
    if since:
        try:
            since_date = datetime.fromisoformat(since.replace("Z",""))
        except Exception:
            raise HTTPException(status_code=400, detail="since inválido")
    else:
        since_date = datetime.utcnow() - timedelta(days=30)

    def row_to_doc(row):
        (hubspot_ticket_id, subject, content, created_at, closed_at,
         itinerary_number, source, category, subcategory, resolution, case_key, owner_id, owner_name) = row

        doc = {
            "id": hubspot_ticket_id,
            "text": f"[Asunto]\n{subject or ''}\n\n[Descripción]\n{content or ''}\n\n[Resolución]\n{resolution or ''}",
            "metadata": {
                "created_at": created_at.isoformat() if created_at else None,
                "closed_at": closed_at.isoformat() if closed_at else None,
                "source": source,
                "category": category,
                "subcategory": subcategory,
                "itinerary_number": itinerary_number,
                "case_key": case_key,
                "owner_id": owner_id,
                "owner_name": owner_name
            }
        }
        return doc

    def generate_ndjson():
        try:
            conn = get_db_connection()
            with conn, conn.cursor() as cur:
                cur.execute("""
                    SELECT hubspot_ticket_id, subject, content, created_at, closed_at,
                           itinerary_number, source, category, subcategory, resolution, case_key, owner_id, owner_name
                    FROM resolved_tickets
                    WHERE closed_at >= %s
                    ORDER BY closed_at DESC
                    LIMIT %s
                """, (since_date, limit))
                for r in cur.fetchall():
                    yield json.dumps(row_to_doc(r), ensure_ascii=False) + "\n"
        except Exception as e:
            # Devuelve un documento de error y corta
            yield json.dumps({"error": str(e)}) + "\n"

    return StreamingResponse(generate_ndjson(), media_type="application/x-ndjson")


@data_app.get("/analytics/categories")
def top_categories(
    from_date: str = Query(..., alias="from", description="YYYY-MM-DD"),
    to_date:   str = Query(..., alias="to",   description="YYYY-MM-DD"),
    top:       int = Query(10, description="Número de categorías a retornar"),
    api_key:   str = Depends(verify_api_key)
):
    """
    Devuelve las categorías más frecuentes de tickets resueltos en un rango de fechas,
    SIEMPRE con chartSpec (Vega-Lite) listo para visualizar.
    """
    # --- Validación de fechas ---
    try:
        from_dt = datetime.fromisoformat(from_date).date()
        to_dt   = datetime.fromisoformat(to_date).date()
    except Exception:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido (use YYYY-MM-DD)")
    if from_dt > to_dt:
        raise HTTPException(status_code=400, detail="'from' no puede ser mayor que 'to'")

    try:
        conn = get_db_connection()
        with conn, conn.cursor() as cur:
            # Rango FIN EXCLUSIVO: closed_at >= from AND closed_at < (to + 1 día)
            cur.execute("""
                SELECT
                    COALESCE(NULLIF(TRIM(category), ''), 'Sin categoría') AS category,
                    COUNT(*)::int AS count
                FROM resolved_tickets
                WHERE closed_at >= %s::date
                  AND closed_at <  (%s::date + INTERVAL '1 day')
                GROUP BY 1
                ORDER BY count DESC
                LIMIT %s
            """, (from_dt, to_dt, top))
            rows = cur.fetchall()

        items = [{"category": r[0], "count": r[1]} for r in rows]
        total = sum(it["count"] for it in items)

        # Altura dinámica para evitar solapamiento (~28 px por barra + margen)
        dyn_height = max(200, 28 * max(1, len(items)) + 40)

        payload = {
            "success": True,
            "metric": "Top de categorías por tickets cerrados",
            "from": from_date,
            "to": to_date,
            "params": {"top": top},
            "top_categories": items,
            "total": total,
            "chartSpec": {
                "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
                "description": "Top de categorías por tickets cerrados",
                "data": {"values": {"$ref": "top_categories"}},
                "mark": {"type": "bar"},
                "width": 560,
                "height": dyn_height,
                "encoding": {
                    # X cuantitativo (incluye 0 por defecto en barras)
                    "x": {
                        "field": "count",
                        "type": "quantitative",
                        "axis": {"title": "Tickets cerrados", "format": "d"},
                        "scale": {"nice": True}
                    },
                    # Y nominal: categorías, ordenadas por valor descendente
                    "y": {
                        "field": "category",
                        "type": "nominal",
                        "sort": "-x",
                        "axis": {"title": "Categoría", "labelLimit": 300}
                    },
                    # 🎨 Usa la paleta universal (category range) por categoría
                    "color": {
                        "field": "category",
                        "type": "nominal",
                        "legend": None
                    },
                    "tooltip": [
                        {"field": "category", "type": "nominal", "title": "Categoría"},
                        {"field": "count",    "type": "quantitative", "title": "Cerrados", "format": "d"}
                    ]
                },
                # ✅ Aplica tu config global (paleta celeste y estilos)
                "config": vega_config_brand()
            }
        }
        return payload

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@data_app.get("/analytics/sources")
def tickets_by_source(
    from_date: str = Query(..., alias="from", description="YYYY-MM-DD"),
    to_date:   str = Query(..., alias="to",   description="YYYY-MM-DD"),
    api_key:   str = Depends(verify_api_key)
):
    """
    Distribución de tickets por canal (source), SIEMPRE con chartSpec (Vega-Lite).
    """
    try:
        from_dt = datetime.fromisoformat(from_date).date()
        to_dt   = datetime.fromisoformat(to_date).date()
    except Exception:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido (use YYYY-MM-DD)")
    if from_dt > to_dt:
        raise HTTPException(status_code=400, detail="'from' no puede ser mayor que 'to'")

    try:
        conn = get_db_connection()
        with conn, conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COALESCE(NULLIF(TRIM(source), ''), 'Desconocido') AS source,
                    COUNT(*)::int AS count
                FROM resolved_tickets
                WHERE closed_at >= %s::date
                  AND closed_at <  (%s::date + INTERVAL '1 day')
                GROUP BY 1
                ORDER BY count DESC
            """, (from_dt, to_dt))
            rows = cur.fetchall()

        total = sum(r[1] for r in rows) or 1
        items = [{"source": r[0], "count": r[1], "pct": round(r[1]*100/total, 1)} for r in rows]

        # Altura dinámica (~28px por barra + margen)
        dyn_height = max(200, 28 * max(1, len(items)) + 40)

        payload = {
            "success": True,
            "metric": "Distribución de tickets por canal",
            "from": from_date,
            "to": to_date,
            "by_source": items,
            "total": total,
            "chartSpec": {
                "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
                "description": "Distribución por canal",
                "data": {"values": {"$ref": "by_source"}},
                "mark": {"type": "bar"},
                "width": 560,
                "height": dyn_height,
                "encoding": {
                    "x": {
                        "field": "count",
                        "type": "quantitative",
                        "axis": {"title": "Tickets cerrados", "format": "d"},
                        "scale": {"nice": True}
                    },
                    "y": {
                        "field": "source",
                        "type": "nominal",
                        "sort": "-x",
                        "axis": {"title": "Canal", "labelLimit": 260}
                    },
                    # 👇 Esta línea activa la paleta celeste de vega_config_brand()
                    "color": {
                        "field": "source",
                        "type": "nominal",
                        "legend": None
                    },
                    "tooltip": [
                        {"field": "source", "type": "nominal", "title": "Canal"},
                        {"field": "count",  "type": "quantitative", "title": "Cerrados", "format": "d"},
                        {"field": "pct",    "type": "quantitative", "title": "%", "format": ".1f"}
                    ]
                },
                "config": vega_config_brand()
            }
        }

        return payload

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@data_app.get("/analytics/agents")
def top_agents(
    from_date: str = Query(..., alias="from", description="YYYY-MM-DD"),
    to_date:   str = Query(..., alias="to",   description="YYYY-MM-DD"),
    top:       int = Query(10, description="Número de agentes a retornar"),
    api_key:   str = Depends(verify_api_key)
):
    """
    Ranking de agentes por tickets cerrados en el rango.
    Siempre devuelve chartSpec (Vega-Lite) con {"$ref":"top_agents"}.
    """
    # Validación de fechas
    try:
        from_dt = datetime.fromisoformat(from_date).date()
        to_dt   = datetime.fromisoformat(to_date).date()
    except Exception:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido (use YYYY-MM-DD)")
    if from_dt > to_dt:
        raise HTTPException(status_code=400, detail="'from' no puede ser mayor que 'to'")

    try:
        conn = get_db_connection()
        with conn, conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COALESCE(
                        NULLIF(TRIM(owner_name), ''),
                        NULLIF(TRIM(owner_id), ''),
                        'Sin asignar'
                    ) AS agent,
                    COUNT(*)::int AS count
                FROM resolved_tickets
                WHERE closed_at >= %s::date
                  AND closed_at <  (%s::date + INTERVAL '1 day')
                GROUP BY 1
                ORDER BY count DESC, agent ASC
                LIMIT %s
            """, (from_dt, to_dt, top))
            rows = cur.fetchall()

        items = [{"agent": r[0], "count": r[1]} for r in rows]
        total = sum(it["count"] for it in items)

        # Altura dinámica: ~28px por barra
        dyn_height = max(200, 28 * max(1, len(items)) + 40)

        payload = {
            "success": True,
            "metric": "Top de agentes por tickets cerrados",
            "from": from_date,
            "to": to_date,
            "params": {"top": top},
            "top_agents": items,
            "total": total,
            "chartSpec": {
                "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
                "description": "Top de agentes por tickets cerrados",
                "data": {"values": {"$ref": "top_agents"}},
                "mark": {"type": "bar"},
                "width": 560,
                "height": dyn_height,
                "encoding": {
                    "x": {
                        "field": "count",
                        "type": "quantitative",
                        "axis": {"title": "Tickets cerrados", "format": "d"},
                        "scale": {"nice": True}
                    },
                    "y": {
                        "field": "agent",
                        "type": "nominal",
                        "sort": "-x",
                        "axis": {"title": "Agente", "labelLimit": 300}
                    },
                    "color": {
                        "field": "agent",
                        "type": "nominal",
                        "legend": None
                    },
                    "tooltip": [
                        {"field": "agent", "type": "nominal", "title": "Agente"},
                        {"field": "count", "type": "quantitative", "title": "Cerrados", "format": "d"}
                    ]
                },
                "config": vega_config_brand()
            }
        }
        return payload

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@data_app.get("/analytics/closed_volume")
def closed_volume(
    from_date: str = Query(..., alias="from", description="YYYY-MM-DD"),
    to_date: str = Query(..., alias="to", description="YYYY-MM-DD"),
    api_key: str = Depends(verify_api_key)
):
    """
    Devuelve el total de tickets cerrados en el rango, el desglose diario (completando días sin datos con 0)
    y un chartSpec (Vega-Lite) listo para visualización SIN problemas de zona horaria (eje X categórico).
    """
    # --- Validación de fechas ---
    try:
        from_dt = datetime.fromisoformat(from_date).date()
        to_dt = datetime.fromisoformat(to_date).date()
    except Exception:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido (use YYYY-MM-DD)")

    if from_dt > to_dt:
        raise HTTPException(status_code=400, detail="'from' no puede ser mayor que 'to'")

    try:
        conn = get_db_connection()
        with conn, conn.cursor() as cur:
            # Total de tickets cerrados
            cur.execute("""
                SELECT COUNT(*)::int AS total_closed
                FROM resolved_tickets
                WHERE closed_at >= %s::date
                  AND closed_at < (%s::date + INTERVAL '1 day')
            """, (from_dt, to_dt))
            total_closed = cur.fetchone()[0]

            # Conteo por día real
            cur.execute("""
                SELECT 
                    DATE(closed_at) AS date,
                    COUNT(*)::int   AS count
                FROM resolved_tickets
                WHERE closed_at >= %s::date
                  AND closed_at <  (%s::date + INTERVAL '1 day')
                GROUP BY DATE(closed_at)
            """, (from_dt, to_dt))
            rows = cur.fetchall()  # [(date, count), ...]

        # --- Completar días faltantes con 0 y ordenar ASC ---
        counts = {str(d): c for (d, c) in rows}
        by_day = []
        d = from_dt
        while d <= to_dt:
            key = d.strftime("%Y-%m-%d")
            by_day.append({"date": key, "count": int(counts.get(key, 0))})
            d += timedelta(days=1)

        # --- Escala Y dinámica: si hay 0 en los datos, arranca en 0; si no, usa [min, max] con nice ---
        counts_only = [item["count"] for item in by_day]
        if counts_only:
            min_val = min(counts_only)
            max_val = max(counts_only)
        else:
            min_val = 0
            max_val = 0

        if min_val == 0:
            y_scale = {"zero": True, "nice": True}
        else:
            y_scale = {"domain": [min_val, max_val], "nice": True}

        payload = {
            "success": True,
            "metric": "Volumen de tickets cerrados",
            "from": from_date,
            "to": to_date,
            "total_closed": total_closed,
            "by_day": by_day,  # p.ej. [{"date":"2025-10-20","count":0}, {"date":"2025-10-21","count":104}, ...]
            "chartSpec": {
                "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
                "description": "Evolución diaria de tickets cerrados",
                "data": {"values": {"$ref": "by_day"}},
                "mark": {"type": "line", "point": True},
                "width": 500,
                "height": 300,
                "encoding": {
                    "x": {
                        "field": "date",
                        "type": "ordinal",     # categórico: una etiqueta por fecha, sin TZ
                        "sort": None,          # respeta el orden del array by_day (ASC)
                        "axis": {
                            "title": "Fecha",
                            "labelAngle": -30,
                            "labelOverlap": False
                        }
                    },
                    "y": {
                        "field": "count",
                        "type": "quantitative",
                        "axis": {"format": "d", "title": "Tickets cerrados"},
                        "scale": y_scale       # << escala dinámica
                    },
                    "tooltip": [
                        {"field": "date",  "type": "ordinal", "title": "Fecha"},
                        {"field": "count", "type": "quantitative", "title": "Cerrados"}
                    ]
                },
                "config": vega_config_brand()
            }
        }
        return payload

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@data_app.get("/analytics/subcategories")
def tickets_by_subcategory(
    from_date: str = Query(..., alias="from", description="YYYY-MM-DD"),
    to_date:   str = Query(..., alias="to",   description="YYYY-MM-DD"),
    top:       int | None = Query(None, description="Opcional: limitar a los N pares category/subcategory más frecuentes"),
    api_key:   str = Depends(verify_api_key)
):
    """
    Top de pares (categoría/subcategoría), SIEMPRE con chartSpec (Vega-Lite).
    """
    # Validación de fechas
    try:
        from_dt = datetime.fromisoformat(from_date).date()
        to_dt   = datetime.fromisoformat(to_date).date()
    except Exception:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido (use YYYY-MM-DD)")
    if from_dt > to_dt:
        raise HTTPException(status_code=400, detail="'from' no puede ser mayor que 'to'")

    try:
        conn = get_db_connection()
        with conn, conn.cursor() as cur:
            sql = """
                SELECT
                  COALESCE(NULLIF(TRIM(category), ''), 'Sin categoría')       AS category,
                  COALESCE(NULLIF(TRIM(subcategory), ''), 'Sin subcategoría') AS subcategory,
                  COUNT(*)::int AS count
                FROM resolved_tickets
                WHERE closed_at >= %s::date
                  AND closed_at <  (%s::date + INTERVAL '1 day')
                GROUP BY 1,2
                ORDER BY count DESC, category ASC, subcategory ASC
            """
            if top and isinstance(top, int) and top > 0:
                sql += " LIMIT %s"
                cur.execute(sql, (from_dt, to_dt, top))
            else:
                cur.execute(sql, (from_dt, to_dt))
            rows = cur.fetchall()

        items = [{"category": r[0], "subcategory": r[1], "count": r[2]} for r in rows]
        total = sum(it["count"] for it in items)

        # Altura dinámica según número de barras
        dyn_height = max(220, 26 * max(1, len(items)) + 60)

        payload = {
            "success": True,
            "metric": "top_subcategories",
            "from": from_date,
            "to": to_date,
            "params": {"top": top} if top else {},
            "top_subcategories": items,
            "total": total,
            "chartSpec": {
                "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
                "description": "Top de subcategorías (Categoría — Subcategoría)",
                "data": {"values": {"$ref": "top_subcategories"}},
                # Creamos una etiqueta combinada "Categoría — Subcategoría" para el eje Y
                "transform": [
                    {"calculate": "datum.category + ' — ' + datum.subcategory", "as": "label"}
                ],
                "mark": {"type": "bar"},
                "width": 680,
                "height": dyn_height,
                "encoding": {
                    "x": {
                        "field": "count",
                        "type": "quantitative",
                        "axis": {"title": "Tickets cerrados", "format": "d"},
                        "scale": {"nice": True}
                    },
                    "y": {
                        "field": "label",
                        "type": "nominal",
                        "sort": "-x",
                        "axis": {"title": "Categoría — Subcategoría", "labelLimit": 480}
                    },
                    "color": {
                        "field": "category",
                        "type": "nominal",
                        "legend": {"title": "Categoría"}
                    },
                    "tooltip": [
                        {"field": "category",    "type": "nominal", "title": "Categoría"},
                        {"field": "subcategory", "type": "nominal", "title": "Subcategoría"},
                        {"field": "count",       "type": "quantitative", "title": "Cerrados", "format": "d"}
                    ]
                },
                "config": vega_config_brand()
            }
        }
        return payload

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Promedio de horas hábiles por agente (L–V 07:00–17:00), rango inclusivo por día
@data_app.get("/analytics/resolution_time/by_agent_business")
def avg_resolution_time_by_agent_business(
    from_date: str = Query(..., alias="from", description="YYYY-MM-DD"),
    to_date:   str = Query(..., alias="to",   description="YYYY-MM-DD"),
    top:       Optional[int] = Query(None, description="Máximo de filas a devolver (orden asc por promedio). Si no se envía, devuelve todos."),
    api_key:   str = Depends(verify_api_key)
):
    try:
        from_dt = datetime.fromisoformat(from_date).date()
        to_dt   = datetime.fromisoformat(to_date).date()
    except Exception:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido (use YYYY-MM-DD)")
    if from_dt > to_dt:
        raise HTTPException(status_code=400, detail="'from' no puede ser mayor que 'to'")

    try:
        conn = get_db_connection()
        with conn, conn.cursor() as cur:
            base_sql = """
                WITH parametros AS (
                  SELECT time '07:00' AS hora_inicio_laboral, time '17:00' AS hora_fin_laboral
                ),
                base AS (
                  SELECT
                    COALESCE(NULLIF(TRIM(t.owner_name), ''), 'Sin asignar') AS owner_name,
                    t.hubspot_ticket_id,
                    t.created_at,
                    t.closed_at
                  FROM resolved_tickets t
                  WHERE t.closed_at >= %s::date
                    AND t.closed_at <  (%s::date + INTERVAL '1 day')
                ),
                dias AS (
                  SELECT
                    b.owner_name,
                    b.hubspot_ticket_id,
                    b.created_at,
                    b.closed_at,
                    gs::date AS d
                  FROM base b
                  JOIN LATERAL generate_series(
                    date_trunc('day', b.created_at),
                    date_trunc('day', b.closed_at),
                    interval '1 day'
                  ) gs ON TRUE
                ),
                ventanas AS (
                  SELECT
                    owner_name,
                    hubspot_ticket_id,
                    GREATEST(d + (SELECT hora_inicio_laboral FROM parametros), created_at) AS win_start,
                    LEAST   (d + (SELECT hora_fin_laboral   FROM parametros), closed_at)  AS win_end,
                    EXTRACT(DOW FROM d)::int AS dow
                  FROM dias
                ),
                filtrado AS (
                  SELECT
                    owner_name,
                    hubspot_ticket_id,
                    CASE
                      WHEN dow NOT IN (0,6) AND win_end > win_start
                        THEN EXTRACT(EPOCH FROM (win_end - win_start))::bigint
                      ELSE 0
                    END AS work_seconds
                  FROM ventanas
                ),
                tiempos_por_ticket AS (
                  SELECT
                    owner_name,
                    hubspot_ticket_id,
                    SUM(work_seconds)/3600.0 AS horas_laborales_resolucion
                  FROM filtrado
                  GROUP BY owner_name, hubspot_ticket_id
                ),
                por_agente AS (
                  SELECT
                    owner_name,
                    COUNT(*)::int AS total_tickets_cerrados,
                    ROUND(AVG(horas_laborales_resolucion)::numeric, 2) AS promedio_horas
                  FROM tiempos_por_ticket
                  GROUP BY owner_name
                )
                SELECT owner_name, total_tickets_cerrados, promedio_horas
                FROM por_agente
                ORDER BY promedio_horas ASC, total_tickets_cerrados DESC, owner_name ASC
            """
            params = [from_dt, to_dt]
            if top is not None:
                sql = base_sql + " LIMIT %s"
                params.append(top)
            else:
                sql = base_sql

            cur.execute(sql, tuple(params))
            rows = cur.fetchall()

            items = [{
                "agent": r[0],
                "total_closed": int(r[1]) if r[1] is not None else 0,
                "avg_hours_business": float(r[2]) if r[2] is not None else 0.0
            } for r in rows]

        payload = {
            "success": True,
            "metric": "Tiempo de resolución promedio por agente",
            "from": from_date,
            "to": to_date,
            "by_agent": items,
            "chartSpec": {
                "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
                "description": "Horas hábiles promedio por agente",
                "data": {"values": {"$ref": "by_agent"}},
                "mark": {"type": "bar"},
                "width": 640,
                "height": 360,
                "encoding": {
                    "y": {
                        "field": "agent",
                        "type": "ordinal",
                        "sort": None,  # respeta el orden del arreglo (ASC por promedio)
                        "axis": {"title": "Agente"}
                    },
                    "x": {
                        "field": "avg_hours_business",
                        "type": "quantitative",
                        "axis": {"title": "Horas hábiles (promedio)"},
                        "scale": {"nice": True}
                    },
                    "color": {
                        "field": "source",
                        "type": "nominal",
                        "legend": None
                    },
                    "tooltip": [
                        {"field": "agent", "type": "ordinal", "title": "Agente"},
                        {"field": "avg_hours_business", "type": "quantitative", "title": "Promedio (h)"},
                        {"field": "total_closed", "type": "quantitative", "title": "Tickets"}
                    ]
                },
                "config": vega_config_brand()
            }
        }
        return payload

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Promedio de horas hábiles global por ticket (rango) ---
from visual.vega_brand import vega_config_brand

@data_app.get("/analytics/resolution_time/avg_business")
def avg_resolution_time_business(
    from_date: str = Query(..., alias="from", description="YYYY-MM-DD"),
    to_date:   str = Query(..., alias="to",   description="YYYY-MM-DD"),
    api_key:   str = Depends(verify_api_key)
):
    """
    Calcula el tiempo de resolución promedio por ticket en horas hábiles
    (L–V, 07:00–17:00). Devuelve también un chartSpec tipo 'big number'
    aplicando la paleta/estilo de marca (celestes) desde vega_config_brand().
    """
    # --- Validación de fechas ---
    try:
        from_dt = datetime.fromisoformat(from_date).date()
        to_dt   = datetime.fromisoformat(to_date).date()
    except Exception:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido (use YYYY-MM-DD)")
    if from_dt > to_dt:
        raise HTTPException(status_code=400, detail="'from' no puede ser mayor que 'to'")

    try:
        conn = get_db_connection()
        with conn, conn.cursor() as cur:
            cur.execute("""
                WITH parametros AS (
                  SELECT time '07:00' AS hora_inicio_laboral, time '17:00' AS hora_fin_laboral
                ),
                base AS (
                  SELECT t.hubspot_ticket_id, t.created_at, t.closed_at
                  FROM resolved_tickets t
                  WHERE t.closed_at >= %s::date
                    AND t.closed_at <  (%s::date + INTERVAL '1 day')
                ),
                dias AS (
                  SELECT
                    b.hubspot_ticket_id,
                    b.created_at,
                    b.closed_at,
                    gs::date AS d
                  FROM base b
                  JOIN LATERAL generate_series(
                    date_trunc('day', b.created_at),
                    date_trunc('day', b.closed_at),
                    interval '1 day'
                  ) gs ON TRUE
                ),
                ventanas AS (
                  SELECT
                    hubspot_ticket_id,
                    GREATEST(d + (SELECT hora_inicio_laboral FROM parametros), created_at) AS win_start,
                    LEAST   (d + (SELECT hora_fin_laboral   FROM parametros), closed_at)  AS win_end,
                    EXTRACT(DOW FROM d)::int AS dow
                  FROM dias
                ),
                filtrado AS (
                  SELECT
                    hubspot_ticket_id,
                    CASE
                      WHEN dow NOT IN (0,6) AND win_end > win_start
                        THEN EXTRACT(EPOCH FROM (win_end - win_start))::bigint
                      ELSE 0
                    END AS work_seconds
                  FROM ventanas
                ),
                tiempos_por_ticket AS (
                  SELECT hubspot_ticket_id,
                         SUM(work_seconds)/3600.0 AS horas_laborales_resolucion
                  FROM filtrado
                  GROUP BY hubspot_ticket_id
                )
                SELECT
                  COUNT(*)::int AS total_tickets_cerrados,
                  ROUND(AVG(horas_laborales_resolucion)::numeric, 2) AS promedio_general_horas
                FROM tiempos_por_ticket;
            """, (from_dt, to_dt))

            row = cur.fetchone()
            total = int(row[0]) if row and row[0] is not None else 0
            avg   = float(row[1]) if row and row[1] is not None else 0.0

        # --- Merge de config de marca + overrides del big number ---
        brand_cfg = vega_config_brand()
        # Copias para no mutar el objeto original
        text_cfg = dict(brand_cfg.get("text", {}))
        view_cfg = dict(brand_cfg.get("view", {}))
        # Overrides específicos del big number
        text_cfg.update({
            "fontSize": 42,
            "align": "center",
            "baseline": "middle",
            # opcional: fija color del número (si no, usa el default de la marca)
            "color": text_cfg.get("color", "#00A9E0")
        })
        view_cfg.update({"stroke": "transparent"})
        merged_cfg = dict(brand_cfg)
        merged_cfg["text"] = text_cfg
        merged_cfg["view"] = view_cfg

        payload = {
            "success": True,
            "metric": "Tiempo de resolución promedio",
            "from": from_date,
            "to": to_date,
            "avg_hours_business": avg,
            "total_closed": total,
            "chartSpec": {
                "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
                "description": "Promedio de horas hábiles (big number)",
                "data": {
                    "values": [
                        {"label": "Promedio (h)", "hours": avg}
                    ]
                },
                "mark": {"type": "text"},
                "width": 200,
                "height": 100,
                "autosize": {"type": "none"},
                "encoding": {
                    "text": {
                        "field": "hours",
                        "type": "quantitative",
                        "format": ".2f"
                    }
                },
                "config": merged_cfg
            }
        }
        return payload

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@data_app.get("/analytics/resolution_time/by_source_business")
def avg_resolution_time_by_source_business(
    from_date: str = Query(..., alias="from", description="YYYY-MM-DD"),
    to_date:   str = Query(..., alias="to",   description="YYYY-MM-DD"),
    order:     str = Query("asc", description="asc = más rápidos primero; desc = más lentos primero"),
    api_key:   str = Depends(verify_api_key)
):
    """
    Promedio de tiempo de resolución por canal (source) contando solo horas hábiles
    (lun–vie, 07:00–17:00). Calculado ticket a ticket y luego promediado por canal.
    Devuelve chartSpec de barras horizontales.
    """
    try:
        from_dt = datetime.fromisoformat(from_date).date()
        to_dt   = datetime.fromisoformat(to_date).date()
    except Exception:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido (use YYYY-MM-DD)")
    if from_dt > to_dt:
        raise HTTPException(status_code=400, detail="'from' no puede ser mayor que 'to'")

    order_norm = (order or "asc").lower()
    if order_norm not in ("asc", "desc"):
        order_norm = "asc"
    order_sql = "ASC" if order_norm == "asc" else "DESC"

    try:
        conn = get_db_connection()
        with conn, conn.cursor() as cur:
            cur.execute(f"""
                WITH parametros AS (
                  SELECT time '07:00' AS hora_inicio_laboral, time '17:00' AS hora_fin_laboral
                ),
                base AS (
                  SELECT
                    COALESCE(NULLIF(TRIM(t.source), ''), 'Desconocido') AS source,
                    t.hubspot_ticket_id,
                    t.created_at,
                    t.closed_at
                  FROM resolved_tickets t
                  WHERE t.closed_at >= %s::date
                    AND t.closed_at <  (%s::date + INTERVAL '1 day')
                ),
                dias AS (
                  SELECT
                    b.source,
                    b.hubspot_ticket_id,
                    b.created_at,
                    b.closed_at,
                    gs::date AS d
                  FROM base b
                  JOIN LATERAL generate_series(
                    date_trunc('day', b.created_at),
                    date_trunc('day', b.closed_at),
                    interval '1 day'
                  ) gs ON TRUE
                ),
                ventanas AS (
                  SELECT
                    source,
                    hubspot_ticket_id,
                    GREATEST(d + (SELECT hora_inicio_laboral FROM parametros), created_at) AS win_start,
                    LEAST   (d + (SELECT hora_fin_laboral   FROM parametros), closed_at)  AS win_end,
                    EXTRACT(DOW FROM d)::int AS dow
                  FROM dias
                ),
                filtrado AS (
                  SELECT
                    source,
                    hubspot_ticket_id,
                    CASE
                      WHEN dow NOT IN (0,6) AND win_end > win_start
                        THEN EXTRACT(EPOCH FROM (win_end - win_start))::bigint
                      ELSE 0
                    END AS work_seconds
                  FROM ventanas
                ),
                tiempos_por_ticket AS (
                  SELECT
                    source,
                    hubspot_ticket_id,
                    SUM(work_seconds)/3600.0 AS horas_laborales_resolucion
                  FROM filtrado
                  GROUP BY source, hubspot_ticket_id
                ),
                por_source AS (
                  SELECT
                    source,
                    COUNT(*)::int AS total_tickets_cerrados,
                    ROUND(AVG(horas_laborales_resolucion)::numeric, 2) AS promedio_horas
                  FROM tiempos_por_ticket
                  GROUP BY source
                )
                SELECT source, total_tickets_cerrados, promedio_horas
                FROM por_source
                ORDER BY promedio_horas {order_sql}, total_tickets_cerrados DESC, source ASC;
            """, (from_dt, to_dt))

            rows = cur.fetchall()
            items = [{
                "source": r[0],
                "tickets": int(r[1]) if r[1] is not None else 0,
                "avg_hours_business": float(r[2]) if r[2] is not None else 0.0
            } for r in rows]

        # sort visual en Vega-Lite alineado con 'order'
        y_sort = "-x" if order_norm == "desc" else "x"
        dyn_height = max(200, 28 * max(1, len(items)) + 40)

        payload = {
            "success": True,
            "metric": "Tiempo de resolución promedio por canal",
            "from": from_date,
            "to": to_date,
            "by_source": items,
            "chartSpec": {
                "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
                "description": "Horas hábiles promedio por canal",
                "data": {"values": {"$ref": "by_source"}},
                "mark": {"type": "bar"},
                "width": 560,
                "height": dyn_height,
                "encoding": {
                    "y": {
                        "field": "source",
                        "type": "ordinal",
                        "sort": y_sort,  # ordena por el valor en X
                        "axis": {"title": "Canal"}
                    },
                    "x": {
                        "field": "avg_hours_business",
                        "type": "quantitative",
                        "axis": {"title": "Horas hábiles (promedio)"},
                        "scale": {"nice": True}
                    },
                    "color": {
                        "field": "source",
                        "type": "nominal",
                        "legend": None
                    },
                    "tooltip": [
                        {"field": "source", "type": "ordinal", "title": "Canal"},
                        {"field": "avg_hours_business", "type": "quantitative", "title": "Promedio (h)"},
                        {"field": "tickets", "type": "quantitative", "title": "Tickets"}
                    ]
                },
                "config": vega_config_brand()
            }
        }
        return payload

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@data_app.get("/analytics/resolution_time/slow_cases_business")
def slow_cases_business(
    from_date: str = Query(..., alias="from", description="YYYY-MM-DD"),
    to_date:   str = Query(..., alias="to",   description="YYYY-MM-DD"),
    top:       int = Query(10, description="Máximo de tickets a devolver"),
    api_key:   str = Depends(verify_api_key)
):
    """
    Casos más lentos por tiempo de resolución en horas hábiles (L–V, 07:00–17:00).
    Siempre devuelve chartSpec (Vega-Lite) con {"$ref":"cases"}.
    """
    try:
        from_dt = datetime.fromisoformat(from_date).date()
        to_dt   = datetime.fromisoformat(to_date).date()
    except Exception:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido (use YYYY-MM-DD)")
    if from_dt > to_dt:
        raise HTTPException(status_code=400, detail="'from' no puede ser mayor que 'to'")

    try:
        conn = get_db_connection()
        with conn, conn.cursor() as cur:
            cur.execute("""
                WITH parametros AS (
                  SELECT time '07:00' AS hora_inicio_laboral, time '17:00' AS hora_fin_laboral
                ),
                base AS (
                  SELECT
                    t.hubspot_ticket_id,
                    t.subject,
                    COALESCE(NULLIF(TRIM(t.owner_name), ''), 'Sin asignar') AS owner_name,
                    COALESCE(NULLIF(TRIM(t.source), ''), 'Desconocido')    AS source,
                    t.created_at,
                    t.closed_at
                  FROM resolved_tickets t
                  WHERE t.closed_at >= %s::date
                    AND t.closed_at <  (%s::date + INTERVAL '1 day')
                ),
                dias AS (
                  SELECT
                    b.hubspot_ticket_id, b.subject, b.owner_name, b.source, b.created_at, b.closed_at,
                    gs::date AS d
                  FROM base b
                  JOIN LATERAL generate_series(
                    date_trunc('day', b.created_at),
                    date_trunc('day', b.closed_at),
                    interval '1 day'
                  ) gs ON TRUE
                ),
                ventanas AS (
                  SELECT
                    hubspot_ticket_id, subject, owner_name, source, created_at, closed_at,
                    GREATEST(d + (SELECT hora_inicio_laboral FROM parametros), created_at) AS win_start,
                    LEAST   (d + (SELECT hora_fin_laboral   FROM parametros), closed_at)  AS win_end,
                    EXTRACT(DOW FROM d)::int AS dow
                  FROM dias
                ),
                filtrado AS (
                  SELECT
                    hubspot_ticket_id, subject, owner_name, source, created_at, closed_at,
                    CASE WHEN dow NOT IN (0,6) AND win_end > win_start
                          THEN EXTRACT(EPOCH FROM (win_end - win_start))::bigint
                         ELSE 0 END AS work_seconds
                  FROM ventanas
                ),
                tiempos_por_ticket AS (
                  SELECT
                    hubspot_ticket_id, subject, owner_name, source, created_at, closed_at,
                    SUM(work_seconds)/3600.0 AS horas_laborales_resolucion
                  FROM filtrado
                  GROUP BY hubspot_ticket_id, subject, owner_name, source, created_at, closed_at
                )
                SELECT
                  hubspot_ticket_id, subject, owner_name, source, created_at, closed_at,
                  ROUND(horas_laborales_resolucion::numeric, 2) AS horas_laborales_resolucion
                FROM tiempos_por_ticket
                ORDER BY horas_laborales_resolucion DESC, closed_at DESC
                LIMIT %s;
            """, (from_dt, to_dt, top))
            rows = cur.fetchall()

        items = [{
            "hubspot_ticket_id": r[0],
            "subject": r[1],
            "owner_name": r[2],
            "source": r[3],
            "created_at": r[4].isoformat() if r[4] else None,
            "closed_at":  r[5].isoformat() if r[5] else None,
            "hours_business_resolution": float(r[6]) if r[6] is not None else 0.0
        } for r in rows]

        # Altura dinámica (~26px por barra)
        dyn_height = max(220, 26 * max(1, len(items)) + 60)

        payload = {
            "success": True,
            "metric": "Casos más lentos",
            "from": from_date,
            "to": to_date,
            "top": top,
            "cases": items,
            "chartSpec": {
                "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
                "description": "Casos más lentos (horas hábiles)",
                "data": {"values": {"$ref": "cases"}},
                "transform": [
                    {
                        "calculate": "datum.hubspot_ticket_id + ' — ' + (isValid(datum.subject) && length(datum.subject) > 0 ? datum.subject : 'Sin asunto')",
                        "as": "label"
                    }
                ],
                "mark": {"type": "bar"},
                "width": 760,
                "height": dyn_height,
                "encoding": {
                    "x": {
                        "field": "hours_business_resolution",
                        "type": "quantitative",
                        "axis": {"title": "Horas hábiles de resolución"},
                        "scale": {"nice": True}
                    },
                    "y": {
                        "field": "label",
                        "type": "nominal",
                        "sort": "-x",
                        "axis": {"title": "Ticket — Asunto", "labelLimit": 560}
                    },
                    "color": {
                        "field": "source",
                        "type": "nominal",
                        "legend": {"title": "Canal"}
                    },
                    "tooltip": [
                        {"field": "hubspot_ticket_id", "type": "nominal", "title": "Ticket"},
                        {"field": "subject",              "type": "nominal", "title": "Asunto"},
                        {"field": "owner_name",           "type": "nominal", "title": "Agente"},
                        {"field": "source",               "type": "nominal", "title": "Canal"},
                        {"field": "hours_business_resolution", "type": "quantitative", "title": "Horas hábiles"}
                    ]
                },
                "config": vega_config_brand()
            }
        }
        return payload

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
