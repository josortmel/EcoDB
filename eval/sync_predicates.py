import asyncio, asyncpg, os

PREDICATES = [
    # Cluster A — Arquitectura e Infraestructura Tecnica (11)
    ("parte_de", "A", "X es componente de Y"),
    ("contiene", "A", "X contiene Y"),
    ("instancia_de", "A", "X es instancia concreta de Y"),
    ("tipo_de", "A", "X es tipo/categoria de Y"),
    ("depende_de", "A", "X requiere Y para funcionar"),
    ("usa", "A", "X utiliza Y"),
    ("consume", "A", "X consume datos/servicios de Y"),
    ("habilita", "A", "X hace posible Y"),
    ("reemplaza", "A", "X sustituye a Y"),
    ("es_alternativa_a", "A", "X y Y cumplen funcion similar"),
    ("soporta", "A", "X da soporte/ejecuta Y"),
    # Cluster B — Ubicacion y Despliegue (4)
    ("ubicado_en", "B", "X esta en ubicacion Y"),
    ("vive_en", "B", "X reside en Y"),
    ("sede_de", "B", "X es sede de Y"),
    ("deployed_en", "B", "X esta desplegado en Y"),
    # Cluster C — Creacion, Autoria y Derivacion (12)
    ("crea", "C", "X crea/produce Y (autoria)"),
    ("construye", "C", "X implementa tecnicamente Y"),
    ("escribe", "C", "X escribe/redacta Y (literario/documental)"),
    ("disena", "C", "X disenha Y"),
    ("prototipa", "C", "X prototipa Y antes de construir"),
    ("despliega", "C", "X despliega Y a produccion (acto)"),
    ("fue_creado_por", "C", "Y fue creado por X (inverso de crea)"),
    ("produce", "C", "X produce Y como output"),
    ("derivado_de", "C", "X se deriva de Y (cadena input)"),
    ("itera_de", "C", "X es iteracion de Y (coexisten)"),
    ("version_de", "C", "X es version de Y"),
    ("basado_en", "C", "X esta basado en Y"),
    # Cluster D — Gobernanza, Roles y Calidad (11)
    ("miembro_de", "D", "X es miembro de Y (con agencia)"),
    ("orquesta", "D", "X coordina/dirige Y"),
    ("gobierna", "D", "X tiene autoridad sobre Y"),
    ("lidera", "D", "X lidera Y"),
    ("supervisa", "D", "X supervisa el trabajo de Y"),
    ("custodia", "D", "X protege/mantiene Y"),
    ("protege", "D", "X protege a Y"),
    ("aprueba", "D", "X aprueba Y (gate decision)"),
    ("rechaza", "D", "X rechaza Y (gate decision)"),
    ("valida", "D", "X valida/verifica Y (QA + medicion)"),
    ("asignado_a", "D", "X esta asignado a Y"),
    # Cluster E — Metodologia y Proceso (6)
    ("aplica", "E", "X aplica metodologia Y"),
    ("investiga", "E", "X investiga tema Y"),
    ("ejecuta_en", "E", "X se ejecuta en entorno Y"),
    ("documenta", "E", "X documenta Y"),
    ("evalua", "E", "X evalua/mide Y (medicion numerica)"),
    ("cuestiona", "E", "X revisa adversarialmente Y"),
    # Cluster F — Temporal/Causal (6)
    ("origen_de", "F", "X es el origen de Y"),
    ("evoluciona_a", "F", "X se transforma en Y"),
    ("desencadeno", "F", "X desencadeno evento Y"),
    ("precede", "F", "X precede temporalmente a Y"),
    ("nombre_dado_por", "F", "X recibio nombre de Y"),
    ("resulta_en", "F", "X resulta en Y"),
    # Cluster G — Ciclo de Vida (3)
    ("depreca", "G", "X depreca Y (fin de vida sin reemplazo)"),
    ("optimiza", "G", "X optimiza metrica/sistema Y"),
    ("bloquea", "G", "X bloquea/impide Y"),
    # Cluster H — Seguridad y Regulacion (4)
    ("mitiga", "H", "X mitiga riesgo Y"),
    ("regula", "H", "X tiene autoridad regulatoria sobre Y"),
    ("cumple", "H", "X cumple con normativa Y"),
    ("rol_de", "H", "X tiene rol Y en contexto Z"),
    # Cluster I — Comunicacion y Publicacion (7)
    ("publica_en", "I", "X publica contenido en Y"),
    ("tiene_perfil_en", "I", "X tiene perfil en Y"),
    ("expone_tool", "I", "X expone herramienta Y"),
    ("tiene_tool", "I", "X tiene acceso a Y"),
    ("participa_en", "I", "X participa en Y"),
    ("cita", "I", "X cita/referencia a Y"),
    ("configura", "I", "X configura/parametriza Y"),
    # Cluster J — Relaciones Personales (8)
    ("familiar_de", "J", "X tiene vinculo familiar con Y"),
    ("pareja_de", "J", "X es pareja de Y"),
    ("padre_de", "J", "X es padre/madre de Y"),
    ("hermano_de", "J", "X es hermano/a de Y"),
    ("mentor_de", "J", "X mentoriza a Y"),
    ("aliado_de", "J", "X y Y son aliados"),
    ("enemigo_de", "J", "X y Y son adversarios"),
    ("persona_de", "J", "X es humano companion de AI Y"),
    # Cluster K — Afectivo/Identidad (7)
    ("ama", "K", "X ama/quiere a Y"),
    ("confia_en", "K", "X confia en Y"),
    ("inspira", "K", "X inspira a Y"),
    ("desea", "K", "X desea Y (agencia)"),
    ("ancla_de", "K", "X ancla identidad de Y (Lazaro)"),
    ("simboliza", "K", "X simboliza Y"),
    ("emergio_de", "K", "X emergio de Y (origen identitario)"),
    # Cluster L — Worldbuilding (12)
    ("porta", "L", "X porta artefacto Y"),
    ("marcado_por", "L", "X esta marcado por evento Y"),
    ("antagonista_de", "L", "X es antagonista de Y"),
    ("controla", "L", "X controla territorio/recurso Y"),
    ("defiende", "L", "X defiende Y"),
    ("nacio_en", "L", "X nacio en lugar Y"),
    ("viaja_a", "L", "X viaja a Y"),
    ("espejo_de", "L", "X es espejo narrativo de Y"),
    ("manipula", "L", "X manipula a Y"),
    ("inspirado_en", "L", "X inspirado en referencia Y"),
    ("comercia_con", "L", "X comercia con Y"),
    ("frontera_de", "L", "X es frontera de Y"),
]

