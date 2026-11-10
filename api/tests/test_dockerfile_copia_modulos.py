"""El Dockerfile de la api copia los módulos uno a uno: uno nuevo que no se añada ahí arranca en local
y falla en el contenedor con ModuleNotFoundError (#919: decisiones.py y vigentes.py)."""
from pathlib import Path

API = Path(__file__).resolve().parent.parent
FUERA_DE_LA_IMAGEN = {"migrate_3_0c_entity_links.py"}  # script de una vez, no lo importa nadie


def test_cada_modulo_de_la_api_esta_en_el_dockerfile():
    dockerfile = (API / "Dockerfile").read_text(encoding="utf-8")
    faltan = [p.name for p in sorted(API.glob("*.py"))
              if p.name not in FUERA_DE_LA_IMAGEN and f"api/{p.name}" not in dockerfile]
    assert faltan == []
