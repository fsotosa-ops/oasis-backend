-- ============================================================
-- Migration: CRM Profile Enrichment
-- Adds demographic fields to crm.contacts and configurable
-- field_options table for select fields.
-- ============================================================

-- 1. Add demographic + location columns to crm.contacts
ALTER TABLE crm.contacts
  ADD COLUMN IF NOT EXISTS birth_date DATE,
  ADD COLUMN IF NOT EXISTS gender TEXT,
  ADD COLUMN IF NOT EXISTS education_level TEXT,
  ADD COLUMN IF NOT EXISTS occupation TEXT,
  ADD COLUMN IF NOT EXISTS state TEXT; -- region / department / province

-- 2. Create crm.field_options — configurable options for select fields
CREATE TABLE IF NOT EXISTS crm.field_options (
  id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  field_name   TEXT        NOT NULL,
  value        TEXT        NOT NULL,
  label        TEXT        NOT NULL,
  sort_order   INT         NOT NULL DEFAULT 0,
  is_active    BOOLEAN     NOT NULL DEFAULT TRUE,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (field_name, value)
);

-- RLS
ALTER TABLE crm.field_options ENABLE ROW LEVEL SECURITY;

-- Everyone authenticated can read options
CREATE POLICY "field_options_read"
  ON crm.field_options FOR SELECT
  USING (auth.role() = 'authenticated');

-- Only platform admins can write
CREATE POLICY "field_options_admin_write"
  ON crm.field_options FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM profiles
      WHERE id = auth.uid() AND is_platform_admin = TRUE
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM profiles
      WHERE id = auth.uid() AND is_platform_admin = TRUE
    )
  );

-- Auto-update updated_at
CREATE TRIGGER update_crm_field_options_modtime
  BEFORE UPDATE ON crm.field_options
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 3. Seed default options
INSERT INTO crm.field_options (field_name, value, label, sort_order) VALUES
  -- Género
  ('gender', 'male',              'Masculino',              1),
  ('gender', 'female',            'Femenino',               2),
  ('gender', 'non_binary',        'No Binario',             3),
  ('gender', 'prefer_not_to_say', 'Prefiero No Responder',  4),

  -- Nivel Educativo
  ('education_level', 'primary',        'Educación Primaria',           1),
  ('education_level', 'secondary',      'Educación Secundaria',         2),
  ('education_level', 'technical',      'Educación Técnica / CFT',      3),
  ('education_level', 'bachelor',       'Licenciatura / Pregrado',      4),
  ('education_level', 'postgraduate',   'Posgrado / Especialización',   5),
  ('education_level', 'master',         'Maestría',                     6),
  ('education_level', 'doctorate',      'Doctorado',                    7),
  ('education_level', 'other',          'Otro',                         8),

  -- Ocupación
  ('occupation', 'student',       'Estudiante',                   1),
  ('occupation', 'employee',      'Empleado',                     2),
  ('occupation', 'self_employed', 'Independiente / Freelancer',   3),
  ('occupation', 'entrepreneur',  'Emprendedor',                  4),
  ('occupation', 'executive',     'Ejecutivo / Directivo',        5),
  ('occupation', 'public_sector', 'Sector Público',               6),
  ('occupation', 'academic',      'Académico / Investigador',     7),
  ('occupation', 'retired',       'Jubilado / Retirado',          8),
  ('occupation', 'unemployed',    'Desempleado',                  9),
  ('occupation', 'other',         'Otro',                        10)
ON CONFLICT (field_name, value) DO NOTHING;