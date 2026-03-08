-- =============================================================================
-- CANONICAL: Audit Categories
-- =============================================================================
-- Single source of truth for all audit category definitions.
-- Referenced by factory_seed.sql via \ir (include relative).
--
-- To add a new category:
--   1. Add it here
--   2. Create a migration: INSERT INTO audit.categories ... ON CONFLICT DO NOTHING
--
-- All inserts are idempotent (ON CONFLICT DO NOTHING).
-- =============================================================================

INSERT INTO audit.categories (code, label, description) VALUES
    ('auth',          'Seguridad',      'Logins, registro, logout'),
    ('org',           'Organización',   'Cambios en empresa, miembros e invitaciones'),
    ('billing',       'Facturación',    'Pagos y suscripciones'),
    ('journey',       'Experiencia',    'Avance de usuarios en journeys'),
    ('system',        'Sistema',        'Errores y tareas automáticas'),
    ('crm',           'CRM',            'Cambios en contactos, notas y tareas del CRM'),
    ('event',         'Evento',         'Creación, modificación y eliminación de eventos'),
    ('resource',      'Recurso',        'Acceso y gestión de recursos educativos'),
    ('gamification',  'Gamificación',   'Recompensas, insignias y puntos de experiencia')
ON CONFLICT (code) DO NOTHING;
