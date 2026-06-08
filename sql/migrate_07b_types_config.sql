-- Config de peso y decay para los nuevos tipos
INSERT INTO memory_type_config (type, base_weight, decay_rate, decay_type) VALUES
  ('caso', 0.5, 0.10, 'fast'),
  ('skill', 0.8, 0.0, 'none')
ON CONFLICT (type) DO NOTHING;
