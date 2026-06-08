DO $$
DECLARE
  _pw TEXT := coalesce(
    current_setting('ecodb.cell_password', true),
    'ecodb_cell_dev_only'
  );
BEGIN
  EXECUTE format('CREATE ROLE ecodb_cell LOGIN PASSWORD %L', _pw);
EXCEPTION WHEN duplicate_object THEN
  EXECUTE format('ALTER ROLE ecodb_cell PASSWORD %L', _pw);
END$$;
