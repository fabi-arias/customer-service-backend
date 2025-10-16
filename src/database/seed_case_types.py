# src/database/seed_case_types.py
import csv
import sys
from pathlib import Path

# imports del proyecto
src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))

from database.db_utils import get_db_connection

def to_keywords_list(s: str):
    """Convierte string separado por | en lista de keywords."""
    if not s: 
        return []
    return [p.strip() for p in s.split("|") if p.strip()]

def seed_case_types():
    """Carga los datos del CSV a la tabla case_types."""
    try:
        conn = get_db_connection()
        
        csv_path = Path(__file__).parent.parent.parent / "seed" / "case_types.csv"
        
        if not csv_path.exists():
            print(f"❌ Archivo CSV no encontrado: {csv_path}")
            return False
            
        with conn, conn.cursor() as cur, open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            inserted_count = 0
            
            for row in reader:
                case_key    = (row["case_key"] or "").strip()
                title       = (row["title"] or "").strip()
                description = (row.get("description") or "").strip()
                category    = (row["category"] or "").strip()
                subcategory = (row["subcategory"] or "").strip().replace("ó","o").replace("Ó","O")
                keywords    = to_keywords_list(row.get("keywords") or "")

                cur.execute("""
                    INSERT INTO case_types (case_key, title, description, category, subcategory, keywords)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (case_key) DO UPDATE SET
                      title=EXCLUDED.title,
                      description=EXCLUDED.description,
                      category=EXCLUDED.category,
                      subcategory=EXCLUDED.subcategory,
                      keywords=EXCLUDED.keywords
                """, (case_key, title, description, category, subcategory, keywords))
                
                inserted_count += cur.rowcount
                
        print(f"✅ case_types upsert OK - {inserted_count} registros procesados")
        return True
        
    except Exception as e:
        print(f"❌ Error al cargar case_types: {e}")
        return False

if __name__ == "__main__":
    seed_case_types()
