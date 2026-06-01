BEGIN;
CREATE TABLE IF NOT EXISTS graph_clusters (
    node_id INT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    cluster_id INT NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (node_id)
);
CREATE INDEX IF NOT EXISTS idx_graph_clusters_cluster ON graph_clusters (cluster_id);
INSERT INTO schema_version (version, notes)
VALUES ('5.1.1', 'graph_clusters table for Louvain community detection')
ON CONFLICT (version) DO NOTHING;
COMMIT;
