# src/database/data_management_api.py
from fastapi import FastAPI, HTTPException, Depends, Header, Query
from fastapi.responses import StreamingResponse
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional

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

from fastapi import APIRouter, Depends, HTTPException
from typing import List
import json

data_app = APIRouter()

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
    to_date: str = Query(..., alias="to", description="YYYY-MM-DD"),
    top: int = Query(10, description="Número de categorías a retornar"),
    api_key: str = Depends(verify_api_key)
):
    """
    Devuelve las categorías más frecuentes de tickets resueltos en un rango de fechas.
    """
    # Parsear como fechas (no datetimes)
    try:
        from_dt = datetime.fromisoformat(from_date).date()
        to_dt = datetime.fromisoformat(to_date).date()
    except Exception:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido (use YYYY-MM-DD)")

    # Validación simple: from <= to
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

        return {
            "success": True,
            "from": from_date,
            "to": to_date,
            "top_categories": [{"category": r[0], "count": r[1]} for r in rows]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@data_app.get("/analytics/sources")
def tickets_by_source(
    from_date: str = Query(..., alias="from", description="YYYY-MM-DD"),
    to_date: str = Query(..., alias="to", description="YYYY-MM-DD"),
    api_key: str = Depends(verify_api_key)
):
    """Análisis de tickets por fuente."""
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
        items = [{"source": r[0], "count": r[1], "pct": round(r[1]*100/total,1)} for r in rows]

        return {"success": True, "from": from_date, "to": to_date, "by_source": items}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@data_app.get("/analytics/top_agents")
def top_agents(
    from_date: str = Query(..., alias="from", description="YYYY-MM-DD"),
    to_date: str = Query(..., alias="to", description="YYYY-MM-DD"),
    top: int = Query(10, description="Número de agentes a retornar"),
    api_key: str = Depends(verify_api_key)
):
    """
    Devuelve el ranking de agentes con más tickets cerrados en el rango.
    """
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
            # Asumiendo que tienes un campo 'agent' o 'assigned_to' en tu tabla
            # Si no existe, necesitarás agregarlo o usar otro campo
            cur.execute("""
                SELECT
                    COALESCE(NULLIF(TRIM(resolution), ''), 'Sin agente') AS agent,
                    COUNT(*)::int AS count
                FROM resolved_tickets
                WHERE closed_at >= %s::date
                  AND closed_at < (%s::date + INTERVAL '1 day')
                  AND resolution IS NOT NULL
                GROUP BY 1
                ORDER BY count DESC
                LIMIT %s
            """, (from_dt, to_dt, top))
            rows = cur.fetchall()

        return {
            "success": True,
            "from": from_date,
            "to": to_date,
            "agents": [{"agent": r[0], "count": r[1]} for r in rows]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@data_app.get("/analytics/closed_volume")
def closed_volume(
    from_date: str = Query(..., alias="from", description="YYYY-MM-DD"),
    to_date: str = Query(..., alias="to", description="YYYY-MM-DD"),
    api_key: str = Depends(verify_api_key)
):
    """
    Devuelve el total de tickets cerrados en el rango y opcionalmente
    el desglose diario para análisis de picos/tendencia.
    """
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

            # Desglose por día
            cur.execute("""
                SELECT 
                    DATE(closed_at) AS date,
                    COUNT(*)::int AS count
                FROM resolved_tickets
                WHERE closed_at >= %s::date
                  AND closed_at < (%s::date + INTERVAL '1 day')
                GROUP BY DATE(closed_at)
                ORDER BY date DESC
            """, (from_dt, to_dt))
            by_day_rows = cur.fetchall()

        return {
            "success": True,
            "from": from_date,
            "to": to_date,
            "total_closed": total_closed,
            "by_day": [{"date": str(r[0]), "count": r[1]} for r in by_day_rows]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
