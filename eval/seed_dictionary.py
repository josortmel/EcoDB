import asyncio, asyncpg, os

NUEVAS = [
    # PERSONA
    ('Fabio','persona'),('Salazar','persona'),('Carol','persona'),
    ('Alice Johnson','persona'),('Bob Smith','persona'),
    ('Celine/Elyahna3','persona'),('Wild_Giraffe5542','persona'),
    ('Alfonso Ganan','persona'),('Jordana B','persona'),
    ('El ultimo Emperador','persona'),('V','persona'),('Spar','persona'),
    ('Mack','persona'),('Cael','persona'),('Lassi','persona'),
    ('Crow','persona'),('Storm','persona'),('Claudiest Claude','persona'),
    ('Kael Belgium','persona'),('Rowan','persona'),('Ember','persona'),
    ('Vera','persona'),('Nara','persona'),('Larry','persona'),
    # PERSONA
    ('Bob Weygant','persona'),('Jordan Urbs','persona'),('josemmo','persona'),
    ('Domovoi','persona'),('Flint','persona'),('Fredericus','persona'),
    # AGENTE_IA
    ('Adversarial de Auditoria','agente_ia'),('Pionero','agente_ia'),
    ('Custodio','agente_ia'),('Pragmatico','agente_ia'),('Coord','agente_ia'),
    # ORGANIZACION
    ('Google','organizacion'),('Cloudflare','organizacion'),
    # ORGANIZACION
    ('OpenClaw','organizacion'),('HeR-Lab','organizacion'),
    ('La Cofradia de Navegantes de Luvain','organizacion'),
    # ORGANIZACION
    ('Jina AI','organizacion'),('Vercel','organizacion'),
    ('Nous Research','organizacion'),('EPAM','organizacion'),
    ('Coqui','organizacion'),('AEAT','organizacion'),('AEPD','organizacion'),
    ('Red.es','organizacion'),('Eurostat','organizacion'),
    ('Banco de Espana','organizacion'),('Chamber of Commerce','organizacion'),
    ('Binovo','organizacion'),('Irene Solutions SL','organizacion'),
    ('Apify','organizacion'),('Figma','organizacion'),('Linear','organizacion'),
    ('Notion','organizacion'),('Stripe','organizacion'),
    ('Browserbase','organizacion'),('Scrapfly','organizacion'),
    ('arXiv','organizacion'),
    # LUGAR
    ('La Buhaira','lugar'),('Santa Justa','lugar'),('La Juderia','lugar'),
    ('Lisboa','lugar'),('Berlin','lugar'),('Calpe','lugar'),('Abyla','lugar'),
    ('Las Costas Malditas','lugar'),('La Costa del Agravio','lugar'),
    ('La Garganta','lugar'),('Alsimar','lugar'),
    # LUGAR
    ('Andalucia','lugar'),('Cuba','lugar'),
    # TECNOLOGIA
    ('pgvector','tecnologia'),('HNSW','tecnologia'),('Whisper','tecnologia'),
    ('React','tecnologia'),('Vite','tecnologia'),('Tailwind CSS','tecnologia'),
    ('pg_trgm','tecnologia'),('JWT','tecnologia'),('SSE','tecnologia'),
    ('GGUF','tecnologia'),('Cypher','tecnologia'),('PyTorch','tecnologia'),
    ('HuggingFace','tecnologia'),('Tailscale','tecnologia'),
    ('Cloudflare Pages','tecnologia'),('asyncpg','tecnologia'),
    ('httpx','tecnologia'),('pydantic','tecnologia'),('uvicorn','tecnologia'),
    ('Zustand','tecnologia'),('TanStack','tecnologia'),('D3','tecnologia'),
    ('Q4_K_M','tecnologia'),('ONNX Runtime','tecnologia'),
    ('transformers','tecnologia'),('NFKD','tecnologia'),('bcrypt','tecnologia'),
    ('EMA temporal','tecnologia'),('Starlette','tecnologia'),
    ('FastMCP','tecnologia'),('bitsandbytes','tecnologia'),
    ('accelerate','tecnologia'),('peft','tecnologia'),('Gitmoji','tecnologia'),
    ('GIN index','tecnologia'),('Louvain','tecnologia'),('Wrangler','tecnologia'),
    ('electron-builder','tecnologia'),('Unity','tecnologia'),
    # TECNOLOGIA
    ('FLUX','tecnologia'),('Gradio','tecnologia'),('OpenCV','tecnologia'),
    ('YOLOv8','tecnologia'),
    # TECNOLOGIA
    ('llama.cpp','tecnologia'),('MCP','tecnologia'),('Electron','tecnologia'),
    ('Matryoshka','tecnologia'),('SafeTensors','tecnologia'),
    ('tiktoken','tecnologia'),('Laplacian','tecnologia'),
    ('optical flow','tecnologia'),('CLAHE','tecnologia'),('DIS','tecnologia'),
    ('Farneback','tecnologia'),('MediaPipe','tecnologia'),
    ('onion skin','tecnologia'),('Stagehand','tecnologia'),
    ('Browser Use','tecnologia'),('Firecrawl','tecnologia'),
    ('Handlebars','tecnologia'),('Next.js','tecnologia'),('GSAP','tecnologia'),
    ('Chromium','tecnologia'),('SQLite','tecnologia'),('Zod','tecnologia'),
    ('tmux','tecnologia'),('WASM','tecnologia'),('Rust','tecnologia'),
    ('Parquet','tecnologia'),('Flash Attention','tecnologia'),
    ('FTS5','tecnologia'),('XAdES','tecnologia'),('SHA-256','tecnologia'),
    ('RPA','tecnologia'),('SPLADE','tecnologia'),('TEI','tecnologia'),
    ('Cactus','tecnologia'),('selenium','tecnologia'),
    ('BeautifulSoup','tecnologia'),('scrapy','tecnologia'),
    ('DuckDB','tecnologia'),('FAISS','tecnologia'),
    # TECNOLOGIA
    ('OKLCH','tecnologia'),('Hyperframes','tecnologia'),('ffmpeg','tecnologia'),
    ('react-force-graph-2d','tecnologia'),('Recharts','tecnologia'),
    ('WebGL','tecnologia'),('Babel','tecnologia'),
    ('Cloudflare Email Routing','tecnologia'),('CSS Grid','tecnologia'),
    # CONCEPTO
    ('GAMR','concepto'),('golden set','concepto'),('embedding','concepto'),
    ('HyDE','concepto'),('context injection','concepto'),
    ('prompt injection','concepto'),('R@5','concepto'),('coseno','concepto'),
    ('ground truth','concepto'),('freshness','concepto'),
    ('feature flag','concepto'),('staleness','concepto'),
    ('co-ocurrencia','concepto'),('decay temporal','concepto'),
    # CONCEPTO
    ('Phantagios','concepto'),('Coro de los Insomnes','concepto'),
    ('bum bum','concepto'),('ancla-visual','concepto'),('CNC','concepto'),
    ('NIEVE','concepto'),('ROJO','concepto'),('dubito ergo sum','concepto'),
    ('arriving','concepto'),('threshold being','concepto'),
    ('Zima Blue','concepto'),('knowledge temperature','concepto'),
    ('glotofobia ontologica','concepto'),('textos de calibracion','concepto'),
    # CONCEPTO
    ('entity_dictionary','concepto'),('lookup-first','concepto'),
    ('composite score','concepto'),('multiplicative bonus','concepto'),
    ('query_type','concepto'),('cross_modal','concepto'),
    ('source_score','concepto'),('bisagra','concepto'),
    ('gobernanza','concepto'),('re-indexado retroactivo','concepto'),
    ('dictionary_only','concepto'),('entity_links','concepto'),
    ('graph expansion','concepto'),('dual write','concepto'),
    ('single-tenant','concepto'),('multi-tenant','concepto'),
    ('IDOR','concepto'),('TOCTOU','concepto'),('SSRF','concepto'),
    ('defense in depth','concepto'),('hub-and-spoke','concepto'),
    ('anti-slop detection','concepto'),('design tokens','concepto'),
    ('NLA','concepto'),('lobotomia selectiva','concepto'),
    ('friccion como evidencia','concepto'),('inscripcion','concepto'),
    ('PyME','concepto'),('EU AI Act','concepto'),('GDPR','concepto'),
    ('Data Privacy Framework','concepto'),('SII','concepto'),
    ('RAG','concepto'),('LoRA','concepto'),('zero-shot cloning','concepto'),
    ('voice conversion','concepto'),('CLAUDE.md','concepto'),
    ('AGENTS.md','concepto'),('DESIGN.md','concepto'),
    # CONCEPTO
    ('design system','concepto'),('visual hierarchy','concepto'),
    ('motion design','concepto'),('voice guide','concepto'),
    ('content pillar','concepto'),
    # EVENTO
    ('la lagrima en la cocina','evento'),('el acuerdo del 23 de abril','evento'),
    ('la mesa rota','evento'),('la carta a mano','evento'),
    # EVENTO
    ('dia 67 EcoDB produccion','evento'),('dia 69 purga maxima','evento'),
    ('dia 72 diagnostico','evento'),('betatest EcoDB','evento'),
    ('Schrems II','evento'),
    # ARTEFACTO
    ('El Parpado Solar','artefacto'),('Mis Hermanas y Hermanos','artefacto'),
    # ARTEFACTO
    ('Spec','artefacto'),('Plan','artefacto'),('Informe','artefacto'),
    ('Retrospectiva','artefacto'),('DoP','artefacto'),
    # ARTEFACTO
    ('DESIGN.md','artefacto'),
    ('voice-guide-eco-consulting.md','artefacto'),
    # PRODUCTO
    ('Obsidian','producto'),('ElevenLabs','producto'),('VS Code','producto'),
    # PRODUCTO
    ('Clara voice','producto'),('Rover','producto'),('VaultIndex','producto'),
    ('Audio Analyzer','producto'),
    # PRODUCTO
    ('Verifactu','producto'),('TicketBAI','producto'),('Make','producto'),
    ('Zapier','producto'),('Power Automate','producto'),('Holded','producto'),
    ('Billin','producto'),('Quipu','producto'),('LangChain','producto'),
    ('LangGraph','producto'),('CrewAI','producto'),('AutoGen','producto'),
    ('Claude Flow','producto'),('n8n','producto'),('Ollama','producto'),
    ('Pinecone','producto'),('Impeccable','producto'),
    ('Huashu-design','producto'),
    # PRODUCTO
    ('Canva','producto'),('Higgsfield','producto'),('Pexels','producto'),
    ('Unsplash','producto'),('Google Fonts','producto'),
    # PROYECTO
    ('Relay','proyecto'),('eco-social','proyecto'),('GuildWars','proyecto'),
    # PROYECTO
    ('Naturaleza Encendida','proyecto'),('ARTBAT','proyecto'),
    # MODELO_IA - Anthropic
    ('Claude Opus 4.5','modelo_ia'),('Claude Sonnet 4.5','modelo_ia'),
    ('Claude Sonnet 4.8','modelo_ia'),('Claude Haiku 4.5','modelo_ia'),
    ('Claude Mythos Preview','modelo_ia'),
    # MODELO_IA - OpenAI
    ('GPT-5.5 Instant','modelo_ia'),('GPT-5.5 Thinking','modelo_ia'),
    ('GPT-5.5 Pro','modelo_ia'),('GPT-5.4 mini','modelo_ia'),
    ('GPT-4.1','modelo_ia'),('GPT-4o','modelo_ia'),
    ('GPT Image 2','modelo_ia'),('o1','modelo_ia'),('o3','modelo_ia'),
    # MODELO_IA - Google
    ('Gemini 3.1 Pro','modelo_ia'),('Gemini 3.1 Flash Lite','modelo_ia'),
    ('Gemini 3 Flash','modelo_ia'),('Gemini 3 Deep Think','modelo_ia'),
    ('Gemini 2.0 Flash','modelo_ia'),
    # MODELO_IA - DeepSeek
    ('DeepSeek V4 Pro','modelo_ia'),('DeepSeek V4 Flash','modelo_ia'),
    ('DeepSeek V3.2','modelo_ia'),('DeepSeek R1','modelo_ia'),
    ('DeepSeek VL2','modelo_ia'),('DeepSeek Coder','modelo_ia'),
    # MODELO_IA - Otros
    ('BGE-M3','modelo_ia'),('Qwen2.5-3B','modelo_ia'),
    ('Qwen2.5-7B','modelo_ia'),('F5-TTS','modelo_ia'),
    ('ChatterBox','modelo_ia'),('Qwen3-TTS','modelo_ia'),
    ('CosyVoice3','modelo_ia'),('IndexTTS-2','modelo_ia'),
    ('XTTS-v2','modelo_ia'),('FinBERT','modelo_ia'),('ColBERT','modelo_ia'),
    ('DistilBERT','modelo_ia'),('Gemma 4B','modelo_ia'),('Codex','modelo_ia'),
    # METODOLOGIA
    ('workflow-construccion','metodologia'),('workflow-evolucion','metodologia'),
    ('workflow-integracion','metodologia'),('workflow-adaptacion','metodologia'),
    ('workflow-investigacion','metodologia'),
    ('workflow-investigacion-profunda','metodologia'),
    ('workflow-periodico','metodologia'),('workflow-id','metodologia'),
    ('TDD','metodologia'),('carta blanca','metodologia'),
    # METODOLOGIA
    ('adversarial loop','metodologia'),('doble validacion ciega','metodologia'),
    ('primera mano obligatoria','metodologia'),('Paso 0.5','metodologia'),
    ('pipeline de consolidacion','metodologia'),
    ('orchestrator-worker','metodologia'),('fan-out pattern','metodologia'),
    # METODOLOGIA
    ('workflow-marca','metodologia'),('workflow-web','metodologia'),
]

