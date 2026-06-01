# Graph Org Scoping — Design Decision

**Status**: Deferred (DD4 / VS1/VS2). Triggers when second org enters production.  
**Spec ref**: §Task 4 — graph isolation for multi-org

---

## 1. Decision: Shared graph with visibility layer

The graph (`ecodb_graph` in AGE) remains a single shared instance — no partition per org.

**Rationale**: AGE does not support multiple named graphs with cross-graph queries. Partitioning would require separate AGE graph instances, which breaks `path_between` (can't traverse org boundaries even when needed) and multiplies maintenance burden. A visibility layer is cheaper and composable.

**Tradeoff**: Super users can traverse the full graph. Org-scoped users see a filtered view. Graph queries become slightly more expensive (JOIN to visibility check).

---

## 2. Schema impact

Nodes have no `organization_id` column today. Org resolution requires traversal:

```
nodes ← entity_links ← memories → projects → workspaces → organizations
```

Or (for document-linked entities):
```
nodes ← document_entity_links ← documents → projects → workspaces → organizations
```

**Options**:

**A. Denormalized column** — add `organization_id INT REFERENCES organizations` to `nodes`.  
Populated by trigger on `entity_links` / `document_entity_links` INSERT. Fast at query time; requires trigger maintenance; node could belong to multiple orgs (shared entities like "Python").

**B. Runtime JOIN** — resolve org on every query via entity_links path.  
No schema change; slower; handles multi-org nodes naturally.

**Recommendation**: Option A with NULL meaning "shared/system node". Trigger sets org_id only when node is exclusive to one org. Nodes appearing in ≥2 orgs stay NULL and are visible to all authenticated users (global knowledge nodes are a feature, not a bug).

---

## 3. Cypher impact

All graph traversal endpoints need org visibility filtering. The filter cannot be injected into AGE Cypher directly (AGE has no access to PostgreSQL row-level security). Pattern: retrieve candidate node IDs via Cypher, then filter in SQL.

**Affected endpoints and strategy**:

| Endpoint | Strategy |
|---|---|
| `GET /graph/neighbors/{node}` | Post-filter: after AGE returns neighbors, `WHERE node_id IN (SELECT id FROM nodes WHERE org_id IS NULL OR org_id = $actor_org)` |
| `GET /graph/path` | Post-filter: path nodes filtered; if any hop is invisible, path is truncated or 404 |
| `GET /graph/search` | SQL-level: add `AND (organization_id IS NULL OR organization_id = $1)` to nodes query |
| `GET /graph/subgraph` | Post-filter: edges involving invisible nodes are dropped |
| `GET /graph/clusters` | Pre-filter: `JOIN nodes n ON n.id = gc.node_id WHERE n.org_id IS NULL OR n.org_id = $actor_org` |
| `expand_by_graph` (GAMR) | Post-filter on SQL side after AGE hop resolution |

The Cypher queries themselves do not change — filtering happens when matching AGE `sql_id` values back to SQL node IDs.

---

## 4. Permission matrix

| Role | Visible nodes |
|---|---|
| Super | All nodes (no filter) |
| CEO | All nodes in own org (`org_id = actor_org`) + NULL nodes (shared) + 1-hop connected nodes from own org regardless of their org_id (traversal discovery) |
| Workspace Lead | Same as CEO within own org |
| Worker | Nodes linked to memories/documents in own visible projects + NULL nodes |

**CEO 1-hop rule**: a CEO querying neighbors of an org node can discover adjacent shared nodes and nodes from other orgs that are directly connected. This is intentional — graph topology is a shared asset. The 1-hop discovery does not grant read access to the content of those nodes' linked memories (memories remain org-scoped separately).

---

## 5. Migration path

1. **Phase 0** (current): No org scoping. All authenticated users see all graph nodes. Acceptable for single-org deployment.

2. **Phase 1** — Add column + backfill (backwards-compatible):
   ```sql
   ALTER TABLE nodes ADD COLUMN organization_id INT REFERENCES organizations;
   -- Backfill via entity_links path
   UPDATE nodes n SET organization_id = (
       SELECT DISTINCT w.organization_id
       FROM entity_links el
       JOIN memories m ON m.id = el.memory_id
       JOIN workspaces w ON w.id = m.workspace_id
       WHERE el.entity = n.name AND w.organization_id IS NOT NULL
       LIMIT 1
   );
   ```
   Deploy with `ENABLE_GRAPH_ORG_SCOPING=false` (new feature flag). No behavioral change.

3. **Phase 2** — Enable flag per-endpoint:
   - Start with `/graph/search` (lowest risk, SQL-only)
   - Then `neighbors`, `subgraph`
   - Last: `expand_by_graph` in GAMR (highest impact, needs load testing)

4. **Phase 3** — Add trigger to maintain `nodes.organization_id` on entity_links INSERT/DELETE.

**Rollback**: Drop column + remove flag. Zero data loss.
