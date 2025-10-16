# src/database/ingest_api.py
from flask import Flask, request, jsonify, Response
import json, os
import sys
from pathlib import Path
from datetime import datetime, timedelta

# imports del proyecto
src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))
from database.db_utils import get_db_connection

app = Flask(__name__)

API_KEY = os.getenv("INGEST_API_KEY", "cambia-esto")  # opcional

def auth_ok(req):
    """Verifica si la autenticación es válida."""
    key = req.headers.get("X-API-Key")
    return (not API_KEY) or key == API_KEY or API_KEY == "cambia-esto"

@app.get("/health")
def health():
    """Endpoint de salud de la API."""
    return {"status": "ok", "service": "ingest-api"}, 200

@app.get("/stats")
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
            
            return jsonify({
                "success": True,
                "total_tickets": total_tickets,
                "categories": [{"category": cat[0], "count": cat[1]} for cat in categories]
            }), 200
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.post("/ingest/resolved-tickets/batch")
def ingest_batch():
    """Endpoint para ingestar tickets resueltos en batch."""
    # Verificar autenticación
    if not auth_ok(request):
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    # Validar JSON
    body = request.get_json(silent=True)
    if body is None:
        return jsonify({"success": False, "error": "Body JSON inválido"}), 400

    # Aceptar array directo o {tickets: [...]}
    tickets = body if isinstance(body, list) else body.get("tickets", [])
    if not isinstance(tickets, list):
        return jsonify({"success": False, "error": "Payload debe ser lista o {tickets: []}"}), 400

    if not tickets:
        return jsonify({"success": False, "error": "Lista de tickets vacía"}), 400

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
                          hubspot_ticket_id, subject, content, created_at, closed_at,
                          itinerary_number, source, category, subcategory,
                          resolution, case_key, raw_hubspot
                        )
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
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
            
        return jsonify(response), 200
        
    except Exception as e:
        return jsonify({"success": False, "error": f"Error de conexión: {str(e)}"}), 500




@app.get("/export/resolved-tickets")
def export_resolved_tickets():
    """
    Exporta tickets resueltos en formato NDJSON (una línea por documento).
    Filtros:
      - since (ISO8601 o 'YYYY-MM-DD')
      - limit (int, por defecto 5000)
    """
    if not auth_ok(request):
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    since_s = request.args.get("since")
    limit = int(request.args.get("limit", 5000))

    # default: últimos 30 días
    if since_s:
        try:
            since = datetime.fromisoformat(since_s.replace("Z",""))
        except Exception:
            return jsonify({"success": False, "error": "since inválido"}), 400
    else:
        since = datetime.utcnow() - timedelta(days=30)

    def row_to_doc(row):
        (hubspot_ticket_id, subject, content, created_at, closed_at,
         itinerary_number, source, category, subcategory, resolution, case_key) = row

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
                "case_key": case_key
            }
        }
        return doc

    def generate_ndjson():
        try:
            conn = get_db_connection()
            with conn, conn.cursor() as cur:
                cur.execute("""
                    SELECT hubspot_ticket_id, subject, content, created_at, closed_at,
                           itinerary_number, source, category, subcategory, resolution, case_key
                    FROM resolved_tickets
                    WHERE closed_at >= %s
                    ORDER BY closed_at DESC
                    LIMIT %s
                """, (since, limit))
                for r in cur.fetchall():
                    yield json.dumps(row_to_doc(r), ensure_ascii=False) + "\n"
        except Exception as e:
            # Devuelve un documento de error y corta
            yield json.dumps({"error": str(e)}) + "\n"

    return Response(generate_ndjson(), mimetype="application/x-ndjson")



@app.get("/analyze/top-categories")
def top_categories():
    """
    Devuelve las categorías más frecuentes de tickets resueltos en un rango de fechas.
    Parámetros:
      - from (YYYY-MM-DD)  obligatorio
      - to   (YYYY-MM-DD)  obligatorio
      - top  (int, default=10)

    Nota: usa rango con fin EXCLUSIVO: [from, to + 1 día)
    """
    if not auth_ok(request):
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    from_s = request.args.get("from")
    to_s   = request.args.get("to")
    top_n  = int(request.args.get("top", 10))

    if not from_s or not to_s:
        return jsonify({"success": False, "error": "Parámetros 'from' y 'to' son obligatorios"}), 400

    # Parsear como fechas (no datetimes)
    try:
        from_date = datetime.fromisoformat(from_s).date()
        to_date   = datetime.fromisoformat(to_s).date()
    except Exception:
        return jsonify({"success": False, "error": "Formato de fecha inválido (use YYYY-MM-DD)"}), 400

    # Validación simple: from <= to
    if from_date > to_date:
        return jsonify({"success": False, "error": "'from' no puede ser mayor que 'to'"}), 400

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
            """, (from_date, to_date, top_n))
            rows = cur.fetchall()

        return jsonify({
            "success": True,
            "from": from_s,  # devolvemos lo solicitado, sin “ajustes”
            "to": to_s,
            "top_categories": [{"category": r[0], "count": r[1]} for r in rows]
        }), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.get("/analyze/by-source")
def tickets_by_source():
    if not auth_ok(request):
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    from_s = request.args.get("from")
    to_s   = request.args.get("to")

    if not from_s or not to_s:
        return jsonify({"success": False, "error": "Parámetros 'from' y 'to' son obligatorios"}), 400

    try:
        from_date = datetime.fromisoformat(from_s).date()
        to_date   = datetime.fromisoformat(to_s).date()
    except Exception:
        return jsonify({"success": False, "error": "Formato de fecha inválido (use YYYY-MM-DD)"}), 400

    if from_date > to_date:
        return jsonify({"success": False, "error": "'from' no puede ser mayor que 'to'"}), 400

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
            """, (from_date, to_date))
            rows = cur.fetchall()

        total = sum(r[1] for r in rows) or 1
        items = [{"source": r[0], "count": r[1], "pct": round(r[1]*100/total,1)} for r in rows]

        return jsonify({"success": True, "from": from_s, "to": to_s, "by_source": items}), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