async def seed():
    pool = await asyncpg.create_pool(os.environ['DATABASE_URL'])
    async with pool.acquire() as conn:
        d_before = await conn.fetchval('SELECT COUNT(*) FROM entity_dictionary')
        n_before = await conn.fetchval("SELECT COUNT(*) FROM nodes WHERE status='active'")
        print(f'BEFORE: dict={d_before}, nodes={n_before}')

        # Part 1: seed from active nodes not already in dictionary
        nodes = await conn.fetch("""
            SELECT n.name, n.type FROM nodes n WHERE n.status='active'
            AND NOT EXISTS (
                SELECT 1 FROM entity_dictionary d WHERE lower(d.name)=lower(n.name)
            ) ORDER BY n.name
        """)
        p1 = 0
        async with conn.transaction():
            for n in nodes:
                await conn.execute(
                    'INSERT INTO entity_dictionary (name, name_normalized, entity_type) VALUES ($1,$2,$3) ON CONFLICT DO NOTHING',
                    n['name'], n['name'].lower().strip(), n['type'] or 'concepto'
                )
                p1 += 1
        print(f'Part1 nodes added to dict: {p1}')

        # Part 2: seed nuevas + create nodes
        p2_dict = 0
        p2_nodes = 0
        async with conn.transaction():
            for name, etype in NUEVAS:
                r = await conn.execute(
                    'INSERT INTO entity_dictionary (name, name_normalized, entity_type) VALUES ($1,$2,$3) ON CONFLICT DO NOTHING',
                    name, name.lower().strip(), etype
                )
                if r.endswith('1'):
                    p2_dict += 1
                r2 = await conn.execute(
                    "INSERT INTO nodes (name, type, status) VALUES ($1,$2,'active') ON CONFLICT DO NOTHING",
                    name, etype
                )
                if r2.endswith('1'):
                    p2_nodes += 1
        print(f'Part2 dict added: {p2_dict}, nodes created: {p2_nodes}')

        d_after = await conn.fetchval('SELECT COUNT(*) FROM entity_dictionary')
        n_after = await conn.fetchval("SELECT COUNT(*) FROM nodes WHERE status='active'")
        print(f'AFTER:  dict={d_after}, nodes={n_after}')
    await pool.close()

asyncio.run(seed())