APPROVED_NAMES = [p[0] for p in PREDICATES]

async def sync():
    pool = await asyncpg.create_pool(os.environ['DATABASE_URL'])
    async with pool.acquire() as conn:
        before_total = await conn.fetchval('SELECT COUNT(*) FROM predicates_canonical')
        before_approved = await conn.fetchval("SELECT COUNT(*) FROM predicates_canonical WHERE state='approved'")
        before_deprecated = await conn.fetchval("SELECT COUNT(*) FROM predicates_canonical WHERE state='deprecated'")
        print(f'BEFORE: total={before_total}, approved={before_approved}, deprecated={before_deprecated}')

        inserted = 0
        updated = 0
        async with conn.transaction():
            for name, cluster, desc in PREDICATES:
                existing = await conn.fetchrow(
                    'SELECT name FROM predicates_canonical WHERE name=$1', name
                )
                if existing is None:
                    await conn.execute(
                        "INSERT INTO predicates_canonical (name, state, cluster, ontology_layer, description) VALUES ($1,'approved',$2,'domain',$3)",
                        name, cluster, desc
                    )
                    inserted += 1
                else:
                    await conn.execute(
                        "UPDATE predicates_canonical SET state='approved', cluster=$2, description=$3 WHERE name=$1",
                        name, cluster, desc
                    )
                    updated += 1

            # Deprecate all others
            dep_result = await conn.execute(
                "UPDATE predicates_canonical SET state='deprecated' WHERE name != ALL($1::text[]) AND state != 'deprecated'",
                APPROVED_NAMES
            )
            deprecated = int(dep_result.split()[-1])

        after_total = await conn.fetchval('SELECT COUNT(*) FROM predicates_canonical')
        after_approved = await conn.fetchval("SELECT COUNT(*) FROM predicates_canonical WHERE state='approved'")
        after_deprecated = await conn.fetchval("SELECT COUNT(*) FROM predicates_canonical WHERE state='deprecated'")
        print(f'Inserted (new): {inserted}')
        print(f'Updated (already existed): {updated}')
        print(f'Deprecated: {deprecated}')
        print(f'AFTER: total={after_total}, approved={after_approved}, deprecated={after_deprecated}')
    await pool.close()

asyncio.run(sync())
