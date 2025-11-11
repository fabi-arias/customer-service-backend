# src/database/db_utils.py
"""
Módulo de utilidades para la base de datos.
Contiene funciones comunes para operaciones de base de datos.
"""
import psycopg2
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from contextlib import closing

# imports del proyecto
src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))

from config.settings import postgres_config

def get_db_connection():
    """
    Obtiene una conexión a la base de datos PostgreSQL.
    
    Returns:
        psycopg2.connection: Conexión a la base de datos
    """
    return psycopg2.connect(
        host=postgres_config.host,
        port=postgres_config.port,
        dbname=postgres_config.name,
        user=postgres_config.user,
        password=postgres_config.password,
    )

def execute_query(query: str, params: Optional[tuple] = None) -> Dict[str, Any]:
    """
    Ejecuta una consulta SQL y retorna el resultado.
    Detecta result sets usando cur.description (DB-API 2.0), no por el texto de la query.
    """
    try:
        with closing(get_db_connection()) as conn:
            with conn, conn.cursor() as cur:
                cur.execute(query, params)

                # ¿La consulta devolvió columnas? Entonces hay result set.
                if cur.description:
                    columns = [desc[0] for desc in cur.description]
                    rows = cur.fetchall()
                    return {
                        "success": True,
                        "columns": columns,
                        "rows": rows,
                        "count": len(rows),
                    }
                else:
                    # Para INSERT, UPDATE, DELETE u operaciones sin result set
                    return {
                        "success": True,
                        "affected_rows": cur.rowcount,
                    }

    except Exception as e:
        # Nota: esta función es de utilería. Evita exponer 'error' directamente en HTTP.
        # La capa API debe registrar el stacktrace y responder con mensaje neutro.
        return {
            "success": False,
            "error": str(e),
        }


def test_connection() -> bool:
    """
    Prueba la conexión a la base de datos.
    
    Returns:
        bool: True si la conexión es exitosa, False en caso contrario
    """
    try:
        with closing(get_db_connection()) as conn:
            with conn, conn.cursor() as cur:
                cur.execute("SELECT 1")
                result = cur.fetchone()
                return result[0] == 1
    except Exception as e:
        print(f"❌ Error de conexión a la base de datos: {e}")
        return False
