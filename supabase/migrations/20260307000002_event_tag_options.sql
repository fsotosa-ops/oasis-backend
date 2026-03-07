-- Seed lookup options for event expected ages and roles
INSERT INTO crm.field_options (field_name, value, label, sort_order) VALUES
  -- Edades esperadas (Eventos)
  ('event_expected_ages', '0_5',    '0–5 años',   1),
  ('event_expected_ages', '6_11',   '6–11 años',  2),
  ('event_expected_ages', '12_17',  '12–17 años', 3),
  ('event_expected_ages', '18_25',  '18–25 años', 4),
  ('event_expected_ages', '26_35',  '26–35 años', 5),
  ('event_expected_ages', '36_50',  '36–50 años', 6),
  ('event_expected_ages', '50_plus','50+ años',   7),

  -- Roles esperados (Eventos)
  ('event_expected_roles', 'students',         'Estudiantes',             1),
  ('event_expected_roles', 'teachers',         'Docentes',                2),
  ('event_expected_roles', 'health_workers',   'Profesionales de Salud',  3),
  ('event_expected_roles', 'families',         'Familias',                4),
  ('event_expected_roles', 'community',        'Comunidad General',       5),
  ('event_expected_roles', 'public_officials', 'Funcionarios Públicos',   6),
  ('event_expected_roles', 'executives',       'Ejecutivos / Directivos', 7),
  ('event_expected_roles', 'other',            'Otro',                    8)
ON CONFLICT (field_name, value) DO NOTHING;
